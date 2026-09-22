"""
Proactive research feed, part 1: real resale transactions matching the
user's stated Den criteria (resale over new launch, near MRT, near a
school) -- not a generic "interesting projects" list, but one filtered
and scored against what they actually said they want.

Real limitation, stated plainly: URA's transaction data has no bedroom
or bathroom count, only floor area, so "min 2 bed 2 bath" can't be
filtered directly. Everything else (resale-only, MRT proximity, school
proximity) uses real data:
  - resale-only: transactions_flat.json's saleType field.
  - MRT/school proximity: candidate projects are geocoded via OneMap
    (same technique as fetch_supply_locations.py) and matched against
    mrt_stations.json / schools.json (already published by this repo).

Not a hard filter -- projects are scored and ranked, not excluded,
so a quiet cycle still returns something rather than nothing.
"""
import json
import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

TRANSACTIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "transactions_flat.json"
MRT_PATH = Path(__file__).resolve().parent.parent / "docs" / "mrt_stations.json"
SCHOOLS_PATH = Path(__file__).resolve().parent.parent / "docs" / "schools.json"
OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "resale_matches.json"

MIN_RECENT_TRANSACTIONS = 3
CANDIDATE_LIMIT = 15  # how many candidate projects get geocoded per run
REQUEST_DELAY_SECONDS = 0.3
HEADERS = {"User-Agent": "Mozilla/5.0"}
GENERIC_PROJECT_NAMES = {"LANDED HOUSING DEVELOPMENT"}


def months_ago(latest: str, months: int) -> str:
    y, m = int(latest[:4]), int(latest[5:7])
    m -= months
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest(lat: float, lon: float, points: list[dict]) -> tuple[dict, float] | None:
    best = None
    for p in points:
        d = haversine_m(lat, lon, p["lat"], p["lon"])
        if best is None or d < best[1]:
            best = (p, d)
    return best


def onemap_search(query: str) -> tuple[float, float] | None:
    url = (
        "https://www.onemap.gov.sg/api/common/elastic/search"
        f"?searchVal={urllib.parse.quote(query)}&returnGeom=Y&getAddrDetails=N&pageNum=1"
    )
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read())
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
    for query in (f"{project} {street}".strip(), street.strip(), project.strip()):
        if not query:
            continue
        point = onemap_search(query)
        time.sleep(REQUEST_DELAY_SECONDS)
        if point:
            return point
    return None


def main() -> None:
    with TRANSACTIONS_PATH.open(encoding="utf-8") as f:
        rows = json.load(f)
    mrt_stations = json.loads(MRT_PATH.read_text(encoding="utf-8")) if MRT_PATH.exists() else []
    schools = json.loads(SCHOOLS_PATH.read_text(encoding="utf-8")) if SCHOOLS_PATH.exists() else []

    resale_rows = [r for r in rows if r.get("saleType") == "Resale"]
    if not resale_rows:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUT_PATH.open("w", encoding="utf-8") as f:
            json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "data_as_of": None, "matches": []}, f)
        print("No resale transactions found -- wrote empty matches.")
        return

    latest = max(r["contractDate"] for r in resale_rows if r["contractDate"])
    recent_cutoff = months_ago(latest, 3)
    trailing_cutoff = months_ago(latest, 12)

    by_project = defaultdict(list)
    for r in resale_rows:
        by_project[r["project"]].append(r)

    candidates = []
    for project, txns in by_project.items():
        if project in GENERIC_PROJECT_NAMES:
            continue
        trailing = [t for t in txns if t["contractDate"] >= trailing_cutoff]
        recent = [t for t in trailing if t["contractDate"] >= recent_cutoff]
        if len(recent) < MIN_RECENT_TRANSACTIONS:
            continue

        recent_median = statistics.median(t["psf"] for t in recent)
        trailing_median = statistics.median(t["psf"] for t in trailing)
        pct_below = (trailing_median - recent_median) / trailing_median * 100 if trailing_median else 0

        # Composite score: recent activity + how far below its own trend
        # -- not a hard filter, just how candidates get ranked/limited
        # before the (rate-limited) geocoding pass.
        score = len(recent) + max(pct_below, 0)
        candidates.append(
            {
                "project": project,
                "street": recent[0]["street"],
                "district": recent[0]["district"],
                "marketSegment": recent[0]["marketSegment"],
                "recentTransactionCount": len(recent),
                "recentMedianPsf": round(recent_median, 0),
                "trailing12moMedianPsf": round(trailing_median, 0),
                "pctBelowTrend": round(pct_below, 1),
                "_score": score,
            }
        )

    candidates.sort(key=lambda c: -c["_score"])
    top_candidates = candidates[:CANDIDATE_LIMIT]

    matches = []
    for c in top_candidates:
        point = geocode(c["project"], c["street"])
        entry = {k: v for k, v in c.items() if k != "_score"}
        if point:
            lat, lon = point
            entry["lat"] = round(lat, 6)
            entry["lon"] = round(lon, 6)
            mrt = nearest(lat, lon, mrt_stations)
            if mrt:
                station, dist = mrt
                entry["nearestMrt"] = {"name": station["name"], "type": station["type"], "meters": round(dist)}
            school = nearest(lat, lon, schools)
            if school:
                sch, dist = school
                entry["nearestSchool"] = {"name": sch["name"], "meters": round(dist)}
        matches.append(entry)

    # Prefer showing genuinely nearby matches first (real MRT/school proximity
    # is part of the stated criteria), but keep everything -- a candidate
    # without a confirmed nearby MRT/school still surfaces, just lower.
    def rank(m: dict) -> float:
        near_mrt = m.get("nearestMrt", {}).get("meters", 99999)
        near_school = m.get("nearestSchool", {}).get("meters", 99999)
        bonus = (1000 if near_mrt <= 1000 else 0) + (1000 if near_school <= 1000 else 0)
        return -(m["recentTransactionCount"] + max(m["pctBelowTrend"], 0) + bonus)

    matches.sort(key=rank)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_as_of": latest,
        "methodology": (
            "Real resale-only URA transactions (saleType=Resale), min 3 recent (last 3mo) sales "
            "per project. Ranked by recent activity + how far below the project's own trailing "
            "12mo median psf, with a bonus for genuine MRT/school proximity (within 1km, geocoded "
            "via OneMap). Bedroom/bathroom count isn't in URA's data, so 'min 2 bed 2 bath' can't "
            "be filtered here -- check listings directly for that."
        ),
        "matches": matches[:10],
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=None)

    print(f"{len(matches)} candidates geocoded, {len(out['matches'])} published -> {OUT_PATH}")


if __name__ == "__main__":
    main()
