#!/usr/bin/env python3
import argparse
import json


def load(path):
    with open(path) as f:
        return json.load(f)


def key(record):
    return (
        record.get("category", ""),
        record.get("metric", ""),
        int(record.get("words", 0)),
        int(record.get("vadd_repeats", 0)),
    )


def index(payload):
    return {key(record): record for record in payload.get("records", [])}


def fmt_ms(value):
    return "-" if value is None else "%.3f" % value


def fmt_speedup(value):
    return "-" if value is None else "%.2fx" % value


def fmt_pct(value):
    return "-" if value is None else "%+.1f%%" % value


def main():
    parser = argparse.ArgumentParser(description="Compare two memory benchmark JSON files")
    parser.add_argument("baseline_json")
    parser.add_argument("candidate_json")
    parser.add_argument("--baseline-label", default=None)
    parser.add_argument("--candidate-label", default=None)
    args = parser.parse_args()

    baseline = load(args.baseline_json)
    candidate = load(args.candidate_json)
    base_label = args.baseline_label or baseline.get("variant", "baseline")
    cand_label = args.candidate_label or candidate.get("variant", "candidate")

    base_idx = index(baseline)
    cand_idx = index(candidate)
    all_keys = sorted(set(base_idx) | set(cand_idx))

    print("Memory Benchmark Comparison")
    print("baseline:  %s" % base_label)
    print("candidate: %s" % cand_label)
    print("")

    header = "%-14s %-32s %8s %10s %10s %10s %10s" % (
        "category", "metric", "words", "base_ms", "cand_ms", "speedup", "MBps_delta"
    )
    print(header)
    print("-" * len(header))

    for rec_key in all_keys:
        category, metric, words, _repeats = rec_key
        b = base_idx.get(rec_key)
        c = cand_idx.get(rec_key)
        if b and b.get("skipped"):
            base_ms = None
        else:
            base_ms = b.get("median_ms") if b else None
        if c and c.get("skipped"):
            cand_ms = None
        else:
            cand_ms = c.get("median_ms") if c else None

        speedup = None
        if base_ms and cand_ms and cand_ms > 0:
            speedup = base_ms / cand_ms

        mbps_delta = None
        if b and c and "median_MBps" in b and "median_MBps" in c and b["median_MBps"] > 0:
            mbps_delta = ((c["median_MBps"] / b["median_MBps"]) - 1.0) * 100.0

        print("%-14s %-32s %8d %10s %10s %10s %10s" % (
            category,
            metric,
            words,
            fmt_ms(base_ms),
            fmt_ms(cand_ms),
            fmt_speedup(speedup),
            fmt_pct(mbps_delta),
        ))

    print("")
    print("Notes:")
    print("- speedup > 1.00x means candidate has lower median latency.")
    print("- MBps_delta > 0 means candidate has higher median bandwidth.")
    print("- skipped rows usually mean the older driver/runtime cannot expose that benchmark.")


if __name__ == "__main__":
    main()
