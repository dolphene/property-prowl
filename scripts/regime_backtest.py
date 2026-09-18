"""
Summarise the master quarterly dataset across well-documented historical
market periods, so we can eyeball what each signal actually did during
known booms/corrections before inventing any WATCH/GET READY/OPPORTUNITY
thresholds. This is observation, not classification -- the periods below
are drawn from documented Singapore property-market history, not fitted.
"""
import csv
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "master_quarterly.csv"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "regime_backtest.csv"

PERIODS = [
    ("2006-Q1", "2007-Q4", "Pre-GFC boom"),
    ("2008-Q1", "2009-Q1", "GFC correction (peak to trough)"),
    ("2009-Q2", "2010-Q4", "V-shaped recovery"),
    ("2011-Q1", "2013-Q2", "Continued boom (pre-TDSR)"),
    ("2013-Q3", "2017-Q2", "Cooling-measures adjustment"),
    ("2017-Q3", "2019-Q4", "Recovery"),
    ("2020-Q1", "2020-Q2", "COVID shock"),
    ("2020-Q3", "2022-Q4", "Post-COVID surge"),
    ("2023-Q1", "2025-Q4", "Higher-rate moderation"),
    ("2026-Q1", "2026-Q2", "Current"),
]

METRICS = [
    "price_all_qoq_pct", "price_all_yoy_pct",
    "rent_nonlanded_qoq_pct", "rent_nonlanded_yoy_pct",
    "price_rent_divergence_yoy_pts", "rent_price_ratio_index",
    "txn_total_qoq_pct", "txn_total_yoy_pct",
    "dev_sales_new_total",
]


def quarter_key(q):
    y, n = q.split("-Q")
    return int(y), int(n)


def in_range(q, start, end):
    return quarter_key(start) <= quarter_key(q) <= quarter_key(end)


def avg(vals):
    vals = [v for v in vals if v not in (None, "")]
    if not vals:
        return None
    vals = [float(v) for v in vals]
    return round(sum(vals) / len(vals), 2)


def main():
    with DATA_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    summary_rows = []
    for start, end, label in PERIODS:
        period_rows = [r for r in rows if in_range(r["quarter"], start, end)]
        summary = {"period": f"{start} to {end}", "label": label, "n_quarters": len(period_rows)}
        for m in METRICS:
            summary[m] = avg([r[m] for r in period_rows])
        summary_rows.append(summary)

    fieldnames = ["period", "label", "n_quarters"] + METRICS
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    # also print a readable table to stdout
    print(f"{'Period':28} {'Label':28} {'PxYoY%':>8} {'RentYoY%':>9} {'Diverg':>7} {'TxnYoY%':>8} {'DevSales':>9}")
    for s in summary_rows:
        print(f"{s['period']:28} {s['label']:28} "
              f"{s['price_all_yoy_pct'] if s['price_all_yoy_pct'] is not None else '':>8} "
              f"{s['rent_nonlanded_yoy_pct'] if s['rent_nonlanded_yoy_pct'] is not None else '':>9} "
              f"{s['price_rent_divergence_yoy_pts'] if s['price_rent_divergence_yoy_pts'] is not None else '':>7} "
              f"{s['txn_total_yoy_pct'] if s['txn_total_yoy_pct'] is not None else '':>8} "
              f"{s['dev_sales_new_total'] if s['dev_sales_new_total'] is not None else '':>9}")

    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
