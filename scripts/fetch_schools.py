"""
Fetch Singapore school locations for the "within 1km of a school" watch
criterion. MOE's own dataset (free, no key, same data.gov.sg pattern used
throughout this project) has each school's postal code but no
coordinates -- so each one is geocoded via OneMap's public search API
(also free, no key required; run live and confirmed to return WGS84
lat/lon directly, no SVY21 conversion needed).

OneMap rate-limits unauthenticated search traffic, so this runs with a
small delay between requests and retries on 429 -- ~340 schools takes a
few minutes, acceptable for a dataset that only changes a few times a
year.
"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

MOE_RESOURCE_ID = "d_688b934f82c1059ed0a6993d2a829089"
OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "schools.json"
REQUEST_DELAY_SECONDS = 0.3
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def fetch_all_schools() -> list[dict]:
    rows: list[dict] = []
    offset = 0
    limit = 100
    while True:
        url = (
            f"https://data.gov.sg/api/action/datastore_search?resource_id={MOE_RESOURCE_ID}"
            f"&limit={limit}&offset={offset}"
        )
        payload = fetch_json(url)
        if not payload.get("success"):
            raise RuntimeError(f"data.gov.sg API error: {payload}")
        batch = payload["result"]["records"]
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return rows


def geocode_postal(postal_code: str) -> tuple[float, float] | None:
    url = (
        "https://www.onemap.gov.sg/api/common/elastic/search"
        f"?searchVal={postal_code}&returnGeom=Y&getAddrDetails=N&pageNum=1"
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


def main() -> None:
    schools = fetch_all_schools()
    out = []
    for row in schools:
        postal = (row.get("postal_code") or "").strip()
        if not postal or postal.lower() == "na":
            continue
        coords = geocode_postal(postal)
        time.sleep(REQUEST_DELAY_SECONDS)
        if coords is None:
            continue
        lat, lon = coords
        out.append(
            {
                "name": row["school_name"].title(),
                "postal_code": postal,
                "level": row.get("mainlevel_code"),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
            }
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=None)

    print(f"Geocoded {len(out)}/{len(schools)} schools -> {OUT_PATH}")


if __name__ == "__main__":
    main()
