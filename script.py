import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests


MAIN_FILE = "Set on tv.m3u"

#--
# Live sports data
#----

SOURCE_LINKS = [
    os.environ.get("SOURCE_M3U_1"),
    os.environ.get("SOURCE_M3U_2"),
    os.environ.get("SOURCE_M3U_3"),
    os.environ.get("SOURCE_M3U_4"),
    os.environ.get("SOURCE_M3U_5"),
]


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
}

SEPARATOR = "--------------Live Sports----------"


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def now_text():
    return datetime.now().strftime("%I:%M:%S %p %d-%m-%Y")


def clean(value):
    if value is None:
        return ""
    return value.strip()


def get_attr(extinf, attr):
    match = re.search(
        rf'{re.escape(attr)}="([^"]*)"',
        extinf,
        flags=re.IGNORECASE
    )
    return match.group(1).strip() if match else ""


def channel_key(extinf):
    """
    Channel identity:
    1. tvg-id
    2. tvg-name
    3. None = cannot safely identify
    """
    tvg_id = get_attr(extinf, "tvg-id")
    if tvg_id:
        return ("id", tvg_id.lower())

    tvg_name = get_attr(extinf, "tvg-name")
    if tvg_name:
        return ("name", tvg_name.lower())

    # Also support EXTINF display name when tvg-name is absent
    if "," in extinf:
        display_name = extinf.split(",", 1)[1].strip()
        if display_name:
            return ("display", display_name.lower())

    return None


def parse_channel_lines(lines):
    """
    Parse #EXTINF + next URL.
    Other comments are ignored.
    """
    channels = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("#EXTINF:"):
            extinf = lines[i].rstrip()

            url = ""
            j = i + 1

            while j < len(lines):
                candidate = lines[j].strip()

                if candidate and not candidate.startswith("#"):
                    url = lines[j].rstrip()
                    break

                # Another EXTINF means previous channel has no URL
                if candidate.startswith("#EXTINF:"):
                    break

                j += 1

            if url:
                channels.append({
                    "extinf": extinf,
                    "url": url,
                    "key": channel_key(extinf),
                })

            i = j + 1
        else:
            i += 1

    return channels


def parse_source_name(lines):
    """
    Find:
    #----
    # Source Name
    # Updated time: ...
    #----
    """
    name = ""

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith("# Updated time:"):
            continue

        if line.startswith("#") and not line.startswith("#EXT"):
            value = line[1:].strip()

            if value and not value.startswith("-"):
                return value

    return name


# ---------------------------------------------------------
# Parse existing Set on tv.m3u
# ---------------------------------------------------------

def parse_existing_playlist(text):
    """
    Separates:

    Main channels
    +
    old source sections

    This is important because old source sections may already
    contain duplicate channels.
    """

    lines = text.splitlines()

    main_channels = []
    source_groups = []

    current_section = None
    header_buffer = []
    header_open = False
    channel_buffer = []

    def flush_channels():
        nonlocal channel_buffer

        if not channel_buffer:
            return

        parsed = parse_channel_lines(channel_buffer)

        if current_section is None:
            main_channels.extend(parsed)
        else:
            current_section["channels"].extend(parsed)

        channel_buffer = []

    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Source section starts
        if stripped == "#----" and not header_open:
            flush_channels()

            header_open = True
            header_buffer = []

            i += 1
            continue

        # Source header ends
        if stripped == "#----" and header_open:
            header_open = False

            name = parse_source_name(header_buffer)

            current_section = {
                "name": name,
                "updated_time": "",
                "channels": [],
            }

            for h in header_buffer:
                h = h.strip()

                if h.startswith("# Updated time:"):
                    current_section["updated_time"] = (
                        h.replace("# Updated time:", "", 1).strip()
                    )

            source_groups.append(current_section)

            i += 1
            continue

        if header_open:
            header_buffer.append(line)
        else:
            channel_buffer.append(line)

        i += 1

    if header_open:
        # Broken/incomplete header: treat safely as comments
        channel_buffer.extend(header_buffer)

    flush_channels()

    return main_channels, source_groups


# ---------------------------------------------------------
# Download source playlist
# ---------------------------------------------------------

def download_source(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        text = response.text

        if not text.strip():
            return None

        return text

    except Exception as e:
        print(f"[WARNING] Source failed: {url}")
        print(f"[WARNING] {e}")
        return None


# ---------------------------------------------------------
# Source playlist parser
# ---------------------------------------------------------

def parse_source_playlist(text):
    lines = text.splitlines()

    channels = parse_channel_lines(lines)
    name = parse_source_name(lines)

    return {
        "name": name,
        "channels": channels,
    }


# ---------------------------------------------------------
# Remove duplicate existing channels
# ---------------------------------------------------------

def clean_existing_channels(main_channels, source_groups):
    """
    Global duplicate removal.

    Main playlist wins over source section.

    If same channel exists:
        first occurrence is kept
        later duplicate is removed
    """

    seen = set()

    cleaned_main = []

    for ch in main_channels:
        key = ch["key"]

        if key is None:
            cleaned_main.append(ch)
            continue

        if key in seen:
            continue

        seen.add(key)
        cleaned_main.append(ch)

    cleaned_groups = []

    for group in source_groups:
        cleaned_channels = []

        for ch in group["channels"]:
            key = ch["key"]

            if key is None:
                cleaned_channels.append(ch)
                continue

            if key in seen:
                continue

            seen.add(key)
            cleaned_channels.append(ch)

        group["channels"] = cleaned_channels

        # Empty source sections are removed
        if cleaned_channels:
            cleaned_groups.append(group)

    return cleaned_main, cleaned_groups


# ---------------------------------------------------------
# Find existing source group
# ---------------------------------------------------------

def find_source_group(source_name, source_groups, used_groups):
    """
    Match source section by source name.

    If source has no name, an unused unnamed section is used.
    """

    source_name = clean(source_name).lower()

    # First try exact source name
    if source_name:
        for index, group in enumerate(source_groups):
            if index in used_groups:
                continue

            if clean(group["name"]).lower() == source_name:
                return index

    # Then unnamed section
    if not source_name:
        for index, group in enumerate(source_groups):
            if index in used_groups:
                continue

            if not clean(group["name"]):
                return index

    return None


# ---------------------------------------------------------
# Build final playlist
# ---------------------------------------------------------

def build_playlist(
    main_channels,
    source_groups,
    new_groups,
    last_update
):
    output = []

    output.append("#EXTM3U")

    if last_update:
        output.append(f"# last_update: {last_update}")

    output.append("")

    # -----------------------------------------------------
    # MAIN PLAYLIST
    # -----------------------------------------------------

    for ch in main_channels:
        output.append(ch["extinf"])
        output.append(ch["url"])

    # -----------------------------------------------------
    # LIVE SPORTS AREA
    # -----------------------------------------------------

    all_groups = source_groups + new_groups

    if all_groups:
        output.append("")
        output.append(SEPARATOR)
        output.append("")

    for group in all_groups:

        if not group["channels"]:
            continue

        output.append("#----")

        if group["name"]:
            output.append(f"# {group['name']}")

        if group["updated_time"]:
            output.append(
                f"# Updated time: {group['updated_time']}"
            )

        output.append("#----")
        output.append("")

        for ch in group["channels"]:
            output.append(ch["extinf"])
            output.append(ch["url"])

        output.append("")

    # Remove excessive blank lines at end
    while output and not output[-1].strip():
        output.pop()

    return "\n".join(output) + "\n"


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    if os.path.exists(MAIN_FILE):
        with open(
            MAIN_FILE,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as f:
            old_text = f.read()
    else:
        old_text = "#EXTM3U\n"

    # -----------------------------------------------------
    # Parse existing file
    # -----------------------------------------------------

    main_channels, source_groups = parse_existing_playlist(
        old_text
    )

    # Clean duplicate channels from old malformed source sections
    main_channels, source_groups = clean_existing_channels(
        main_channels,
        source_groups
    )

    # Global channel map
    channel_map = {}

    for ch in main_channels:
        if ch["key"] is not None:
            channel_map[ch["key"]] = ch

    for group in source_groups:
        for ch in group["channels"]:
            if ch["key"] is not None:
                channel_map[ch["key"]] = ch

    # -----------------------------------------------------
    # Process sources
    # -----------------------------------------------------

    used_groups = set()
    new_groups = []

    playlist_changed = False

    for source_index, source_url in enumerate(SOURCE_LINKS, start=1):

        if not source_url:
            continue

        print(f"\n[INFO] Checking SOURCE_M3U_{source_index}")

        source_text = download_source(source_url)

        if source_text is None:
            print("[INFO] Source skipped.")
            continue

        source = parse_source_playlist(source_text)

        source_name = source["name"]
        source_channels = source["channels"]

        print(
            f"[INFO] Source name: "
            f"{source_name or '(no name)'}"
        )

        if not source_channels:
            print("[INFO] No channels found.")
            continue

        # Find existing source section
        group_index = find_source_group(
            source_name,
            source_groups,
            used_groups
        )

        if group_index is not None:
            group = source_groups[group_index]
            used_groups.add(group_index)
        else:
            group = {
                "name": source_name,
                "updated_time": "",
                "channels": [],
            }

            new_groups.append(group)

        source_group_changed = False

        # -------------------------------------------------
        # Process every source channel
        # -------------------------------------------------

        for source_channel in source_channels:

            key = source_channel["key"]

            # Cannot safely identify a channel
            if key is None:
                # Treat as a new channel
                group["channels"].append(source_channel)
                source_group_changed = True
                playlist_changed = True
                continue

            # -------------------------------------------------
            # Existing channel
            # -------------------------------------------------

            if key in channel_map:

                existing = channel_map[key]

                # Same EXTINF metadata stays unchanged.
                # ONLY stream URL is updated.
                if existing["url"] != source_channel["url"]:

                    print(
                        "[UPDATE] URL changed: "
                        f"{key}"
                    )

                    existing["url"] = source_channel["url"]

                    playlist_changed = True

                    # If channel belongs to this source group,
                    # its source timestamp should update.
                    for g in source_groups:
                        if existing in g["channels"]:
                            if g is group:
                                source_group_changed = True
                            break

                    for g in new_groups:
                        if existing in g["channels"]:
                            if g is group:
                                source_group_changed = True
                            break

                continue

            # -------------------------------------------------
            # Truly NEW channel
            # -------------------------------------------------

            print(
                "[NEW] Adding channel: "
                f"{key}"
            )

            group["channels"].append(source_channel)

            channel_map[key] = source_channel

            source_group_changed = True
            playlist_changed = True

        # Update source timestamp ONLY when that source
        # actually added/changed channel data.
        if source_group_changed:

            group["updated_time"] = now_text()

            if not group["name"] and source_name:
                group["name"] = source_name

    # ---------------------------------------------------------
    # If nothing changed, do NOT rewrite the file.
    # ---------------------------------------------------------

    if not playlist_changed:

        print("\n[INFO] No channel changes.")
        print("[INFO] Set on tv.m3u was NOT rewritten.")

        return

    # ---------------------------------------------------------
    # Main last_update
    # ---------------------------------------------------------

    new_last_update = now_text()

    # ---------------------------------------------------------
    # Build final file
    # ---------------------------------------------------------

    final_text = build_playlist(
        main_channels=main_channels,
        source_groups=source_groups,
        new_groups=new_groups,
        last_update=new_last_update
    )

    # ---------------------------------------------------------
    # Write only if content really changed
    # ---------------------------------------------------------

    if final_text != old_text:

        with open(
            MAIN_FILE,
            "w",
            encoding="utf-8",
            newline="\n"
        ) as f:
            f.write(final_text)

        print("\n[SUCCESS] Playlist updated.")

    else:
        print("\n[INFO] Final content unchanged.")


if __name__ == "__main__":
    main()
