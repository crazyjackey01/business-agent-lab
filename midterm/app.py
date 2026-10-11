"""Local web app: type any topic, get its search data and a fact-based analysis.

Starts a small server on your own computer (only reachable from it) and opens
the dashboard with a search box. Typing a topic runs the whole pipeline:
topic_trends.py collects fresh data, analyze_topic.py measures the facts and
writes the cited explanation, and the result appears on the page.

A Korean topic is searched in Korea (ko/KR); anything else in the US (en/US).
One search takes about 30-60 seconds.

Usage:
    python midterm/app.py              # then use the page that opens
    python midterm/app.py --port 8800 --no-open
"""
import argparse
import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from analyze_topic import analyze, save_analysis
from build_dashboard import payload, render

MAX_TOPIC_LENGTH = 60
# One search at a time: each one makes ~20 requests to Google and two model calls.
search_lock = threading.Lock()


def guess_region(topic):
    """Korean letters -> Korea; otherwise US English."""
    if re.search(r"[가-힣]", topic):
        return "ko", "KR"
    return "en", "US"


class Handler(BaseHTTPRequestHandler):
    def send_body(self, status, body, content_type):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, obj):
        self.send_body(status, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_body(200, render({**payload(), "live": True}), "text/html; charset=utf-8")
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/analyze":
            return self.send_json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(min(length, 10_000)) or b"{}")
        except ValueError:
            return self.send_json(400, {"error": "bad request"})

        topic = " ".join(str(request.get("topic", "")).split())
        if not topic or len(topic) > MAX_TOPIC_LENGTH:
            return self.send_json(400, {"error": f"type a topic of 1-{MAX_TOPIC_LENGTH} characters"})
        lang, geo = guess_region(topic)
        if request.get("region") in ("KR", "US"):
            lang, geo = ("ko", "KR") if request["region"] == "KR" else ("en", "US")

        if not search_lock.acquire(blocking=False):
            return self.send_json(429, {"error": "another search is running, try again in a moment"})
        try:
            print(f"searching: {topic} ({geo})")
            result = analyze(topic, lang, geo, refresh=True)
            save_analysis(result)
        except Exception as error:  # show any failure on the page instead of a dead request
            return self.send_json(500, {"error": f"{type(error).__name__}: {error}"})
        finally:
            search_lock.release()
        self.send_json(200, result)

    def log_message(self, format, *args):
        pass  # keep the terminal quiet; searches are printed above


def main():
    parser = argparse.ArgumentParser(description="Search any topic in a local web page.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}/"
    print(f"Trend Signals running at {url}  (Ctrl+C to stop)")
    if not args.no_open:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
