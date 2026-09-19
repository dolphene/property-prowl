"""
Fetch the real private-residential vacancy rate straight from URA's own
quarterly "Release of Nth Quarter <year> real estate statistics" press
release. This is the one signal we could never get through any API (URA
doesn't expose vacancy as structured data on data.gov.sg or its Data
Service API) -- but URA DOES publish it as a plain sentence on its own
website every quarter, and that page turns out to have no bot protection
(same browser-like User-Agent already used for the Data API works fine).

Discovery: URA's own sitemap.xml lists every /news/media/pr<id>/ page
with a <lastmod> timestamp. Press release IDs aren't predictable (they
cover every topic URA publishes, not just real estate stats), so this
walks the most-recently-modified ones, newest first, until it finds one
containing the standard vacancy sentence -- rather than guessing a URL.
"""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "vacancy_snapshot.json"
SITEMAP_URL = "https://www.ura.gov.sg/sitemap.xml"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Matches: "the vacancy rate of completed private residential units
# (excluding ECs) increased to 6.4% as at the end of 2nd Quarter 2026,
# from 6.2% in the previous quarter" -- and the "remained unchanged at"
# phrasing URA uses when the rate doesn't move.
VACANCY_RE = re.compile(
    r"vacancy rate of completed private residential units \(excluding ECs\)\s+"
    r"(?:increased|decreased|remained (?:unchanged|the same))\s+(?:to|at)\s+"
    r"([\d.]+)%\s+as at the end of ([A-Za-z0-9\s]+?\d{4})"
    r"(?:,\s+from\s+([\d.]+)%)?",
    re.IGNORECASE,
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def candidate_urls(limit: int = 30) -> list[str]:
    xml_text = fetch(SITEMAP_URL)
    root = ET.fromstring(xml_text)
    entries = []
    for url_el in root.findall(f"{SITEMAP_NS}url"):
        loc = url_el.findtext(f"{SITEMAP_NS}loc") or ""
        lastmod = url_el.findtext(f"{SITEMAP_NS}lastmod") or ""
        if "/news/media/pr" in loc:
            entries.append((lastmod, loc))
    entries.sort(reverse=True)
    return [loc for _, loc in entries[:limit]]


def main() -> None:
    for url in candidate_urls():
        try:
            html = fetch(url)
        except Exception:
            continue
        match = VACANCY_RE.search(html)
        if not match:
            continue

        rate_str, quarter_label, prev_rate_str = match.groups()
        out = {
            "rate": float(rate_str),
            "previousRate": float(prev_rate_str) if prev_rate_str else None,
            "asOf": quarter_label.strip(),
            "sourceUrl": url,
        }
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(out, f, indent=None)

        print(f"Vacancy: {out['rate']}% as at {out['asOf']} (prev {out['previousRate']}) -- {url}")
        return

    raise RuntimeError(
        "Could not find a recent URA press release containing the vacancy sentence -- "
        "URA may have changed their wording, or the release hasn't been indexed yet."
    )


if __name__ == "__main__":
    main()
