"""
Flatten URA's nested PMI_Resi_Transaction JSON (one record per project, each
holding a nested list of transactions) into one row per transaction -- the
shape the comparables engine actually needs to query.

No bedroom count is present anywhere in URA's transaction data -- only
floor area. The brief's Tier 1-4 hierarchy calls for "same bedroom" as a
match criterion; since that field doesn't exist, size similarity (with
tolerance bands, per the brief's own ±10/15/20% guidance) is used as the
practical substitute. This is a real data limitation, not an oversight --
documented here and in the comparables engine itself.
"""
import json
from pathlib import Path

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "transaction_ura_api.json"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "transactions_flat.json"
OUT_PATH_FULL = Path(__file__).resolve().parent.parent / "data" / "processed" / "transactions_flat_full.json"

SALE_TYPE = {"1": "New Sale", "2": "Sub Sale", "3": "Resale"}

# The full flattened dataset is ~46MB / 130k+ rows -- too large to ship to a
# browser for a client-side static-site prototype (this is exactly the kind
# of data a real backend/database should serve, queried server-side, once
# this becomes a Lovable+Supabase app). For now, filter to the districts
# covering the default watchlist areas (Serangoon/Kovan/Bartley=19,
# Bishan/Thomson=20, Toa Payoh=12, Potong Pasir/MacPherson=13,
# Paya Lebar=14, Katong=15) so the prototype's comparables demo is
# realistic and fast. transactions_flat_full.json (all districts) is still
# written for reference/future use.
DEFAULT_WATCHLIST_DISTRICTS = {"12", "13", "14", "15", "19", "20"}


def parse_contract_date(s: str) -> str:
    """'0522' -> '2022-05'. URA uses MMYY."""
    if not s or len(s) != 4:
        return ""
    mm, yy = s[:2], s[2:]
    year = 2000 + int(yy)
    return f"{year:04d}-{mm}"


def main() -> None:
    with RAW_PATH.open(encoding="utf-8") as f:
        projects = json.load(f)

    rows = []
    for p in projects:
        base = {
            "project": p.get("project"),
            "street": p.get("street"),
            "marketSegment": p.get("marketSegment"),
        }
        for t in p.get("transaction", []):
            try:
                area = float(t.get("area") or 0)
                price = float(t.get("price") or 0)
            except ValueError:
                continue
            if area <= 0 or price <= 0:
                continue
            rows.append({
                **base,
                "district": t.get("district"),
                "propertyType": t.get("propertyType"),
                "typeOfArea": t.get("typeOfArea"),
                "tenure": t.get("tenure"),
                "floorRange": t.get("floorRange"),
                "area_sqft": round(area, 1),
                "price": price,
                "psf": round(price / area, 2),
                "contractDate": parse_contract_date(t.get("contractDate", "")),
                "saleType": SALE_TYPE.get(t.get("typeOfSale"), t.get("typeOfSale")),
                "noOfUnits": t.get("noOfUnits"),
            })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH_FULL.open("w", encoding="utf-8") as f:
        json.dump(rows, f)
    print(f"Flattened {len(projects)} projects -> {len(rows)} individual transactions (all districts)")
    print(f"Wrote {OUT_PATH_FULL} ({OUT_PATH_FULL.stat().st_size / 1e6:.1f} MB)")

    watchlist_rows = [r for r in rows if r["district"] in DEFAULT_WATCHLIST_DISTRICTS]

    # The brief's own comparables tiers never look back further than 24
    # months (Tier 2/3 cutoff), so nothing older is ever used -- trimming
    # it isn't an arbitrary size hack, it matches the spec.
    latest = max((r["contractDate"] for r in watchlist_rows if r["contractDate"]), default="")
    if latest:
        cutoff_year, cutoff_month = int(latest[:4]), int(latest[5:7])
        cutoff_month -= 24
        while cutoff_month <= 0:
            cutoff_month += 12
            cutoff_year -= 1
        cutoff = f"{cutoff_year:04d}-{cutoff_month:02d}"
        watchlist_rows = [r for r in watchlist_rows if r["contractDate"] >= cutoff]

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(watchlist_rows, f)
    print(f"Filtered to default-watchlist districts + last 24 months -> {len(watchlist_rows)} transactions")
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
