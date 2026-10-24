"""Two-node FedAvg simulation on development-only data.

Run inside the Stage 2 environment:
    $env:TF_USE_LEGACY_KERAS = '1'
    .venv312\\Scripts\\python.exe stage2/python/fedavg_two_node_dev.py

This is a local simulation of two nodes; it does not require MQTT or boards.
Results are synthetic development artifacts and are not thesis evidence.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tf_keras as keras
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import reportlib as R

FEATURES = ["temperature", "humidity", "pir"]
ROUNDS = 5
LOCAL_EPOCHS = 3


def make_model():
    model = keras.Sequential([
        keras.layers.Input(shape=(3,)),
        keras.layers.Dense(16, activation="relu"),
        keras.layers.Dense(8, activation="relu"),
        keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3), loss="binary_crossentropy")
    return model


def score(model, x_test, y_test):
    probability = model.predict(x_test, verbose=0).reshape(-1)
    prediction = (probability >= 0.5).astype(int)
    return {
        "precision_anomaly": float(precision_score(y_test, prediction, zero_division=0)),
        "recall_anomaly": float(recall_score(y_test, prediction, zero_division=0)),
        "f1_anomaly": float(f1_score(y_test, prediction, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, probability)),
    }


def average_weights(weight_sets, counts):
    total = float(sum(counts))
    return [sum(weights[index] * count for weights, count in zip(weight_sets, counts)) / total
            for index in range(len(weight_sets[0]))]


def main():
    stage2 = ROOT / "stage2"
    data_dir = stage2 / "data"
    report_dir = stage2 / "reports" / "phase_b"
    report_dir.mkdir(parents=True, exist_ok=True)
    train = pd.read_csv(data_dir / "DEV_ONLY_train.csv")
    test = pd.read_csv(data_dir / "DEV_ONLY_test.csv")
    with open(stage2 / "models" / "DEV_ONLY_normalizer.json", encoding="utf-8") as file:
        normalizer = json.load(file)
    mean = np.asarray([normalizer["mean"][feature] for feature in FEATURES], dtype=np.float32)
    std = np.asarray([normalizer["std"][feature] for feature in FEATURES], dtype=np.float32)
    x = (train[FEATURES].to_numpy(dtype=np.float32) - mean) / std
    y = train["anomaly"].to_numpy(dtype=np.float32)
    x_test = (test[FEATURES].to_numpy(dtype=np.float32) - mean) / std
    y_test = test["anomaly"].to_numpy(dtype=np.float32)

    x_node1, x_node2, y_node1, y_node2 = train_test_split(
        x, y, test_size=0.5, random_state=42, stratify=y
    )
    nodes = [("node1", x_node1, y_node1), ("node2", x_node2, y_node2)]
    global_model = make_model()
    global_weights = global_model.get_weights()
    rounds = []
    for round_number in range(1, ROUNDS + 1):
        local_weights = []
        local_counts = []
        local_scores = {}
        for node_name, node_x, node_y in nodes:
            local_model = make_model()
            local_model.set_weights(global_weights)
            negative = max(1, int((node_y == 0).sum()))
            positive = max(1, int((node_y == 1).sum()))
            local_model.fit(
                node_x, node_y, epochs=LOCAL_EPOCHS, batch_size=32,
                class_weight={0: 1.0, 1: negative / positive}, verbose=0,
            )
            local_weights.append(local_model.get_weights())
            local_counts.append(len(node_y))
            local_scores[node_name] = score(local_model, x_test, y_test)
        global_weights = average_weights(local_weights, local_counts)
        global_model.set_weights(global_weights)
        global_score = score(global_model, x_test, y_test)
        rounds.append({"round": round_number, "global": global_score,
                       "local": local_scores, "node_rows": local_counts})

    figure, axis = plt.subplots(figsize=(5.2, 3.0))
    axis.plot([row["round"] for row in rounds], [row["global"]["f1_anomaly"] for row in rounds], marker="o")
    axis.set_xlabel("FedAvg round")
    axis.set_ylabel("Global anomaly F1")
    axis.set_ylim(0, 1)
    figure_path = report_dir / "fig_two_node_fedavg.png"
    R.savefig(str(figure_path))

    summary = {
        "warning": "DEVELOPMENT-ONLY SYNTHETIC DATA. Do not cite in thesis or paper.",
        "nodes": 2,
        "rounds": ROUNDS,
        "local_epochs": LOCAL_EPOCHS,
        "partition": "stratified 50/50 split of the development training set",
        "node_rows": {name: int(len(node_y)) for name, _, node_y in nodes},
        "rounds_detail": rounds,
        "final_global": rounds[-1]["global"],
        "mqtt": False,
    }
    R.dump_json(summary, report_dir / "two_node_fedavg_summary_DEV_ONLY.json")

    document = R.new_doc(
        "Stage 2 Phase B: Two-Node FedAvg Simulation",
        "Two simulated nodes with laptop-side weight aggregation",
        simulated=True,
    )
    document.add_heading("1. Method", 1)
    document.add_paragraph(
        "The development training split was divided into two disjoint, stratified partitions. Both nodes started each round "
        "from the same global neural-network weights, trained locally, and returned weights to a laptop-side aggregator. "
        "The aggregator computed a sample-count-weighted FedAvg update. This run is an in-process simulation and does not use MQTT."
    )
    R.table(document, ["Property", "Value"], [
        ["Nodes", 2], ["Rounds", ROUNDS],
        ["Local epochs per round", LOCAL_EPOCHS],
        ["Node 1 rows", len(x_node1)], ["Node 2 rows", len(x_node2)],
    ])
    R.table(document, ["Round", "Global precision", "Global recall", "Global F1", "Global ROC-AUC"], [
        [row["round"], f"{row['global']['precision_anomaly']:.4f}", f"{row['global']['recall_anomaly']:.4f}",
         f"{row['global']['f1_anomaly']:.4f}", f"{row['global']['roc_auc']:.4f}"] for row in rounds
    ])
    R.picture(document, str(figure_path), "Global anomaly F1 over two-node FedAvg rounds.", 5.2)
    document.add_heading("2. Interpretation limit", 1)
    document.add_paragraph(
        "This report validates two-node weight averaging, not wireless federation. The labels are synthetic and the nodes "
        "run in one Python process. MQTT latency, message loss, and ESP32 inference are not measured here."
    )
    document.save(report_dir / "S2_PhaseB_TwoNode_FedAvg_Report_DEV_ONLY.docx")
    print("DEVELOPMENT-ONLY two-node FedAvg: PASS")
    print(f"Final global metrics: {rounds[-1]['global']}")
    print(f"Report: {report_dir / 'S2_PhaseB_TwoNode_FedAvg_Report_DEV_ONLY.docx'}")


if __name__ == "__main__":
    main()
