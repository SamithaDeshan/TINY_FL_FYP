"""S1.4 report: on-device benchmark logs -> thesis-ready DOCX.

    python tools/s1_4_report.py --base data/s1_4_base.csv --model data/s1_4_model.csv --f32 data/s1_4_model_f32.csv \
        [--ram-base 22000 --ram-model 22000 --ram-f32 22000]
Static RAM numbers (optional) are the 'RAM: ... used N bytes' lines of each PlatformIO build.
Capture each log with:  python tools/logger.py --port COM5 --out data/s1_4_model.csv --send R --until "# done"
"""
import argparse
import io
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportlib as R
import matplotlib.pyplot as plt

PAPER = {"flash_kb": 3.2, "ram_kb": 1.0, "latency_ms": 0.3}


def load(path):
    kv, rows = {}, []
    for ln in open(path, encoding="utf-8", errors="replace"):
        ln = ln.rstrip("\r\n")
        if ln.startswith("#"):
            for k, v in re.findall(r"(\w+)=(\S+)", ln):
                kv[k] = v
        elif re.match(r"^\d+,", ln):
            rows.append(ln)
    df = pd.read_csv(io.StringIO("\n".join(rows)), names=["i", "expected", "pred", "abs_diff", "us"]) if rows else None
    return kv, df


def rel(measured, claim):
    if measured is None:
        return "n/a"
    r = measured / claim
    return f"{r:.2f}x the paper value ({'below' if r < 1 else 'above'})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base"); ap.add_argument("--model", required=True); ap.add_argument("--f32")
    ap.add_argument("--ram-base", type=int); ap.add_argument("--ram-model", type=int); ap.add_argument("--ram-f32", type=int)
    ap.add_argument("--out", default="reports/s1_4"); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    runs = {"model (double literals)": (a.model, a.ram_model)}
    if a.f32:
        runs["model (float literals)"] = (a.f32, a.ram_f32)
    base_kv = load(a.base)[0] if a.base else None
    sim = False
    res, fig_data, rows = {}, {}, []
    for name, (path, ram) in runs.items():
        kv, df = load(path)
        sim |= kv.get("source", "").upper() == "SIMULATED"
        if df is None or not len(df):
            sys.exit(f"No data rows in {path}")
        us = df["us"].values.astype(float)
        e = df["abs_diff"].values
        r8 = np.clip((df["pred"] + 0.5).astype(int), 0, 255) == np.clip((df["expected"] + 0.5).astype(int), 0, 255)
        flash_delta = (int(kv["sketch_bytes"]) - int(base_kv["sketch_bytes"])) if base_kv else None
        stack_delta = (int(kv["stack_used_bytes"]) - int(base_kv["stack_used_bytes"])) if base_kv else None
        ram_delta = (ram - a.ram_base) if (ram is not None and a.ram_base is not None) else None
        res[name] = {"n": len(df), "max_abs_diff": float(e.max()), "mean_abs_diff": float(e.mean()),
                     "uint8_equal_pct": float(r8.mean() * 100), "lat_min_us": float(us.min()), "lat_mean_us": float(us.mean()),
                     "lat_median_us": float(np.median(us)), "lat_p99_us": float(np.percentile(us, 99)), "lat_max_us": float(us.max()),
                     "batch_ns": int(kv["batch_ns_per_inference"]), "flash_delta_bytes": flash_delta,
                     "stack_delta_bytes": stack_delta, "static_ram_delta_bytes": ram_delta,
                     "heap_before": int(kv["heap_free_before"]), "heap_after": int(kv["heap_free_after"]),
                     "cpu_mhz": kv.get("cpu_mhz"), "optimisation": kv.get("optimisation"), "sdk": kv.get("sdk"),
                     "core": kv.get("arduino_core")}
        fig_data[name] = us
        rows.append(name)
    first = res[rows[0]]
    fig, ax = plt.subplots(figsize=(5.2, 2.7))
    for (name, us), sty in zip(fig_data.items(), ("0.2", "0.65")):
        ax.hist(us, bins=np.arange(0, max(30, us.max() + 2)), alpha=0.8, color=sty, label=name)
    ax.set_xlabel("Latency per inference (us, timer resolution 1 us)"); ax.set_ylabel("Calls"); ax.legend(frameon=False, fontsize=8)
    fig_path = os.path.join(a.out, "fig_latency.png"); R.savefig(fig_path)

    d = R.new_doc("Step S1.4 Report: On-device Benchmark of the Random Forest",
                  f"TinyFL / Stage 1, ESP32-S3 at {first['cpu_mhz']} MHz, SDK {first['sdk']}, Arduino core {first['core']}, "
                  f"optimisation {first['optimisation']}", simulated=sim)
    d.add_heading("1. Purpose", 1)
    d.add_paragraph("Measure, on the target microcontroller, what the exported model costs in flash, stack, heap and time, "
                    "and confirm that it produces the same predictions as the Python model. These measured figures replace "
                    "estimates in the paper and thesis.")
    d.add_heading("2. Method", 1)
    d.add_paragraph("The firmware embeds 500 held-out test rows with the Python prediction for each. For every row it calls "
                    "predict() on the board and records the output and the call time (esp_timer, 1 us resolution). A 20-pass "
                    "batch gives the mean time in nanoseconds with less quantisation error. Flash cost is the difference in "
                    "firmware size between the model build and a reference build with the model removed; stack use is "
                    "measured in a separate task of 4096 bytes whose high-water mark is read after the work; heap is "
                    "compared before and after. No sensors are involved.")
    d.add_heading("3. Results", 1)
    d.add_heading("3.1 On-device correctness", 2)
    R.table(d, ["Variant", "Rows", "Max abs diff vs Python", "Mean abs diff", "Equal after uint8 rounding"],
            [[k, v["n"], f"{v['max_abs_diff']:.2e}", f"{v['mean_abs_diff']:.2e}", f"{v['uint8_equal_pct']:.2f}%"] for k, v in res.items()])
    R.caption(d, "Table 1. Board predictions compared with the Python model on the same inputs.")
    d.add_heading("3.2 Latency", 2)
    R.table(d, ["Variant", "Batch mean (us)", "Per-call min", "median", "p99", "max (us)"],
            [[k, f"{v['batch_ns']/1000:.2f}", f"{v['lat_min_us']:.0f}", f"{v['lat_median_us']:.0f}",
              f"{v['lat_p99_us']:.0f}", f"{v['lat_max_us']:.0f}"] for k, v in res.items()])
    R.caption(d, "Table 2. Inference time. The batch mean is the most accurate average; per-call values are limited by the 1 us timer.")
    R.picture(d, fig_path, "Figure 1. Distribution of per-call latency.", 4.6)
    d.add_heading("3.3 Memory", 2)
    fm = lambda x: "n/a (no base log)" if x is None else f"{x:,} B"
    R.table(d, ["Variant", "Flash added (B)", "Stack used delta (B)", "Static RAM delta (B)", "Heap change (B)"],
            [[k, fm(v["flash_delta_bytes"]), fm(v["stack_delta_bytes"]), fm(v["static_ram_delta_bytes"]) if v["static_ram_delta_bytes"] is not None else "not supplied",
              f"{v['heap_after'] - v['heap_before']:+d}"] for k, v in res.items()])
    R.caption(d, "Table 3. Resource cost of the model relative to the reference build.")
    d.add_heading("4. Comparison with the published claims", 1)
    R.table(d, ["Quantity", "Paper", "Measured (" + rows[0] + ")", "Relation"], [
        ["Flash", f"~{PAPER['flash_kb']} KB", fm(first["flash_delta_bytes"]),
         rel(first["flash_delta_bytes"] / 1024 if first["flash_delta_bytes"] is not None else None, PAPER["flash_kb"])],
        ["RAM", f"<{PAPER['ram_kb']:.0f} KB", f"stack {fm(first['stack_delta_bytes'])}; heap {first['heap_after']-first['heap_before']:+d} B",
         rel(first["stack_delta_bytes"] / 1024 if first["stack_delta_bytes"] is not None else None, PAPER["ram_kb"])],
        ["Latency", f"~{PAPER['latency_ms']} ms", f"{first['batch_ns']/1e6:.4f} ms", rel(first['batch_ns'] / 1e6, PAPER["latency_ms"])]], [1.0, 1.0, 2.6, 1.9])
    R.caption(d, "Table 4. Published claims versus measured values. Update the paper's Table 6 to the measured numbers.")
    d.add_heading("5. Limitations", 1)
    d.add_paragraph("Latency covers predict() only, not sensor reads or PWM update. Flash delta depends on the compiler "
                    "version and optimisation level, which are stated above; rebuild and re-measure if either changes. "
                    "Stack measurement has the granularity of the RTOS stack fill and is an indication, not an exact figure.")
    d.add_heading("6. Draft text for the thesis", 1)
    d.add_paragraph(f"The exported model was benchmarked on the ESP32-S3 at {first['cpu_mhz']} MHz using {first['n']} held-out "
                    f"test vectors. Board predictions matched the Python model to within {first['max_abs_diff']:.1e} PWM "
                    f"units. Mean inference time was {first['batch_ns']/1000:.1f} us, with a 99th-percentile per-call time of "
                    f"{first['lat_p99_us']:.0f} us. The model added "
                    + (f"{first['flash_delta_bytes']:,} bytes of flash" if first["flash_delta_bytes"] is not None else "[flash, from base build]")
                    + (" and used no heap memory. " if first["heap_after"] == first["heap_before"] else
                       f" and changed free heap by {first['heap_after'] - first['heap_before']:+d} bytes. ")
                    + "a sentence on the float-literal variant if it differs.]")
    d.save(os.path.join(a.out, "S1_4_Report.docx"))
    R.dump_json(res, os.path.join(a.out, "s1_4_summary.json"))
    for k, v in res.items():
        print(k, {x: v[x] for x in ("max_abs_diff", "uint8_equal_pct", "batch_ns", "flash_delta_bytes", "stack_delta_bytes")})


if __name__ == "__main__":
    main()
