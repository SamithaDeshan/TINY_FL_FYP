"""S1.1 - Generate the physics-based smart-lighting dataset and its report.

    python tools/s1_1_dataset.py            # 10,000 samples, seed 42
Outputs: data/lighting_dataset.csv, data/lighting_dataset_meta.json,
         reports/s1_1/S1_1_Report.docx (+ figures, summary json)

Design (all assumptions are written into the report):
  true state : occupied ~ Bernoulli(0.5); LDR ~ U(0,1023); T ~ U(15,35) C; RH ~ U(30,80) %
  label      : PIR=0 -> 0 ; PIR=1 -> 255*clip((700-LDR)/400,0,1) - comfort term + N(0,3^2), clipped 0..255, rounded
               (LDR<=300 -> full output, LDR>=700 -> off, linear in between = daylight harvesting)
  features   : true values + sensor noise (LDR N(0,10^2), T N(0,0.5^2), RH N(0,2^2), PIR flipped with 2 %),
               temperature and humidity rounded to integers because the rig uses a DHT11.
"""
import argparse
import hashlib
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportlib as R
import matplotlib.pyplot as plt

P = dict(n=10000, seed=42, p_occ=0.5, ldr_lo=300, ldr_hi=700, k_t=0.003, k_h=0.0015, t_ref=25, h_ref=55,
         label_sd=3.0, ldr_noise=10.0, t_noise=0.5, h_noise=2.0, pir_flip=0.02)


def generate(p=P):
    rng = np.random.default_rng(p["seed"])
    n = p["n"]
    occ = (rng.random(n) < p["p_occ"]).astype(int)
    ldr = rng.uniform(0, 1023, n)
    t = rng.uniform(15, 35, n)
    h = rng.uniform(30, 80, n)
    day = np.clip((p["ldr_hi"] - ldr) / (p["ldr_hi"] - p["ldr_lo"]), 0, 1)
    comfort = 255 * (p["k_t"] * (t - p["t_ref"]) + p["k_h"] * (h - p["h_ref"]))
    y = occ * (255 * day - comfort) + rng.normal(0, p["label_sd"], n)
    y = np.rint(np.clip(y, 0, 255)).astype(int)
    pir = np.where(rng.random(n) < p["pir_flip"], 1 - occ, occ)
    f_ldr = np.rint(np.clip(ldr + rng.normal(0, p["ldr_noise"], n), 0, 1023)).astype(int)
    f_t = np.rint(np.clip(t + rng.normal(0, p["t_noise"], n), 15, 35)).astype(int)
    f_h = np.rint(np.clip(h + rng.normal(0, p["h_noise"], n), 30, 80)).astype(int)
    return pd.DataFrame({"pir": pir, "ldr": f_ldr, "temp": f_t, "hum": f_h, "pwm": y})


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="reports/s1_1"); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); os.makedirs(os.path.join(R.ROOT, "data"), exist_ok=True)
    df = generate()
    csv = os.path.join(R.ROOT, "data", "lighting_dataset.csv")
    df.to_csv(csv, index=False)
    sha = hashlib.sha256(open(csv, "rb").read()).hexdigest()[:16]
    R.dump_json({"params": P, "sha256_16": sha}, os.path.join(R.ROOT, "data", "lighting_dataset_meta.json"))

    # ---- checks ----
    chk = [("No missing values", bool(df.notna().all().all()), f"{int(df.isna().sum().sum())} missing"),
           ("PIR binary", set(df.pir.unique()) <= {0, 1}, "values " + ",".join(str(int(v)) for v in sorted(df.pir.unique()))),
           ("LDR within 0-1023", bool(df.ldr.between(0, 1023).all()), f"{df.ldr.min()}-{df.ldr.max()}"),
           ("Temperature within 15-35 C", bool(df.temp.between(15, 35).all()), f"{df.temp.min()}-{df.temp.max()}"),
           ("Humidity within 30-80 %", bool(df.hum.between(30, 80).all()), f"{df.hum.min()}-{df.hum.max()}"),
           ("Target within 0-255", bool(df.pwm.between(0, 255).all()), f"{df.pwm.min()}-{df.pwm.max()}")]
    # ---- figures ----
    fig, ax = plt.subplots(1, 2, figsize=(6.5, 2.7))
    for v, mk, c in ((1, "o", "black"), (0, "x", "0.55")):
        s = df[df.pir == v].sample(800, random_state=0)
        ax[0].scatter(s.ldr, s.pwm, s=4, marker=mk, color=c, label=f"PIR = {v}")
    ax[0].set_xlabel("LDR (0-1023)"); ax[0].set_ylabel("Target PWM"); ax[0].legend(frameon=False, fontsize=7)
    ax[1].hist(df.pwm, bins=32, color="0.3"); ax[1].set_xlabel("Target PWM"); ax[1].set_ylabel("Samples")
    f1 = os.path.join(a.out, "fig_overview.png"); R.savefig(f1)
    corr = df.corr()["pwm"].drop("pwm")

    d = R.new_doc("Step S1.1 Report: Synthetic Smart-Lighting Dataset",
                  "TinyFL / Stage 1, from-scratch rebuild on the ESP32-S3 rig")
    d.add_heading("1. Purpose", 1)
    d.add_paragraph("No labelled dataset linking PIR, LDR, temperature and humidity readings to a suitable LED brightness "
                    "exists, so a physics-inspired synthetic dataset is generated. It is the single starting point for "
                    "model training (S1.2), C export (S1.3) and on-device benchmarking (S1.4). The generator is "
                    f"deterministic (seed {P['seed']}) so every number in later reports can be reproduced.")
    d.add_heading("2. Generation method", 1)
    d.add_paragraph("Each sample draws a true room state, derives the target brightness from lighting heuristics, and then "
                    "produces noisy sensor features, so the model must learn to see through realistic sensor error.")
    R.table(d, ["Item", "Definition"], [
        ["Occupancy", f"Bernoulli({P['p_occ']})"],
        ["Ambient light", "LDR ~ Uniform(0, 1023) (10-bit scale used by the model)"],
        ["Temperature / humidity", "Uniform(15, 35) C / Uniform(30, 80) %"],
        ["Daylight harvesting", f"day = clip((700 - LDR) / 400, 0, 1): full output at LDR <= {P['ldr_lo']}, off at LDR >= {P['ldr_hi']}"],
        ["Comfort term", f"255 x ({P['k_t']} x (T - 25) + {P['k_h']} x (RH - 55)): warm/humid rooms are lit slightly less"],
        ["Target PWM", "0 if unoccupied, else 255 x day - comfort; plus N(0, 3^2); clipped 0-255; rounded"],
        ["Sensor noise", f"LDR N(0, {P['ldr_noise']:.0f}^2); T N(0, {P['t_noise']}^2); RH N(0, {P['h_noise']:.0f}^2); "
                         f"PIR flipped with probability {P['pir_flip']:.0%}"],
        ["Quantisation", "Temperature and humidity rounded to integers (the rig uses a DHT11)"]], [1.6, 4.9])
    R.caption(d, "Table 1. Generator definition. All coefficients are modelling assumptions, not measured values.")
    d.add_heading("3. Dataset summary", 1)
    desc = df.describe().T[["mean", "std", "min", "max"]]
    R.table(d, ["Column", "Mean", "SD", "Min", "Max"],
            [[c, f"{r['mean']:.2f}", f"{r['std']:.2f}", f"{r['min']:.0f}", f"{r['max']:.0f}"] for c, r in desc.iterrows()])
    R.caption(d, f"Table 2. Descriptive statistics, n = {len(df)} (SHA-256 prefix {sha}).")
    R.picture(d, f1, "Figure 1. Left: target PWM versus LDR (800 samples per PIR state). Right: target distribution.")
    at0, at255 = (df.pwm == 0).mean() * 100, (df.pwm == 255).mean() * 100
    d.add_paragraph(f"{df.pir.mean()*100:.1f}% of samples have PIR = 1. {at0:.1f}% of targets are 0 (lights off) and "
                    f"{at255:.1f}% are 255 (full brightness); the remainder is the daylight-harvesting ramp. "
                    "Pearson correlation with the target: " +
                    ", ".join(f"{k} {v:+.2f}" for k, v in corr.items()) + ".")
    d.add_heading("4. Data integrity checks", 1)
    R.table(d, ["Check", "Result", "Evidence"], [[c, "PASS" if ok else "FAIL", e] for c, ok, e in chk], [2.4, 0.8, 3.3])
    R.caption(d, "Table 3. Automated integrity checks.")
    d.add_heading("5. Limitations", 1)
    d.add_paragraph("The target function is a designed rule set, so a model that scores highly has learned the rules, not "
                    "real occupant preference. The coefficients and noise levels are assumptions. Real-sensor "
                    "validation (S1.5 and S1.6) is what tests whether the synthetic ranges and the 300/700 LDR "
                    "thresholds hold on the actual prototype.")
    d.add_heading("6. Draft text for the thesis", 1)
    d.add_paragraph(f"A synthetic dataset of {len(df):,} samples was generated with a fixed random seed. Occupancy, ambient "
                    "light, temperature and humidity were sampled uniformly over the ranges of the target environment, and "
                    "the target PWM was computed from occupancy-based and daylight-harvesting rules with a small "
                    "temperature/humidity comfort adjustment. Gaussian sensor noise, a 2% PIR error rate and DHT11 "
                    "integer quantisation were then applied to the features.")
    d.save(os.path.join(a.out, "S1_1_Report.docx"))
    R.dump_json({"n": len(df), "sha256_16": sha, "pir_high_pct": df.pir.mean() * 100, "pwm_zero_pct": at0,
                 "pwm_full_pct": at255, "corr_with_target": corr.to_dict(),
                 "checks": [{"check": c, "pass": ok, "evidence": e} for c, ok, e in chk]},
                os.path.join(a.out, "s1_1_summary.json"))
    print(f"{len(df)} rows -> {csv}\nreport -> {a.out}/S1_1_Report.docx")
    for c, ok, e in chk:
        print(("PASS " if ok else "FAIL ") + c + " - " + e)


if __name__ == "__main__":
    main()
