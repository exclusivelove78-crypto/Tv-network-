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
# DOWNLOAD SOURCE
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
# CHANNEL KEY
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
# PARSE CHANNELS
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
# REMOVE DUPLICATES FROM MAIN PLAYLIST
# ============================================================

def clean_existing_channels(channels):

    cleaned = []
    seen = set()

    removed = 0

    for channel in channels:

        key = channel["key"]

        # If channel has no ID/name, keep it
        # because we cannot safely identify duplicates.
        if not key:

            cleaned.append(channel)
            continue

        # Duplicate
        if key in seen:

            removed += 1
            continue

        seen.add(key)

        cleaned.append(channel)

    return cleaned, removed


# ============================================================
# NORMALIZE FOR CHANGE CHECK
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
    channels,
    new_source_groups,
    updated_time
):

    output = [
        "#EXTM3U",
        ""
    ]

    # ========================================================
    # MAIN PLAYLIST
    # ========================================================

    for channel in channels:

        output.append(
            channel["extinf"]
        )

        output.append(
            channel["url"]
        )

        output.append("")

    # ========================================================
    # NEW SOURCE CHANNELS
    # ALWAYS AT THE VERY BOTTOM
    # ========================================================

    for group in new_source_groups:

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

        old_channels_raw = parse_playlist(
            old_text
        )

        print(
            f"Channels read from file: "
            f"{len(old_channels_raw)}"
        )

    else:

        old_channels_raw = []

        print(
            "Set on tv.m3u not found."
        )

    # ========================================================
    # CLEAN DUPLICATES FROM EXISTING FILE
    # ========================================================

    old_channels, removed_duplicates = (
        clean_existing_channels(
            old_channels_raw
        )
    )

    if removed_duplicates:

        print(
            f"Duplicate channels removed: "
            f"{removed_duplicates}"
        )

    # ========================================================
    # WORKING COPY
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
    # ONLY NEW CHANNELS GO HERE
    # ========================================================

    new_source_groups = []

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
        # Parse source
        # ----------------------------------------------------

        source_channels = parse_playlist(
            source_text
        )

        print(
            f"Source channels: "
            f"{len(source_channels)}"
        )

        # Only NEW channels from this source
        new_channels_for_source = []

        # Prevent duplicate channels inside
        # the same source itself.
        source_seen = set()

        for new_channel in source_channels:

            key = new_channel["key"]

            # ------------------------------------------------
            # Cannot safely identify
            # ------------------------------------------------

            if not key:

                print(
                    "Skipped channel "
                    "(no tvg-id/tvg-name)."
                )

                continue

            # ------------------------------------------------
            # Duplicate inside same source
            # ------------------------------------------------

            if key in source_seen:

                print(
                    f"Duplicate in source: "
                    f"{key}"
                )

                continue

            source_seen.add(key)

            # =================================================
            # EXISTING MAIN PLAYLIST CHANNEL
            # =================================================

            if key in channel_map:

                index = channel_map[key]

                old_channel = channels[index]

                # Same URL
                if (
                    old_channel["url"]
                    == new_channel["url"]
                ):

                    print(
                        f"Same link: {key}"
                    )

                # New URL
                else:

                    # IMPORTANT:
                    # Keep old EXTINF metadata.
                    # Change ONLY the stream URL.
                    channels[index]["url"] = (
                        new_channel["url"]
                    )

                    updated += 1

                    print(
                        f"Updated link: {key}"
                    )

                # IMPORTANT:
                # Do NOT add this existing channel
                # to bottom source section.

                continue

            # =================================================
            # BRAND NEW CHANNEL
            # =================================================

            channel_map[key] = len(channels)

            channels.append(
                new_channel
            )

            new_channels_for_source.append(
                new_channel
            )

            added += 1

            print(
                f"New channel: {key}"
            )

        # ----------------------------------------------------
        # Add source section ONLY if it has
        # brand-new channels.
        # ----------------------------------------------------

        if new_channels_for_source:

            new_source_groups.append({
                "name": source_name,
                "channels": new_channels_for_source
            })

    # ========================================================
    # CHECK WHETHER ANY REAL CHANGE HAPPENED
    # ========================================================

    old_normalized = normalize_channels(
        old_channels
    )

    new_normalized = normalize_channels(
        channels
    )

    # No channel change and no duplicate cleanup
    if (
        old_normalized == new_normalized
        and removed_duplicates == 0
    ):

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
    # BUILD FINAL PLAYLIST
    # ========================================================

    new_playlist = build_playlist(
        channels=channels,
        new_source_groups=new_source_groups,
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
    print(f"Added:              {added}")
    print(f"Updated:            {updated}")
    print(f"Duplicates removed: {removed_duplicates}")
    print(f"Total:              {len(channels)}")
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
