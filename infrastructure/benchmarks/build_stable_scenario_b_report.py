#!/usr/bin/env python3
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(r"c:\Omkar\Workspace\DATA_236\Project\infrastructure\benchmarks")
OUT = ROOT / "charts"
OUT.mkdir(exist_ok=True)

CONFIGS = [
    ("B", "results_stable_B_jtl.csv"),
    ("B+S", "results_stable_BS_jtl.csv"),
    ("B+S+K", "results_stable_BSK_jtl.csv"),
    ("B+S+K+Other", "results_stable_BSKO_jtl.csv"),
]


def parse_metrics(path: Path):
    elapsed = []
    success = 0
    total = 0
    ts = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("label") != "POST /api/applications/submit":
                continue
            total += 1
            try:
                elapsed.append(int(row.get("elapsed", "0")))
                ts.append(int(row.get("timeStamp", "0")))
            except Exception:
                elapsed.append(0)
                ts.append(0)
            if str(row.get("success", "")).lower() == "true":
                success += 1
    elapsed.sort()
    duration = max((max(ts) - min(ts)) / 1000.0, 1.0) if ts else 1.0
    err_rate = (total - success) * 100.0 / total if total else 0.0
    p95 = elapsed[int(len(elapsed) * 0.95)] if elapsed else 0.0
    return {
        "throughput": total / duration if total else 0.0,
        "avg_ms": (sum(elapsed) / len(elapsed)) if elapsed else 0.0,
        "p95_ms": p95,
        "error_pct": err_rate,
    }


def main():
    labels = []
    throughput = []
    avg = []
    p95 = []
    err = []
    rows = []

    for label, filename in CONFIGS:
        m = parse_metrics(ROOT / filename)
        labels.append(label)
        throughput.append(m["throughput"])
        avg.append(m["avg_ms"])
        p95.append(m["p95_ms"])
        err.append(m["error_pct"])
        rows.append((label, m))

    x = np.arange(len(labels))
    fig, axes = plt.subplots(1, 4, figsize=(18, 4.5))
    fig.suptitle("Scenario B Stable Rerun: Apply Submit (DB + Kafka)", fontsize=13, fontweight="bold")

    series = [
        (throughput, "Throughput (req/s)"),
        (avg, "Average Latency (ms)"),
        (p95, "P95 Latency (ms)"),
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
    fig.savefig(OUT / "benchmark_scenario_B_stable.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    summary = ROOT / "benchmark_summary_stable_scenario_B.md"
    with summary.open("w", encoding="utf-8") as f:
        f.write("# Stable Scenario B Summary\n\n")
        f.write("100 threads, 5 loops, reset application tables before each run.\n\n")
        f.write("| Config | Throughput (req/s) | Avg (ms) | P95 (ms) | Error % |\n")
        f.write("|---|---:|---:|---:|---:|\n")
        for label, m in rows:
            f.write(f"| {label} | {m['throughput']:.2f} | {m['avg_ms']:.1f} | {m['p95_ms']:.1f} | {m['error_pct']:.2f} |\n")

    print("Generated:")
    print(OUT / "benchmark_scenario_B_stable.png")
    print(summary)


if __name__ == "__main__":
    main()
