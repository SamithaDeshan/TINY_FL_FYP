"""Create a descriptive report for an unlabeled physical-node MQTT capture.

Example:
    .venv312\\Scripts\\python.exe stage2/python/report_physical_collection.py \\
        stage2/data/physical_overnight_unlabeled_20261025.csv

This report describes sensor/telemetry distributions only; without ground-truth
labels it does not measure anomaly-classification accuracy.
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import reportlib as R

REQUIRED = [
    "received_at_utc", "collection_id", "scenario", "ground_truth_anomaly", "node", "sample",
    "temperature", "humidity", "pir", "ldr_raw", "ldr10", "anomaly", "confidence",
    "inference_us", "battery_pct", "battery_source", "energy_mode", "indicator_pwm", "sample_period_ms",
]
MEASURED = ["temperature", "humidity", "pir", "ldr_raw", "ldr10", "confidence", "inference_us"]


def analyze(csv_path):
    data = pd.read_csv(csv_path)
    missing_columns = sorted(set(REQUIRED) - set(data.columns))
    if missing_columns:
        raise ValueError("CSV missing required columns: " + ", ".join(missing_columns))
    data["received_at_utc"] = pd.to_datetime(data["received_at_utc"], utc=True, errors="coerce")
    numeric = ["node", "sample", *MEASURED, "anomaly", "battery_pct", "indicator_pwm", "sample_period_ms"]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    invalid_timestamp_rows = int(data["received_at_utc"].isna().sum())
    data = data.dropna(subset=["received_at_utc", "node", "sample"])
    if data.empty:
        raise ValueError("No rows with valid timestamp, node ID, and sample number.")

    per_node = []
    for node, group in data.groupby("node"):
        group = group.sort_values("received_at_utc").copy()
        intervals = group["received_at_utc"].diff().dt.total_seconds() * 1000
        metrics = {
            "node": int(node),
            "rows": int(len(group)),
            "duration_s": float((group["received_at_utc"].iloc[-1] - group["received_at_utc"].iloc[0]).total_seconds()),
            "sample_interval_median_ms": float(intervals.median()) if intervals.notna().any() else None,
            "sample_interval_p95_ms": float(intervals.quantile(0.95)) if intervals.notna().any() else None,
        }
        for column in MEASURED:
            values = group[column].dropna()
            metrics[f"{column}_n"] = int(len(values))
            metrics[f"{column}_missing"] = int(group[column].isna().sum())
            if len(values):
                metrics[f"{column}_mean"] = float(values.mean())
                metrics[f"{column}_sd"] = float(values.std(ddof=1)) if len(values) > 1 else 0.0
                metrics[f"{column}_min"] = float(values.min())
                metrics[f"{column}_max"] = float(values.max())
        metrics["pir_high_pct"] = float(group["pir"].dropna().mean() * 100)
        metrics["predicted_anomaly_pct"] = float(group["anomaly"].dropna().mean() * 100)
        metrics["predicted_confidence_ge_0_5_pct"] = float((group["confidence"].dropna() >= 0.5).mean() * 100)
        metrics["battery_sources"] = sorted(group["battery_source"].dropna().astype(str).unique().tolist())
        metrics["energy_modes"] = {str(k): int(v) for k, v in group["energy_mode"].value_counts(dropna=False).items()}
        per_node.append(metrics)

    ground_truth_present = int(data["ground_truth_anomaly"].notna().sum())
    summary = {
        "data_type": "physical sensor/MQTT telemetry; labels unavailable",
        "warning": "Model anomaly/confidence are predictions, not ground truth. Do not calculate or claim classification accuracy from this file.",
        "csv": str(csv_path),
        "rows": int(len(data)),
        "nodes": sorted(int(x) for x in data["node"].unique()),
        "session_ids": sorted(data["collection_id"].dropna().astype(str).unique().tolist()),
        "scenarios": sorted(data["scenario"].dropna().astype(str).unique().tolist()),
        "ground_truth_labeled_rows": ground_truth_present,
        "invalid_timestamp_rows": invalid_timestamp_rows,
        "start_utc": data["received_at_utc"].min().isoformat(),
        "end_utc": data["received_at_utc"].max().isoformat(),
        "duration_s": float((data["received_at_utc"].max() - data["received_at_utc"].min()).total_seconds()),
        "battery_sources": sorted(data["battery_source"].dropna().astype(str).unique().tolist()),
        "per_node": per_node,
    }
    return data, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="physical collector CSV")
    parser.add_argument("--out", default="stage2/reports/physical_telemetry")
    args = parser.parse_args()
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    output = Path(args.out)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    data, summary = analyze(csv_path)

    figure, axes = plt.subplots(3, 1, figsize=(7, 7), sharex=True)
    start = data["received_at_utc"].min()
    data = data.copy()
    data["elapsed_hours"] = (data["received_at_utc"] - start).dt.total_seconds() / 3600
    for node, group in data.groupby("node"):
        group = group.sort_values("received_at_utc")
        axes[0].plot(group["elapsed_hours"], group["temperature"], linewidth=0.45, label=f"Node {int(node)}")
        axes[1].plot(group["elapsed_hours"], group["humidity"], linewidth=0.45, label=f"Node {int(node)}")
        axes[2].plot(group["elapsed_hours"], group["ldr10"], linewidth=0.45, label=f"Node {int(node)}")
    axes[0].set_ylabel("Temperature (°C)")
    axes[1].set_ylabel("Humidity (%)")
    axes[2].set_ylabel("LDR10 (0–1023)")
    axes[2].set_xlabel("Elapsed time (hours)")
    for axis in axes:
        axis.legend(frameon=False, ncol=2)
    figure_path = output / "fig_physical_sensor_traces.png"
    R.savefig(str(figure_path))

    document = R.new_doc("Stage 2 Physical Sensor Telemetry Report", "Unlabeled overnight two-node MQTT collection")
    document.add_heading("1. Data scope", 1)
    document.add_paragraph(
        "This report describes physical sensor and inference telemetry received from two ESP32-S3 nodes. "
        "The ground-truth anomaly field is unlabeled. The firmware's anomaly/confidence values are model predictions, "
        "not labels; therefore accuracy, precision, recall, F1, and ROC-AUC are not calculated. Battery percentage is simulated."
    )
    document.add_paragraph(
        f"The capture contains {summary['rows']:,} rows from nodes {summary['nodes']} over "
        f"{summary['duration_s'] / 3600:.2f} hours, from {summary['start_utc']} to {summary['end_utc']}. "
        f"Ground-truth-labeled rows: {summary['ground_truth_labeled_rows']}. Invalid timestamps: {summary['invalid_timestamp_rows']}."
    )
    rows = []
    for item in summary["per_node"]:
        rows.append([
            item["node"], item["rows"], f"{item['sample_interval_median_ms']:.1f}",
            f"{item['temperature_min']:.1f}–{item['temperature_max']:.1f}",
            f"{item['humidity_min']:.1f}–{item['humidity_max']:.1f}",
            f"{item['pir_high_pct']:.2f}%", f"{int(item['ldr10_min'])}–{int(item['ldr10_max'])}",
            f"{item['inference_us_mean']:.1f}",
        ])
    R.table(document, ["Node", "Rows", "Median interval (ms)", "Temp range (°C)", "RH range (%)", "PIR high", "LDR10 range", "Mean inference (µs)"], rows, size=8.5)
    R.picture(document, str(figure_path), "Physical sensor traces by node; anomaly outputs are model predictions only.", 6.1)
    document.add_heading("2. Interpretation and limitations", 1)
    document.add_paragraph(
        "The node distributions are descriptive and should be interpreted alongside documented sensor placement and calibration. "
        "Because this session has no event labels, it is suitable for baseline sensor-range, data continuity, and inference-timing "
        "characterization, not supervised anomaly-classification evaluation. The battery field is simulation metadata, not measured energy."
    )
    document.save(output / "S2_Physical_Telemetry_Report.docx")
    R.dump_json(summary, output / "s2_physical_telemetry_summary.json")
    print(f"Report: {output / 'S2_Physical_Telemetry_Report.docx'}")
    print(f"Summary: {output / 's2_physical_telemetry_summary.json'}")
    print(f"Rows: {summary['rows']}; nodes: {summary['nodes']}; ground-truth labels: {summary['ground_truth_labeled_rows']}")


if __name__ == "__main__":
    main()
