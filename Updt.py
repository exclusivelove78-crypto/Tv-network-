import requests

SOURCES = [
    "https://raw.githubusercontent.com/sm-monirulislam/SM-Live-TV/main/IPTV_BDIX.m3u",
    "https://raw.githubusercontent.com/USERNAME/REPOSITORY/main/playlist.m3u"
]

TARGET_FILE = "Sei-link.m3u"


def parse_m3u(lines):
    channels = {}

    for i, line in enumerate(lines):
        if line.startswith("#EXTINF") and 'tvg-id="' in line:
            tvg_id = line.split('tvg-id="')[1].split('"')[0].strip()

            if i + 1 < len(lines):
                url = lines[i + 1].strip()

                if url.startswith("http"):
                    channels[tvg_id] = url

    return channels


source_urls = {}

for source in SOURCES:
    try:
        data = requests.get(source, timeout=30).text.splitlines()
        parsed = parse_m3u(data)

        for k, v in parsed.items():
            if k not in source_urls:
                source_urls[k] = v

    except Exception as e:
        print(f"Failed: {source} -> {e}")


with open(TARGET_FILE, "r", encoding="utf-8") as f:
    target_lines = f.read().splitlines()

updated = False

for i, line in enumerate(target_lines):
    if line.startswith("#EXTINF") and 'tvg-id="' in line:
        tvg_id = line.split('tvg-id="')[1].split('"')[0].strip()

        if tvg_id in source_urls:
            if i + 1 < len(target_lines):
                if target_lines[i + 1].strip() != source_urls[tvg_id]:
                    target_lines[i + 1] = source_urls[tvg_id]
                    updated = True

if updated:
    with open(TARGET_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(target_lines) + "\n")
    print("Playlist updated.")
else:
    print("No changes.")
