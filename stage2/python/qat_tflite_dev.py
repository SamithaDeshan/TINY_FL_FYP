"""QAT fine-tuning and full-int8 TFLite conversion for development-only data.

Run inside the Stage 2 environment:
    $env:TF_USE_LEGACY_KERAS = '1'
    .venv312\\Scripts\\python.exe stage2/python/qat_tflite_dev.py

All outputs are synthetic development artifacts and are not thesis evidence.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import tensorflow as tf
import tensorflow_model_optimization as tfmot
import tf_keras as keras
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import reportlib as R

FEATURES = ["temperature", "humidity", "pir"]


def metrics_for(labels, probabilities):
    predictions = (probabilities >= 0.5).astype(int)
    return {
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision_anomaly": float(precision_score(labels, predictions, zero_division=0)),
        "recall_anomaly": float(recall_score(labels, predictions, zero_division=0)),
        "f1_anomaly": float(f1_score(labels, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
    }


def write_header(model_bytes, path):
    with open(path, "w", encoding="utf-8") as file:
        file.write("#pragma once\n#include <cstdint>\n\n")
        file.write("alignas(8) const unsigned char g_model[] = {\n")
        for start in range(0, len(model_bytes), 12):
            chunk = model_bytes[start:start + 12]
            file.write("  " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",\n")
        file.write("};\n")
        file.write(f"const unsigned int g_model_len = {len(model_bytes)};\n")


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
    x_train = ((train[FEATURES].to_numpy(dtype=np.float32) - mean) / std)
    y_train = train["anomaly"].to_numpy(dtype=np.float32)
    x_test = ((test[FEATURES].to_numpy(dtype=np.float32) - mean) / std)
    y_test = test["anomaly"].to_numpy(dtype=np.float32)

    model = keras.models.load_model(model_dir / "DEV_ONLY_nn_float.keras")
    qat_model = tfmot.quantization.keras.quantize_model(model)
    negative = max(1, int((y_train == 0).sum()))
    positive = max(1, int((y_train == 1).sum()))
    class_weight = {0: 1.0, 1: negative / positive}
    qat_model.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-4), loss="binary_crossentropy")
    qat_history = qat_model.fit(
        x_train, y_train, validation_split=0.2, epochs=10, batch_size=32,
        class_weight=class_weight, verbose=0,
    )

    float_probabilities = model.predict(x_test, verbose=0).reshape(-1)
    qat_probabilities = qat_model.predict(x_test, verbose=0).reshape(-1)
    float_metrics = metrics_for(y_test, float_probabilities)
    qat_metrics = metrics_for(y_test, qat_probabilities)

    def representative_dataset():
        for row in x_train[:300]:
            yield [row.reshape(1, -1).astype(np.float32)]

    converter = tf.lite.TFLiteConverter.from_keras_model(qat_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite_bytes = converter.convert()
    tflite_path = model_dir / "DEV_ONLY_model_int8.tflite"
    tflite_path.write_bytes(tflite_bytes)
    write_header(tflite_bytes, model_dir / "DEV_ONLY_model_data.h")

    interpreter = tf.lite.Interpreter(model_content=tflite_bytes)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]
    input_scale, input_zero = input_details["quantization"]
    output_scale, output_zero = output_details["quantization"]
    tflite_probabilities = []
    for row in x_test:
        quantized = np.round(row / input_scale + input_zero).clip(-128, 127).astype(np.int8)
        interpreter.set_tensor(input_details["index"], quantized.reshape(1, -1))
        interpreter.invoke()
        output = interpreter.get_tensor(output_details["index"])[0, 0]
        tflite_probabilities.append((float(output) - output_zero) * output_scale)
    tflite_probabilities = np.asarray(tflite_probabilities)
    tflite_metrics = metrics_for(y_test, tflite_probabilities)

    with open(model_dir / "DEV_ONLY_model_params.json", "w", encoding="utf-8") as file:
        json.dump({
            "warning": "DEVELOPMENT-ONLY synthetic model; not thesis evidence",
            "feature_order": FEATURES,
            "normalizer": normalizer,
            "input_scale": float(input_scale),
            "input_zero_point": int(input_zero),
            "output_scale": float(output_scale),
            "output_zero_point": int(output_zero),
            "tflite_bytes": len(tflite_bytes),
        }, file, indent=2)

    summary = {
        "warning": "DEVELOPMENT-ONLY SYNTHETIC DATA. Do not cite in thesis or paper.",
        "qat_epochs": len(qat_history.history["loss"]),
        "float_metrics": float_metrics,
        "qat_metrics": qat_metrics,
        "int8_tflite_metrics": tflite_metrics,
        "tflite_bytes": len(tflite_bytes),
        "input_quantization": {"scale": float(input_scale), "zero_point": int(input_zero)},
        "output_quantization": {"scale": float(output_scale), "zero_point": int(output_zero)},
        "model_files": {
            "tflite": "stage2/models/DEV_ONLY_model_int8.tflite",
            "header": "stage2/models/DEV_ONLY_model_data.h",
            "params": "stage2/models/DEV_ONLY_model_params.json",
        },
    }
    R.dump_json(summary, report_dir / "DEV_ONLY_qat_tflite_summary.json")

    document = R.new_doc(
        "Stage 2 Phase A: QAT and int8 TFLite Development Check",
        "Full-int8 conversion on development-only synthetic data",
        simulated=True,
    )
    document.add_heading("1. Method", 1)
    document.add_paragraph(
        "The float neural baseline was wrapped with quantization-aware training and fine-tuned for 10 epochs. "
        "A representative set of 300 normalized training rows was used for full-int8 TFLite conversion. "
        "The resulting model was executed with tf.lite.Interpreter on the held-out test set."
    )
    R.table(document, ["Metric", "Float", "QAT", "int8 TFLite"], [
        [name, f"{float_metrics[name]:.4f}", f"{qat_metrics[name]:.4f}", f"{tflite_metrics[name]:.4f}"]
        for name in ("accuracy", "precision_anomaly", "recall_anomaly", "f1_anomaly", "roc_auc")
    ])
    R.table(document, ["Artifact", "Value"], [
        ["TFLite size", f"{len(tflite_bytes):,} bytes"],
        ["Input scale / zero point", f"{input_scale} / {input_zero}"],
        ["Output scale / zero point", f"{output_scale} / {output_zero}"],
    ])
    document.add_heading("2. Interpretation limit", 1)
    document.add_paragraph(
        "This conversion proves the development pipeline can produce and execute a full-int8 model. "
        "All metrics are based on synthetic labels and must not be presented as real anomaly-detection performance."
    )
    document.save(report_dir / "S2_PhaseA_QAT_TFLite_Report_DEV_ONLY.docx")
    print("DEVELOPMENT-ONLY QAT/TFLite pipeline: PASS")
    print(f"TFLite bytes: {len(tflite_bytes)}")
    print(f"float metrics: {float_metrics}")
    print(f"qat metrics: {qat_metrics}")
    print(f"int8 metrics: {tflite_metrics}")
    print(f"Report: {report_dir / 'S2_PhaseA_QAT_TFLite_Report_DEV_ONLY.docx'}")


if __name__ == "__main__":
    main()
