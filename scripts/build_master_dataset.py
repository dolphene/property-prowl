"""
Merge the raw data.gov.sg/URA CSVs into one clean quarterly master table
(2006-Q1 onward) and compute the derived signals from the Prowl spec:
QoQ, YoY, 4-quarter trend, peak-to-current, and price/rent divergence.

Pure standard library (no pandas) -- this machine's Application Control
policy blocks pandas' native DLL, so everything here is plain csv/dict code.
"""
import csv
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_QUARTER = "2006-Q1"


def read_csv(name: str) -> list[dict]:
    path = RAW_DIR / f"{name}.csv"
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def quarter_key(q: str) -> tuple[int, int]:
    year, qtr = q.split("-Q")
    return int(year), int(qtr)


def all_quarters_from(start: str, end: str) -> list[str]:
    (sy, sq), (ey, eq) = quarter_key(start), quarter_key(end)
    quarters = []
    y, q = sy, sq
    while (y, q) <= (ey, eq):
        quarters.append(f"{y}-Q{q}")
        q += 1
        if q > 4:
            q = 1
            y += 1
    return quarters


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---- load raw series into {quarter: value} maps -----------------------

def load_price_index_by_type():
    rows = read_csv("price_index_by_type")
    out = {"all": {}, "landed": {}, "nonlanded": {}}
    key_map = {"All Residential": "all", "Landed": "landed", "Non-Landed": "nonlanded"}
    for r in rows:
        k = key_map.get(r["property_type"])
        if k:
            out[k][r["quarter"]] = to_float(r["index"])
    return out


def load_price_index_by_locality():
    rows = read_csv("price_index_by_locality")
    out = {"ccr": {}, "rcr": {}, "ocr": {}}
    key_map = {
        "Core Central Region": "ccr",
        "Rest of Central Region": "rcr",
        "Outside Central Region": "ocr",
    }
    for r in rows:
        k = key_map.get(r["market_segment"])
        if k:
            out[k][r["quarter"]] = to_float(r["price_index"])
    return out


def load_rental_index_by_type():
    rows = read_csv("rental_index_by_type")
    out = {"all": {}, "landed": {}, "nonlanded": {}, "ccr": {}, "rcr": {}, "ocr": {}}
    locality_key = {
        "Core Central Region": "ccr",
        "Rest of Central Region": "rcr",
        "Outside Central Region": "ocr",
    }
    for r in rows:
        q = r["quarter"]
        if r["locality"] == "Whole Island":
            if r["property_type"] == "All Residential":
                out["all"][q] = to_float(r["index"])
            elif r["property_type"] == "Landed":
                out["landed"][q] = to_float(r["index"])
            elif r["property_type"] == "Non-Landed":
                out["nonlanded"][q] = to_float(r["index"])
        elif r["property_type"] == "Non-Landed" and r["locality"] in locality_key:
            out[locality_key[r["locality"]]][q] = to_float(r["index"])
    return out


def load_transactions_by_sale_type():
    rows = read_csv("transactions_by_sale_type")
    out = {"new_sale_completed": {}, "new_sale_uncompleted": {}, "resale": {}, "subsale": {}}
    for r in rows:
        q, units = r["quarter"], to_float(r["units"]) or 0.0
        if r["type_of_sale"] == "New Sale" and r["sale_status"] == "Completed":
            out["new_sale_completed"][q] = units
        elif r["type_of_sale"] == "New Sale" and r["sale_status"] == "Uncompleted":
            out["new_sale_uncompleted"][q] = units
        elif r["type_of_sale"] == "Resale":
            out["resale"][q] = units
        elif r["type_of_sale"] == "Sub Sale":
            out["subsale"][q] = units
    return out


def load_completed_units_sold():
    rows = read_csv("completed_units_sold")
    out = {}
    for r in rows:
        out[r["quarter"]] = to_float(r["units"]) or 0.0
    return out


def load_uncompleted_units_sold():
    rows = read_csv("uncompleted_units_sold")
    out = {"ccr": {}, "rcr": {}, "ocr": {}}
    key_map = {
        "Core Central Region": "ccr",
        "Rest of Central Region": "rcr",
        "Outside Central Region": "ocr",
    }
    for r in rows:
        k = key_map.get(r["market_segment"])
        if k:
            out[k][r["quarter"]] = to_float(r["units"]) or 0.0
    return out


# ---- derived signal helpers --------------------------------------------

def qoq_pct(series: list, i: int):
    if i < 1 or series[i] is None or series[i - 1] in (None, 0):
        return None
    return round((series[i] - series[i - 1]) / series[i - 1] * 100, 2)


def yoy_pct(series: list, i: int):
    if i < 4 or series[i] is None or series[i - 4] in (None, 0):
        return None
    return round((series[i] - series[i - 4]) / series[i - 4] * 100, 2)


def trend_4q(qoq_series: list, i: int):
    """Average QoQ % over the trailing 4 quarters -- a simple momentum trend."""
    window = qoq_series[max(0, i - 3): i + 1]
    vals = [v for v in window if v is not None]
    if len(vals) < 2:
        return None
    return round(sum(vals) / len(vals), 2)


def peak_to_current_pct(series: list, i: int):
    """% change from the highest value seen so far (within this dataset) to current."""
    history = [v for v in series[: i + 1] if v is not None]
    if not history or series[i] is None:
        return None
    peak = max(history)
    if peak == 0:
        return None
    return round((series[i] - peak) / peak * 100, 2)


def main():
    price_type = load_price_index_by_type()
    price_loc = load_price_index_by_locality()
    rent = load_rental_index_by_type()
    txn = load_transactions_by_sale_type()
    completed_sold = load_completed_units_sold()
    uncompleted_sold = load_uncompleted_units_sold()

    # figure out the latest quarter actually present across sources
    all_quarters = set()
    for src in [price_type["all"], price_loc["ccr"], rent["all"], txn["resale"]]:
        all_quarters.update(src.keys())
    latest = max(all_quarters, key=quarter_key)

    quarters = all_quarters_from(START_QUARTER, latest)

    def series_for(d: dict) -> list:
        return [d.get(q) for q in quarters]

    price_all = series_for(price_type["all"])
    price_landed = series_for(price_type["landed"])
    price_nonlanded = series_for(price_type["nonlanded"])
    price_ccr = series_for(price_loc["ccr"])
    price_rcr = series_for(price_loc["rcr"])
    price_ocr = series_for(price_loc["ocr"])

    rent_all = series_for(rent["all"])
    rent_landed = series_for(rent["landed"])
    rent_nonlanded = series_for(rent["nonlanded"])
    rent_ccr = series_for(rent["ccr"])
    rent_rcr = series_for(rent["rcr"])
    rent_ocr = series_for(rent["ocr"])

    txn_new_completed = series_for(txn["new_sale_completed"])
    txn_new_uncompleted = series_for(txn["new_sale_uncompleted"])
    txn_resale = series_for(txn["resale"])
    txn_subsale = series_for(txn["subsale"])

    dev_sales_completed_stock = series_for(completed_sold)
    dev_sales_ccr = series_for(uncompleted_sold["ccr"])
    dev_sales_rcr = series_for(uncompleted_sold["rcr"])
    dev_sales_ocr = series_for(uncompleted_sold["ocr"])

    def total_or_none(*vals):
        present = [v for v in vals if v is not None]
        return round(sum(present), 1) if present else None

    txn_new_total = [total_or_none(a, b) for a, b in zip(txn_new_completed, txn_new_uncompleted)]
    txn_total = [
        total_or_none(a, b, c, d)
        for a, b, c, d in zip(txn_new_completed, txn_new_uncompleted, txn_resale, txn_subsale)
    ]
    dev_sales_new_total = [
        total_or_none(a, b, c) for a, b, c in zip(dev_sales_ccr, dev_sales_rcr, dev_sales_ocr)
    ]

    price_all_qoq = [qoq_pct(price_all, i) for i in range(len(quarters))]
    price_all_yoy = [yoy_pct(price_all, i) for i in range(len(quarters))]
    price_all_trend = [trend_4q(price_all_qoq, i) for i in range(len(quarters))]
    price_all_peak = [peak_to_current_pct(price_all, i) for i in range(len(quarters))]

    price_ccr_qoq = [qoq_pct(price_ccr, i) for i in range(len(quarters))]
    price_ccr_yoy = [yoy_pct(price_ccr, i) for i in range(len(quarters))]
    price_rcr_qoq = [qoq_pct(price_rcr, i) for i in range(len(quarters))]
    price_rcr_yoy = [yoy_pct(price_rcr, i) for i in range(len(quarters))]
    price_ocr_qoq = [qoq_pct(price_ocr, i) for i in range(len(quarters))]
    price_ocr_yoy = [yoy_pct(price_ocr, i) for i in range(len(quarters))]

    rent_all_qoq = [qoq_pct(rent_all, i) for i in range(len(quarters))]
    rent_all_yoy = [yoy_pct(rent_all, i) for i in range(len(quarters))]
    rent_nonlanded_qoq = [qoq_pct(rent_nonlanded, i) for i in range(len(quarters))]

    txn_total_qoq = [qoq_pct(txn_total, i) for i in range(len(quarters))]
    txn_total_yoy = [yoy_pct(txn_total, i) for i in range(len(quarters))]

    # price/rent divergence: YoY price momentum minus YoY rent momentum.
    # Positive = prices outrunning rents (yields compressing); negative = rents
    # holding up while prices fall (yields improving) -- the pattern flagged
    # in the spec as worth watching.
    #
    # Uses the Non-Landed pair rather than "All Residential": data.gov.sg's
    # rental_index_by_type mirror stopped publishing the combined "All
    # Residential" rental series after 2021-Q3 (Landed and Non-Landed are
    # still published separately), so "all" would leave 2021-Q4 onward blank.
    # Non-Landed is populated across the full 2006-2026 window on both sides.
    price_nonlanded_yoy = [yoy_pct(price_nonlanded, i) for i in range(len(quarters))]
    rent_nonlanded_yoy = [yoy_pct(rent_nonlanded, i) for i in range(len(quarters))]
    price_rent_divergence = [
        round(p - r, 2) if p is not None and r is not None else None
        for p, r in zip(price_nonlanded_yoy, rent_nonlanded_yoy)
    ]
    # rent/price ratio index: both series share the same 2009-Q1=100 base,
    # so this ratio is a valid *relative* yield-trend proxy, not an actual
    # dollar yield (that needs bucket B transaction-level data).
    rent_price_ratio = [
        round(r / p * 100, 2) if p not in (None, 0) and r is not None else None
        for p, r in zip(price_nonlanded, rent_nonlanded)
    ]

    fieldnames = [
        "quarter",
        "price_all", "price_all_qoq_pct", "price_all_yoy_pct", "price_all_4q_trend_pct", "price_all_peak_to_current_pct",
        "price_landed", "price_nonlanded",
        "price_ccr", "price_ccr_qoq_pct", "price_ccr_yoy_pct",
        "price_rcr", "price_rcr_qoq_pct", "price_rcr_yoy_pct",
        "price_ocr", "price_ocr_qoq_pct", "price_ocr_yoy_pct",
        "rent_all", "rent_all_qoq_pct", "rent_all_yoy_pct",
        "rent_landed", "rent_nonlanded", "rent_nonlanded_qoq_pct", "rent_nonlanded_yoy_pct",
        "rent_ccr", "rent_rcr", "rent_ocr",
        "price_rent_divergence_yoy_pts", "rent_price_ratio_index",
        "txn_new_sale_completed", "txn_new_sale_uncompleted", "txn_new_sale_total",
        "txn_resale", "txn_subsale", "txn_total", "txn_total_qoq_pct", "txn_total_yoy_pct",
        "dev_sales_completed_stock", "dev_sales_new_ccr", "dev_sales_new_rcr", "dev_sales_new_ocr", "dev_sales_new_total",
    ]

    out_path = OUT_DIR / "master_quarterly.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for i, q in enumerate(quarters):
            writer.writerow([
                q,
                price_all[i], price_all_qoq[i], price_all_yoy[i], price_all_trend[i], price_all_peak[i],
                price_landed[i], price_nonlanded[i],
                price_ccr[i], price_ccr_qoq[i], price_ccr_yoy[i],
                price_rcr[i], price_rcr_qoq[i], price_rcr_yoy[i],
                price_ocr[i], price_ocr_qoq[i], price_ocr_yoy[i],
                rent_all[i], rent_all_qoq[i], rent_all_yoy[i],
                rent_landed[i], rent_nonlanded[i], rent_nonlanded_qoq[i], rent_nonlanded_yoy[i],
                rent_ccr[i], rent_rcr[i], rent_ocr[i],
                price_rent_divergence[i], rent_price_ratio[i],
                txn_new_completed[i], txn_new_uncompleted[i], txn_new_total[i],
                txn_resale[i], txn_subsale[i], txn_total[i], txn_total_qoq[i], txn_total_yoy[i],
                dev_sales_completed_stock[i], dev_sales_ccr[i], dev_sales_rcr[i], dev_sales_ocr[i], dev_sales_new_total[i],
            ])

    print(f"Wrote {len(quarters)} quarters ({quarters[0]} to {quarters[-1]}) -> {out_path}")


if __name__ == "__main__":
    main()
