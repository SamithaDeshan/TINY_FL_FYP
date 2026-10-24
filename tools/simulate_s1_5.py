"""Generates a SIMULATED Step 1 CSV so the report pipeline can be tested without hardware.
The output is stamped '# source=SIMULATED' and the report prints a warning banner.
NEVER use this data in the thesis."""
import sys

import numpy as np

rng = np.random.default_rng(1)
out = sys.argv[1] if len(sys.argv) > 1 else "data/SIMULATED_s1_5.csv"
lines = ["# source=SIMULATED", "# chip=ESP32-S3 rev=0 cores=2 cpu_mhz=240",
         "# flash_chip_bytes=8388608 sketch_bytes=300000 free_sketch_bytes=1000000",
         "# heap_total=300000 heap_free=250000 min_heap_free=240000",
         "# pins pir=4 ldr=1 dht=5 led_pwm=6 oled_sda=8 oled_scl=9",
         "# dht_type=DHT11 pwm_freq=5000 pwm_res_bits=8 oled=ok",
         "ms,label,pir,ldr_raw,ldr10,temp_c,hum_pct,dht_status,pwm"]
phases = [("warmup", 30, 2000, 0.0), ("dark", 30, 300, 0.0), ("ambient", 30, 1800, 0.0),
          ("bright", 30, 3500, 0.0), ("still", 30, 1800, 0.0), ("motion", 30, 1800, 0.6),
          ("ramp", 10, 1800, 0.0)]
ms, temp, hum, nextdht = 0, 29.0, 68.0, 0
for name, secs, ldr, pm in phases:
    for i in range(secs * 10):
        ms += 100
        raw = int(np.clip(rng.normal(ldr, 25), 0, 4095))
        pir = int(rng.random() < pm) if name == "motion" else 0
        st = 0
        if ms >= nextdht:
            nextdht = ms + 2000
            if rng.random() < 0.03:
                st = -1
            else:
                temp += rng.choice([-1, 0, 0, 0, 1]); hum += rng.choice([-1, 0, 0, 1]); st = 1
        pwm = int(i / (secs * 10) * 255) if name == "ramp" else 0
        lines.append(f"{ms},{name},{pir},{raw},{raw >> 2},{temp:.1f},{hum:.1f},{st},{pwm}")
open(out, "w").write("\n".join(lines) + "\n")
print("wrote", out)
