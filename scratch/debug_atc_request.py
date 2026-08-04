from __future__ import annotations

import urllib.error
import urllib.request

URL = "https://bidplus.gem.gov.in/bidding/downloadOmppdfile/"
TIMEOUT = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Referer": "https://bidplus.gem.gov.in/",
}


def fetch(url: str, headers: dict[str, str] | None = None) -> tuple[str, int | None, str, bytes]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return (
                "ok",
                getattr(resp, "status", None),
                resp.headers.get("Content-Type", ""),
                resp.read(256),
            )
    except urllib.error.HTTPError as err:
        return (
            "http_error",
            err.code,
            err.headers.get("Content-Type", "") if err.headers else "",
            err.read(256),
        )
    except Exception as err:
        return (f"exception:{type(err).__name__}", None, str(err), b"")


for label, headers in [
    ("headered", HEADERS),
    ("bare", None),
]:
    state, status, content_type, body = fetch(URL, headers)
    print(f"{label}: state={state} status={status} content_type={content_type!r} body_prefix={body[:120]!r}")
