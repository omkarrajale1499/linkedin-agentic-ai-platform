#!/usr/bin/env python3
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(r"c:\Omkar\Workspace\DATA_236\Project\infrastructure\benchmarks")
OUT_DIR = ROOT / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)
MAX_VALID_ELAPSED_MS = 30000

CONFIGS = ["B", "BS", "BSK", "BSKO"]
DISPLAY = {
    "B": "B",
    "BS": "B+S",
    "BSK": "B+S+K",
    "BSKO": "B+S+K+Other",
}


def percentile(values, p):
    if not values:
        return 0.0
    k = (len(values) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(values[int(k)])
    return float(values[f] + (values[c] - values[f]) * (k - f))


def parse_jmeter_csv(path: Path, label_filter=None):
    samples = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        next(f, None)  # header
        for line in f:
            line = line.strip()
            if not line:
                continue
            # First columns are stable: timeStamp,elapsed,label
            parts = line.split(",", 3)
            if len(parts) < 3:
                continue
            try:
                ts = int(parts[0])
                elapsed = int(parts[1])
            except Exception:
                continue
            label = parts[2]
            if label_filter and not any(token in label for token in label_filter):
                continue
            m = re.search(r",text,(true|false),", line, flags=re.IGNORECASE)
            success = m.group(1).lower() == "true" if m else False
            # Drop obvious corrupted/outlier elapsed values (seen in interrupted runs).
            if elapsed < 0 or elapsed > MAX_VALID_ELAPSED_MS:
                continue
            samples.append((ts, elapsed, success))

    if not samples:
        return {
            "count": 0,
            "throughput": 0.0,
            "avg_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "error_rate_pct": 0.0,
        }

    elapsed = [s[1] for s in samples]
    elapsed_sorted = sorted(elapsed)
    ts = [s[0] for s in samples]
    start_ts, end_ts = min(ts), max(ts)
    duration_s = max((end_ts - start_ts) / 1000.0, 1e-6)

    errors = sum(1 for s in samples if not s[2])
    count = len(samples)
    return {
        "count": count,
        "throughput": count / duration_s,
        "avg_ms": sum(elapsed) / count,
        "p95_ms": percentile(elapsed_sorted, 0.95),
        "p99_ms": percentile(elapsed_sorted, 0.99),
        "error_rate_pct": (errors / count) * 100.0,
    }


def collect_metrics():
    scenario_a = {}
    scenario_b = {}
    for key in CONFIGS:
        jtl = ROOT / f"results_{key}_jtl.csv"
        scenario_a[key] = parse_jmeter_csv(
            jtl,
            label_filter=["POST /api/jobs/search", "POST /api/jobs/get"],
        )
        scenario_b[key] = parse_jmeter_csv(
            jtl,
            label_filter=["POST /api/applications/submit"],
        )
    return scenario_a, scenario_b


def plot_scenario(metrics, title, out_name):
    labels = [DISPLAY[c] for c in CONFIGS]
    x = np.arange(len(labels))

    throughput = [metrics[c]["throughput"] for c in CONFIGS]
    avg_ms = [metrics[c]["avg_ms"] for c in CONFIGS]
    p95_ms = [metrics[c]["p95_ms"] for c in CONFIGS]
    err = [metrics[c]["error_rate_pct"] for c in CONFIGS]

    fig, axes = plt.subplots(1, 4, figsize=(18, 4.5))
    fig.suptitle(title, fontsize=13, fontweight="bold")

    series = [
        (throughput, "Throughput (req/s)"),
        (avg_ms, "Average Latency (ms)"),
        (p95_ms, "P95 Latency (ms)"),
        (err, "Error Rate (%)"),
    ]

    for ax, (vals, ylabel) in zip(axes, series):
        bars = ax.bar(x, vals)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=20, ha="right")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.1f}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    fig.savefig(OUT_DIR / out_name, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_combined(scenario_a, scenario_b):
    labels = [DISPLAY[c] for c in CONFIGS]
    x = np.arange(len(labels))
    w = 0.35

    a_t = [scenario_a[c]["throughput"] for c in CONFIGS]
    b_t = [scenario_b[c]["throughput"] for c in CONFIGS]
    a_l = [scenario_a[c]["avg_ms"] for c in CONFIGS]
    b_l = [scenario_b[c]["avg_ms"] for c in CONFIGS]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    fig.suptitle("Benchmark Comparison (100 users)", fontsize=13, fontweight="bold")

    axes[0].bar(x - w / 2, a_t, width=w, label="Scenario A")
    axes[0].bar(x + w / 2, b_t, width=w, label="Scenario B")
    axes[0].set_title("Throughput (req/s)")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, rotation=20, ha="right")
    axes[0].legend()
    axes[0].grid(axis="y", linestyle="--", alpha=0.4)

    axes[1].bar(x - w / 2, a_l, width=w, label="Scenario A")
    axes[1].bar(x + w / 2, b_l, width=w, label="Scenario B")
    axes[1].set_title("Average Latency (ms)")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=20, ha="right")
    axes[1].legend()
    axes[1].grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "benchmark_comparison.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def write_summary(scenario_a, scenario_b):
    out = ROOT / "benchmark_summary.md"
    with out.open("w", encoding="utf-8") as f:
        f.write("# JMeter Benchmark Summary\n\n")
        f.write("Load profile: Scenario A (100x10), Scenario B (100x5), ramp 10s.\n\n")
        f.write("## Scenario A: Job Search + Job Detail\n\n")
        f.write("| Config | Throughput (req/s) | Avg (ms) | P95 (ms) | P99 (ms) | Error % |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for c in CONFIGS:
            m = scenario_a[c]
            f.write(f"| {DISPLAY[c]} | {m['throughput']:.2f} | {m['avg_ms']:.1f} | {m['p95_ms']:.1f} | {m['p99_ms']:.1f} | {m['error_rate_pct']:.2f} |\n")

        f.write("\n## Scenario B: Apply Submit (DB + Kafka)\n\n")
        f.write("| Config | Throughput (req/s) | Avg (ms) | P95 (ms) | P99 (ms) | Error % |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for c in CONFIGS:
            m = scenario_b[c]
            f.write(f"| {DISPLAY[c]} | {m['throughput']:.2f} | {m['avg_ms']:.1f} | {m['p95_ms']:.1f} | {m['p99_ms']:.1f} | {m['error_rate_pct']:.2f} |\n")

        f.write("\n## Notes\n\n")
        f.write("- B run was executed with Redis + Kafka stack stopped.\n")
        f.write("- B+S run had Redis enabled, Kafka stack stopped.\n")
        f.write("- B+S+K and B+S+K+Other ran with Redis + Kafka stack enabled.\n")
        f.write("- Error rates and timeout sensitivity indicate capacity limits under mixed read/write concurrency and should be discussed in the final report.\n")


def main():
    scenario_a, scenario_b = collect_metrics()
    plot_scenario(scenario_a, "Scenario A: Job Search + Job Detail", "benchmark_scenario_A.png")
    plot_scenario(scenario_b, "Scenario B: Apply Submit (DB + Kafka)", "benchmark_scenario_B.png")
    plot_combined(scenario_a, scenario_b)
    write_summary(scenario_a, scenario_b)
    print(f"Report generated in: {ROOT}")
    print(f"Charts generated in: {OUT_DIR}")


if __name__ == "__main__":
    main()
