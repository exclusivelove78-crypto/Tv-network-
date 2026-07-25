import requests

SOURCE = "https://raw.githubusercontent.com/sm-monirulislam/SM-Live-TV/main/IPTV_BDIX.m3u"
TARGET_FILE = "Sei-link.m3u"

def parse_m3u(lines):
    channels = {}
    current_id = None

    for i, line in enumerate(lines):
        if line.startswith("#EXTINF"):
            current_id = None
            if 'tvg-id="' in line:
                current_id = line.split('tvg-id="')[1].split('"')[0].strip()

            if current_id and i + 1 < len(lines):
                channels[current_id] = lines[i + 1].strip()

    return channels

source_lines = requests.get(SOURCE, timeout=30).text.splitlines()

with open(TARGET_FILE, "r", encoding="utf-8") as f:
    target_lines = f.read().splitlines()

source_urls = parse_m3u(source_lines)

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
