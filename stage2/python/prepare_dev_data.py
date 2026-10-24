"""Create clearly marked development-only Stage 2 data and a stratified split.

Run from any directory with the project's Python dependencies installed:
    python stage2/python/prepare_dev_data.py

These synthetic outputs are for pipeline development only, not thesis evidence.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import reportlib as R

FEATURES = ["temperature", "humidity", "pir"]
ANOMALY_TYPES = ["temperature_event", "humidity_event", "pir_burst"]


def generate_dataset(rows, anomaly_rate, seed):
    if rows < 20:
        raise ValueError("Use at least 20 rows for a stratified 80/20 split.")
    if not 0 < anomaly_rate < 0.5:
        raise ValueError("Anomaly rate must be between 0 and 0.5.")

    rng = np.random.default_rng(seed)
    anomaly_rows = round(rows * anomaly_rate)
    normal_rows = rows - anomaly_rows
    base, remainder = divmod(anomaly_rows, len(ANOMALY_TYPES))
    type_sizes = [base + (index < remainder) for index in range(len(ANOMALY_TYPES))]

    samples = []

    def add_group(count, temperature, humidity, pir, anomaly, anomaly_type):
        samples.extend(zip(
            rng.integers(*temperature, size=count),
            rng.integers(*humidity, size=count),
            pir(count),
            np.full(count, anomaly, dtype=int),
            np.full(count, anomaly_type, dtype=object),
        ))

    # Nominal sensor conditions and PIR activity are explicit simulation assumptions.
    add_group(normal_rows, (24, 32), (60, 81),
              lambda count: rng.binomial(1, 0.08, size=count), 0, "normal")

    add_group(type_sizes[0], (32, 36), (60, 81),
              lambda count: rng.binomial(1, 0.08, size=count), 1, ANOMALY_TYPES[0])
    add_group(type_sizes[1], (24, 32), (81, 91),
              lambda count: rng.binomial(1, 0.08, size=count), 1, ANOMALY_TYPES[1])
    add_group(type_sizes[2], (24, 32), (60, 81),
              lambda count: np.ones(count, dtype=int), 1, ANOMALY_TYPES[2])

    order = rng.permutation(rows)
    values = np.asarray(samples, dtype=object)[order]
    return pd.DataFrame({
        "sample_id": np.arange(rows, dtype=int),
        "temperature": values[:, 0].astype(int),
        "humidity": values[:, 1].astype(int),
        "pir": values[:, 2].astype(int),
        "anomaly": values[:, 3].astype(int),
        "anomaly_type": values[:, 4].astype(str),
    })


def make_report(dataset, train, test, normalizer, output_dir, seed, anomaly_rate):
    figure_path = output_dir / "fig_dev_data_distributions.png"
    figure, axes = plt.subplots(1, 3, figsize=(7.0, 2.8))
    colors = {0: "0.65", 1: "0.15"}
    for label, color in colors.items():
        subset = dataset[dataset["anomaly"] == label]
        axes[0].hist(subset["temperature"], bins=np.arange(23.5, 36.5, 1),
                     alpha=0.65, color=color, label="anomaly" if label else "normal")
        axes[1].hist(subset["humidity"], bins=np.arange(59.5, 91.5, 1),
                     alpha=0.65, color=color)
    axes[0].set_xlabel("Temperature (C)")
    axes[0].set_ylabel("Samples")
    axes[0].legend(frameon=False, fontsize=7)
    axes[1].set_xlabel("Humidity (%)")
    axes[2].bar(["normal", "anomaly"], dataset.groupby("anomaly")["pir"].mean().reindex([0, 1]),
                color=[colors[0], colors[1]])
    axes[2].set_ylim(0, 1)
    axes[2].set_ylabel("PIR high fraction")
    R.savefig(str(figure_path))

    type_counts = dataset["anomaly_type"].value_counts().reindex(["normal", *ANOMALY_TYPES], fill_value=0)
    split_rows = []
    for split_name, frame in (("Train", train), ("Test", test)):
        counts = frame["anomaly"].value_counts().reindex([0, 1], fill_value=0)
        split_rows.append([split_name, len(frame), int(counts[0]), int(counts[1]),
                           f"{counts[1] / len(frame) * 100:.2f}%"])

    document = R.new_doc(
        "Stage 2 Phase A: Development Data and Split",
        "TinyFL federated anomaly detection; reproducible synthetic pipeline check",
        simulated=True,
    )
    document.add_heading("1. Data source and scope", 1)
    document.add_paragraph(
        "This dataset is generated from explicit software assumptions because no Stage 2 anomaly CSV was present. "
        "It is for validating the data pipeline only. It is not measured sensor data and must not be used as thesis or paper evidence."
    )
    document.add_heading("2. Synthetic label rules", 1)
    R.table(document, ["Class/type", "Generated conditions"], [
        ["Normal", "Temperature 24-31 C, humidity 60-80%; PIR high with probability 8%"],
        ["temperature_event", "Temperature 32-35 C; humidity 60-80%"],
        ["humidity_event", "Temperature 24-31 C; humidity 81-90%"],
        ["pir_burst", "Nominal temperature/humidity; PIR high"],
    ], [1.5, 4.8])
    document.add_paragraph(
        "DHT11-like temperature and humidity values are integer-valued. The PIR burst is a synthetic single-row proxy; "
        "it does not model a temporal motion sequence."
    )
    document.add_heading("3. Dataset and split", 1)
    R.table(document, ["Type", "Rows"], [[name, int(count)] for name, count in type_counts.items()])
    R.table(document, ["Split", "Rows", "Normal", "Anomaly", "Anomaly rate"], split_rows)
    R.picture(document, str(figure_path), "Synthetic feature distributions by generated label.", 6.2)
    document.add_heading("4. Train-only normalization", 1)
    R.table(document, ["Feature", "Train mean", "Train population SD"], [
        [feature, f"{normalizer['mean'][feature]:.5f}", f"{normalizer['std'][feature]:.5f}"]
        for feature in FEATURES
    ])
    document.add_paragraph("Normalization is z-score scaling; statistics were fitted on training rows only (ddof=0).")
    document.add_heading("5. Limitations", 1)
    document.add_paragraph(
        "The labels are directly constructed from the generated conditions, so model results measure recovery of these "
        "assumptions, not real-world anomaly detection. Replace this dataset with the actual Stage 2 dataset before "
        "drawing scientific conclusions or citing metrics."
    )
    document.save(output_dir / "S2_PhaseA_Data_Report_DEV_ONLY.docx")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--anomaly-rate", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    stage2 = ROOT / "stage2"
    data_dir = stage2 / "data"
    model_dir = stage2 / "models"
    report_dir = stage2 / "reports" / "phase_a"
    for directory in (data_dir, model_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)

    dataset = generate_dataset(args.rows, args.anomaly_rate, args.seed)
    train, test = train_test_split(dataset, test_size=0.2, random_state=args.seed,
                                   stratify=dataset["anomaly"])
    train = train.reset_index(drop=True)
    test = test.reset_index(drop=True)

    mean = train[FEATURES].mean()
    std = train[FEATURES].std(ddof=0)
    if (std == 0).any():
        raise ValueError("Cannot normalize a constant training feature.")
    normalizer = {
        "source": "development-only synthetic data; not thesis evidence",
        "method": "z-score",
        "ddof": 0,
        "feature_order": FEATURES,
        "train_rows": len(train),
        "mean": {feature: float(mean[feature]) for feature in FEATURES},
        "std": {feature: float(std[feature]) for feature in FEATURES},
    }

    dataset_path = data_dir / "DEV_ONLY_synthetic_tinyfl_dataset.csv"
    train_path = data_dir / "DEV_ONLY_train.csv"
    test_path = data_dir / "DEV_ONLY_test.csv"
    dataset.to_csv(dataset_path, index=False)
    train.to_csv(train_path, index=False)
    test.to_csv(test_path, index=False)
    with open(model_dir / "DEV_ONLY_normalizer.json", "w", encoding="utf-8") as file:
        json.dump(normalizer, file, indent=2)

    checks = {
        "row_count": len(dataset) == args.rows,
        "binary_labels": set(dataset["anomaly"].unique()) == {0, 1},
        "pir_binary": set(dataset["pir"].unique()) <= {0, 1},
        "integer_dht_values": all(pd.api.types.is_integer_dtype(dataset[column]) for column in ("temperature", "humidity")),
        "temperature_range": bool(dataset["temperature"].between(24, 35).all()),
        "humidity_range": bool(dataset["humidity"].between(60, 90).all()),
        "disjoint_splits": set(train["sample_id"]).isdisjoint(set(test["sample_id"])),
        "all_samples_split": len(train) + len(test) == len(dataset),
    }
    if not all(checks.values()):
        raise RuntimeError(f"Development data integrity check failed: {checks}")

    make_report(dataset, train, test, normalizer, report_dir, args.seed, args.anomaly_rate)
    summary = {
        "warning": "DEVELOPMENT-ONLY SYNTHETIC DATA. Do not cite in thesis or paper.",
        "rows": len(dataset),
        "seed": args.seed,
        "requested_anomaly_rate": args.anomaly_rate,
        "actual_anomaly_rate": float(dataset["anomaly"].mean()),
        "type_counts": {str(key): int(value) for key, value in dataset["anomaly_type"].value_counts().items()},
        "train_rows": len(train),
        "test_rows": len(test),
        "train_anomaly_rate": float(train["anomaly"].mean()),
        "test_anomaly_rate": float(test["anomaly"].mean()),
        "normalizer": normalizer,
        "checks": checks,
        "files": {
            "dataset": str(dataset_path.relative_to(ROOT)),
            "train": str(train_path.relative_to(ROOT)),
            "test": str(test_path.relative_to(ROOT)),
            "normalizer": "stage2/models/DEV_ONLY_normalizer.json",
            "report": "stage2/reports/phase_a/S2_PhaseA_Data_Report_DEV_ONLY.docx",
        },
    }
    R.dump_json(summary, str(report_dir / "phase_a_summary_DEV_ONLY.json"))
    print(f"DEVELOPMENT-ONLY synthetic data: {dataset_path}")
    print(f"Train/test: {len(train)}/{len(test)} rows; anomaly rate {dataset['anomaly'].mean():.2%}")
    print(f"Report: {report_dir / 'S2_PhaseA_Data_Report_DEV_ONLY.docx'}")
    print("Integrity checks: PASS")


if __name__ == "__main__":
    main()