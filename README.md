# The Property Prowl — data layer

Historical calibration dataset for Singapore private residential property,
2006–2026, built before any dashboard/UI work (Lovable spec comes last).

## Live, automated (as of 2026-09-18)

Public repo: https://github.com/dolphene/property-prowl. A scheduled GitHub Actions workflow (`.github/workflows/refresh-data.yml`) runs the full pipeline twice a week (Mon & Thu 22:00 UTC) and publishes the result to GitHub Pages at **https://dolphene.github.io/property-prowl/master_quarterly_signals.json** — that's the live public data URL, consumed by `property-prowl-site`'s own workflow. Trigger manually with `gh workflow run refresh-data.yml -R dolphene/property-prowl`.

**Update 2026-09-18: URA key added and tested.** `URA_ACCESS_KEY` is set as a GitHub secret. Three real endpoints confirmed working against the live key:

- `PMI_Resi_Transaction` (batched, 4 pages) — **caveat-level transactions**: project, street, price, floor range, area, contract date, sale type, property type, district, tenure, market segment. This is the property-level data the original spec's "Bucket B" needed for comparables — previously thought unavailable for free.
- `PMI_Resi_Pipeline` — pipeline supply by project (units by type, district, expected TOP year, development status).
- `PMI_Resi_Rental_Median` — per-project median rental PSF by quarter, with 25th/75th percentile.

Raw output saved to `data/raw/{transaction,pipeline,rental_median}_ura_api.json` (transaction file is ~31MB — every project's transaction records). **Not yet processed into the master quarterly table or the site's signals/comparables** — that's a real design task (how to aggregate pipeline data into a "Supply Pressure" signal, how to build the property comparables engine from raw transactions) still pending user direction, not silently built.

**Vacancy was NOT found** despite testing every plausible service name (`PMI_Resi_Vacancy`, `PMI_Resi_Stock`, `PMI_Resi_Occupancy`, `PMI_Resi_Completion`, and more — all return `"Invalid service."`). Either it's under a name not yet guessed, or it isn't exposed via this API at all. See `scripts/fetch_ura_api.py`'s docstring for how to find the real name if you can see URA's own API reference while logged in.

## Pipeline

1. `scripts/fetch_datagovsg.py` — pulls raw series from data.gov.sg's
   datastore API (mirrors of URA data; no API key required). Saves one CSV
   per dataset to `data/raw/`.
2. `scripts/build_master_dataset.py` — merges the raw CSVs into one quarterly
   table, `data/processed/master_quarterly.csv`, 2006-Q1 to latest, and
   computes derived signals (QoQ, YoY, 4-quarter trend, peak-to-current,
   price/rent divergence).

Both scripts are pure standard-library Python — pandas is blocked by this
machine's Application Control policy (native DLL load failure), so no
third-party dependency is required to reproduce the dataset.

## Data dictionary

| Column | Source dataset | Meaning |
|---|---|---|
| `price_all` / `price_landed` / `price_nonlanded` | `price_index_by_type` (`d_97f8a2e995022d311c6c68cfda6d034c`) | URA private residential price index, base 2009-Q1=100 |
| `price_ccr` / `price_rcr` / `price_ocr` | `price_index_by_locality` (`d_f65e490a8ad430f60a9a3d9df2bff2a0`) | Non-landed price index by market segment (Core/Rest/Outside Central Region) |
| `rent_all` / `rent_landed` / `rent_nonlanded` | `rental_index_by_type` (`d_8e4c50283fb7052a391dfb746a05c853`) | Rental index, base 2009-Q1=100, whole island. **`rent_all` is blank from 2021-Q4 onward** — data.gov.sg's mirror discontinued the combined "All Residential" series; `rent_landed`/`rent_nonlanded` are still populated for the full window |
| `rent_ccr` / `rent_rcr` / `rent_ocr` | same dataset | Non-landed rental index by market segment |
| `txn_new_sale_completed` / `_uncompleted` | `transactions_by_sale_type` (`d_7c69c943d5f0d89d6a9a773d2b51f337`) | New Sale transactions, split by whether the unit was completed at time of sale |
| `txn_resale` / `txn_subsale` | same | Resale / Sub Sale transaction volumes |
| `txn_total` | derived | Sum of all four transaction categories — the liquidity signal |
| `dev_sales_completed_stock` | `completed_units_sold` (`d_a283de8cb3b4e80a228bf5f5e0bc4449`) | Completed private residential units sold in the quarter |
| `dev_sales_new_ccr/rcr/ocr/total` | `uncompleted_units_sold` (`d_e1c5b0df62729e69c82716355ef295ba`) | Uncompleted (new sale, developer) units sold by market segment |

Derived columns:

- `*_qoq_pct`, `*_yoy_pct` — simple percentage change quarter-on-quarter / year-on-year.
- `price_all_4q_trend_pct` — average of the trailing 4 quarters' QoQ price change (momentum direction, per the ChatGPT spec's "sequence not a single number" approach).
- `price_all_peak_to_current_pct` — % below the highest price index value seen up to that quarter (only meaningful from 2006 onward, since that's our window's own peak).
- `price_rent_divergence_yoy_pts` — price YoY% minus rent YoY%, computed on the Non-Landed price/rent pair (fully populated for the full window, unlike `_all`). Positive = prices outrunning rents (yields compressing); negative = rents holding up while prices soften (yields improving).
- `rent_price_ratio_index` — rent index ÷ price index × 100. Both series share the 2009-Q1=100 base, so this is a valid **relative yield-trend proxy**, not an actual dollar yield. Actual gross yield requires transaction-level $ data (the property-level "Bucket B" from the original spec — not built yet).

## Known gaps (not yet in the dataset)

- **Vacancy rate** — the only free dataset on data.gov.sg has just 2 years (2013–2014), annual. Not usable for a 2006–2026 series.
- **Pipeline supply / completions** — data.gov.sg's mirror is stale, stopping at 2018-Q3.

Both require URA's own eService Data API (AccessKey via `https://www.ura.gov.sg/maps/api/reg.html`, 1–2 business day approval). Once the key is available, add `scripts/fetch_ura_api.py` to pull these two series and extend the master table — the rest of the schema and derived-signal logic doesn't need to change.

## Validation

2009-Q1 computed QoQ price change: **-14.09%**. URA's officially reported figure for 1Q2009: **-14.1%**. Confirms the merge/derivation logic is correct.

## Signal thresholds (v3, draft)

`scripts/regime_backtest.py` averages every signal across 10 documented historical periods (`data/processed/regime_backtest.csv`) — used to sanity-check what real booms/corrections actually looked like before setting any thresholds.

`scripts/signal_thresholds.py` then produces `data/processed/master_quarterly_signals.csv` — a per-quarter `prowl_signal` column: `WATCH` / `STALKING` / `GET_READY` / `OPPORTUNITY`.

This is calibrated against the one full historical correction in the dataset (2008–09 GFC) — not invented. Full reasoning and rule definitions are in the script's docstring. Summary:

- **OPPORTUNITY**: YoY price deeply negative (≤ -15%) AND liquidity YoY has turned positive/improving — the 2009-Q1/Q2 signature (price still falling, but transaction volume already recovering).
- **GET_READY**: YoY negative (≤ -5%), trailing trend still negative, AND this quarter's own QoQ is still ≤ 0 (still actively falling, not just carrying a negative YoY base effect).
- **STALKING**: momentum decelerating or YoY has turned mildly negative — the pre-crash/early-warning tier.
- **WATCH**: the calm default — everything else, including a correction that has already turned QoQ-positive but hasn't cleared its YoY base yet.

v1 → v2 fix: the original GET_READY rule (YoY + trailing trend only) misclassified 2009-Q3 as GET_READY even though the market had already turned (QoQ +15.7% that quarter) — both YoY and the 4-quarter trailing trend lag a sharp V-shaped turn. Adding a same-quarter QoQ ≤ 0 requirement fixed the sequencing; the ladder now reads cleanly `WATCH → STALKING (2008-Q4) → OPPORTUNITY (2009-Q1, Q2) → STALKING (2009-Q3) → WATCH`.

v2 → v3 rename: The Property Prowl brief (second HTML build) defines the state names WATCH / STALKING / GET_READY / OPPORTUNITY, with WATCH as the calm default and STALKING deliberately MORE attention-intensive than WATCH (predator arc: watch from a distance → stalk once something's forming → get ready → pounce). v2's `NEUTRAL` and `WATCH` were renamed to `WATCH` and `STALKING` respectively to fit; no threshold logic changed.

**Known limitation**: calibrated against a single correction (2008–09). `price_rent_divergence` was tested as a threshold and rejected — it was just as negative during the 2007 boom as during real stress, so it doesn't discriminate on its own. It's still reported as context. Thresholds should be revisited once the URA supply/vacancy series are added and once we've looked at whether 2013–17's WATCH classification (a genuine multi-year soft patch, not a crash) is the right treatment or needs its own tier.

## Next step

Property-level data (Bucket B: per-transaction price/PSF/tenure/floor) or the Lovable spec — pending user direction. Market regime tagging (Boom / Cooling / Correction / Recovery / Stress) as a separate, broader classification is still open, distinct from the WATCH/GET_READY/OPPORTUNITY buy-signal ladder above.
