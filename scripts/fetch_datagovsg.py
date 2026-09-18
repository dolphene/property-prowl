"""
Fetch URA property-market series that are freely available (no key required)
via the data.gov.sg datastore API, and save each as raw CSV.

Covers: price index (by type + by locality), rental index (by type + locality),
transactions (by sale type), and developer sales (completed + uncompleted units sold).

Pipeline supply and vacancy are NOT covered here -- data.gov.sg's mirrors of
those series are stale/thin. See fetch_ura_api.py (added once a URA AccessKey
is available) for those.
"""
import csv
import time
import urllib.request
import json
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://data.gov.sg/api/action/datastore_search"

DATASETS = {
    "price_index_by_type": "d_97f8a2e995022d311c6c68cfda6d034c",
    "price_index_by_locality": "d_f65e490a8ad430f60a9a3d9df2bff2a0",
    "rental_index_by_type": "d_8e4c50283fb7052a391dfb746a05c853",
    "transactions_by_sale_type": "d_7c69c943d5f0d89d6a9a773d2b51f337",
    "completed_units_sold": "d_a283de8cb3b4e80a228bf5f5e0bc4449",
    "uncompleted_units_sold": "d_e1c5b0df62729e69c82716355ef295ba",
}


def fetch_page(url: str, max_retries: int = 6) -> dict:
    delay = 5
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(url) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                print(f"    rate limited, retrying in {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise


def fetch_all_records(resource_id: str, page_size: int = 500) -> list[dict]:
    records = []
    offset = 0
    while True:
        url = f"{BASE_URL}?resource_id={resource_id}&limit={page_size}&offset={offset}"
        payload = fetch_page(url)
        if not payload.get("success"):
            raise RuntimeError(f"API error for {resource_id}: {payload}")
        result = payload["result"]
        batch = result["records"]
        records.extend(batch)
        total = result["total"]
        offset += page_size
        if offset >= total:
            break
        time.sleep(5)  # be polite to the unauthenticated rate limit
    return records


def save_csv(name: str, records: list[dict]) -> None:
    if not records:
        print(f"  no records for {name}, skipping")
        return
    fieldnames = [k for k in records[0].keys() if k != "_id"]
    out_path = RAW_DIR / f"{name}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow({k: row[k] for k in fieldnames})
    print(f"  saved {len(records)} rows -> {out_path}")


def main() -> None:
    for name, resource_id in DATASETS.items():
        out_path = RAW_DIR / f"{name}.csv"
        if out_path.exists():
            print(f"Skipping {name}, already fetched at {out_path}")
            continue
        print(f"Fetching {name} ({resource_id})...")
        records = fetch_all_records(resource_id)
        save_csv(name, records)
        time.sleep(5)


if __name__ == "__main__":
    main()
