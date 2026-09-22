import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

import requests


# ============================================================
# SETTINGS
# ============================================================

OUTPUT_FILE = Path("Set on tv.m3u")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
}

TIMEOUT = 60


# ============================================================
# DOWNLOAD SOURCE PLAYLIST
# ============================================================

def download_playlist(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        text = response.text.strip()

        if not text.startswith("#EXTM3U"):
            print("Invalid M3U source.")
            return None

        return text

    except requests.RequestException as e:
        print(f"Source download failed: {e}")
        return None


# ============================================================
# GET SOURCE NAME
# ============================================================

def get_source_name(text):
    """
    Try to read:

    # name: Live sports

    If not found, return empty string.
    """

    match = re.search(
        r"(?im)^\s*#\s*name\s*:\s*(.*?)\s*$",
        text
    )

    if match:
        name = match.group(1).strip()

        if name:
            return name

    return ""


# ============================================================
# GET CHANNEL KEY
# ============================================================

def get_channel_key(extinf):

    # First priority: tvg-id
    match = re.search(
        r'tvg-id="([^"]*)"',
        extinf,
        re.I
    )

    if match and match.group(1).strip():
        return (
            "id:"
            + match.group(1).strip().lower()
        )

    # Second priority: tvg-name
    match = re.search(
        r'tvg-name="([^"]*)"',
        extinf,
        re.I
    )

    if match and match.group(1).strip():
        return (
            "name:"
            + match.group(1).strip().lower()
        )

    return None


# ============================================================
# PARSE PLAYLIST
# ============================================================

def parse_playlist(text):

    lines = text.splitlines()

    channels = []

    i = 0

    while i < len(lines):

        line = lines[i].strip()

        if line.startswith("#EXTINF:"):

            extinf = line

            stream_url = None

            j = i + 1

            while j < len(lines):

                candidate = lines[j].strip()

                if (
                    candidate
                    and not candidate.startswith("#")
                ):
                    stream_url = candidate
                    break

                j += 1

            if stream_url:

                channels.append({
                    "key": get_channel_key(extinf),
                    "extinf": extinf,
                    "url": stream_url
                })

            i = j

        i += 1

    return channels


# ============================================================
# NORMALIZE CHANNELS
# ============================================================

def normalize_channels(channels):

    return [
        (
            channel["key"],
            channel["extinf"],
            channel["url"]
        )
        for channel in channels
    ]


# ============================================================
# BUILD PLAYLIST
# ============================================================

def build_playlist(source_groups):

    output = [
        "#EXTM3U",
        ""
    ]

    for group in source_groups:

        source_name = group["name"]
        updated_time = group["updated_time"]
        channels = group["channels"]

        # ----------------------------------------------------
        # Source section header
        # ----------------------------------------------------

        output.append("#----")

        if source_name:
            output.append(
                f"# {source_name}"
            )

        output.append(
            f"# Updated time: {updated_time}"
        )

        output.append("#----")
        output.append("")

        # ----------------------------------------------------
        # Channels
        # ----------------------------------------------------

        for channel in channels:

            output.append(
                channel["extinf"]
            )

            output.append(
                channel["url"]
            )

            output.append("")

    return "\n".join(output).rstrip() + "\n"


# ============================================================
# MAIN
# ============================================================

def main():

    print("================================")
    print("Starting playlist update")
    print("================================")

    # --------------------------------------------------------
    # Existing main playlist
    # --------------------------------------------------------

    if OUTPUT_FILE.exists():

        old_text = OUTPUT_FILE.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        old_channels = parse_playlist(
            old_text
        )

        print(
            f"Existing channels: "
            f"{len(old_channels)}"
        )

    else:

        old_channels = []

        print(
            "Set on tv.m3u not found."
        )

    # --------------------------------------------------------
    # Keep existing channels
    # --------------------------------------------------------

    channels = old_channels.copy()

    channel_map = {}

    for index, channel in enumerate(channels):

        if channel["key"]:

            channel_map[
                channel["key"]
            ] = index

    added = 0
    updated = 0

    # --------------------------------------------------------
    # Source groups
    # --------------------------------------------------------

    source_groups = []

    # Action run time
    current_time = datetime.now().strftime(
        "%I:%M:%S %p %d-%m-%Y"
    )

    # --------------------------------------------------------
    # Check all source playlists
    # --------------------------------------------------------

    for number, source_url in enumerate(
        SOURCE_LINKS,
        1
    ):

        if not source_url:
            continue

        print(
            f"\nChecking source #{number}"
        )

        source_text = download_playlist(
            source_url
        )

        if not source_text:

            print(
                "Source skipped."
            )

            continue

        # ----------------------------------------------------
        # Source name
        # ----------------------------------------------------

        source_name = get_source_name(
            source_text
        )

        if source_name:

            print(
                f"Source name: "
                f"{source_name}"
            )

        else:

            print(
                "Source name: Not found"
            )

        # ----------------------------------------------------
        # Parse source channels
        # ----------------------------------------------------

        source_channels = parse_playlist(
            source_text
        )

        print(
            f"Source channels: "
            f"{len(source_channels)}"
        )

        # Keep channels belonging to this source
        source_group_channels = []

        for new_channel in source_channels:

            key = new_channel["key"]

            # Cannot safely identify channel
            if not key:

                print(
                    "Skipped channel "
                    "(no tvg-id/tvg-name)."
                )

                continue

            # ------------------------------------------------
            # Existing channel
            # ------------------------------------------------

            if key in channel_map:

                index = channel_map[key]

                old_channel = channels[index]

                # IMPORTANT:
                # Keep existing EXTINF metadata.
                # Only update stream URL.
                if old_channel["url"] != new_channel["url"]:

                    channels[index]["url"] = (
                        new_channel["url"]
                    )

                    updated += 1

                    print(
                        f"Updated URL: "
                        f"{key}"
                    )

                # Use the current main playlist channel
                source_group_channels.append(
                    channels[index]
                )

            # ------------------------------------------------
            # New channel
            # ------------------------------------------------

            else:

                channel_map[key] = len(channels)

                channels.append(
                    new_channel
                )

                source_group_channels.append(
                    new_channel
                )

                added += 1

                print(
                    f"Added: {key}"
                )

        # ----------------------------------------------------
        # Add source section
        # ----------------------------------------------------

        if source_group_channels:

            source_groups.append({
                "name": source_name,
                "updated_time": current_time,
                "channels": source_group_channels
            })

    # --------------------------------------------------------
    # Check actual channel changes
    # --------------------------------------------------------

    old_normalized = normalize_channels(
        old_channels
    )

    new_normalized = normalize_channels(
        channels
    )

    # --------------------------------------------------------
    # Nothing changed
    # --------------------------------------------------------

    if old_normalized == new_normalized:

        print("\n================================")
        print("No new or changed links found.")
        print("Set on tv.m3u remains unchanged.")
        print("================================")

        return

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # If changes happened, rebuild playlist.
    #
    # Existing channels that were not found in the current
    # sources are also preserved at the end.
    # --------------------------------------------------------

    source_group_keys = set()

    for group in source_groups:

        for channel in group["channels"]:

            if channel["key"]:
                source_group_keys.add(
                    channel["key"]
                )

    # --------------------------------------------------------
    # Preserve old channels that were not in sources
    # --------------------------------------------------------

    remaining_channels = []

    for channel in channels:

        if channel["key"] not in source_group_keys:

            remaining_channels.append(
                channel
            )

    # --------------------------------------------------------
    # Add remaining old channels as one section
    # --------------------------------------------------------

    if remaining_channels:

        source_groups.append({
            "name": "",
            "updated_time": current_time,
            "channels": remaining_channels
        })

    # --------------------------------------------------------
    # Build final playlist
    # --------------------------------------------------------

    new_playlist = build_playlist(
        source_groups
    )

    # --------------------------------------------------------
    # Safe temporary write
    # --------------------------------------------------------

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=".",
        suffix=".tmp"
    ) as temp:

        temp.write(
            new_playlist
        )

        temp_path = Path(
            temp.name
        )

    temp_path.replace(
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # Done
    # --------------------------------------------------------

    print("\n================================")
    print("PLAYLIST UPDATED")
    print(f"Added:   {added}")
    print(f"Updated: {updated}")
    print(f"Total:   {len(channels)}")
    print("================================")


# ============================================================
# SOURCE PLAYLIST LINKS
# ============================================================

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


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
