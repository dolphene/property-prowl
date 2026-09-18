"""
Turn the raw PMI_Resi_Pipeline snapshot into the real Supply Pressure
signal. This is a SNAPSHOT, not a time series -- data.gov.sg's own mirror
of this dataset is stale (see README), and our own fetch only gives us
whatever URA reports as the CURRENT pipeline each run, not history since
inception. So there's no QoQ/YoY momentum to compute here the way the
other signals do it; instead this reports the real current total and a
near-term (next 2 years) breakdown where URA has a confirmed TOP year --
most of the pipeline (roughly 3 in 4 units, as of 2026-09) doesn't have a
confirmed TOP year yet (still in planning), so treat "near-term" as a
lower bound, not the whole picture.
"""
import json
from pathlib import Path

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "pipeline_ura_api.json"
OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "supply_snapshot.json"


def main() -> None:
    with RAW_PATH.open(encoding="utf-8") as f:
        rows = json.load(f)

    total_units = sum(r.get("totalUnits") or 0 for r in rows)
    by_top_year: dict[str, int] = {}
    for r in rows:
        year = r.get("expectedTOPYear") or "na"
        by_top_year[year] = by_top_year.get(year, 0) + (r.get("totalUnits") or 0)

    confirmed_years = sorted(y for y in by_top_year if y != "na")
    near_term_years = confirmed_years[:2]  # next 2 confirmed TOP years in the data
    near_term_units = sum(by_top_year.get(y, 0) for y in near_term_years)
    no_confirmed_top_units = by_top_year.get("na", 0)

    out = {
        "totalPipelineUnits": total_units,
        "projectCount": len(rows),
        "byTopYear": by_top_year,
        "nearTermYears": near_term_years,
        "nearTermUnits": near_term_units,
        "unitsWithoutConfirmedTop": no_confirmed_top_units,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=None)

    print(f"Total pipeline: {total_units} units across {len(rows)} projects")
    print(f"Near-term ({near_term_years}): {near_term_units} units")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
