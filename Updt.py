import requests

FILES = [
    {
        "source": "https://raw.githubusercontent.com/USER1/REPO1/main/IPTV_BDIX.m3u",
        "target": "Sei-link.m3u",
        "type": "m3u"
    },
    {
        "source": "https://raw.githubusercontent.com/USER2/REPO2/main/Sports.m3u",
        "target": "Sports.m3u",
        "type": "m3u"
    },
    {
        "source": "https://raw.githubusercontent.com/USER3/REPO3/main/channels.json",
        "target": "channels.json",
        "type": "json"
    },
    {
        "source": "https://raw.githubusercontent.com/USER4/REPO4/main/epg.json",
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
