"""
Convert master_quarterly_signals.csv into a JS file the dashboard can load
via a plain <script src> tag (works when the page is opened directly from
disk -- fetch()/XHR are blocked by CORS under file://, but a same-origin
<script src="data.js"> is not).
"""
import csv
import json
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "data" / "processed" / "master_quarterly_signals.csv"
OUT = Path(__file__).resolve().parent.parent / "web" / "data.js"

NUMERIC_SUFFIXES = ("_pct", "_pts", "_index")
NUMERIC_EXACT = {
    "price_all", "price_landed", "price_nonlanded", "price_ccr", "price_rcr", "price_ocr",
    "rent_all", "rent_landed", "rent_nonlanded", "rent_ccr", "rent_rcr", "rent_ocr",
    "txn_new_sale_completed", "txn_new_sale_uncompleted", "txn_new_sale_total",
    "txn_resale", "txn_subsale", "txn_total",
    "dev_sales_completed_stock", "dev_sales_new_ccr", "dev_sales_new_rcr", "dev_sales_new_ocr", "dev_sales_new_total",
}


def to_value(key, raw):
    if raw == "" or raw is None:
        return None
    if key.endswith(NUMERIC_SUFFIXES) or key in NUMERIC_EXACT:
        try:
            return float(raw)
        except ValueError:
            return None
    return raw


def main():
    with SRC.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    records = [{k: to_value(k, v) for k, v in row.items()} for row in rows]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        f.write("const PROWL_DATA = ")
        json.dump(records, f, indent=None)
        f.write(";\n")

    print(f"Wrote {len(records)} quarters -> {OUT}")


if __name__ == "__main__":
    main()
