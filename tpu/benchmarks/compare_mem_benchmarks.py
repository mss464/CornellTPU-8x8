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
        int(record.get("mxu_repeats", 0)),
    )


def index(payload):
    return {key(record): record for record in payload.get("records", [])}


def fmt_ms(value):
    return "-" if value is None else "%.3f" % value


def fmt_speedup(value):
    return "-" if value is None else "%.2fx" % value


def fmt_pct(value):
    return "-" if value is None else "%+.1f%%" % value


def usable(record):
    return record is not None and not record.get("skipped") and record.get("median_ms", 0) > 0


def matching(records, category, metric):
    return [
        rec for rec in records
        if rec.get("category") == category and rec.get("metric") == metric
    ]


def max_words(records, category, metric):
    usable_records = [rec for rec in matching(records, category, metric) if usable(rec)]
    if not usable_records:
        return None
    return sorted(usable_records, key=lambda rec: int(rec.get("words", 0)))[-1]


def same_key(idx, record):
    return idx.get(key(record)) if record else None


def common_pair(base_records, cand_idx, category, metric):
    for base in sorted(matching(base_records, category, metric),
                       key=lambda rec: int(rec.get("words", 0)),
                       reverse=True):
        cand = same_key(cand_idx, base)
        if usable(base) and usable(cand):
            return base, cand
    return None, None


def record_by_words(records, category, metric, words):
    for rec in records:
        if (rec.get("category") == category
                and rec.get("metric") == metric
                and int(rec.get("words", 0)) == int(words)):
            return rec
    return None


def fmt_bw(record):
    if not record or "median_MBps" not in record:
        return "-"
    return "%.1f MB/s" % record["median_MBps"]


def fmt_advantage(speedup):
    if speedup is None:
        return "-"
    if speedup >= 1.0:
        return "%.2fx faster" % speedup
    return "%.2fx as fast" % speedup


def print_strength_scorecard(baseline, candidate, base_idx, cand_idx):
    base_records = baseline.get("records", [])
    cand_records = candidate.get("records", [])
    rows = []

    for category, metric, label in (
        ("dma", "host_to_sysmem_write", "Host write bandwidth"),
        ("dma", "sysmem_to_host_read", "Host read bandwidth"),
        ("workload", "host_roundtrip_write_read", "Host write+read roundtrip"),
    ):
        b, c = common_pair(base_records, cand_idx, category, metric)
        if usable(b) and usable(c):
            speed = b["median_ms"] / c["median_ms"]
            rows.append((
                "%s (%d words)" % (label, int(b.get("words", 0))),
                "%s, %s" % (fmt_ms(b["median_ms"]), fmt_bw(b)),
                "%s, %s" % (fmt_ms(c["median_ms"]), fmt_bw(c)),
                fmt_advantage(speed),
            ))

    c_compute = max_words(cand_records, "compute", "vadd_program")
    b_compute = same_key(base_idx, c_compute)
    if usable(b_compute) and usable(c_compute):
        speed = b_compute["median_ms"] / c_compute["median_ms"]
        rows.append((
            "VADD compute (%d words x %d)" % (
                int(c_compute.get("words", 0)),
                int(c_compute.get("vadd_repeats", 0))),
            "%s ms" % fmt_ms(b_compute["median_ms"]),
            "%s ms" % fmt_ms(c_compute["median_ms"]),
            fmt_advantage(speed),
        ))

    c_mxu = max_words(cand_records, "compute", "mxu_4x4_matmul")
    b_mxu = same_key(base_idx, c_mxu)
    if usable(b_mxu) and usable(c_mxu):
        speed = b_mxu["median_ms"] / c_mxu["median_ms"]
        rows.append((
            "MXU 4x4 matmul (%d repeats)" % int(c_mxu.get("mxu_repeats", 0)),
            "%s ms" % fmt_ms(b_mxu["median_ms"]),
            "%s ms" % fmt_ms(c_mxu["median_ms"]),
            fmt_advantage(speed),
        ))

    c_overlap = max_words(cand_records, "double_buffer", "overlapped_compute_and_dma")
    if usable(c_overlap):
        b_compute_for_overlap = same_key(base_idx, c_compute) if c_compute else None
        b_next_dma = record_by_words(base_records, "dma", "host_to_sysmem_write",
                                     int(c_overlap.get("words", 0)))
        if usable(b_compute_for_overlap) and usable(b_next_dma):
            baseline_serial = b_compute_for_overlap["median_ms"] + b_next_dma["median_ms"]
            speed = baseline_serial / c_overlap["median_ms"]
            rows.append((
                "Pipeline compute + next DMA",
                "serial estimate %.3f ms" % baseline_serial,
                "overlapped %.3f ms" % c_overlap["median_ms"],
                fmt_advantage(speed),
            ))

    c_serial = max_words(cand_records, "double_buffer", "serial_estimate_compute_plus_dma")
    if usable(c_serial) and c_serial.get("speedup_vs_overlap"):
        rows.append((
            "Candidate double buffering",
            "serial %.3f ms" % c_serial["median_ms"],
            "overlap %.3f ms" % c_serial.get("overlap_median_ms", 0.0),
            fmt_advantage(c_serial["speedup_vs_overlap"]),
        ))

    c_l1 = max_words(cand_records, "l1_copy", "sysmem_to_l1")
    b_l1 = same_key(base_idx, c_l1)
    if usable(c_l1) and (b_l1 is None or b_l1.get("skipped")):
        rows.append((
            "Explicit sysmem->L1 copy",
            "not exposed",
            "%s ms at %d words" % (fmt_ms(c_l1["median_ms"]), int(c_l1.get("words", 0))),
            "candidate-only feature",
        ))

    c_vpu_model = max_words(cand_records, "banked_compute", "vpu_vector_add_model")
    b_vpu_model = same_key(base_idx, c_vpu_model)
    if usable(b_vpu_model) and usable(c_vpu_model):
        speed = b_vpu_model["median_ms"] / c_vpu_model["median_ms"]
        rows.append((
            "8-bank VPU/L1 transaction model",
            "%d transactions" % int(b_vpu_model.get("memory_transactions", 0)),
            "%d transactions" % int(c_vpu_model.get("memory_transactions", 0)),
            fmt_advantage(speed),
        ))

    if not rows:
        return

    print("")
    print("Strength Scorecard:")
    header = "%-36s %-24s %-24s %-18s" % (
        "evaluation", "baseline", "candidate", "advantage"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print("%-36s %-24s %-24s %-18s" % row)


def print_highlights(baseline, candidate, base_idx, cand_idx):
    base_records = baseline.get("records", [])
    cand_records = candidate.get("records", [])
    lines = []

    for metric, label in (
        ("host_to_sysmem_write", "largest raw host write"),
        ("sysmem_to_host_read", "largest raw host read"),
    ):
        b = max_words(base_records, "dma", metric)
        c = same_key(cand_idx, b)
        if usable(b) and usable(c):
            speed = b["median_ms"] / c["median_ms"]
            lines.append(
                "%s (%d words): candidate is %.2fx baseline latency (%s vs %s ms)"
                % (label, int(b.get("words", 0)), c["median_ms"] / b["median_ms"],
                   fmt_ms(c["median_ms"]), fmt_ms(b["median_ms"]))
            )
            lines.append(
                "  speedup column view: %.2fx, so values below 1.00x mean raw DMA is slower"
                % speed
            )

    c_compute = max_words(cand_records, "compute", "vadd_program")
    b_compute = same_key(base_idx, c_compute)
    if usable(b_compute) and usable(c_compute):
        speed = b_compute["median_ms"] / c_compute["median_ms"]
        note = ""
        if b_compute.get("single_shot"):
            note = " (baseline single-shot: %s)" % b_compute.get("single_shot_reason", "legacy runtime")
        lines.append(
            "VADD compute (%d words x %d repeats): candidate is %.2fx baseline%s"
            % (int(c_compute.get("words", 0)), int(c_compute.get("vadd_repeats", 0)),
               speed, note)
        )

    c_mxu = max_words(cand_records, "compute", "mxu_4x4_matmul")
    b_mxu = same_key(base_idx, c_mxu)
    if usable(b_mxu) and usable(c_mxu):
        speed = b_mxu["median_ms"] / c_mxu["median_ms"]
        note = ""
        if b_mxu.get("single_shot"):
            note = " (baseline single-shot)"
        lines.append(
            "MXU 4x4 matmul (%d repeats, %d MACs): candidate is %.2fx baseline%s"
            % (int(c_mxu.get("mxu_repeats", 0)),
               int(c_mxu.get("mxu_macs", 0)),
               speed,
               note)
        )

    c_vpu = max_words(cand_records, "banked_compute", "vpu_vector_add")
    b_vpu = same_key(base_idx, c_vpu)
    if usable(b_vpu) and usable(c_vpu):
        speed = b_vpu["median_ms"] / c_vpu["median_ms"]
        note = ""
        if b_vpu.get("single_shot"):
            note = " (baseline single-shot)"
        lines.append(
            "banked VPU vector add (%d elements): candidate is %.2fx baseline; paths %s -> %s%s"
            % (int(c_vpu.get("words", 0)), speed,
               b_vpu.get("path", "baseline"),
               c_vpu.get("path", "candidate"),
               note)
        )
        if b_vpu.get("instruction_count") and c_vpu.get("instruction_count"):
            lines.append(
                "  instruction count drops from %d to %d by using 8-lane banked VLOAD/VSTORE/VCOMPUTE"
                % (int(b_vpu["instruction_count"]), int(c_vpu["instruction_count"]))
            )

    c_vpu_model = max_words(cand_records, "banked_compute", "vpu_vector_add_model")
    b_vpu_model = same_key(base_idx, c_vpu_model)
    if usable(b_vpu_model) and usable(c_vpu_model):
        speed = b_vpu_model["median_ms"] / c_vpu_model["median_ms"]
        lines.append(
            "banked VPU memory model (%d elements): candidate is %.2fx baseline; paths %s -> %s"
            % (int(c_vpu_model.get("words", 0)), speed,
               b_vpu_model.get("path", "baseline_model"),
               c_vpu_model.get("path", "candidate_model"))
        )
        if b_vpu_model.get("memory_transactions") and c_vpu_model.get("memory_transactions"):
            lines.append(
                "  modeled L1 transactions drop from %d to %d with 8-wide banked rows"
                % (int(b_vpu_model["memory_transactions"]),
                   int(c_vpu_model["memory_transactions"]))
            )

    c_serial = max_words(cand_records, "double_buffer", "serial_estimate_compute_plus_dma")
    if usable(c_serial) and c_serial.get("speedup_vs_overlap"):
        lines.append(
            "double buffering: %.2fx faster than candidate serial compute+DMA estimate (%s ms -> %s ms)"
            % (c_serial["speedup_vs_overlap"],
               fmt_ms(c_serial.get("median_ms")),
               fmt_ms(c_serial.get("overlap_median_ms")))
        )

    c_l1 = max_words(cand_records, "l1_copy", "sysmem_to_l1")
    b_l1 = same_key(base_idx, c_l1)
    if usable(c_l1) and (b_l1 is None or b_l1.get("skipped")):
        lines.append(
            "explicit L1 copy path exists only in candidate for this benchmark; %d-word sysmem->L1 median is %s ms"
            % (int(c_l1.get("words", 0)), fmt_ms(c_l1.get("median_ms")))
        )

    c_model = max_words(cand_records, "model", "wide_l1_8bank_vector_add_cycles")
    if c_model and c_model.get("ideal_bank_speedup"):
        lines.append(
            "8-bank model: ideal same-clock L1 bandwidth speedup is %.2fx over one-bank scalar access"
            % c_model["ideal_bank_speedup"]
        )

    if lines:
        print("")
        print("Highlights:")
        for line in lines:
            print("- %s" % line)


def print_skipped_rows(base_idx, cand_idx, all_keys):
    lines = []
    for rec_key in all_keys:
        category, metric, words, _repeats = rec_key
        for label, idx in (("baseline", base_idx), ("candidate", cand_idx)):
            rec = idx.get(rec_key)
            if rec and rec.get("skipped"):
                reason = rec.get("reason", "no reason recorded")
                lines.append("%s %s/%s (%d words): %s" %
                             (label, category, metric, words, reason))

    if lines:
        print("")
        print("Skipped Rows:")
        for line in lines:
            print("- %s" % line)


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

    print_strength_scorecard(baseline, candidate, base_idx, cand_idx)
    print_highlights(baseline, candidate, base_idx, cand_idx)
    print_skipped_rows(base_idx, cand_idx, all_keys)

    print("")
    print("Notes:")
    print("- speedup > 1.00x means candidate has lower median latency.")
    print("- MBps_delta > 0 means candidate has higher median bandwidth.")
    print("- skipped rows usually mean the older driver/runtime cannot expose that benchmark.")


if __name__ == "__main__":
    main()
