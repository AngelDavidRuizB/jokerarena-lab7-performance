"""Analyze k6 load test outputs, compute the performance knee, and plot the curve."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt


LOAD_LEVELS = [1, 50, 200, 500, 2000]


def load_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_metrics(vus: int, summary: dict) -> dict:
    metrics = summary["metrics"]
    dur = metrics["http_req_duration"]
    failed = metrics["http_req_failed"]
    reqs = metrics["http_reqs"]
    return {
        "vus": vus,
        "requests": int(reqs["count"]),
        "rps": float(reqs["rate"]),
        "avg_ms": float(dur["avg"]),
        "min_ms": float(dur["min"]),
        "med_ms": float(dur["med"]),
        "p90_ms": float(dur["p(90)"]),
        "p95_ms": float(dur["p(95)"]),
        "max_ms": float(dur["max"]),
        "error_pct": float(failed["value"]) * 100.0,
        "failed_count": int(failed.get("passes", 0)),
    }


def find_knee(rows: list[dict]) -> dict:
    """Identify the knee below the first load level where http_req_failed > 0%."""
    error_threshold_idx = next(
        (i for i, r in enumerate(rows) if r["error_pct"] > 0.0), len(rows) - 1
    )
    candidates = rows[: max(2, error_threshold_idx + 1)]
    if len(candidates) <= 2:
        return candidates[0]

    x_min, x_max = candidates[0]["vus"], candidates[-1]["vus"]
    y_min = min(r["avg_ms"] for r in candidates)
    y_max = max(r["avg_ms"] for r in candidates)
    x_span = max(1e-9, x_max - x_min)
    y_span = max(1e-9, y_max - y_min)

    pts = [
        ((r["vus"] - x_min) / x_span, (r["avg_ms"] - y_min) / y_span)
        for r in candidates
    ]
    x1, y1 = pts[0]
    x2, y2 = pts[-1]
    denom = math.hypot(y2 - y1, x2 - x1) or 1e-9

    best_idx = 0
    best_dist = -1.0
    # Restrict knee strictly below the threshold where errors begin if possible.
    search_end = error_threshold_idx if error_threshold_idx > 1 else len(candidates) - 1
    for i in range(1, search_end):
        px, py = pts[i]
        dist = abs((y2 - y1) * px - (x2 - x1) * py + x2 * y1 - y2 * x1) / denom
        if dist > best_dist:
            best_dist = dist
            best_idx = i
    return rows[best_idx]


def plot_curve(rows: list[dict], knee: dict, out_path: Path) -> None:
    vus = [r["vus"] for r in rows]
    avg_ms = [r["avg_ms"] for r in rows]
    p95_ms = [r["p95_ms"] for r in rows]
    err_pct = [r["error_pct"] for r in rows]

    x_pos = list(range(len(vus)))
    knee_idx = vus.index(knee["vus"])

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 7.5), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]}
    )
    fig.patch.set_facecolor("#ffffff")

    ax1.plot(x_pos, avg_ms, marker="o", linewidth=2.5, color="#1d4ed8", label="Avg Response Time (http_req_duration avg)")
    ax1.plot(x_pos, p95_ms, marker="s", linestyle="--", linewidth=1.6, color="#64748b", label="p95 Response Time")
    ax1.scatter([knee_idx], [knee["avg_ms"]], color="#dc2626", s=130, zorder=5, label=f"Knee ({knee['vus']} VUs, {knee['avg_ms']:.1f} ms)")
    for xi, yi in zip(x_pos, avg_ms):
        ax1.annotate(f"{yi:.0f} ms", (xi, yi), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=8.5, color="#1e3a8a")
    ax1.annotate(
        f"Knee: {knee['vus']} VUs\n({knee['avg_ms']:.1f} ms, 0.00% err)",
        xy=(knee_idx, knee["avg_ms"]),
        xytext=(knee_idx - 0.95, knee["avg_ms"] + max(avg_ms) * 0.22),
        arrowprops={"arrowstyle": "->", "color": "#dc2626", "lw": 1.5},
        fontsize=9.5,
        fontweight="bold",
        color="#991b1b",
        bbox={"boxstyle": "round,pad=0.3", "fc": "#fef2f2", "ec": "#dc2626"},
    )
    ax1.set_ylabel("Response Time (ms)", fontsize=11, fontweight="bold")
    ax1.set_title("JokerArena Leaderboard — Performance Curve & Knee Analysis (k6)", fontsize=13, fontweight="bold", pad=12)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left")

    ax2.plot(x_pos, err_pct, marker="^", linewidth=2.2, color="#dc2626", label="Error Rate (http_req_failed %)")
    ax2.axhline(0.0, color="#16a34a", linestyle="--", linewidth=1.2, label="0% Error Threshold")
    for xi, y in zip(x_pos, err_pct):
        ax2.annotate(f"{y:.2f}%", (xi, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
    ax2.set_xlabel("Concurrent Virtual Users (VUs)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Error Rate (%)", fontsize=11, fontweight="bold")
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels([str(v) for v in vus])
    ax2.set_ylim(-4, max(15, max(err_pct) * 1.22))
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper left")

    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close(fig)


def main() -> None:
    results_dir = Path(__file__).resolve().parent / "results"
    rows = []
    for vus in LOAD_LEVELS:
        p = results_dir / f"summary_{vus}vu.json"
        if not p.exists():
            raise FileNotFoundError(f"Missing {p}. Run run_load_tests.ps1 first.")
        rows.append(extract_metrics(vus, load_summary(p)))

    knee = find_knee(rows)
    plot_curve(rows, knee, results_dir / "performance_curve.png")

    summary_out = {"rows": rows, "knee": knee}
    (results_dir / "analysis_summary.json").write_text(
        json.dumps(summary_out, indent=2), encoding="utf-8"
    )

    print("VUs | Requests | RPS | Avg (ms) | Med (ms) | p95 (ms) | Max (ms) | Error %")
    print("-" * 82)
    for r in rows:
        print(
            f"{r['vus']:>4} | {r['requests']:>8} | {r['rps']:>5.1f} | "
            f"{r['avg_ms']:>8.2f} | {r['med_ms']:>8.2f} | {r['p95_ms']:>8.2f} | "
            f"{r['max_ms']:>8.2f} | {r['error_pct']:>6.2f}%"
        )
    print(f"\nIdentified Knee: {knee['vus']} VUs (avg={knee['avg_ms']:.2f} ms, error={knee['error_pct']:.2f}%)")


if __name__ == "__main__":
    main()
