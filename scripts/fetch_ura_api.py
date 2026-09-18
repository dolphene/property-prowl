"""
Fetch vacancy and pipeline-supply data from URA's own Data Service API
(eservice.ura.gov.sg) -- the two series that aren't available for free on
data.gov.sg. Requires a URA AccessKey (register at
https://www.ura.gov.sg/maps/api/reg.html, ~1-2 business days for approval).

Set the URA_ACCESS_KEY environment variable (or a GitHub Actions secret of
the same name) before running.

STATUS: the auth flow below (daily token generation) is implemented per
URA's documented API. The actual dataset endpoint paths for vacancy and
pipeline supply are NOT filled in yet -- URA's API reference page is
JS-rendered and gated behind having a real key, so I could not verify the
exact paths/response shape without one. Once you have a key:

  1. Log into https://eservice.ura.gov.sg/maps/api/ with your AccessKey
     and find the exact endpoint names for:
     - "Vacancy" / "Stock and Vacancy of Completed Private Residential Units"
     - "Private Residential Properties in the Pipeline by Development Status"
  2. Fill in DATASET_ENDPOINTS below with the real paths.
  3. Run this script -- it will save raw JSON to data/raw/, matching the
     pattern of fetch_datagovsg.py, then re-run build_master_dataset.py to
     fold them into the master table.

Do NOT guess at the endpoint paths -- get them from the real docs once
logged in, so this doesn't silently fetch the wrong thing.
"""
import json
import os
import urllib.request
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

TOKEN_URL = "https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1"

# TODO: fill in once confirmed against the real API reference (see docstring).
DATASET_ENDPOINTS = {
    # "vacancy": "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1?service=<TODO>",
    # "pipeline_supply": "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1?service=<TODO>",
}


def get_daily_token(access_key: str) -> str:
    req = urllib.request.Request(TOKEN_URL, headers={"AccessKey": access_key})
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read())
    if payload.get("Status") != "Success":
        raise RuntimeError(f"Failed to get URA token: {payload}")
    return payload["Result"]


def fetch_dataset(name: str, url: str, access_key: str, token: str) -> None:
    req = urllib.request.Request(url, headers={"AccessKey": access_key, "Token": token})
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read())
    out_path = RAW_DIR / f"{name}_ura_api.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f)
    print(f"  saved -> {out_path}")


def main() -> None:
    access_key = os.environ.get("URA_ACCESS_KEY")
    if not access_key:
        print("URA_ACCESS_KEY not set -- skipping (this is expected until the key arrives).")
        return

    if not DATASET_ENDPOINTS:
        print("Auth works, but DATASET_ENDPOINTS is empty -- fill in the real endpoint "
              "paths once you can see URA's API reference (see this script's docstring).")
        return

    token = get_daily_token(access_key)
    for name, url in DATASET_ENDPOINTS.items():
        print(f"Fetching {name}...")
        fetch_dataset(name, url, access_key, token)


if __name__ == "__main__":
    main()
