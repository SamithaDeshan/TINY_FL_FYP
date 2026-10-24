# TinyFL hardware project - Stage 1 rebuilt from scratch

Rig (your pin map): OLED SDA 8 / SCL 9 (0x3C), PIR 4, LDR 1, DHT11 5, LED PWM 6 (5 kHz, 8-bit).
Every step produces `reports/<step>/S1_x_Report.docx` (tables, plain figures, checks, draft thesis paragraph)
and a `*_summary.json` with the numbers, so thesis tables are never retyped by hand.

## One-time setup (Windows, Arduino IDE)
1. Arduino IDE > Boards Manager > install **esp32 by Espressif Systems**.
2. Library Manager > install **Adafruit SSD1306**, **Adafruit GFX Library**, **DHT sensor library** (Adafruit),
   **Adafruit Unified Sensor** (accept "install all dependencies"). Only S1.5 needs these.
3. Tools menu for both sketches: Board = **ESP32S3 Dev Module**; Port = your COM port;
   **USB CDC On Boot = Enabled** if you plug into the USB port marked USB (native), **Disabled** for the UART/COM port.
4. Terminal in this folder: `pip install numpy pandas scikit-learn matplotlib python-docx joblib micromlgen pyserial`
5. S1.3 host test needs `g++` (MSYS2/MinGW).

## Steps (S1.1 to S1.3 need no hardware; reports for them are already in `reports/`)
| Step | Run | Output | Feeds |
|---|---|---|---|
| S1.1 dataset | `python tools/s1_1_dataset.py` | `data/lighting_dataset.csv`, report | paper Sec. III-A/B, thesis methodology |
| S1.2 train + compare | `python tools/s1_2_train.py` | `models/rf_model.joblib`, report | paper Tables 3-5, Figs 3-6 |
| S1.3 export to C + host check | `python tools/s1_3_export.py` | model headers in `arduino/s1_4_benchmark`, report | paper Sec. V-A |
| S1.4 on-device benchmark (ESP32-S3 only, no sensors) | see below | report | paper Tables 6-7 (replaces estimates) |
| S1.5 sensor bring-up (needs sensors wired) | see below | report | thesis sensor characterisation, paper Sec. II-A |
| S1.6 closed loop on real inputs | not built yet | | paper Sec. VI-D |

All scripts are seeded, so re-running gives identical numbers.

## S1.4 on the board (Arduino IDE)
1. File > Open > `arduino/s1_4_benchmark/s1_4_benchmark.ino` (keep it inside its own folder with the .h files).
2. Near the top set `#define VARIANT_CHOICE 0` (base: model removed). Click **Upload**.
   Note the line "Global variables use N bytes" from the build output (optional, for static RAM).
3. Capture the output, either way:
   - Python: close the Serial Monitor, then
     `python tools/logger.py --port COM5 --out data/s1_4_base.csv --send R --until "# done"`
   - or Serial Monitor (115200 baud, line ending "Newline"): type `R`, Enter, wait for `# done`,
     select all output, paste into a text file saved as `data/s1_4_base.csv`.
4. Change to `VARIANT_CHOICE 1` (model, saves as `data/s1_4_model.csv`), Upload, capture. Then `2` (model_f32).
5. `python tools/s1_4_report.py --base data/s1_4_base.csv --model data/s1_4_model.csv --f32 data/s1_4_model_f32.csv`
   (add `--ram-base N --ram-model N --ram-f32 N` with the numbers from step 2 if you noted them).
If the board prints nothing, switch USB port or flip "USB CDC On Boot".

## S1.5 sensor bring-up (when sensors are wired)
Open `arduino/s1_5_bringup/s1_5_bringup.ino`, Upload, close the Serial Monitor, then
`python tools/logger.py --port COM5 --out data/s1_5_session1.csv`.
While logging type (Enter after each, about 30 s each): `L warmup`, `L dark` (cover LDR), `L ambient`, `L bright`
(torch), `L still`, `L motion` (wave at PIR), `L ramp` then `R`. Ctrl+C, then
`python tools/s1_5_report.py data/s1_5_session1.csv`.

## Things to decide before the paper/thesis are final
- **Numbers differ from the published paper.** This rebuild uses a new seeded dataset: RF R2 is about 0.938 (paper 0.9789),
  max error is large because 2% of PIR readings are simulated as wrong (parameter `pir_flip` in `s1_1_dataset.py`),
  and a single depth-5 tree scores the same as the 10-tree forest. Either update the paper to these numbers or find the
  original generator. Do not mix the two.
- Paper says **DHT22**; rig has **DHT11** (integers, about +/-2 C, +/-5 %RH). The new dataset is DHT11-quantised.
- Paper's LDR scale is **0-1023**; the ESP32-S3 ADC is 12-bit (firmware logs `raw >> 2`). Run S1.5 to check LDR polarity.
- Paper's KNN result (R2 0.11) used unscaled features; S1.2 also reports standardised KNN for a fair comparison.
- Paper prototype figure lists an **LCD**; rig has an **OLED**.
- HC-SR501 needs 5 V supply (3.3 V logic out) and about 60 s warm-up.

Files named `SIMULATED_*` (if any appear) are pipeline tests only; never cite them.
