"""S1.6 closed-loop CSV report generator.

Usage:
    python tools/s1_6_report.py data/s1_6_empty.csv data/s1_6_normal.csv data/s1_6_changing.csv
"""
import argparse
import os
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportlib as R

COLUMNS = ["ms", "pir", "ldr_raw", "ldr10", "temp_c", "hum_pct", "model_pwm", "rule_pwm", "cal_valid"]


def load(path):
    metadata = []
    rows = []
    with open(path, encoding="utf-8", errors="replace") as file:
        for line in file:
            line = line.rstrip("\r\n")
            if line.startswith("#"):
                metadata.append(line[1:].strip())
            elif line and not line.startswith("ms,"):
                rows.append(line)
    frame = pd.read_csv(pd.io.common.StringIO("\n".join(rows)), names=COLUMNS, on_bad_lines="skip")
    for column in COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["ms", "pir", "ldr_raw", "ldr10", "model_pwm", "rule_pwm"])
    frame["t"] = (frame["ms"] - frame["ms"].iloc[0]) / 1000.0
    return frame, metadata


def response_times(frame):
    times = []
    for index in range(1, len(frame)):
        if frame.iloc[index - 1]["pir"] < 0.5 and frame.iloc[index]["pir"] >= 0.5:
            start_pwm = frame.iloc[index - 1]["model_pwm"]
            changed = frame.iloc[index:][np.abs(frame.iloc[index:]["model_pwm"] - start_pwm) >= 1]
            if len(changed):
                times.append(float(changed.iloc[0]["t"] - frame.iloc[index]["t"]))
    return times


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", help="one or more S1.6 CSV sessions")
    parser.add_argument("--out", default="reports/s1_6")
    args = parser.parse_args()
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)

    sessions = []
    for path in args.inputs:
        frame, metadata = load(path)
        if len(frame) == 0:
            raise SystemExit(f"No valid S1.6 data rows in {path}")
        sessions.append((Path(path), frame, metadata))

    all_data = pd.concat([frame.assign(session=path.stem) for path, frame, _ in sessions], ignore_index=True)
    difference = all_data["model_pwm"] - all_data["rule_pwm"]
    correlation = float(all_data["model_pwm"].corr(all_data["rule_pwm"])) if difference.std() else float("nan")
    latencies = sum((response_times(frame) for _, frame, _ in sessions), [])
    summary = {
        "sessions": len(sessions),
        "rows": int(len(all_data)),
        "model_rule_mae_pwm": float(np.abs(difference).mean()),
        "model_rule_bias_pwm": float(difference.mean()),
        "model_rule_correlation": correlation,
        "pir_off_pct": float((all_data["pir"] == 0).mean() * 100),
        "temperature_range_c": [float(all_data["temp_c"].min()), float(all_data["temp_c"].max())],
        "humidity_range_pct": [float(all_data["hum_pct"].min()), float(all_data["hum_pct"].max())],
        "ldr10_range": [int(all_data["ldr10"].min()), int(all_data["ldr10"].max())],
        "calibration_valid_pct": float(all_data.get("cal_valid", pd.Series(dtype=float)).mean() * 100),
        "motion_to_model_change_s": {
            "count": len(latencies),
            "median": float(np.median(latencies)) if latencies else None,
            "p95": float(np.percentile(latencies, 95)) if latencies else None,
        },
        "input_files": [str(path) for path, _, _ in sessions],
    }

    figure, axes = plt.subplots(2, 1, figsize=(7, 5), sharex=False)
    axes[0].plot(all_data["t"], all_data["model_pwm"], label="model PWM", color="black", linewidth=0.7)
    axes[0].plot(all_data["t"], all_data["rule_pwm"], label="rule PWM", color="0.55", linewidth=0.7)
    axes[0].set_ylabel("PWM")
    axes[0].legend(frameon=False)
    axes[1].plot(all_data["t"], all_data["ldr10"], color="black", linewidth=0.7)
    axes[1].set_xlabel("Time within concatenated sessions (s)")
    axes[1].set_ylabel("LDR (0-1023)")
    figure_path = output / "fig_closed_loop.png"
    R.savefig(str(figure_path))

    document = R.new_doc(
        "Step S1.6 Report: Closed-Loop Model Validation",
        "ESP32-S3 real sensor inputs, Random Forest PWM versus rule baseline",
    )
    document.add_heading("1. Method", 1)
    document.add_paragraph(
        "The firmware reads PIR, LDR and DHT11 values every 100 ms, maps the LDR into the model's 0-1023 feature scale, "
        "runs the exported float Random Forest, and drives the LED with the model PWM. A rule baseline uses PIR=0 -> 0 "
        "and a linear 300-700 LDR ramp when PIR=1. Metrics are computed from the captured CSV files."
    )
    R.table(document, ["Metric", "Value"], [
        ["Sessions / rows", f"{summary['sessions']} / {summary['rows']}"],
        ["Model-rule MAE (PWM)", f"{summary['model_rule_mae_pwm']:.2f}"],
        ["Model-rule correlation", f"{summary['model_rule_correlation']:.4f}"],
        ["PIR-off fraction", f"{summary['pir_off_pct']:.2f}%"],
        ["Calibration valid rows", f"{summary['calibration_valid_pct']:.2f}%"],
        ["Motion-to-model change median", str(summary['motion_to_model_change_s']['median']) + " s"],
    ])
    R.picture(document, str(figure_path), "Model/rule PWM and calibrated LDR over the captured sessions.", 6.2)
    document.add_heading("2. Input coverage", 1)
    R.table(document, ["Input", "Minimum", "Maximum"], [
        ["Temperature (C)", f"{summary['temperature_range_c'][0]:.1f}", f"{summary['temperature_range_c'][1]:.1f}"],
        ["Humidity (%)", f"{summary['humidity_range_pct'][0]:.1f}", f"{summary['humidity_range_pct'][1]:.1f}"],
        ["LDR (0-1023)", summary['ldr10_range'][0], summary['ldr10_range'][1]],
    ])
    document.add_heading("3. Limitations", 1)
    document.add_paragraph(
        "The rule baseline is a designed comparator, not ground truth. Results depend on the LDR calibration and the "
        "single-room test setup. Report at least three sessions and retain the raw CSV files before using these numbers in the thesis."
    )
    document.save(output / "S1_6_Report.docx")
    R.dump_json(summary, output / "s1_6_summary.json")
    print(f"Report: {output / 'S1_6_Report.docx'}")
    print(f"Summary: {output / 's1_6_summary.json'}")


if __name__ == "__main__":
    main()
