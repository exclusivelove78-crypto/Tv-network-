import os
import re
from datetime import datetime

import requests


MAIN_FILE = "Set on tv.m3u"

# =========================================================
# SOURCE LINKS
# =========================================================

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
# GET SOURCE HEADER
# =========================================================

def get_source_header(text):

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
# EXTINF ATTRIBUTE
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
# PARSE SOURCE
# =========================================================

def parse_source(text):

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

                # These NEVER enter main playlist
                if (
                    lower.startswith("#telegram:")
                    or lower.startswith("#owner:")
                    or lower.startswith("#special thanks to:")
                ):

                    j += 1
                    continue

                # Stream URL
                if (
                    stripped
                    and not line.lstrip().startswith("#")
                ):

                    block.append(line)

                    url_index = j

                    break

                # EXT-related lines
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

        print("[WARNING] Source failed:")
        print(e)

        return None


# =========================================================
# FIND SOURCE SECTIONS
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

    # Each section ends immediately before
    # the next section.
    for n in range(len(sections) - 1):

        sections[n]["end"] = (
            sections[n + 1]["start"] - 1
        )

    return sections


# =========================================================
# GET SECTION NAME
# =========================================================

def get_section_name(lines, section):

    for i in range(
        section["start"] + 1,
        section["header_end"]
    ):

        line = lines[i].strip()

        if line.lower().startswith("#name:"):

            return line.split(
                ":",
                1
            )[1].strip()

        if line.startswith("# "):

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
# FIND SOURCE SECTION
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
            section_name.strip().lower()
            == source_name_lower
        ):

            return section

    return None


# =========================================================
# BUILD NEW SOURCE SECTION
# =========================================================

def build_source_section(
    name_line,
    last_update_line,
    channels
):

    new_section = []

    new_section.append("#----")

    if name_line:
        new_section.append(name_line)

    if last_update_line:
        new_section.append(last_update_line)

    new_section.append("#----")

    new_section.append("")

    for channel in channels:

        new_section.extend(
            channel["block"]
        )

    return new_section


# =========================================================
# REPLACE EXISTING SOURCE SECTION
# =========================================================

def replace_source_section(
    lines,
    section,
    name_line,
    last_update_line,
    channels
):

    new_section = build_source_section(
        name_line,
        last_update_line,
        channels
    )

    start = section["start"]
    end = section["end"]

    # IMPORTANT:
    #
    # Only this source section is replaced.
    #
    # Everything before and after it stays
    # exactly where it was.

    lines[
        start:end + 1
    ] = new_section

    return lines


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

    # Existing playlist-এর শেষের formatting
    # unnecessarily modify করা হবে না.

    if lines and lines[-1].strip():

        lines.append("")

    separator_exists = any(
        line.strip()
        == LIVE_SPORTS_SEPARATOR
        for line in lines
    )

    if not separator_exists:

        lines.append(
            LIVE_SPORTS_SEPARATOR
        )

        lines.append("")

    elif lines and lines[-1].strip():

        lines.append("")

    new_section = build_source_section(
        name_line,
        last_update_line,
        channels
    )

    lines.extend(new_section)

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
    # IMPORTANT:
    # splitlines() changes internal representation only.
    # We write the file only if actual resulting text
    # is different.
    # -------------------------------------------------------

    lines = original_text.splitlines()

    # -------------------------------------------------------
    # PROCESS EACH SOURCE
    # -------------------------------------------------------

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

        # ---------------------------------------------------
        # If source fails:
        #
        # DO NOT DELETE OLD SOURCE.
        #
        # This is very important.
        # ---------------------------------------------------

        if source_text is None:

            print(
                "[INFO] Source failed. "
                "Old section kept unchanged."
            )

            continue

        # ---------------------------------------------------
        # SOURCE HEADER
        # ---------------------------------------------------

        name_line, last_update_line = (
            get_source_header(
                source_text
            )
        )

        # ---------------------------------------------------
        # SOURCE CHANNELS
        # ---------------------------------------------------

        source_channels = parse_source(
            source_text
        )

        if not source_channels:

            print(
                "[INFO] Source returned "
                "no channels. "
                "Old section kept unchanged."
            )

            continue

        print(
            f"[INFO] Source has "
            f"{len(source_channels)} channels."
        )

        # ---------------------------------------------------
        # SOURCE NAME
        # ---------------------------------------------------

        source_name = ""

        if name_line:

            source_name = (
                name_line.split(
                    ":",
                    1
                )[1].strip()
            )

        # ---------------------------------------------------
        # FIND EXISTING SOURCE SECTION
        # ---------------------------------------------------

        section = find_matching_source_section(
            lines,
            source_name
        )

        # ---------------------------------------------------
        # EXISTING SOURCE
        # ---------------------------------------------------

        if section is not None:

            old_channel_count = 0

            for line in lines[
                section["start"]:
                section["end"] + 1
            ]:

                if line.startswith("#EXTINF:"):
                    old_channel_count += 1

            print(
                f"[INFO] Replacing source section: "
                f"{source_name}"
            )

            print(
                f"[INFO] Old channels: "
                f"{old_channel_count}"
            )

            print(
                f"[INFO] New channels: "
                f"{len(source_channels)}"
            )

            # -----------------------------------------------
            # THIS IS THE IMPORTANT PART
            #
            # Old source section is completely removed.
            # New source section is inserted.
            #
            # Therefore:
            #
            # OLD channel gone from source
            # -> OLD channel gone from main playlist
            #
            # OLD URL
            # -> gone
            #
            # NEW URL
            # -> inserted
            # -----------------------------------------------

            lines = replace_source_section(
                lines,
                section,
                name_line,
                last_update_line,
                source_channels
            )

        # ---------------------------------------------------
        # NEW SOURCE
        # ---------------------------------------------------

        else:

            print(
                f"[INFO] New source section: "
                f"{source_name}"
            )

            lines = append_new_source_section(
                lines,
                name_line,
                last_update_line,
                source_channels
            )

    # =======================================================
    # CREATE FINAL TEXT
    # =======================================================

    new_text = "\n".join(lines)

    # Preserve original final newline
    if original_text.endswith("\n"):

        new_text += "\n"

    # =======================================================
    # WRITE ONLY WHEN ACTUALLY CHANGED
    # =======================================================

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
            "[INFO] No changes."
        )

        print(
            "[INFO] Main playlist was NOT rewritten."
        )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
