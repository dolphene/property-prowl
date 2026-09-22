"""
Geocode URA's private-residential supply pipeline (already fetched into
data/raw/pipeline_ura_api.json by fetch_ura_api.py) for the Map page's
"Future supply" layer -- real project locations, not illustrative pins.

Same OneMap public search API used for schools (free, no key, WGS84
directly). Pipeline project names are sometimes generic catch-alls
("Residential/service apartments", "Service apartments/Office/retail
development") that won't geocode well alone, so this tries
"<project> <street>" first (most specific) and falls back to the street
name by itself if that returns nothing.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "pipeline_ura_api.json"
OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "supply_locations.json"
REQUEST_DELAY_SECONDS = 0.3
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def onemap_search(query: str) -> tuple[float, float] | None:
    url = (
        "https://www.onemap.gov.sg/api/common/elastic/search"
        f"?searchVal={urllib.parse.quote(query)}&returnGeom=Y&getAddrDetails=N&pageNum=1"
    )
    for attempt in range(3):
        try:
            payload = fetch_json(url)
            if payload.get("found") and payload["results"]:
                r = payload["results"][0]
                return float(r["LATITUDE"]), float(r["LONGITUDE"])
            return None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            return None
    return None


def geocode(project: str, street: str) -> tuple[float, float] | None:
    for query in (f"{project} {street}".strip(), street.strip()):
        if not query:
            continue
        point = onemap_search(query)
        time.sleep(REQUEST_DELAY_SECONDS)
        if point:
            return point
    return None


def main() -> None:
    with RAW_PATH.open(encoding="utf-8") as f:
        rows = json.load(f)

    out = []
    geocoded = 0
    for r in rows:
        project = (r.get("project") or "").strip()
        street = (r.get("street") or "").strip()
        if not project:
            continue
        point = geocode(project, street)
        if point is None:
            continue
        geocoded += 1
        lat, lon = point
        out.append(
            {
                "project": project,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "totalUnits": r.get("totalUnits") or 0,
                "expectedTopYear": r.get("expectedTOPYear") or "na",
                "developerName": r.get("developerName") or "",
            }
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=None)

    print(f"Geocoded {geocoded}/{len(rows)} pipeline projects -> {OUT_PATH}")


if __name__ == "__main__":
    main()
