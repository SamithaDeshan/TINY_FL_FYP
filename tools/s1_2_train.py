"""S1.2 - Train and compare regression models, then report.

    python tools/s1_2_train.py
Needs data/lighting_dataset.csv (run s1_1_dataset.py first).
Outputs: models/rf_model.joblib, data/train.csv, data/test.csv, reports/s1_2/S1_2_Report.docx (+json, figures)
Protocol follows the Stage 1 paper: 80/20 random split, 5-fold CV on the training part, RF with
n_estimators=10, max_depth=5, random_state=42. Decision tree uses max_depth=5 (same size class as one RF tree).
KNN is run twice: unscaled (paper protocol) and standardised (fair comparison).
"""
import argparse
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import explained_variance_score, max_error, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_validate, learning_curve, train_test_split
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeRegressor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportlib as R
import matplotlib.pyplot as plt

FEATURES = ["pir", "ldr", "temp", "hum"]  # order used by the firmware: {pir, ldr, temp, hum}
PAPER_RF = {"R2": 0.9789, "RMSE": 8.98, "MAE": 4.88}


def models():
    return {"Random Forest (10 trees, depth 5)": RandomForestRegressor(n_estimators=10, max_depth=5, random_state=42),
            "Decision Tree (depth 5)": DecisionTreeRegressor(max_depth=5, random_state=42),
            "Linear Regression": LinearRegression(),
            "KNN k=5 (unscaled, paper protocol)": KNeighborsRegressor(n_neighbors=5),
            "KNN k=5 (standardised)": make_pipeline(StandardScaler(), KNeighborsRegressor(n_neighbors=5))}


def test_metrics(y, p):
    e = y - p
    return {"MSE": mean_squared_error(y, p), "RMSE": mean_squared_error(y, p) ** 0.5, "MAE": mean_absolute_error(y, p),
            "R2": r2_score(y, p), "ExplVar": explained_variance_score(y, p), "MaxAbsErr": max_error(y, p),
            "ErrSD": float(np.std(e)), "ErrMean": float(np.mean(e)), "Over40pct": float((np.abs(e) > 40).mean() * 100)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="reports/s1_2"); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); os.makedirs(os.path.join(R.ROOT, "models"), exist_ok=True)
    df = pd.read_csv(os.path.join(R.ROOT, "data", "lighting_dataset.csv"))
    X, y = df[FEATURES].values.astype(float), df["pwm"].values.astype(float)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
    pd.DataFrame(Xtr, columns=FEATURES).assign(pwm=ytr).to_csv(os.path.join(R.ROOT, "data", "train.csv"), index=False)
    pd.DataFrame(Xte, columns=FEATURES).assign(pwm=yte).to_csv(os.path.join(R.ROOT, "data", "test.csv"), index=False)

    cv_rows, te_rows, res = [], [], {"n_train": len(Xtr), "n_test": len(Xte), "models": {}}
    fitted = {}
    for name, m in models().items():
        cv = cross_validate(m, Xtr, ytr, cv=5, scoring=("neg_mean_squared_error", "r2"))
        mse = -cv["test_neg_mean_squared_error"]
        m.fit(Xtr, ytr); fitted[name] = m
        tm = test_metrics(yte, m.predict(Xte))
        res["models"][name] = {"cv_mse_mean": mse.mean(), "cv_mse_sd": mse.std(), "cv_rmse": mse.mean() ** 0.5,
                               "cv_r2_mean": cv["test_r2"].mean(), "cv_r2_sd": cv["test_r2"].std(), "test": tm}
        cv_rows.append([name, f"{mse.mean():.2f} +/- {mse.std():.2f}", f"{mse.mean()**0.5:.2f}",
                        f"{cv['test_r2'].mean():.4f} +/- {cv['test_r2'].std():.4f}"])
        te_rows.append([name, f"{tm['RMSE']:.2f}", f"{tm['MAE']:.2f}", f"{tm['R2']:.4f}", f"{tm['MaxAbsErr']:.1f}"])
    rf_name = list(fitted)[0]; rf = fitted[rf_name]
    joblib.dump(rf, os.path.join(R.ROOT, "models", "rf_model.joblib"))
    best_cv = max(res["models"], key=lambda k: res["models"][k]["cv_r2_mean"])
    tm = res["models"][rf_name]["test"]

    # ---- importance, residuals, learning curve ----
    imp = dict(zip(FEATURES, rf.feature_importances_)); res["importance"] = imp
    pred = rf.predict(Xte); resid = yte - pred
    fig, ax = plt.subplots(1, 2, figsize=(6.5, 2.8))
    ax[0].scatter(yte, pred, s=3, color="black"); ax[0].plot([0, 255], [0, 255], color="0.5", lw=0.8)
    ax[0].set_xlabel("Actual PWM"); ax[0].set_ylabel("Predicted PWM")
    ax[1].hist(resid, bins=40, color="0.3"); ax[1].set_xlabel("Residual (actual - predicted)"); ax[1].set_ylabel("Samples")
    f_pred = os.path.join(a.out, "fig_pred_resid.png"); R.savefig(f_pred)
    sizes, trs, vas = learning_curve(RandomForestRegressor(n_estimators=10, max_depth=5, random_state=42), Xtr, ytr,
                                     train_sizes=np.linspace(0.05, 1.0, 8), cv=5, scoring="r2")
    fig, ax = plt.subplots(figsize=(4.8, 2.7))
    ax.plot(sizes, trs.mean(1), "k--o", ms=3, label="Training"); ax.plot(sizes, vas.mean(1), "k-s", ms=3, label="Validation")
    ax.set_xlabel("Training samples"); ax.set_ylabel("R2"); ax.legend(frameon=False, fontsize=8)
    f_lc = os.path.join(a.out, "fig_learning_curve.png"); R.savefig(f_lc)
    fig, ax = plt.subplots(figsize=(4.8, 2.4))
    order = sorted(imp, key=imp.get)
    ax.barh(order, [imp[k] * 100 for k in order], color="0.3"); ax.set_xlabel("Importance (%)")
    f_imp = os.path.join(a.out, "fig_importance.png"); R.savefig(f_imp)
    res["learning_curve"] = {"sizes": sizes.tolist(), "train": trs.mean(1).tolist(), "val": vas.mean(1).tolist()}
    plateau = next((int(s) for s, v in zip(sizes, vas.mean(1)) if v >= vas.mean(1)[-1] - 0.005), int(sizes[-1]))
    res["plateau_samples"] = plateau
    res["best_cv_model"] = best_cv

    d = R.new_doc("Step S1.2 Report: Model Training and Comparison",
                  "TinyFL / Stage 1, regression of LED PWM from PIR, LDR, temperature and humidity")
    d.add_heading("1. Purpose", 1)
    d.add_paragraph("Compare candidate regressors on the S1.1 dataset with evidence rather than assumption, and fix the "
                    "model that will be exported to C for the ESP32-S3.")
    d.add_heading("2. Method", 1)
    d.add_paragraph(f"The dataset (S1.1) was split 80/20 at random with seed 42 ({len(Xtr)} training, {len(Xte)} test "
                    "samples). Each candidate was scored by 5-fold cross-validation on the training part, then refitted on "
                    "the whole training part and scored once on the held-out test part. Feature order is "
                    "[PIR, LDR, temperature, humidity], matching the firmware. The Random Forest uses 10 trees, maximum "
                    "depth 5 (small enough for a microcontroller). The decision tree uses depth 5. KNN (k = 5) is "
                    "reported both on raw features, as in the published paper, and on standardised features, because "
                    "unscaled distances are dominated by the 0-1023 LDR range.")
    d.add_heading("3. Results", 1)
    d.add_heading("3.1 Cross-validation", 2)
    R.table(d, ["Model", "MSE (mean +/- SD)", "RMSE", "R2 (mean +/- SD)"], cv_rows, [2.6, 1.6, 0.8, 1.5])
    R.caption(d, "Table 1. 5-fold cross-validation on the training set.")
    d.add_heading("3.2 Held-out test set", 2)
    R.table(d, ["Model", "RMSE", "MAE", "R2", "Max abs error"], te_rows, [2.8, 0.8, 0.8, 0.9, 1.2])
    R.caption(d, "Table 2. Test-set performance of all models.")
    R.table(d, ["Random Forest metric", "Value"], [
        ["MSE", f"{tm['MSE']:.2f}"], ["RMSE", f"{tm['RMSE']:.2f}"], ["MAE", f"{tm['MAE']:.2f} ({tm['MAE']/255*100:.1f}% of full scale)"],
        ["R2", f"{tm['R2']:.4f}"], ["Explained variance", f"{tm['ExplVar']*100:.1f}%"], ["Max abs error", f"{tm['MaxAbsErr']:.1f}"],
        ["Error SD", f"{tm['ErrSD']:.2f}"], ["Error mean", f"{tm['ErrMean']:+.2f}"],
        ["Samples with |error| > 40", f"{tm['Over40pct']:.2f}%"]], [3.0, 2.5])
    R.caption(d, "Table 3. Detailed test-set metrics of the selected Random Forest.")
    R.picture(d, f_pred, "Figure 1. Left: actual vs predicted PWM on the test set. Right: residual distribution.")
    d.add_heading("3.3 Feature importance and learning curve", 2)
    R.table(d, ["Rank", "Feature", "Importance", "%"],
            [[i + 1, k, f"{imp[k]:.3f}", f"{imp[k]*100:.1f}"] for i, k in enumerate(sorted(imp, key=imp.get, reverse=True))])
    R.caption(d, "Table 4. Random Forest feature importance (impurity based).")
    R.picture(d, f_imp, "Figure 2. Feature importance.", 4.2)
    R.picture(d, f_lc, f"Figure 3. Learning curve; validation R2 is within 0.005 of its final value from about {plateau} samples.", 4.5)
    d.add_heading("4. Comparison with the published paper", 1)
    R.table(d, ["Random Forest metric", "Published (original dataset)", "This rebuild (S1.1 dataset)"],
            [["R2", f"{PAPER_RF['R2']}", f"{tm['R2']:.4f}"], ["RMSE", f"{PAPER_RF['RMSE']}", f"{tm['RMSE']:.2f}"],
             ["MAE", f"{PAPER_RF['MAE']}", f"{tm['MAE']:.2f}"]], [2.0, 2.2, 2.3])
    R.caption(d, "Table 5. The published figures came from a different generated dataset, so differences are expected.")
    d.add_paragraph("Do not mix the two sets of numbers inside one document. Either update the paper/thesis tables to the "
                    "values in this report (recommended, because they are reproducible from the seeded scripts) or "
                    "locate the original generator and dataset.")
    d.add_heading("5. Limitations", 1)
    d.add_paragraph("Scores measure how well a model recovers the designed rule set from noisy synthetic inputs, not "
                    "agreement with real occupants. The impurity-based importance is biased towards features with many "
                    "split points and is indicative only. One random split is used; the cross-validation SD gives the "
                    "spread.")
    d.add_heading("6. Draft text for the thesis", 1)
    d.add_paragraph(f"Four regression algorithms were compared using 5-fold cross-validation on {len(Xtr)} training samples. "
                    f"The best cross-validated model was {best_cv} (R2 = {res['models'][best_cv]['cv_r2_mean']:.4f}). The "
                    f"selected Random Forest (10 trees, depth 5) achieved R2 = {tm['R2']:.4f}, RMSE = {tm['RMSE']:.2f} and "
                    f"MAE = {tm['MAE']:.2f} PWM units ({tm['MAE']/255*100:.1f}% of full scale) on the {len(Xte)}-sample "
                    f"held-out set. PIR ({imp['pir']*100:.1f}%) and LDR ({imp['ldr']*100:.1f}%) dominated the feature "
                    "importance, consistent with occupancy-based control and daylight harvesting. [State here whether the "
                    "Random Forest was chosen for accuracy, size, or both, citing Table 1 and the S1.3 footprint.]")
    d.save(os.path.join(a.out, "S1_2_Report.docx"))
    R.dump_json(res, os.path.join(a.out, "s1_2_summary.json"))
    print("\n".join(" | ".join(r) for r in te_rows)); print("best CV model:", best_cv)
    print("RF importance:", {k: round(v, 3) for k, v in imp.items()}, "plateau", plateau)


if __name__ == "__main__":
    main()
