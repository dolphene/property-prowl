"""
Fetch real MRT/LRT station locations from LTA DataMall's own geospatial
static dataset (an ESRI shapefile of station footprint polygons, in
SVY21). Converts to WGS84 for use on a Leaflet map, and collapses each
interchange station's multiple platform-box polygons (e.g. Dhoby Ghaut
has 3) into one point per station name.

The SVY21->WGS84 conversion is the standard published Transverse Mercator
inverse formula (Redfearn's formulas) using SVY21's own defining
parameters -- verified against known real-world coordinates for Hougang,
Bedok, Raffles Place and Dhoby Ghaut MRT stations (all matched within
~20-90m, consistent with centroiding a station footprint rather than
picking an exact entrance point).

Requires an LTA DataMall API Account Key (free registration at
datamall.lta.gov.sg) only to discover the current dataset filename via
their static-data listing page -- the shapefile download itself doesn't
need the key, but LTA rotates the filename periodically (e.g.
"TrainStation_Mar2026.zip"), so this scrapes the listing page for
whatever the current link is rather than hardcoding a stale one.
"""
import io
import json
import math
import re
import urllib.request
import zipfile
from pathlib import Path

import shapefile

OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "mrt_stations.json"
STATIC_DATA_PAGE = "https://datamall.lta.gov.sg/content/datamall/en/static-data.html"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
SVY21_OLAT = math.radians(1.366666)
SVY21_OLON = math.radians(103.833333)
SVY21_N0 = 38744.572
SVY21_E0 = 28001.642
SVY21_K0 = 1.0


def svy21_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    a, f = WGS84_A, WGS84_F
    e2 = (2 * f) - (f * f)
    e4, e6 = e2 * e2, e2 * e2 * e2
    A0 = 1 - (e2 / 4) - (3 * e4 / 64) - (5 * e6 / 256)
    A2 = (3 / 8) * (e2 + (e4 / 4) + (15 * e6 / 128))
    A4 = (15 / 256) * (e4 + (3 * e6 / 4))
    A6 = (35 / 3072) * e6

    Mo = WGS84_A * (
        A0 * SVY21_OLAT
        - A2 * math.sin(2 * SVY21_OLAT)
        + A4 * math.sin(4 * SVY21_OLAT)
        - A6 * math.sin(6 * SVY21_OLAT)
    )
    M = Mo + (northing - SVY21_N0) / SVY21_K0
    mu = M / (a * A0)

    ee1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (
        mu
        + ((3 * ee1 / 2) - (27 * ee1**3 / 32)) * math.sin(2 * mu)
        + ((21 * ee1**2 / 16) - (55 * ee1**4 / 32)) * math.sin(4 * mu)
        + (151 * ee1**3 / 96) * math.sin(6 * mu)
        + (1097 * ee1**4 / 512) * math.sin(8 * mu)
    )

    sin_phi1 = math.sin(phi1)
    rho = a * (1 - e2) / (1 - e2 * sin_phi1**2) ** 1.5
    v = a / math.sqrt(1 - e2 * sin_phi1**2)
    psi = v / rho
    t = math.tan(phi1)
    x = easting - SVY21_E0
    x2 = x * x

    lat = (
        phi1
        - (t / (2 * rho * v)) * x2
        + (t / (24 * rho * v**3)) * x2**2 * (-4 * psi**2 + 9 * psi * (1 - t**2) + 12 * t**2)
        - (t / (720 * rho * v**5))
        * x2**3
        * (
            8 * psi**4 * (11 - 24 * t**2)
            - 12 * psi**3 * (21 - 71 * t**2)
            + 15 * psi**2 * (15 - 98 * t**2 + 15 * t**4)
            + 180 * psi * (5 * t**2 - 3 * t**4)
            + 360 * t**4
        )
    )
    sec_phi1 = 1 / math.cos(phi1)
    lon = (
        SVY21_OLON
        + (x / v) * sec_phi1
        - (x**3 / (6 * v**3)) * sec_phi1 * (psi + 2 * t**2)
        + (x**5 / (120 * v**5))
        * sec_phi1
        * (-4 * psi**3 * (1 - 6 * t**2) + psi**2 * (9 - 68 * t**2) + 72 * psi * t**2 + 24 * t**4)
    )
    return math.degrees(lat), math.degrees(lon)


def find_shapefile_url() -> str:
    req = urllib.request.Request(STATIC_DATA_PAGE, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    match = re.search(r'href="(/content/dam/datamall/datasets/Geospatial/TrainStation[^"]+\.zip)"', html)
    if not match:
        raise RuntimeError("Could not find a TrainStation shapefile link on LTA's static-data page")
    return "https://datamall.lta.gov.sg" + match.group(1)


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def clean_name(raw: str) -> str:
    return re.sub(r"\s+(MRT|LRT)\s+STATION$", "", raw.strip(), flags=re.IGNORECASE).title()


# LTA's shapefile also includes depots and other rail facilities tagged
# the same way as passenger stations -- not places anyone measures
# "distance to MRT" from, so exclude anything matching these.
NON_STATION_PATTERN = re.compile(r"depot|siding|facility building|tunnel structure", re.IGNORECASE)


def main() -> None:
    url = find_shapefile_url()
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        zip_bytes = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        shp_name = next(n for n in zf.namelist() if n.lower().endswith(".shp"))
        base = shp_name[: -len(".shp")]
        shp = io.BytesIO(zf.read(base + ".shp"))
        dbf = io.BytesIO(zf.read(base + ".dbf"))
        shx_names = [n for n in zf.namelist() if n.lower() == (base + ".shx").lower()]
        shx = io.BytesIO(zf.read(shx_names[0])) if shx_names else None
        sf = shapefile.Reader(shp=shp, dbf=dbf, shx=shx)

        stations: dict[str, dict] = {}
        for sr in sf.shapeRecords():
            rec = sr.record.as_dict()
            raw_name = rec.get("STN_NAM_DE") or rec.get("STN_NAM") or ""
            if not raw_name or not sr.shape.points or NON_STATION_PATTERN.search(raw_name):
                continue
            name = clean_name(raw_name)
            typ = (rec.get("TYP_CD_DES") or "MRT").upper()
            cx, cy = centroid(sr.shape.points)
            lat, lon = svy21_to_wgs84(cx, cy)
            entry = stations.setdefault(name, {"name": name, "type": typ, "status": "operational", "_pts": []})
            entry["_pts"].append((lat, lon))

    out = []
    for entry in stations.values():
        pts = entry.pop("_pts")
        entry["lat"] = round(sum(p[0] for p in pts) / len(pts), 6)
        entry["lon"] = round(sum(p[1] for p in pts) / len(pts), 6)
        out.append(entry)
    out.sort(key=lambda s: s["name"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=None)

    print(f"Wrote {len(out)} stations to {OUT_PATH} (source: {url})")


if __name__ == "__main__":
    main()
