"""Benchmark the AI service on labeled images (Section 10.4).

1. Put images in a folder, e.g. benchmark/
2. Make benchmark/labels.csv with columns:  filename,plate
3. Start the AI service, then run:
       python tools/evaluate.py benchmark
Writes results/evaluation_results.csv and prints a summary.
"""
import argparse
import csv
import os
import re
import statistics
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def norm(t):
    return re.sub(r"[^A-Z0-9]", "", (t or "").upper())


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def pct(values, p):
    values = sorted(values)
    if not values:
        return 0
    k = max(0, min(len(values) - 1, round(p / 100 * len(values) + 0.5) - 1))
    return values[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--ai-url", default=os.getenv("AI_URL", "http://127.0.0.1:8001"))
    ap.add_argument("--conf-min", type=float, default=float(os.getenv("CONF_MIN", "0.5")))
    args = ap.parse_args()

    folder = Path(args.folder)
    labels = folder / "labels.csv"
    if not labels.exists():
        sys.exit(f"Missing {labels} (columns: filename,plate)")

    rows, latencies, detected, exact, cer_sum = [], [], 0, 0, 0.0
    accepted_wrong = 0
    with open(labels, newline="", encoding="utf-8") as f:
        items = list(csv.DictReader(f))

    for item in items:
        truth = norm(item["plate"])
        data = (folder / item["filename"]).read_bytes()
        t0 = time.perf_counter()
        r = httpx.post(f"{args.ai_url}/v1/read-plate/raw", content=data, timeout=60,
                       headers={"Content-Type": "image/jpeg",
                                "X-API-Key": os.getenv("AI_API_KEY", "")})
        ms = int((time.perf_counter() - t0) * 1000)
        res = r.json()
        pred = norm(res.get("plate_text"))
        ocr = res.get("ocr_confidence") or 0
        latencies.append(ms)
        detected += bool(res.get("plate_found"))
        exact += pred == truth
        cer = edit_distance(pred, truth) / max(len(truth), 1)
        cer_sum += cer
        # would be trusted by the gateway but text is wrong -> risk of false accept
        risky = pred != truth and ocr >= args.conf_min and res.get("valid_format")
        accepted_wrong += bool(risky)
        rows.append([item["filename"], truth, pred, res.get("detection_confidence"),
                     ocr, res.get("valid_format"), round(cer, 3), ms, risky])
        print(f"{item['filename']:30} truth={truth:12} pred={pred:12} ocr={ocr:.2f} {ms} ms")

    n = len(items) or 1
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    with open(out / "evaluation_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename", "truth", "predicted", "det_conf", "ocr_conf",
                    "valid_format", "cer", "latency_ms", "confident_but_wrong"])
        w.writerows(rows)

    print("\n===== SUMMARY =====")
    print(f"Images:                 {len(items)}")
    print(f"Plate found rate:       {detected / n:.1%}")
    print(f"Exact-match accuracy:   {exact / n:.1%}")
    print(f"Mean char error rate:   {cer_sum / n:.3f}")
    print(f"Confident-but-wrong:    {accepted_wrong}  (false-accept risk, target 0)")
    print(f"Latency p50 / p95:      {statistics.median(latencies) if latencies else 0:.0f} / "
          f"{pct(latencies, 95)} ms")
    print(f"Saved: {out / 'evaluation_results.csv'}")


if __name__ == "__main__":
    main()
