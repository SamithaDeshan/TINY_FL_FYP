"""Train the Stage 2 neural baseline on development-only data.

Run with the Stage 2 Python environment:
    $env:TF_USE_LEGACY_KERAS = '1'
    .venv312\\Scripts\\python.exe stage2/python/train_nn_dev.py

Outputs are synthetic development artifacts and are not thesis evidence.
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
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import reportlib as R

FEATURES = ["temperature", "humidity", "pir"]


def main():
    stage2 = ROOT / "stage2"
    data_dir = stage2 / "data"
    model_dir = stage2 / "models"
    report_dir = stage2 / "reports" / "phase_a"
    train = pd.read_csv(data_dir / "DEV_ONLY_train.csv")
    test = pd.read_csv(data_dir / "DEV_ONLY_test.csv")
    with open(model_dir / "DEV_ONLY_normalizer.json", encoding="utf-8") as file:
        normalizer = json.load(file)

    mean = np.asarray([normalizer["mean"][feature] for feature in FEATURES], dtype=np.float32)
    std = np.asarray([normalizer["std"][feature] for feature in FEATURES], dtype=np.float32)
    x_all = train[FEATURES].to_numpy(dtype=np.float32)
    y_all = train["anomaly"].to_numpy(dtype=np.float32)
    x_test = test[FEATURES].to_numpy(dtype=np.float32)
    y_test = test["anomaly"].to_numpy(dtype=np.float32)
    x_all = (x_all - mean) / std
    x_test = (x_test - mean) / std

    x_train, x_val, y_train, y_val = train_test_split(
        x_all, y_all, test_size=0.2, random_state=42, stratify=y_all
    )
    negative = max(1, int((y_train == 0).sum()))
    positive = max(1, int((y_train == 1).sum()))
    class_weight = {0: 1.0, 1: negative / positive}

    model = keras.Sequential([
        keras.layers.Input(shape=(3,), name="sensor_features"),
        keras.layers.Dense(16, activation="relu"),
        keras.layers.Dense(8, activation="relu"),
        keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3),
                  loss="binary_crossentropy")
    history = model.fit(
        x_train, y_train,
        validation_data=(x_val, y_val),
        epochs=100,
        batch_size=32,
        class_weight=class_weight,
        callbacks=[keras.callbacks.EarlyStopping(monitor="val_loss", patience=12, restore_best_weights=True)],
        verbose=0,
    )

    probabilities = model.predict(x_test, verbose=0).reshape(-1)
    predicted = (probabilities >= 0.5).astype(int)
    matrix = confusion_matrix(y_test.astype(int), predicted, labels=[0, 1])
    metrics = {
        "accuracy": float(accuracy_score(y_test, predicted)),
        "precision_anomaly": float(precision_score(y_test, predicted, zero_division=0)),
        "recall_anomaly": float(recall_score(y_test, predicted, zero_division=0)),
        "f1_anomaly": float(f1_score(y_test, predicted, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, probabilities)),
        "threshold": 0.5,
        "confusion_matrix_labels_0_1": matrix.tolist(),
        "test_rows": int(len(test)),
    }

    model_path = model_dir / "DEV_ONLY_nn_float.keras"
    model.save(model_path)
    curve_path = report_dir / "fig_dev_nn_training.png"
    figure, axis = plt.subplots(figsize=(5.0, 3.0))
    axis.plot(history.history["loss"], label="train")
    axis.plot(history.history["val_loss"], label="validation")
    axis.set_xlabel("Epoch")
    axis.set_ylabel("Binary cross-entropy")
    axis.legend(frameon=False)
    R.savefig(str(curve_path))

    matrix_path = report_dir / "fig_dev_nn_confusion_matrix.png"
    figure, axis = plt.subplots(figsize=(3.7, 3.1))
    image = axis.imshow(matrix, cmap="Greys")
    axis.set(xticks=[0, 1], yticks=[0, 1], xticklabels=["normal", "anomaly"],
             yticklabels=["normal", "anomaly"], xlabel="Predicted", ylabel="Actual")
    for row in range(2):
        for column in range(2):
            axis.text(column, row, str(matrix[row, column]), ha="center", va="center")
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    R.savefig(str(matrix_path))

    document = R.new_doc(
        "Stage 2 Phase A: Neural Network Baseline",
        "Held-out evaluation on development-only synthetic data",
        simulated=True,
    )
    document.add_heading("1. Architecture and training", 1)
    document.add_paragraph(
        "The classifier is Dense(16, relu) -> Dense(8, relu) -> Dense(1, sigmoid), with binary cross-entropy and Adam. "
        "The three inputs were normalized using statistics fitted on the training split only. Class weighting addresses the "
        "approximately 92/8 normal/anomaly imbalance. Validation data was held out from the training split, and early stopping "
        "restored the best validation-loss weights."
    )
    R.table(document, ["Property", "Value"], [
        ["Parameters", model.count_params()],
        ["Training rows", len(x_train)],
        ["Validation rows", len(x_val)],
        ["Epochs run", len(history.history["loss"])],
        ["Class weight anomaly", f"{class_weight[1]:.3f}"],
    ])
    document.add_heading("2. Held-out test metrics", 1)
    R.table(document, ["Metric", "Value"], [
        ["Accuracy", f"{metrics['accuracy']:.4f}"],
        ["Precision (anomaly)", f"{metrics['precision_anomaly']:.4f}"],
        ["Recall (anomaly)", f"{metrics['recall_anomaly']:.4f}"],
        ["F1 (anomaly)", f"{metrics['f1_anomaly']:.4f}"],
        ["ROC-AUC", f"{metrics['roc_auc']:.4f}"],
    ])
    R.picture(document, str(curve_path), "Training and validation loss.", 5.0)
    R.picture(document, str(matrix_path), "Confusion matrix; rows are actual labels, columns are predictions.", 3.8)
    document.add_heading("3. Interpretation limit", 1)
    document.add_paragraph(
        "These metrics describe a neural network evaluated against labels generated by the development simulator. "
        "They do not measure real-world sensor anomaly detection and must not be cited as thesis or paper results."
    )
    document.save(report_dir / "S2_PhaseA_NN_Report_DEV_ONLY.docx")

    summary = {
        "warning": "DEVELOPMENT-ONLY SYNTHETIC DATA. Do not cite in thesis or paper.",
        "architecture": ["Dense(16,relu)", "Dense(8,relu)", "Dense(1,sigmoid)"],
        "parameters": int(model.count_params()),
        "feature_order": FEATURES,
        "normalizer_source": "stage2/models/DEV_ONLY_normalizer.json",
        "train_rows": int(len(x_train)),
        "validation_rows": int(len(x_val)),
        "test_rows": int(len(x_test)),
        "epochs_run": int(len(history.history["loss"])),
        "class_weight": class_weight,
        "metrics": metrics,
        "model_file": "stage2/models/DEV_ONLY_nn_float.keras",
    }
    with open(report_dir / "DEV_ONLY_nn_summary.json", "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)
    print("DEVELOPMENT-ONLY neural baseline")
    for name, value in metrics.items():
        print(f"{name}: {value}")
    print(f"parameters: {model.count_params()}")
    print(f"epochs_run: {len(history.history['loss'])}")
    print(f"Report: {report_dir / 'S2_PhaseA_NN_Report_DEV_ONLY.docx'}")


if __name__ == "__main__":
    main()
