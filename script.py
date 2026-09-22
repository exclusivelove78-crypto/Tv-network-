import os
import re
from datetime import datetime

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

LIVE_SPORTS_SEPARATOR = "--------------Live Sports----------"


# =========================================================
# TIME
# =========================================================

def current_time():
    return datetime.now().strftime("%I:%M:%S %p %d-%m-%Y")


# =========================================================
# EXTINF ATTRIBUTES
# =========================================================

def get_attr(extinf, attr):
    match = re.search(
        rf'{re.escape(attr)}="([^"]*)"',
        extinf,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    return ""


def get_channel_key(extinf):
    """
    Channel identity:
    1. tvg-id
    2. tvg-name
    3. display name
    """

    tvg_id = get_attr(extinf, "tvg-id").strip()

    if tvg_id:
        return ("id", tvg_id.lower())

    tvg_name = get_attr(extinf, "tvg-name").strip()

    if tvg_name:
        return ("name", tvg_name.lower())

    if "," in extinf:
        display_name = extinf.split(",", 1)[1].strip()

        if display_name:
            return ("display", display_name.lower())

    return None


# =========================================================
# FIND SOURCE NAME
# =========================================================

def get_source_name(text):
    """
    Source playlist থেকে শুধু # name: নেওয়া হবে।
    """

    for line in text.splitlines():

        stripped = line.strip()

        if stripped.lower().startswith("# name:"):
            return stripped.split(":", 1)[1].strip()

    return ""


# =========================================================
# PARSE SOURCE CHANNELS
# =========================================================

def parse_source(text):
    lines = text.splitlines()

    channels = []

    i = 0

    while i < len(lines):

        line = lines[i]

        if line.startswith("#EXTINF:"):

            extinf = line

            url_index = None

            j = i + 1

            while j < len(lines):

                candidate = lines[j].strip()

                if candidate and not candidate.startswith("#"):
                    url_index = j
                    break

                if candidate.startswith("#EXTINF:"):
                    break

                j += 1

            if url_index is not None:

                channels.append({
                    "extinf": extinf,
                    "url": lines[url_index],
                    "key": get_channel_key(extinf),
                })

                i = url_index

        i += 1

    return {
        "name": get_source_name(text),
        "channels": channels,
    }


# =========================================================
# DOWNLOAD SOURCE
# =========================================================

def download_source(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        if not response.text.strip():
            return None

        return response.text

    except Exception as e:

        print(f"[WARNING] Source failed")
        print(e)

        return None


# =========================================================
# FIND ALL EXISTING CHANNELS
# =========================================================

def find_existing_channels(lines):
    """
    Existing file-এর কোনো formatting পরিবর্তন না করে
    শুধু channel position এবং URL বের করে।
    """

    channels = []

    i = 0

    while i < len(lines):

        if lines[i].startswith("#EXTINF:"):

            extinf_index = i
            url_index = None

            j = i + 1

            while j < len(lines):

                candidate = lines[j].strip()

                if candidate and not candidate.startswith("#"):
                    url_index = j
                    break

                if candidate.startswith("#EXTINF:"):
                    break

                j += 1

            if url_index is not None:

                channels.append({
                    "extinf_index": extinf_index,
                    "url_index": url_index,
                    "key": get_channel_key(lines[extinf_index]),
                    "extinf": lines[extinf_index],
                    "url": lines[url_index],
                })

                i = url_index

        i += 1

    return channels


# =========================================================
# CHECK WHETHER POSITION IS INSIDE SOURCE SECTION
# =========================================================

def find_source_section_ranges(lines):
    """
    Existing source sections detect করে।

    Format:

    #----
    # Source Name
    # Updated time: ...
    #----

    channels...
    """

    ranges = []

    i = 0

    while i < len(lines):

        if lines[i].strip() == "#----":

            start = i

            second_marker = None

            j = i + 1

            while j < len(lines):

                if lines[j].strip() == "#----":
                    second_marker = j
                    break

                j += 1

            if second_marker is not None:

                ranges.append({
                    "start": start,
                    "header_end": second_marker,
                    "end": len(lines) - 1,
                })

                i = second_marker

        i += 1

    # Determine each section end
    for index in range(len(ranges) - 1):

        ranges[index]["end"] = (
            ranges[index + 1]["start"] - 1
        )

    return ranges


def is_inside_source_section(index, ranges):

    for r in ranges:

        if r["start"] <= index <= r["end"]:
            return True

    return False


# =========================================================
# FIND SOURCE GROUP
# =========================================================

def find_matching_source_section(lines, source_name):

    if not source_name:
        return None

    ranges = find_source_section_ranges(lines)

    source_name_lower = source_name.lower()

    for r in ranges:

        for i in range(
            r["start"] + 1,
            r["header_end"]
        ):

            line = lines[i].strip()

            if line.startswith("#"):

                value = line[1:].strip()

                if (
                    value
                    and not value.startswith("-")
                    and not value.lower().startswith("updated time:")
                ):

                    if value.lower() == source_name_lower:
                        return r

    return None


# =========================================================
# APPEND NEW SOURCE SECTION
# =========================================================

def append_new_source_section(
    lines,
    source_name,
    channels
):

    if not channels:
        return lines

    # Ensure final channel has normal separation
    if lines and lines[-1].strip():

        lines.append("")

    # If separator isn't already the final Live Sports area,
    # add it.
    separator_exists = False

    for line in lines:

        if line.strip() == LIVE_SPORTS_SEPARATOR:
            separator_exists = True
            break

    if not separator_exists:

        lines.append(LIVE_SPORTS_SEPARATOR)
        lines.append("")

    else:

        # Existing separator exists but this source section
        # doesn't. Add another source section below it.
        if lines and lines[-1].strip():
            lines.append("")

    lines.append("#----")

    if source_name:
        lines.append(f"# {source_name}")

    lines.append(
        f"# Updated time: {current_time()}"
    )

    lines.append("#----")
    lines.append("")

    for channel in channels:

        lines.append(channel["extinf"])
        lines.append(channel["url"])

    return lines


# =========================================================
# APPEND TO EXISTING SOURCE SECTION
# =========================================================

def append_to_existing_source(
    lines,
    section,
    source_name,
    channels
):

    if not channels:
        return lines

    # Recalculate section because lines may change
    ranges = find_source_section_ranges(lines)

    # Find the same section again
    target = None

    source_name_lower = source_name.lower()

    for r in ranges:

        header_name = ""

        for i in range(
            r["start"] + 1,
            r["header_end"]
        ):

            value = lines[i].strip()

            if (
                value.startswith("#")
                and not value.startswith("#EXT")
                and not value.startswith("# Updated time:")
            ):

                candidate = value[1:].strip()

                if candidate and not candidate.startswith("-"):
                    header_name = candidate
                    break

        if header_name.lower() == source_name_lower:
            target = r
            break

    if target is None:
        return lines

    # Insert before trailing blank lines of this section.
    insert_at = target["end"] + 1

    while (
        insert_at > target["header_end"]
        and lines[insert_at - 1].strip() == ""
    ):
        insert_at -= 1

    new_lines = []

    for channel in channels:

        new_lines.append(channel["extinf"])
        new_lines.append(channel["url"])

    lines[insert_at:insert_at] = new_lines

    # Update ONLY the existing source timestamp.
    # No other spacing is touched.
    new_ranges = find_source_section_ranges(lines)

    for r in new_ranges:

        if r["start"] == target["start"]:

            for i in range(
                r["start"] + 1,
                r["header_end"]
            ):

                if lines[i].strip().startswith(
                    "# Updated time:"
                ):

                    # Preserve indentation/format before '#'
                    prefix = lines[i][:len(lines[i]) - len(lines[i].lstrip())]

                    lines[i] = (
                        prefix
                        + "# Updated time: "
                        + current_time()
                    )

                    break

            break

    return lines


# =========================================================
# MAIN
# =========================================================

def main():

    if os.path.exists(MAIN_FILE):

        with open(
            MAIN_FILE,
            "r",
            encoding="utf-8",
            newline=""
        ) as f:

            original_text = f.read()

    else:

        original_text = "#EXTM3U\n"

    # IMPORTANT:
    # splitlines() preserves the actual text of every line.
    # We do NOT strip/reformat existing lines.
    lines = original_text.splitlines()

    # Existing channels
    existing_channels = find_existing_channels(lines)

    # First occurrence wins
    channel_map = {}

    for channel in existing_channels:

        key = channel["key"]

        if key is None:
            continue

        if key not in channel_map:

            channel_map[key] = channel

    # Existing source sections
    source_ranges = find_source_section_ranges(lines)

    # Lines that need to be removed because they are duplicate
    # copies inside source sections.
    duplicate_ranges = []

    # ---------------------------------------------------------
    # Download and process every source
    # ---------------------------------------------------------

    new_channels_by_source = []

    playlist_changed = False

    for source_number, source_url in enumerate(
        SOURCE_LINKS,
        start=1
    ):

        if not source_url:
            continue

        print(
            f"[INFO] Checking SOURCE_M3U_{source_number}"
        )

        source_text = download_source(source_url)

        if source_text is None:
            print("[INFO] Source skipped.")
            continue

        source = parse_source(source_text)

        source_name = source["name"]
        source_channels = source["channels"]

        if not source_channels:
            print("[INFO] No channels found.")
            continue

        new_channels = []

        for source_channel in source_channels:

            key = source_channel["key"]

            # -------------------------------------------------
            # Identifiable channel
            # -------------------------------------------------

            if key is not None and key in channel_map:

                existing = channel_map[key]

                # Only URL changes.
                # EXTINF formatting stays EXACTLY as existing.
                if existing["url"] != source_channel["url"]:

                    print(
                        f"[UPDATE] URL changed: {key}"
                    )

                    lines[existing["url_index"]] = (
                        source_channel["url"]
                    )

                    existing["url"] = (
                        source_channel["url"]
                    )

                    playlist_changed = True

                continue

            # -------------------------------------------------
            # Truly new channel
            # -------------------------------------------------

            new_channels.append(source_channel)

            if key is not None:
                channel_map[key] = source_channel

            playlist_changed = True

        if new_channels:

            new_channels_by_source.append({
                "name": source_name,
                "channels": new_channels,
            })

    # ---------------------------------------------------------
    # CLEAN OLD DUPLICATE SOURCE CHANNELS
    # ---------------------------------------------------------
    #
    # If an old malformed file has:
    #
    # Main channel
    #
    # #----
    # # SonyLiv
    # #----
    #
    # Same channel again
    #
    # then only the later duplicate channel block is removed.
    #
    # All other spaces/comments/lines remain untouched.
    # ---------------------------------------------------------

    if existing_channels:

        seen = set()

        remove_indexes = set()

        source_ranges = find_source_section_ranges(lines)

        for channel in existing_channels:

            key = channel["key"]

            if key is None:
                continue

            if key in seen:

                if is_inside_source_section(
                    channel["extinf_index"],
                    source_ranges
                ):

                    # Remove EXTINF + URL only
                    remove_indexes.add(
                        channel["extinf_index"]
                    )

                    remove_indexes.add(
                        channel["url_index"]
                    )

                    playlist_changed = True

            else:

                seen.add(key)

    # Remove duplicate lines from bottom to top.
    if remove_indexes:

        for index in sorted(
            remove_indexes,
            reverse=True
        ):

            del lines[index]

    # ---------------------------------------------------------
    # Add NEW source channels at the VERY BOTTOM
    # ---------------------------------------------------------

    for source in new_channels_by_source:

        source_name = source["name"]
        new_channels = source["channels"]

        # Try existing source section
        if source_name:

            section = find_matching_source_section(
                lines,
                source_name
            )

        else:

            section = None

        if section is not None:

            lines = append_to_existing_source(
                lines,
                section,
                source_name,
                new_channels
            )

        else:

            lines = append_new_source_section(
                lines,
                source_name,
                new_channels
            )

    # ---------------------------------------------------------
    # Write ONLY when something changed
    # ---------------------------------------------------------

    # Preserve final newline state as much as possible.
    new_text = "\n".join(lines)

    if original_text.endswith("\n"):
        new_text += "\n"

    if new_text != original_text:

        with open(
            MAIN_FILE,
            "w",
            encoding="utf-8",
            newline=""
        ) as f:

            f.write(new_text)

        print("[SUCCESS] Playlist updated.")

    else:

        print(
            "[INFO] No changes. "
            "File was not rewritten."
        )


if __name__ == "__main__":
    main()
