"""Build midterm/dashboard.html, a page to see the project's latest results.

It reads the newest files in data/ and puts them into one self-contained HTML
file (no server needed, open it in a browser):
  - one section per analyzed topic: coverage chart, search intent, news drivers,
    scheduled events, and the cited explanation (every citation links to its source)
  - the latest general trends: Google Trends and most-viewed Wikipedia articles

Usage:
    python midterm/build_dashboard.py
    python midterm/build_dashboard.py --open      # also open it in the browser
"""
import argparse
import json
import shutil
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUTPUT = HERE / "dashboard.html"
TEMPLATE = HERE / "dashboard_template.html"


def newest_per_topic(folder):
    """The newest file for each topic in a folder, keyed by topic."""
    latest = {}
    for path in sorted(folder.glob("*.json")):  # names end with the time, so sorted = oldest first
        data = json.loads(path.read_text(encoding="utf-8"))
        latest[data["topic"]] = data
    return list(latest.values())


def newest_file(folder):
    paths = sorted(folder.glob("*.json"))
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else None


def payload():
    analyses = newest_per_topic(DATA / "analysis") if (DATA / "analysis").exists() else []
    analyses.sort(key=lambda a: a["facts"]["coverage"]["momentum"], reverse=True)  # hottest topic first
    return {
        "built_at": datetime.now().astimezone().isoformat(timespec="minutes"),
        "analyses": analyses,
        "snapshot": newest_file(DATA / "snapshots") if (DATA / "snapshots").exists() else None,
    }


def render(data):
    """The dashboard template filled with data. app.py serves this too."""
    # "</" inside the JSON would end the <script> tag early.
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", data_json)


def build():
    OUTPUT.write_text(render(payload()), encoding="utf-8")
    return OUTPUT


def open_in_browser(path):
    # Under WSL, hand the file to Windows so it opens in the normal browser.
    if shutil.which("wslview"):
        subprocess.run(["wslview", str(path)], check=False)
    elif shutil.which("explorer.exe"):
        windows_path = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True).stdout.strip()
        subprocess.run(["explorer.exe", windows_path], check=False)
    else:
        webbrowser.open(path.as_uri())


def main():
    parser = argparse.ArgumentParser(description="Build the project dashboard page.")
    parser.add_argument("--open", action="store_true", help="open the page after building it")
    args = parser.parse_args()

    path = build()
    print(f"Wrote {path.relative_to(HERE.parent)}")
    if args.open:
        open_in_browser(path)


if __name__ == "__main__":
    main()
