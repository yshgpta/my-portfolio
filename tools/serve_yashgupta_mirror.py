from __future__ import annotations

import json
import mimetypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests


HOST = "127.0.0.1"
PORT = 5174
MANIFEST_PATH = Path("mirror-manifest.json")
ORIGIN = "https://yshgpta.vercel.app"
OLD_SITE_PREFIX = Path("downloads/yashgupta.in/www.yashgupta.in")


class MirrorServer(BaseHTTPRequestHandler):
    manifest: dict[str, dict[str, str | int]]

    def do_GET(self) -> None:
        self.serve_request(head_only=False)

    def do_HEAD(self) -> None:
        self.serve_request(head_only=True)

    def do_POST(self) -> None:
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def serve_request(self, head_only: bool) -> None:
        parsed = urlparse(self.path)

        if self.try_serve_next_image(parsed, head_only):
            return

        candidates = []

        if parsed.path in {"", "/"}:
            candidates.append(f"{ORIGIN}/")
        else:
            query = f"?{parsed.query}" if parsed.query else ""
            candidates.append(f"{ORIGIN}{parsed.path}{query}")
            candidates.append(f"{ORIGIN}{parsed.path}")

        for url in candidates:
            item = self.manifest.get(url)
            if item and item.get("status") != "failed":
                path = self.resolve_local_path(Path(str(item["path"])))
                if path.exists() and path.is_file():
                    self.send_file(path, str(item.get("content_type", "")), head_only)
                    return

        local_path = Path(parsed.path.lstrip("/"))
        if local_path.exists() and local_path.is_file():
            self.send_file(local_path, "", head_only)
            return

        origin_url = candidates[0]
        if origin_url.startswith(ORIGIN):
            item = self.fetch_on_demand(origin_url)
            if item:
                path = self.resolve_local_path(Path(str(item["path"])))
                self.send_file(path, str(item.get("content_type", "")), head_only)
                return

        self.send_error(404, "Resource not found in downloaded mirror")

    def fetch_on_demand(self, url: str) -> dict[str, str | int] | None:
        try:
            response = requests.get(
                url,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148 Safari/537.36"
                },
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - localhost mirror should keep running.
            self.manifest[url] = {"status": "failed", "error": str(exc)}
            MANIFEST_PATH.write_text(json.dumps(self.manifest, indent=2, sort_keys=True))
            return None

        parsed = urlparse(url)
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        name = Path(parsed.path).name or "index"
        if "." not in name:
            name = f"{quote(name, safe='')}.{digest}.html"
        target = Path(parsed.path.strip("/").rsplit("/", 1)[0]) / name
        if parsed.query:
            target = target.with_name(f"{target.stem}.{digest}{target.suffix}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)

        item: dict[str, str | int] = {
            "status": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "bytes": len(response.content),
            "path": str(target),
        }
        self.manifest[url] = item
        MANIFEST_PATH.write_text(json.dumps(self.manifest, indent=2, sort_keys=True))
        return item

    def try_serve_next_image(self, parsed, head_only: bool) -> bool:
        if parsed.path != "/_next/image":
            return False

        image_path = parse_qs(parsed.query).get("url", [None])[0]
        if not image_path:
            return False

        local_path = Path(unquote(image_path).lstrip("/"))
        if local_path.exists() and local_path.is_file():
            self.send_file(local_path, "", head_only)
            return True

        return False

    def resolve_local_path(self, path: Path) -> Path:
        try:
            return path.relative_to(OLD_SITE_PREFIX)
        except ValueError:
            return path

    def send_file(self, path: Path, content_type: str, head_only: bool) -> None:
        body = path.read_bytes()
        guessed_type = mimetypes.guess_type(path.name)[0]
        resolved_type = content_type or guessed_type or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", resolved_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"Manifest not found: {MANIFEST_PATH}")

    MirrorServer.manifest = json.loads(MANIFEST_PATH.read_text())
    server = ThreadingHTTPServer((HOST, PORT), MirrorServer)
    print(f"Serving downloaded yashgupta mirror at http://{HOST}:{PORT}/")
    print("Site files are served from the project root")
    server.serve_forever()


if __name__ == "__main__":
    main()
