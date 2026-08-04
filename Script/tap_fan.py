import os
import requests


BASE_FILE = "set on tv.m3u"
MARKER = "######## TAPMAD + FANCODE UPDATED LIST ########"


PLAYLIST_URLS = [
    os.environ["TAPMAD_URL"],
    os.environ["FANCODE_URL"],
]


def download_playlist(url):
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    return response.text


def extract_channels(content):
    lines = content.splitlines()

    channels = []
    entry = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith("#EXTM3U"):
            continue

        if line.startswith("#EXTINF"):
            if entry:
                channels.append(entry)

            entry = [line]

        elif entry:
            entry.append(line)

    if entry:
        channels.append(entry)

    return channels




def main():

    if not os.path.exists(BASE_FILE):
        print(f"Missing file: {BASE_FILE}")
        return


    with open(
        BASE_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        old_data = f.read()


    # Keep only fixed channels
    if MARKER in old_data:

        fixed_part = old_data.split(
            MARKER,
            1
        )[0]

    else:

        fixed_part = old_data.rstrip() + "\n\n"


    new_content = []

    new_content.append(
        fixed_part.rstrip()
    )

    new_content.append("")
    new_content.append(MARKER)
    new_content.append("")


    total = 0


    for url in PLAYLIST_URLS:

        try:

            print("Downloading playlist")

            data = download_playlist(url)

            channels = extract_channels(data)


            for channel in channels:

                new_content.extend(channel)
                new_content.append("")

                total += 1


        except Exception as e:

            print(
                "Playlist error:",
                e
            )


    final_data = "\n".join(new_content).rstrip() + "\n"


    with open(
        BASE_FILE,
        "w",
        encoding="utf-8",
        newline="\n"
    ) as f:

        f.write(final_data)


    print(
        f"Updated successfully. Total channels added: {total}"
    )


if __name__ == "__main__":
    main()
