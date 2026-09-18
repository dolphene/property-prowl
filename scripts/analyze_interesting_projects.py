"""
Surface projects/developments with notable recent transaction patterns --
the auto-populated "Prowl list" per user direction. Real URA transaction
data (data/processed/transactions_flat.json), refreshed on the same
twice-weekly schedule as everything else -- roughly every 3-4 days, per
the ask.

Important scope note: this is about developments showing interesting
PATTERNS in completed sales, not live asking-price listings. There is no
legitimate free/cheap live-listings data source (PropertyGuru/99.co/SRX
don't offer public APIs; third-party scrapers of those sites violate their
Terms of Service and won't be used here). See project READMEs for the full
reasoning. If the user wants literal "catch a live fire sale" monitoring,
that needs manual price tracking on properties they've explicitly added
(stalked_properties + stalked_property_events), which is a separate,
already-built feature -- not this script.

Three categories, minimum 3 recent transactions required per project to
avoid single-transaction noise:

  below_trend   Recent (last 3 months) median psf is notably below the
                project's own trailing-12-month median psf -- the project
                itself may be softening, or a discount cluster occurred.
  most_active   Highest transaction count in the last 3 months -- where
                real buyer activity concentrated recently.
  tight_pricing Lowest psf coefficient of variation over the last 12
                months among actively-transacting projects -- consistent,
                predictable pricing (lower valuation risk).
"""
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "transactions_flat.json"
OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "interesting_projects.json"

MIN_RECENT_TRANSACTIONS = 3

# URA groups landed-housing transactions that aren't part of a named
# condo/EC project under this generic catch-all -- not a real, stalkable
# development, so exclude it.
GENERIC_PROJECT_NAMES = {"LANDED HOUSING DEVELOPMENT"}


def months_ago(latest: str, months: int) -> str:
    y, m = int(latest[:4]), int(latest[5:7])
    m -= months
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def main() -> None:
    with DATA_PATH.open(encoding="utf-8") as f:
        rows = json.load(f)

    latest = max(r["contractDate"] for r in rows if r["contractDate"])
    recent_cutoff = months_ago(latest, 3)
    trailing_cutoff = months_ago(latest, 12)

    by_project = defaultdict(list)
    for r in rows:
        by_project[r["project"]].append(r)

    below_trend, most_active, tight_pricing = [], [], []

    for project, txns in by_project.items():
        if project in GENERIC_PROJECT_NAMES:
            continue
        trailing = [t for t in txns if t["contractDate"] >= trailing_cutoff]
        recent = [t for t in trailing if t["contractDate"] >= recent_cutoff]
        if len(recent) < MIN_RECENT_TRANSACTIONS:
            continue

        recent_psf = [t["psf"] for t in recent]
        trailing_psf = [t["psf"] for t in trailing]
        recent_median = statistics.median(recent_psf)
        trailing_median = statistics.median(trailing_psf)

        base = {
            "project": project,
            "district": recent[0]["district"],
            "marketSegment": recent[0]["marketSegment"],
            "recentTransactionCount": len(recent),
            "recentMedianPsf": round(recent_median, 0),
            "trailing12moMedianPsf": round(trailing_median, 0),
        }

        if trailing_median > 0:
            pct_below = (trailing_median - recent_median) / trailing_median * 100
            if pct_below >= 5:  # recent median at least 5% below trailing 12mo median
                below_trend.append({**base, "pctBelowTrend": round(pct_below, 1)})

        most_active.append(base)

        if len(trailing_psf) >= 5:
            mean = statistics.mean(trailing_psf)
            stdev = statistics.stdev(trailing_psf)
            cv = (stdev / mean * 100) if mean else None
            if cv is not None:
                tight_pricing.append({**base, "psfCoefficientOfVariation": round(cv, 1)})

    below_trend.sort(key=lambda p: -p["pctBelowTrend"])
    most_active.sort(key=lambda p: -p["recentTransactionCount"])
    tight_pricing.sort(key=lambda p: p["psfCoefficientOfVariation"])

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_as_of": latest,
        "methodology": (
            "Real URA caveat transactions (completed sales), not live listings. "
            "below_trend: recent (last 3mo) median psf vs trailing 12mo median psf, "
            "min 3 recent transactions. most_active: highest recent transaction count. "
            "tight_pricing: lowest psf coefficient of variation over trailing 12mo, min 5 transactions."
        ),
        "categories": {
            "below_trend": below_trend[:10],
            "most_active": most_active[:10],
            "tight_pricing": tight_pricing[:10],
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=None)

    print(f"below_trend: {len(below_trend)}, most_active: {len(most_active)}, tight_pricing: {len(tight_pricing)}")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
