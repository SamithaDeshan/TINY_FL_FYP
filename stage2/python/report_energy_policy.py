"""Report the Stage 2 energy-policy demo from a collector CSV.

Example:
    .venv312\\Scripts\\python.exe stage2/python/report_energy_policy.py \\
        stage2/data/energy_policy_sim.csv

The battery percentage in the current firmware is simulated, not measured.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import reportlib as R

REQUIRED = {
    "received_at_utc", "node", "battery_pct", "battery_source", "energy_mode",
    "indicator_pwm", "sample_period_ms", "confidence", "anomaly", "ldr_raw", "ldr10",
}
MODE_ORDER = ["NORMAL", "ECO", "CRITICAL"]
EXPECTED_INTERVAL_MS = {"NORMAL": 2000, "ECO": 5000, "CRITICAL": 15000}
PWM_CAPS = {"NORMAL": 255, "ECO": 128, "CRITICAL": 0}


def analyze(path):
    data = pd.read_csv(path)
    missing = REQUIRED - set(data.columns)
    if missing:
        raise ValueError("CSV is missing required columns: " + ", ".join(sorted(missing)))
    data["received_at_utc"] = pd.to_datetime(data["received_at_utc"], utc=True, errors="coerce")
    numeric = ["node", "battery_pct", "indicator_pwm", "sample_period_ms", "confidence", "anomaly", "ldr_raw", "ldr10"]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["received_at_utc", *numeric, "energy_mode"])
    if data.empty:
        raise ValueError("No valid records found in the collector CSV.")

    node_summaries = []
    mode_rows = []
    for node, group in data.groupby("node"):
        group = group.sort_values("received_at_utc").copy()
        group["interval_ms"] = group["received_at_utc"].diff().dt.total_seconds() * 1000
        node_summaries.append({
            "node": int(node),
            "rows": int(len(group)),
            "duration_s": float((group["received_at_utc"].iloc[-1] - group["received_at_utc"].iloc[0]).total_seconds()),
            "median_interval_ms": float(group["interval_ms"].median()) if group["interval_ms"].notna().any() else None,
            "battery_start_pct": float(group["battery_pct"].iloc[0]),
            "battery_end_pct": float(group["battery_pct"].iloc[-1]),
            "ldr10_min": int(group["ldr10"].min()),
            "ldr10_max": int(group["ldr10"].max()),
        })
        for mode in MODE_ORDER:
            selected = group[group["energy_mode"].str.upper() == mode]
            if selected.empty:
                continue
            intervals = selected["interval_ms"].dropna()
            expected_pwm = PWM_CAPS[mode]
            mode_rows.append({
                "node": int(node),
                "mode": mode,
                "rows": int(len(selected)),
                "battery_min_pct": float(selected["battery_pct"].min()),
                "battery_max_pct": float(selected["battery_pct"].max()),
                "pwm_max": int(selected["indicator_pwm"].max()),
                "pwm_cap": expected_pwm,
                "pwm_cap_pass_pct": float((selected["indicator_pwm"] <= expected_pwm).mean() * 100),
                "expected_interval_ms": EXPECTED_INTERVAL_MS[mode],
                "observed_interval_median_ms": float(intervals.median()) if len(intervals) else None,
            })

    sources = sorted(data["battery_source"].dropna().astype(str).unique().tolist())
    summary = {
        "warning": "Battery percentage is simulated by firmware; this is not battery voltage or energy measurement.",
        "input_csv": str(path),
        "rows": int(len(data)),
        "nodes": sorted(int(value) for value in data["node"].unique()),
        "duration_s": float((data["received_at_utc"].max() - data["received_at_utc"].min()).total_seconds()),
        "battery_sources": sources,
        "battery_simulation_confirmed": sources == ["simulated"],
        "overall_pwm_cap_pass_pct": float(sum(row["rows"] * row["pwm_cap_pass_pct"] for row in mode_rows) / sum(row["rows"] for row in mode_rows)) if mode_rows else None,
        "node_summaries": node_summaries,
        "mode_summaries": mode_rows,
    }
    return data, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="CSV created by collect_node_data.py")
    parser.add_argument("--out", default="stage2/reports/energy_policy")
    args = parser.parse_args()
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    output = Path(args.out)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)

    data, summary = analyze(csv_path)
    plot_path = output / "fig_energy_policy_modes.png"
    counts = data.groupby(["node", "energy_mode"]).size().unstack(fill_value=0).reindex(columns=MODE_ORDER, fill_value=0)
    axis = counts.plot(kind="bar", figsize=(6.0, 3.2), color=["0.25", "0.5", "0.75"])
    axis.set_xlabel("Node ID")
    axis.set_ylabel("Received MQTT samples")
    axis.legend(title="Energy mode", frameon=False)
    R.savefig(str(plot_path))

    document = R.new_doc(
        "Stage 2 Energy-Aware Policy Check",
        "Physical node telemetry with simulated battery level",
    )
    document.add_heading("1. Scope", 1)
    document.add_paragraph(
        "This report checks mode-dependent sample intervals and confidence-indicator PWM caps using node telemetry. "
        "The firmware battery percentage is randomly simulated; no battery voltage, current, or energy consumption was measured."
    )
    R.table(document, ["Node", "Rows", "Duration (s)", "Median interval (ms)", "Battery start/end (%)", "LDR10 range"], [
        [item["node"], item["rows"], f"{item['duration_s']:.1f}",
         "n/a" if item["median_interval_ms"] is None else f"{item['median_interval_ms']:.0f}",
         f"{item['battery_start_pct']:.0f}/{item['battery_end_pct']:.0f}",
         f"{item['ldr10_min']}–{item['ldr10_max']}"] for item in summary["node_summaries"]
    ])
    R.table(document, ["Node", "Mode", "Rows", "Battery range (%)", "PWM max/cap", "Cap pass (%)", "Interval expected/observed (ms)"], [
        [item["node"], item["mode"], item["rows"],
         f"{item['battery_min_pct']:.0f}–{item['battery_max_pct']:.0f}",
         f"{item['pwm_max']}/{item['pwm_cap']}", f"{item['pwm_cap_pass_pct']:.1f}",
         f"{item['expected_interval_ms']}/{item['observed_interval_median_ms'] if item['observed_interval_median_ms'] is not None else 'n/a'}"]
        for item in summary["mode_summaries"]
    ], size=8.5)
    R.picture(document, str(plot_path), "Received MQTT samples per node and simulated energy mode.", 5.8)
    document.add_heading("2. Interpretation", 1)
    document.add_paragraph(
        "Passing these checks demonstrates the firmware's simulated energy policy only. It does not demonstrate battery life, "
        "measured energy savings, or performance under a physical low-voltage condition."
    )
    document.save(output / "S2_Energy_Policy_Report.docx")
    R.dump_json(summary, output / "s2_energy_policy_summary.json")
    print(f"Report: {output / 'S2_Energy_Policy_Report.docx'}")
    print(f"Summary: {output / 's2_energy_policy_summary.json'}")
    print(f"Rows: {summary['rows']}; nodes: {summary['nodes']}; sources: {sources if (sources := summary['battery_sources']) else []}")


if __name__ == "__main__":
    main()
