"""
Fetch real SORA (Singapore Overnight Rate Average) data -- the real
Financing signal, replacing the illustrative placeholder. Source: MAS's
"Current Banks Interest Rates" dataset, mirrored on data.gov.sg (same
free, no-key, no-bot-protection API used throughout this project --
unlike mas.gov.sg's own site, which blocks automated fetches).

Uses the 3-Month Compounded SORA series specifically, since that's the
benchmark most floating-rate Singapore mortgages are actually priced
against (not the raw overnight SORA, which is too volatile day-to-day to
be a useful "financing conditions" read).
"""
import json
from pathlib import Path

import urllib.request

RESOURCE_ID = "d_5fe5a4bb4a1ecc4d8a56a095832e2b24"
SERIES_NAME = "Compounded Singapore Overnight Rate Average (SORA) - 3 Month"
OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "sora_snapshot.json"


def main() -> None:
    url = f"https://data.gov.sg/api/action/datastore_search?resource_id={RESOURCE_ID}&limit=10"
    with urllib.request.urlopen(url) as resp:
        payload = json.loads(resp.read())
    if not payload.get("success"):
        raise RuntimeError(f"API error: {payload}")

    row = next((r for r in payload["result"]["records"] if r.get("DataSeries") == SERIES_NAME), None)
    if row is None:
        raise RuntimeError(f"Series '{SERIES_NAME}' not found in dataset")

    # Columns are like "2026Jul", "2026Jun", ... -- find the most recent
    # populated ones in chronological order (dataset columns run newest
    # first).
    month_cols = [k for k in row if k != "DataSeries" and k != "_id"]

    def col_sort_key(col: str) -> tuple[int, int]:
        months = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        }
        year, mon = int(col[:4]), months[col[4:]]
        return (year, mon)

    month_cols.sort(key=col_sort_key, reverse=True)

    series = []
    for col in month_cols:
        val = row.get(col)
        if val in (None, "", "na"):
            continue
        try:
            series.append({"month": col, "sora3mCompounded": float(val)})
        except ValueError:
            continue
        if len(series) >= 13:  # latest + trailing 12 months, enough for a YoY read
            break

    out = {"seriesName": SERIES_NAME, "monthly": series}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=None)

    print(f"Latest: {series[0]['month']} = {series[0]['sora3mCompounded']}%")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
