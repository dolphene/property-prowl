"""
Fetch from URA's own Data Service API (eservice.ura.gov.sg) -- the data not
available for free on data.gov.sg. Requires a URA AccessKey (register at
https://www.ura.gov.sg/maps/api/reg.html, ~1-2 business days for approval).

Set the URA_ACCESS_KEY environment variable (or GitHub Actions secret of
the same name) before running.

CONFIRMED WORKING (tested against a real key on 2026-09-18):

  PMI_Resi_Transaction   Caveat-level transactions: project, street, price,
                          floor range, area, contract date, sale type,
                          property type, district, tenure, market segment.
                          Paginated via &batch=1..4 (all 4 required for full
                          coverage -- confirmed range, batch=5 errors).
                          THIS IS THE PROPERTY-LEVEL DATA the original spec's
                          "Bucket B" needed for comparables -- not previously
                          available for free.
  PMI_Resi_Pipeline       Pipeline supply by project: units by type
                          (apartment/condo/landed), district, expected TOP
                          year, development status. No batching needed.
  PMI_Resi_Rental_Median  Per-project median rental PSF by quarter
                          (refPeriod), with 25th/75th percentile. No
                          batching needed.

NOT FOUND despite testing every plausible name (PMI_Resi_Vacancy,
PMI_Resi_Stock, PMI_Resi_Occupancy, PMI_Resi_Completion, and others --
all return "Invalid service"): a vacancy or stock-and-vacancy dataset.
Either it's under a name that wasn't guessed, or it isn't exposed via this
API. If you can see URA's own API reference while logged in with this key
(https://eservice.ura.gov.sg/maps/api/), check there for the real name and
add it to DATASET_ENDPOINTS below -- don't keep guessing blindly.

Two things about this API worth knowing if you extend this script:
  1. It sits behind an F5 bot-protection layer that returns an HTML "Site
     is not available" challenge page (not JSON) for requests without a
     browser-like User-Agent -- see COMMON_HEADERS below.
  2. Some large responses (PMI_Resi_Transaction batch=2/3) contain a stray
     non-UTF-8 byte somewhere in a project/street name. Decoded with
     errors="replace" rather than failing the whole fetch over one bad
     character.
"""
import gzip
import json
import os
import urllib.request
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

TOKEN_URL = "https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1"
DS_URL = "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1"

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
}

# name -> (service, list of extra query-param dicts; one fetch per dict, results concatenated)
DATASET_ENDPOINTS = {
    "transaction": ("PMI_Resi_Transaction", [{"batch": str(b)} for b in range(1, 5)]),
    "pipeline": ("PMI_Resi_Pipeline", [{}]),
    "rental_median": ("PMI_Resi_Rental_Median", [{}]),
    # "vacancy": (...)  -- TODO once the real service name is known, see docstring.
}


def read_json(resp) -> dict:
    raw = resp.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8", errors="replace"))


def get_daily_token(access_key: str) -> str:
    req = urllib.request.Request(TOKEN_URL, headers={"AccessKey": access_key, **COMMON_HEADERS})
    with urllib.request.urlopen(req) as resp:
        payload = read_json(resp)
    if payload.get("Status") != "Success":
        raise RuntimeError(f"Failed to get URA token: {payload}")
    return payload["Result"]


def fetch_service(service: str, params: dict, access_key: str, token: str) -> list:
    query = "&".join([f"service={service}"] + [f"{k}={v}" for k, v in params.items()])
    url = f"{DS_URL}?{query}"
    req = urllib.request.Request(url, headers={"AccessKey": access_key, "Token": token, **COMMON_HEADERS})
    with urllib.request.urlopen(req) as resp:
        payload = read_json(resp)
    if payload.get("Status") != "Success":
        raise RuntimeError(f"URA API error for {service} {params}: {payload}")
    return payload.get("Result", [])


def main() -> None:
    access_key = os.environ.get("URA_ACCESS_KEY")
    if not access_key:
        print("URA_ACCESS_KEY not set -- skipping (expected until the key is configured).")
        return

    token = get_daily_token(access_key)
    print("URA auth OK.")

    for name, (service, param_sets) in DATASET_ENDPOINTS.items():
        print(f"Fetching {name} ({service})...")
        records = []
        for params in param_sets:
            records.extend(fetch_service(service, params, access_key, token))
        out_path = RAW_DIR / f"{name}_ura_api.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(records, f)
        print(f"  saved {len(records)} project records -> {out_path}")


if __name__ == "__main__":
    main()
