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
# SOURCE HEADER
# =========================================================

def get_source_header(text):
    """
    Source থেকে শুধু এই 2টি line নেওয়া হবে:

    #name: ...
    #last update time: ...

    এগুলো নেওয়া হবে না:
    #telegram:
    #owner:
    #special thanks to:
    """

    name_line = ""
    last_update_line = ""

    for line in text.splitlines():

        stripped = line.strip()

        lower = stripped.lower()

        if lower.startswith("#name:"):

            name_line = line

        elif lower.startswith("#last update time:"):

            last_update_line = line

    return name_line, last_update_line


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


# =========================================================
# CHANNEL KEY
# =========================================================

def get_channel_key(extinf):

    tvg_id = get_attr(
        extinf,
        "tvg-id"
    ).strip().lower()

    tvg_name = get_attr(
        extinf,
        "tvg-name"
    ).strip().lower()

    if "," in extinf:

        display_name = (
            extinf.split(",", 1)[1]
            .strip()
            .lower()
        )

    else:

        display_name = ""

    # Same tvg-id but different name
    # = different channel

    if tvg_id and tvg_name:

        return (
            "id_name",
            tvg_id,
            tvg_name
        )

    if tvg_id and display_name:

        return (
            "id_display",
            tvg_id,
            display_name
        )

    if tvg_name:

        return (
            "name",
            tvg_name
        )

    if display_name:

        return (
            "display",
            display_name
        )

    return None


# =========================================================
# PARSE SOURCE CHANNELS
# =========================================================

def parse_source(text):
    """
    Source-এর channel block:

    #EXTINF
    #EXTVLCOPT
    #EXTVLCOPT
    URL

    source থেকে হুবহু নেওয়া হবে।

    Global header:
    #telegram
    #owner
    #special thanks

    channel block-এর মধ্যে থাকলেও বাদ দেওয়া হবে।
    """

    lines = text.splitlines()

    channels = []

    i = 0

    while i < len(lines):

        if lines[i].startswith("#EXTINF:"):

            extinf = lines[i]

            block = [extinf]

            url_index = None

            j = i + 1

            while j < len(lines):

                line = lines[j]

                # Next channel
                if line.startswith("#EXTINF:"):

                    break

                stripped = line.strip()

                lower = stripped.lower()

                # Global source information বাদ
                if (
                    lower.startswith("#telegram:")
                    or lower.startswith("#owner:")
                    or lower.startswith("#special thanks to:")
                ):

                    j += 1
                    continue

                # First normal line = stream URL
                if (
                    stripped
                    and not line.lstrip().startswith("#")
                ):

                    block.append(line)

                    url_index = j

                    break

                # EXT-related lines exactly preserve
                block.append(line)

                j += 1

            if url_index is not None:

                channels.append({
                    "extinf": extinf,
                    "url": lines[url_index],
                    "block": block,
                    "key": get_channel_key(extinf),
                })

                i = url_index

        i += 1

    return channels


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

        print("[WARNING] Source failed")
        print(e)

        return None


# =========================================================
# FIND EXISTING CHANNELS
# =========================================================

def find_existing_channels(lines):

    channels = []

    i = 0

    while i < len(lines):

        if lines[i].startswith("#EXTINF:"):

            extinf_index = i

            url_index = None

            j = i + 1

            while j < len(lines):

                candidate = lines[j].strip()

                if candidate.startswith("#EXTINF:"):

                    break

                if (
                    candidate
                    and not candidate.startswith("#")
                ):

                    url_index = j

                    break

                j += 1

            if url_index is not None:

                channels.append({
                    "extinf_index": extinf_index,
                    "url_index": url_index,
                    "key": get_channel_key(
                        lines[extinf_index]
                    ),
                    "extinf": lines[extinf_index],
                    "url": lines[url_index],
                })

                i = url_index

        i += 1

    return channels


# =========================================================
# SOURCE SECTION
# =========================================================

def find_source_sections(lines):

    sections = []

    i = 0

    while i < len(lines):

        if lines[i].strip() == "#----":

            start = i

            header_end = None

            j = i + 1

            while j < len(lines):

                if lines[j].strip() == "#----":

                    header_end = j

                    break

                j += 1

            if header_end is not None:

                sections.append({
                    "start": start,
                    "header_end": header_end,
                    "end": len(lines) - 1,
                })

                i = header_end

        i += 1

    for n in range(len(sections) - 1):

        sections[n]["end"] = (
            sections[n + 1]["start"] - 1
        )

    return sections


# =========================================================
# SOURCE SECTION NAME
# =========================================================

def get_section_name(lines, section):

    for i in range(
        section["start"] + 1,
        section["header_end"]
    ):

        line = lines[i].strip()

        if line.startswith("#name:"):

            return line.split(
                ":",
                1
            )[1].strip()

        if line.startswith("# ") :

            value = line[2:].strip()

            if (
                value
                and not value.lower().startswith(
                    "updated time:"
                )
            ):

                return value

    return ""


# =========================================================
# FIND MATCHING SOURCE SECTION
# =========================================================

def find_matching_source_section(
    lines,
    source_name
):

    if not source_name:

        return None

    source_name_lower = (
        source_name.strip().lower()
    )

    sections = find_source_sections(lines)

    for section in sections:

        section_name = get_section_name(
            lines,
            section
        )

        if (
            section_name.lower()
            == source_name_lower
        ):

            return section

    return None


# =========================================================
# APPEND NEW SOURCE SECTION
# =========================================================

def append_new_source_section(
    lines,
    name_line,
    last_update_line,
    channels
):

    if not channels:

        return lines

    # Keep existing file untouched as much as possible.
    if lines and lines[-1].strip():

        lines.append("")

    separator_exists = any(
        line.strip() == LIVE_SPORTS_SEPARATOR
        for line in lines
    )

    if not separator_exists:

        lines.append(
            LIVE_SPORTS_SEPARATOR
        )

        lines.append("")

    elif lines and lines[-1].strip():

        lines.append("")

    # Source header
    lines.append("#----")

    if name_line:

        lines.append(name_line)

    if last_update_line:

        lines.append(last_update_line)

    lines.append("#----")

    lines.append("")

    # Source channel blocks EXACTLY
    for channel in channels:

        lines.extend(
            channel["block"]
        )

    return lines


# =========================================================
# APPEND TO EXISTING SOURCE SECTION
# =========================================================

def append_to_existing_source(
    lines,
    section,
    channels
):

    if not channels:

        return lines

    insert_at = (
        section["end"] + 1
    )

    # Existing trailing blank lines preserve
    while (
        insert_at > section["header_end"]
        and lines[insert_at - 1].strip() == ""
    ):

        insert_at -= 1

    new_lines = []

    for channel in channels:

        # Entire source block unchanged
        new_lines.extend(
            channel["block"]
        )

    lines[
        insert_at:insert_at
    ] = new_lines

    return lines


# =========================================================
# MAIN
# =========================================================

def main():

    # -------------------------------------------------------
    # READ MAIN FILE
    # -------------------------------------------------------

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

    # -------------------------------------------------------
    # Preserve original lines
    # -------------------------------------------------------

    lines = original_text.splitlines()

    # -------------------------------------------------------
    # Existing channels
    # -------------------------------------------------------

    existing_channels = (
        find_existing_channels(lines)
    )

    channel_map = {}

    # First occurrence wins
    for channel in existing_channels:

        key = channel["key"]

        if key is None:

            continue

        if key not in channel_map:

            channel_map[key] = channel

    # -------------------------------------------------------
    # Process sources
    # -------------------------------------------------------

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

        source_text = download_source(
            source_url
        )

        if source_text is None:

            print(
                "[INFO] Source skipped."
            )

            continue

        name_line, last_update_line = (
            get_source_header(
                source_text
            )
        )

        source_channels = parse_source(
            source_text
        )

        if not source_channels:

            print(
                "[INFO] No channels found."
            )

            continue

        print(
            f"[INFO] Found "
            f"{len(source_channels)} channels."
        )

        new_channels = []

        # ---------------------------------------------------
        # Process each channel
        # ---------------------------------------------------

        for source_channel in source_channels:

            key = source_channel["key"]

            # ------------------------------------------------
            # Existing channel
            # ------------------------------------------------

            if (
                key is not None
                and key in channel_map
            ):

                existing = channel_map[key]

                # ONLY URL changes.
                # EXTINF / VLCOPT untouched.
                if (
                    existing["url"]
                    != source_channel["url"]
                ):

                    print(
                        f"[UPDATE] URL changed: {key}"
                    )

                    lines[
                        existing["url_index"]
                    ] = source_channel["url"]

                    existing["url"] = (
                        source_channel["url"]
                    )

                    playlist_changed = True

                continue

            # ------------------------------------------------
            # New channel
            # ------------------------------------------------

            new_channels.append(
                source_channel
            )

            if key is not None:

                channel_map[key] = (
                    source_channel
                )

            playlist_changed = True

        if new_channels:

            new_channels_by_source.append({
                "name_line": name_line,
                "last_update_line": last_update_line,
                "channels": new_channels,
            })

    # ========================================================
    # REMOVE DUPLICATE SOURCE CHANNELS
    # ========================================================

    current_channels = (
        find_existing_channels(lines)
    )

    seen = set()

    remove_indexes = set()

    source_sections = (
        find_source_sections(lines)
    )

    for channel in current_channels:

        key = channel["key"]

        if key is None:

            continue

        if key in seen:

            # Duplicate only removed when it is
            # inside a source section.
            inside_source = False

            for section in source_sections:

                if (
                    section["start"]
                    <= channel["extinf_index"]
                    <= section["end"]
                ):

                    inside_source = True
                    break

            if inside_source:

                remove_indexes.add(
                    channel["extinf_index"]
                )

                remove_indexes.add(
                    channel["url_index"]
                )

                playlist_changed = True

        else:

            seen.add(key)

    # Remove from bottom
    for index in sorted(
        remove_indexes,
        reverse=True
    ):

        del lines[index]

    # ========================================================
    # APPEND NEW CHANNELS
    # ========================================================

    for source in new_channels_by_source:

        name_line = source["name_line"]

        last_update_line = (
            source["last_update_line"]
        )

        new_channels = source["channels"]

        # Source name থেকে section match
        if name_line:

            source_name = (
                name_line.split(
                    ":",
                    1
                )[1].strip()
            )

            section = (
                find_matching_source_section(
                    lines,
                    source_name
                )
            )

        else:

            section = None

        if section is not None:

            lines = append_to_existing_source(
                lines,
                section,
                new_channels
            )

        else:

            lines = append_new_source_section(
                lines,
                name_line,
                last_update_line,
                new_channels
            )

    # ========================================================
    # WRITE ONLY IF CHANGED
    # ========================================================

    new_text = "\n".join(lines)

    # Preserve original final newline
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

        print(
            "[SUCCESS] Playlist updated."
        )

    else:

        print(
            "[INFO] No changes. "
            "File was not rewritten."
        )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
