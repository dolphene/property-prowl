"""
First-pass WATCH / STALKING / GET_READY / OPPORTUNITY classifier.

This is deliberately v1, calibrated against the ONE full historical
correction we have clean data for (2008-09 GFC), not invented. The
signature that actually distinguished the 2009-Q1 opportunity quarter from
the rest of the crash:

    price_all_yoy_pct   deeply negative (market genuinely correcting)
    price_all_4q_trend  still negative (decline hasn't reversed yet)
    txn_total_yoy_pct   has turned positive again (liquidity returning
                        while price is still falling -- buyers stepping
                        back in before the headline number recovers)

price_rent_divergence was tested as a threshold and rejected for v1: it
was just as negative during the 2007 boom (rents outrunning prices in a
euphoric market) as during real stress, so on its own it doesn't
discriminate opportunity from boom. Kept as a reported column for context,
not as a rule input. This needs revisiting once more corrections (not
just 2008-09) are in the sample.

v1 -> v2 fix: GET_READY originally used only price_all_yoy_pct and the
trailing 4-quarter trend, both of which lag a sharp turn -- 2009-Q3 was
misclassified GET_READY (yoy still -10.98%) even though the market had
already turned (QoQ +15.74% that same quarter, the start of the V-shaped
recovery). GET_READY now also requires the CURRENT quarter's QoQ to still
be non-positive, i.e. the market must still be actively falling quarter
over quarter, not just carrying a negative YoY base effect. This is the
kind of correction the "we calibrate against history, not assume" approach
is meant to catch.

v2 -> v3 rename: The Property Prowl brief defines four named states --
STALKING / WATCH / GET_READY / OPPORTUNITY -- with WATCH as the calm
default for ordinary/mixed conditions, and STALKING as MORE
attention-intensive than WATCH (the predator-behaviour arc: watch from a
distance -> actively stalk once something's forming -> get ready to
pounce -> pounce). That is the reverse of what the label "WATCH" suggested
in v2, where it was the pre-crash early-warning tier above the calm
default. No threshold logic changed -- this is a pure rename to fit that
arc, since it maps exactly onto the tiers we'd already validated:

    v2 label    ->  v3 label     (meaning, unchanged)
    NEUTRAL     ->  WATCH        calm/default, nothing notable
    WATCH       ->  STALKING     momentum decelerating / early warning
    GET_READY   ->  GET_READY    confirmed correction, still actively falling
    OPPORTUNITY ->  OPPORTUNITY  deep correction + liquidity turning

WATCH:        calm default -- normal market, including a correction that
              has visibly turned (QoQ back positive) but hasn't yet
              cleared the YoY base effect.
STALKING:     price momentum decelerating -- trend has dropped but yoy
              is still positive, or yoy has just turned mildly negative.
GET_READY:    yoy clearly negative, trend still worsening, AND this
              quarter's own QoQ is still <= 0 -- confirmed correction that
              is still actively falling, no sign of a floor yet.
OPPORTUNITY:  yoy deeply negative AND liquidity yoy has turned positive
              (or less negative than the prior quarter) -- the 2009-Q1
              signature.
"""
import csv
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "master_quarterly.csv"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "master_quarterly_signals.csv"

YOY_STALKING_THRESHOLD = 0.0   # yoy has crossed from positive momentum into softening
YOY_CORRECTION_THRESHOLD = -5.0    # confirmed correction territory
YOY_DEEP_THRESHOLD = -15.0     # deep correction -- matches 2009-Q1's -21%


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def classify(yoy, trend, qoq, txn_yoy, txn_yoy_prev):
    if yoy is None or trend is None:
        return ""

    if yoy <= YOY_DEEP_THRESHOLD and txn_yoy is not None and txn_yoy_prev is not None and txn_yoy > txn_yoy_prev and txn_yoy > 0:
        return "OPPORTUNITY"

    if yoy <= YOY_CORRECTION_THRESHOLD and trend < 0 and qoq is not None and qoq <= 0:
        return "GET_READY"

    if yoy <= YOY_STALKING_THRESHOLD or (trend is not None and trend < 0 and yoy < 10):
        return "STALKING"

    return "WATCH"


def main():
    with DATA_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    txn_yoy_series = [to_float(r["txn_total_yoy_pct"]) for r in rows]

    for i, r in enumerate(rows):
        yoy = to_float(r["price_all_yoy_pct"])
        trend = to_float(r["price_all_4q_trend_pct"])
        qoq = to_float(r["price_all_qoq_pct"])
        txn_yoy = txn_yoy_series[i]
        txn_yoy_prev = txn_yoy_series[i - 1] if i > 0 else None
        r["prowl_signal"] = classify(yoy, trend, qoq, txn_yoy, txn_yoy_prev)

    fieldnames = list(rows[0].keys())
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"quarter       yoy%     trend%   txnYoY%   signal")
    for r in rows:
        yoy = r["price_all_yoy_pct"] or ""
        trend = r["price_all_4q_trend_pct"] or ""
        txn = r["txn_total_yoy_pct"] or ""
        print(f"{r['quarter']:12}  {yoy:>7}  {trend:>7}  {txn:>8}   {r['prowl_signal']}")

    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
