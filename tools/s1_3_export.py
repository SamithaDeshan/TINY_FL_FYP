"""S1.3 - Export the Random Forest to C (micromlgen), verify it on the host, report footprint trade-offs.

    pip install micromlgen
    python tools/s1_3_export.py
Needs models/rf_model.joblib and data/test.csv (run s1_2_train.py first) and g++ for the host parity test.
Outputs into arduino/s1_4_benchmark: smart_light_model.h (micromlgen as-is), smart_light_model_f32.h
(same model, float literals instead of double), test_vectors.h (first 500 test rows + Python predictions).
"""
import argparse
import os
import re
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportlib as R
import matplotlib.pyplot as plt

try:
    from micromlgen import port
except ImportError:
    sys.exit("micromlgen is not installed. Run: pip install micromlgen")

FEATURES = ["pir", "ldr", "temp", "hum"]
N_VEC = 500


def to_f32(code):
    code = re.sub(r"(?<![\w.])(\d+\.\d+)(?![\w.])", r"\1f", code)
    code = code.replace("y_pred / 10;", "y_pred / 10.0f;")
    return code.replace("class RandomForestRegressor", "class RandomForestRegressorF32")


def host_run(header, cls, test_csv, workdir):
    exe = os.path.join(workdir, "parity_" + cls.split("::")[-1])
    cmd = ["g++", "-O2", f'-DMODEL_HEADER="{header}"', f"-DMODEL_CLASS={cls}",
           os.path.join(R.ROOT, "tools", "host_parity.cpp"), "-o", exe]
    subprocess.run(cmd, check=True)
    out = subprocess.run([exe, test_csv], check=True, capture_output=True, text=True).stdout.split()
    return np.array(out, dtype=float)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="reports/s1_3"); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    fw = os.path.join(R.ROOT, "arduino", "s1_4_benchmark"); os.makedirs(fw, exist_ok=True)
    rf = joblib.load(os.path.join(R.ROOT, "models", "rf_model.joblib"))
    test = pd.read_csv(os.path.join(R.ROOT, "data", "test.csv")); train = pd.read_csv(os.path.join(R.ROOT, "data", "train.csv"))
    Xte, yte = test[FEATURES].values, test["pwm"].values
    code = port(rf); code32 = to_f32(code)
    h1, h2 = os.path.join(fw, "smart_light_model.h"), os.path.join(fw, "smart_light_model_f32.h")
    open(h1, "w").write(code); open(h2, "w").write(code32)
    pred_py = rf.predict(Xte)
    with open(os.path.join(fw, "test_vectors.h"), "w") as f:
        f.write(f"#pragma once\n// {N_VEC} held-out test rows and the Python (float64) Random Forest prediction for each.\n")
        f.write(f"#define TV_N {N_VEC}\nstatic const float TV_X[TV_N][4] = {{\n")
        for r in Xte[:N_VEC]:
            f.write("  {" + ", ".join(f"{v:.1f}f" for v in r) + "},\n")
        f.write("};\nstatic const float TV_Y[TV_N] = {\n")
        for v in pred_py[:N_VEC]:
            f.write(f"  {v:.6f}f,\n")
        f.write("};\n")

    # ---- host parity ----
    tcsv = os.path.join(R.ROOT, "data", "test.csv")
    par = {}
    for tag, hdr, cls in (("micromlgen (double literals)", h1, "Eloquent::ML::Port::RandomForestRegressor"),
                          ("float-literal variant", h2, "Eloquent::ML::Port::RandomForestRegressorF32")):
        c = host_run(hdr, cls, tcsv, a.out)
        dlt = np.abs(c - pred_py)
        r8 = np.clip((c + 0.5).astype(int), 0, 255); p8 = np.clip((pred_py + 0.5).astype(int), 0, 255)
        par[tag] = {"max_abs_diff": float(dlt.max()), "mean_abs_diff": float(dlt.mean()),
                    "uint8_equal_pct": float((r8 == p8).mean() * 100), "r2_c": float(r2_score(yte, c)), "n": len(c),
                    "bytes": os.path.getsize(hdr)}

    # ---- structure + trade-off sweep ----
    trees = [e.tree_ for e in rf.estimators_]
    nodes = sum(t.node_count for t in trees); leaves = sum(t.n_leaves for t in trees)
    depth = max(t.max_depth for t in trees)
    Xtr, ytr = train[FEATURES].values, train["pwm"].values
    sweep = []
    for ne in (1, 5, 10, 20, 50):
        for dp in (3, 4, 5, 6, 8):
            m = RandomForestRegressor(n_estimators=ne, max_depth=dp, random_state=42).fit(Xtr, ytr)
            sweep.append({"trees": ne, "depth": dp, "r2": r2_score(yte, m.predict(Xte)),
                          "nodes": sum(e.tree_.node_count for e in m.estimators_)})
    sw = pd.DataFrame(sweep)
    fig, ax = plt.subplots(figsize=(5.2, 3.0))
    ax.scatter(sw.nodes, sw.r2, s=14, color="0.5")
    sel = sw[(sw.trees == 10) & (sw.depth == 5)].iloc[0]
    ax.scatter([sel.nodes], [sel.r2], s=60, facecolors="none", edgecolors="black", linewidths=1.5, label="Selected (10 trees, depth 5)")
    ax.set_xscale("log"); ax.set_xlabel("Total tree nodes (proxy for flash size)"); ax.set_ylabel("Test R2")
    ax.legend(frameon=False, fontsize=8)
    f_sw = os.path.join(a.out, "fig_tradeoff.png"); R.savefig(f_sw)

    d = R.new_doc("Step S1.3 Report: Conversion to C and Host Verification",
                  "TinyFL / Stage 1, Random Forest to dependency-free C++ for the ESP32-S3")
    d.add_heading("1. Purpose", 1)
    d.add_paragraph("The ESP32-S3 cannot run a scikit-learn model, so the trained Random Forest is converted to nested "
                    "if/else C++ with micromlgen. Before any hardware is involved, this step proves on the host that the "
                    "generated code reproduces the Python model, and quantifies the size/accuracy trade-off behind the "
                    "choice of 10 trees and depth 5.")
    d.add_heading("2. Method", 1)
    d.add_paragraph("The saved model from S1.2 was exported with micromlgen. A second header was derived from it by adding "
                    "the f suffix to every numeric literal, because the generated code uses double-precision constants "
                    "and the ESP32-S3 has a single-precision FPU only; S1.4 measures whether this matters. Both headers "
                    "were compiled with g++ -O2 and run on every held-out test row; the outputs were compared with "
                    "the Python predictions. Feature order is {PIR, LDR, temperature, humidity}.")
    d.add_heading("3. Results", 1)
    R.table(d, ["Property", "Value"], [["Trees", len(trees)], ["Maximum depth", depth], ["Total nodes", nodes],
                                      ["Total leaves", leaves], ["Features", ", ".join(FEATURES)]], [2.5, 3.0])
    R.caption(d, "Table 1. Structure of the exported model.")
    R.table(d, ["Variant", "Source bytes", "Max abs diff vs Python", "Mean abs diff", "Equal after uint8 rounding", "R2 of C output"],
            [[k, v["bytes"], f"{v['max_abs_diff']:.2e}", f"{v['mean_abs_diff']:.2e}", f"{v['uint8_equal_pct']:.2f}%",
              f"{v['r2_c']:.4f}"] for k, v in par.items()], [1.7, 0.8, 1.1, 0.9, 1.1, 0.9], size=8.5)
    R.caption(d, f"Table 2. Host parity test on {len(yte)} held-out rows. Source size is text size, not flash size.")
    d.add_heading("3.1 Size versus accuracy", 2)
    piv = sw.pivot(index="trees", columns="depth", values="r2")
    R.table(d, ["Trees \\ depth"] + [str(c) for c in piv.columns],
            [[str(i)] + [f"{v:.4f}" for v in row] for i, row in piv.iterrows()])
    R.caption(d, "Table 3. Test R2 for different forest sizes (trained on the S1.2 training set).")
    pn = sw.pivot(index="trees", columns="depth", values="nodes")
    R.table(d, ["Trees \\ depth"] + [str(c) for c in pn.columns],
            [[str(i)] + [str(int(v)) for v in row] for i, row in pn.iterrows()])
    R.caption(d, "Table 4. Total tree nodes for the same configurations.")
    R.picture(d, f_sw, "Figure 1. Accuracy versus model size for 25 configurations.", 4.6)
    d.add_heading("4. Output files", 1)
    d.add_paragraph("arduino/s1_4_benchmark/smart_light_model.h, smart_light_model_f32.h and test_vectors.h "
                    f"(the first {N_VEC} test rows with the expected prediction). Flash, RAM and latency are measured "
                    "on the board in S1.4; node counts here are only a proxy.")
    d.add_heading("5. Limitations", 1)
    d.add_paragraph("Host parity shows the C code equals the Python model, not that the model is right for real rooms. "
                    "The host uses a different compiler and CPU from the ESP32-S3, so tiny floating-point differences "
                    "can still appear on the board; S1.4 checks this directly.")
    d.add_heading("6. Draft text for the thesis", 1)
    p = par["micromlgen (double literals)"]
    d.add_paragraph(f"The trained Random Forest ({len(trees)} trees, depth {depth}, {nodes} nodes) was converted to "
                    "dependency-free C++ using micromlgen. On the held-out test set, the generated code reproduced the "
                    f"Python predictions with a maximum absolute difference of {p['max_abs_diff']:.1e} PWM units, and "
                    f"{p['uint8_equal_pct']:.2f}% of outputs were identical after conversion to the 8-bit PWM value.")
    d.save(os.path.join(a.out, "S1_3_Report.docx"))
    R.dump_json({"trees": len(trees), "depth": depth, "nodes": nodes, "leaves": leaves, "parity": par,
                 "sweep": sweep}, os.path.join(a.out, "s1_3_summary.json"))
    for k, v in par.items():
        print(k, v)


if __name__ == "__main__":
    main()
