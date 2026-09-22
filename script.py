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

    # Priority 1: tvg-id
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

    # Priority 2: tvg-name
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
# BUILD FINAL PLAYLIST
# ============================================================

def build_playlist(
    old_channels,
    source_groups,
    updated_time
):

    output = [
        "#EXTM3U",
        ""
    ]

    # ========================================================
    # OLD MAIN PLAYLIST
    # ========================================================

    for channel in old_channels:

        output.append(
            channel["extinf"]
        )

        output.append(
            channel["url"]
        )

        output.append("")

    # ========================================================
    # NEW SOURCE DATA
    # ALWAYS AT THE VERY BOTTOM
    # ========================================================

    for group in source_groups:

        output.append("#----")

        if group["name"]:

            output.append(
                f"# {group['name']}"
            )

        output.append(
            f"# Updated time: {updated_time}"
        )

        output.append("#----")
        output.append("")

        for channel in group["channels"]:

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

    # ========================================================
    # READ EXISTING MAIN PLAYLIST
    # ========================================================

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

    # ========================================================
    # COPY OLD PLAYLIST
    # ========================================================

    channels = old_channels.copy()

    channel_map = {}

    for index, channel in enumerate(channels):

        if channel["key"]:

            channel_map[
                channel["key"]
            ] = index

    # ========================================================
    # SOURCE GROUPS
    # ========================================================

    source_groups = []

    added = 0
    updated = 0

    # ========================================================
    # CHECK SOURCES
    # ========================================================

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
        # SOURCE NAME
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
        # SOURCE CHANNELS
        # ----------------------------------------------------

        source_channels = parse_playlist(
            source_text
        )

        print(
            f"Source channels: "
            f"{len(source_channels)}"
        )

        new_source_channels = []

        for new_channel in source_channels:

            key = new_channel["key"]

            # Cannot identify safely
            if not key:

                continue

            # =================================================
            # EXISTING CHANNEL
            # =================================================

            if key in channel_map:

                index = channel_map[key]

                old_channel = channels[index]

                # Same URL = nothing changes
                if old_channel["url"] == new_channel["url"]:

                    print(
                        f"Same link: {key}"
                    )

                # New URL = update only URL
                else:

                    channels[index]["url"] = (
                        new_channel["url"]
                    )

                    updated += 1

                    print(
                        f"Updated link: {key}"
                    )

            # =================================================
            # NEW CHANNEL
            # =================================================

            else:

                channel_map[key] = len(channels)

                channels.append(
                    new_channel
                )

                new_source_channels.append(
                    new_channel
                )

                added += 1

                print(
                    f"New channel: {key}"
                )

        # ----------------------------------------------------
        # Add only NEW channels to bottom section
        # ----------------------------------------------------

        if new_source_channels:

            source_groups.append({
                "name": source_name,
                "channels": new_source_channels
            })

    # ========================================================
    # CHECK ACTUAL CHANGES
    # ========================================================

    old_normalized = normalize_channels(
        old_channels
    )

    new_normalized = normalize_channels(
        channels
    )

    # Nothing changed
    if old_normalized == new_normalized:

        print("\n================================")
        print("No new or changed links found.")
        print("Set on tv.m3u remains unchanged.")
        print("================================")

        return

    # ========================================================
    # ACTION RUN TIME
    # ========================================================

    updated_time = datetime.now().strftime(
        "%I:%M:%S %p %d-%m-%Y"
    )

    # ========================================================
    # BUILD PLAYLIST
    # ========================================================

    new_playlist = build_playlist(
        old_channels=channels,
        source_groups=source_groups,
        updated_time=updated_time
    )

    # ========================================================
    # SAFE WRITE
    # ========================================================

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

    # ========================================================
    # RESULT
    # ========================================================

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
