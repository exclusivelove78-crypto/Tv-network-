import requests
import os

FILES = [
    {
        "source": os.getenv("SOURCE1_URL"),
        "target": "Sei-link.m3u",
        "type": "m3u"
    },
    {
        "source": os.getenv("SOURCE2_URL"),
        "target": "Sports.m3u",
        "type": "m3u"
    },
    {
        "source": os.getenv("SOURCE3_URL"),
        "target": "channels.json",
        "type": "json"
    },
    {
        "source": os.getenv("SOURCE4_URL"),
        "target": "epg.json",
        "type": "json"
    }
]

def download(src):
    r = requests.get(src, timeout=60)
    r.raise_for_status()
    return r.text

changed = False

for item in FILES:
    if not item["source"]:
        print(f'Secret missing for {item["target"]}')
        continue

    try:
        data = download(item["source"])

        try:
            with open(item["target"], "r", encoding="utf-8") as f:
                old = f.read()
        except FileNotFoundError:
            old = ""

        if old != data:
            with open(item["target"], "w", encoding="utf-8", newline="\n") as f:
                f.write(data)
            changed = True
            print(f'Updated: {item["target"]}')
        else:
            print(f'No change: {item["target"]}')

    except Exception as e:
        print(f'Error {item["target"]}: {e}')

if changed:
    print("Done.")
else:
    print("Nothing changed.")
