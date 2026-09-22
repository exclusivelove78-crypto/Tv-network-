import os
import re
import sys
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


def get_channel_key(extinf):
    match = re.search(r'tvg-id="([^"]*)"', extinf, re.I)

    if match and match.group(1).strip():
        return "id:" + match.group(1).strip().lower()

    match = re.search(r'tvg-name="([^"]*)"', extinf, re.I)

    if match and match.group(1).strip():
        return "name:" + match.group(1).strip().lower()

    return None


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

                if candidate and not candidate.startswith("#"):
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


def normalize_channels(channels):
    return [
        (
            channel["key"],
            channel["extinf"],
            channel["url"]
        )
        for channel in channels
    ]


def build_playlist(channels):
    output = [
        "#EXTM3U",
        f"# last_update: {datetime.now().strftime('%I:%M:%S %p %d-%m-%Y')}",
        ""
    ]

    for channel in channels:
        output.append(channel["extinf"])
        output.append(channel["url"])
        output.append("")

    return "\n".join(output).rstrip() + "\n"


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

        old_channels = parse_playlist(old_text)

        print(
            f"Existing channels: {len(old_channels)}"
        )

    else:

        old_channels = []

        print(
            "Set on tv.m3u not found."
        )

    channels = old_channels.copy()

    channel_map = {}

    for index, channel in enumerate(channels):

        if channel["key"]:
            channel_map[channel["key"]] = index

    added = 0
    updated = 0

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
            print("Source skipped.")
            continue

        source_channels = parse_playlist(
            source_text
        )

        print(
            f"Source channels: "
            f"{len(source_channels)}"
        )

        for new_channel in source_channels:

            key = new_channel["key"]

            # Cannot safely identify channel
            if not key:
                continue

            # Existing channel
            if key in channel_map:

                index = channel_map[key]

                old_channel = channels[index]

                if (
                    old_channel["extinf"]
                    != new_channel["extinf"]
                    or
                    old_channel["url"]
                    != new_channel["url"]
                ):

                    channels[index] = new_channel
                    updated += 1

            # New channel
            else:

                channel_map[key] = len(channels)

                channels.append(new_channel)

                added += 1

    # --------------------------------------------------------
    # Check for actual changes
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Create updated playlist
    # --------------------------------------------------------

    new_playlist = build_playlist(
        channels
    )

    # Safe temporary write
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=".",
        suffix=".tmp"
    ) as temp:

        temp.write(new_playlist)

        temp_path = Path(
            temp.name
        )

    temp_path.replace(
        OUTPUT_FILE
    )

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


if __name__ == "__main__":
    main()
