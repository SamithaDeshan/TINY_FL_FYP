# TinyFL - Detailed instructions for the next stages

Environment assumed: Windows, Arduino IDE, Python. Where something is not built yet it says **[TO BUILD]**:
tell me "build <step>" and I will generate the script/sketch and the matching Word report.
Items marked **[VERIFY]** are version-dependent facts I could not confirm from here; check them the first time.

Rule for every step: run it, keep the CSV/log in `data/`, generate the report, copy the numbers from the report
into the thesis. Never type results by hand and never cite anything named `SIMULATED_*`.

---------------------------------------------------------------------
## PART 1 - Close out Stage 1
---------------------------------------------------------------------

### 1.1 Run S1.4 (ESP32-S3 only, no sensors) - about 30 minutes
Goal: replace the paper's estimated 3.2 KB flash / <1 KB RAM / ~0.3 ms with measured values.

1. Arduino IDE > File > Open > `arduino/s1_4_benchmark/s1_4_benchmark.ino`.
2. Tools: Board = ESP32S3 Dev Module, Port = your COM port,
   USB CDC On Boot = Enabled (native USB port) or Disabled (UART port).
3. Line `#define VARIANT_CHOICE 0` (base, no model) > Upload. Note "Global variables use N bytes" in the output pane.
4. Capture the output:
   - Python: close the Serial Monitor, then
     `python tools/logger.py --port COM5 --out data/s1_4_base.csv --send R --until "# done"`
   - or Serial Monitor (115200, "Newline"): type `R`, Enter, wait for `# done`, copy all output into `data/s1_4_base.csv`.
5. Set `VARIANT_CHOICE 1` > Upload > capture to `data/s1_4_model.csv`. Then `2` > `data/s1_4_model_f32.csv`.
6. `python tools/s1_4_report.py --base data/s1_4_base.csv --model data/s1_4_model.csv --f32 data/s1_4_model_f32.csv`
   (add `--ram-base N --ram-model N --ram-f32 N` using the numbers from step 3).
7. Open `reports/s1_4/S1_4_Report.docx`.

Pass criteria: on-device max difference vs Python below 1e-3; 100% equal after uint8 rounding.
If parity fails, do not continue; send me the CSV.
Write down: flash added, stack delta, mean latency (batch), and whether float literals are faster than double.

### 1.2 Run S1.5 (needs sensors wired) - about 20 minutes
Wiring check first: PIR (HC-SR501) powered from 5 V, output to GPIO4 (3.3 V logic); LDR in a divider to GPIO1
(LDR to 3.3 V, fixed resistor about 10 kohm to GND, midpoint to GPIO1); DHT11 data to GPIO5 with 10 kohm pull-up to 3.3 V
if your module has none; LED on GPIO6 through 220-330 ohm; OLED SDA 8, SCL 9.

1. Open `arduino/s1_5_bringup/s1_5_bringup.ino`, install the four libraries (see README), Upload.
2. Wait 60 s for the PIR to warm up. Close the Serial Monitor.
3. `python tools/logger.py --port COM5 --out data/s1_5_session1.csv`
4. Type each label, then do the action for about 30 s:
   `L warmup` (stay still) | `L dark` (cover LDR) | `L ambient` | `L bright` (phone torch at LDR) |
   `L still` | `L motion` (wave in front of PIR) | `L ramp` then `R` (LED ramp, point LED at LDR if you want a response curve).
5. Ctrl+C, then `python tools/s1_5_report.py data/s1_5_session1.csv`.
6. Take a photo of the rig and the PIR potentiometer positions for the thesis.

If a check FAILS: LDR polarity inverted -> swap LDR and resistor, or invert in firmware; PIR always high -> wait longer,
turn the sensitivity pot down; DHT11 failures -> check pull-up and wiring, never poll faster than 1 s.

### 1.3 S1.6 closed-loop validation **[TO BUILD]**
Goal: close the paper's Section VI-D limitation with real sensor inputs.
Plan: firmware reads PIR/LDR/DHT11, maps LDR to the model's 0-1023 scale using the S1.5 dark/bright values,
runs the Random Forest, drives the LED, and logs inputs, model PWM and a rule-based baseline PWM
(PIR=0 off; else linear 300-700 LDR ramp) every 100 ms for at least 3 sessions of 10 minutes
(empty room, normal use, lights/daylight changing). Report: agreement model vs rule (MAE, correlation),
fraction of time PIR-off, input ranges versus the synthetic ranges, response time from motion to LED change.
Optional energy comparison: needs a USB power meter or INA219; compare "model" vs "always on" vs "rule-based".

### 1.4 Update the paper (do this after 1.1-1.3)
- Replace Tables 3-5 and Figures 3-6 with S1.2 outputs, or locate the original generator. Never mix both.
- Replace Table 6 with S1.4 measured values; fill the empty Table 7 (ESP32-S3 parameters: 240 MHz, 12-bit ADC,
  LEDC 5 kHz 8-bit, PIR/LDR/DHT11 pins).
- Change DHT22 to DHT11 and LCD to OLED, or swap the hardware. State the 12-bit ADC -> 10-bit mapping.
- In Limitations, state what S1.5/S1.6 did and did not cover (single room, no lux meter).
- Remove the wording "hardware-verified" for anything not measured by S1.4-S1.6.

### Stage 1 "done" checklist
[ ] S1.4 report generated, parity PASS   [ ] S1.5 report generated, checks reviewed
[ ] S1.6 done or listed as a limitation  [ ] paper tables/figures from one consistent dataset
[ ] DHT11 / OLED / ADC wording fixed     [ ] all `data/` and `reports/` files backed up

---------------------------------------------------------------------
## PART 2 - Stage 2: TinyFL federated anomaly detection
---------------------------------------------------------------------
Task: binary anomaly flag from DHT11 temperature, humidity and PIR. Two or three identical ESP32-S3 nodes
(your notes say 3 nodes; the roadmap PDF says 2: decide and use one number everywhere), MQTT via Mosquitto,
adapted FedAvg on a laptop, int8 TFLite Micro model below 50 KB, energy-aware duty cycling.

### One-time setup
1. Install **Python 3.11 or 3.12** (64-bit) **[VERIFY: TensorFlow support for newer Python]** and make a virtual env:
   `py -3.12 -m venv .venv` then `.venv\Scripts\activate`.
2. `pip install numpy pandas scikit-learn matplotlib python-docx joblib paho-mqtt pyserial tensorflow tensorflow-model-optimization tf_keras`
3. Quantisation-aware training with tensorflow-model-optimization may need the legacy Keras: set the environment variable
   `TF_USE_LEGACY_KERAS=1` before starting Python **[VERIFY]**. Run a tiny QAT test first (Step 6) before relying on it.
4. Install Mosquitto for Windows (mosquitto.org). Create `mosquitto.conf` with
   `listener 1883` and `allow_anonymous true` (lab network only). Start: `mosquitto -c mosquitto.conf -v`.
   Allow port 1883 in Windows Defender Firewall (private network).
5. Arduino libraries for Phase C/D: **PubSubClient** (MQTT), **DHT sensor library** + Adafruit Unified Sensor,
   and a TensorFlow Lite Micro library for ESP32, for example **Chirale_TensorFlowLite**
   (https://reference.arduino.cc/reference/en/libraries/chirale_tensorflowlite) **[VERIFY: it compiles for ESP32-S3
   with your core version; if not, use Espressif's esp-tflite-micro]**.

Layout to create: `stage2/data`, `stage2/models`, `stage2/python`, `stage2/arduino`, `stage2/reports`.
Reuse `tools/reportlib.py` for every Stage 2 report.

### Phase A - Data and model (offline, no hardware)

**Step 1 - dataset (DONE per roadmap)**
Check `tinyfl_dataset.csv`: 5,000 rows; columns temperature, humidity, pir, anomaly; about 8% anomalies; temperature 24-35 C,
humidity 60-90%. Put it in `stage2/data/`. **[TO BUILD]** a data report (class balance, anomaly types, distributions)
so the thesis can describe it. If you have only the file and not its generator, say so in the thesis.
Decision to record: DHT11 gives integer values; the dataset should be rounded the same way.

**Step 2 - stratified 80/20 split**
`train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)`; save `train.csv`, `test.csv`; check both keep about 8% anomalies.
Report: counts and anomaly ratio per split. Also fit the normaliser (min/max or mean/std) on **train only** and save its
numbers: they must be hard-coded into the firmware in Step 13.

**Step 3 - neural network**
Keras: Dense(16, relu) -> Dense(8, relu) -> Dense(1, sigmoid); Adam; binary cross-entropy; normalised inputs.
Handle the 92/8 imbalance (class weights or report precision/recall, not accuracy alone). Hold out 10-20% of train for
validation; use early stopping. Save `models/nn_float.keras` and the training curves.
Report: architecture, parameter count (16*3+16 + 8*16+8 + 8+1 = 209), curves, threshold choice.

**Step 4 - Random Forest baseline**
The roadmap says RandomForestRegressor, but the task is classification: use **RandomForestClassifier** (or state clearly that a
regressor output is thresholded). Same split, same features. Offline only.

**Step 5 - evaluate both on the held-out test set**
Accuracy, precision, recall, F1 (anomaly = positive class), confusion matrix, ROC-AUC. Report both models side by side.
Pick the decision threshold on validation data, not on test data.

**Step 6 - quantisation-aware training**
Wrap the trained model with `tfmot.quantization.keras.quantize_model`, fine-tune about 10 epochs at a low learning rate.
If it fails on Keras 3, use legacy Keras (setup item 3). Report float vs QAT metrics.

**Step 7 - convert to int8 TFLite**
`TFLiteConverter` with `Optimize.DEFAULT`, a representative dataset (a few hundred normalised training rows),
`inference_input_type` and `inference_output_type` = int8, `supported_ops = [TFLITE_BUILTIN_INT8]`.
Re-evaluate the .tflite model on the test set in Python (`tf.lite.Interpreter`); record the metric loss from quantisation.
Save the input and output scale/zero-point: the firmware needs them.

**Step 8 - size check**
File size must be below 50 KB (NFR-1). A 209-parameter int8 model is a few KB, so the real limit will be the TFLM runtime.
Report the .tflite size and, later, the compiled sketch size.

**Step 9 - model_data.h**
Python: write the bytes as `alignas(8) const unsigned char g_model[] = {...}; const unsigned int g_model_len = N;`
(or `xxd -i model.tflite` if you have it). Also write `model_params.h` with normaliser values and int8 scale/zero-point.
Verify by checksum: print the checksum in Python and from the firmware in Phase C.

### Phase B - Federated logic (offline)

**Step 10 - FedAvg in pure Python**
Split the training set into two (or three) node partitions (state whether IID or not; for the thesis also try a skewed split).
Train a local model per node from the same initial weights, average the weights (weighted by sample count), evaluate the
global model. Run 5-10 rounds. Report: per-round global F1, local-only vs federated vs centralised comparison.

**Step 11 - MQTT round trip**
Topic plan: `tinyfl/node/<id>/result` (node -> aggregator), `tinyfl/node/<id>/weights`, `tinyfl/global/update`,
`tinyfl/global/consensus`. Scripts: `node1.py`, `node2.py`, `aggregator.py` with paho-mqtt.
paho-mqtt 2.x needs `mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)`. JSON messages with round number, node id, payload, timestamp.
Aggregator waits for all live nodes, then publishes. Add a timeout so a missing node does not stall a round.
Measure: round latency, message size, loss rate over 100 rounds. Run against local Mosquitto.

**Step 12 - real training over MQTT**
Each simulated node trains locally and publishes real weights; aggregator averages and publishes the global model;
nodes load it. Report the same metrics as Step 10, now with message sizes and round times.
Design note for the thesis: the roadmap's on-device aggregation exchanges inference results and confidence scores
(consensus), while weight FedAvg happens offline; state exactly which of the two the hardware demo performs.

### Phase C - Firmware preparation (desk-checked, board optional)

**Step 13 - node firmware (Arduino IDE)**
Loop: read DHT11 (at most once per second) and PIR, normalise with `model_params.h`, quantise to int8, `interpreter->Invoke()`,
dequantise, apply threshold, publish `{node, round, y, conf, mode, ts}` with PubSubClient. Allocate the tensor arena statically
(start at 8 KB and tune); print `arena_used_bytes()`. Never send raw sensor readings (privacy boundary).
Reconnect Wi-Fi and MQTT with back-off. Also log locally over serial for Step 18.

**Step 14 - energy manager**
Battery divider (two equal 100 kohm resistors) from the cell to an **ADC1** pin (GPIO1-10; avoid ADC2, which conflicts with Wi-Fi)
and not GPIO4/5 (PIR/DHT). Use a protected Li-ion cell with a proper charger/regulator board; never wire a bare cell to the 3.3 V pin.
`readBatteryVoltage()` averages 16 samples and applies a measured calibration factor (compare with a multimeter).
`decideMode()` with hysteresis: normal above about 3.8 V, eco 3.5-3.8 V, critical below 3.5 V **[tune from your cell's discharge curve]**.
Modes change the sampling/publish interval and use light sleep between samples; critical mode publishes rarely and sleeps.

**Step 15 - desk-check with mocked inputs**
Compile a test sketch (or a host build) that feeds scripted sensor and ADC values, including edge cases: DHT read failure,
battery just above/below each threshold, MQTT down. Confirm every branch and that the quantised model on the board gives
the same outputs as Python for 100 stored test rows (same method as S1.4 parity).

### Phase D - Physical testbed

**Step 16 - flash the nodes**
Same sketch and same `model_data.h` on every board; only the node id differs (set by one `#define` or read from the MAC).
Check the model checksum on every board.

**Step 17 - run the system**
Laptop: Mosquitto + `aggregator.py`. Nodes on the same Wi-Fi. Controlled scenarios: normal, injected heat (hair dryer/warm
air), humidity (breath/steam), unusual motion pattern. Log ground truth by writing the scenario label with timestamps.

**Step 18 - measurements (the thesis numbers)**
- Accuracy / precision / recall / F1 / confusion matrix against the ground-truth labels, per node and for the consensus.
- Inference latency (microseconds around `Invoke()`), end-to-end latency (publish to consensus received).
- Memory: sketch size, global RAM, tensor arena used, minimum free heap (`ESP.getMinFreeHeap()`).
- Battery decay: log voltage every minute for each mode until cut-off (several hours; start early, run overnight).
  Optional: USB power meter or INA219 for current, giving mAh per hour per mode.
- Repeat each scenario at least 3 times and report mean and spread.
**[TO BUILD]** log parser + report for each of these (same pattern as S1.4).

**Step 19 - comparison**
Table: Stage 1 footprint, TinyFL measured values, and published figures for TinyFed, TinyFedTL and Ficco et al. Use only numbers you
can cite from those papers; say where the setups are not comparable (different hardware, task, dataset).

### Phase E - Writing

**Step 20 - results into the IEEE paper**
Replace placeholders with the report tables/figures; use black-and-white-safe figures; every number traceable to a `*_summary.json`.

**Step 21 - final checks**
IEEE checklist: two columns, margins, caption style, reference consistency (Harvard in the thesis, IEEE numbers in the paper),
abstract length, figure resolution (300 dpi), spell check, and a "claims audit": every sentence with a number points to a report.

---------------------------------------------------------------------
## Suggested order and time
---------------------------------------------------------------------
1. S1.4 run (30 min) -> 2. S1.5 run (20 min) -> 3. Stage 2 Steps 2-9 (one evening) -> 4. Steps 10-12 (one evening) ->
5. S1.6 build and run (one day) -> 6. Steps 13-15 (two days) -> 7. Steps 16-18 (several days; battery tests are slow) ->
8. Steps 19-21 and paper/thesis (rest of the time).

Thesis mapping: dataset and methods -> Ch3/Ch4; implementation and measurements -> Ch6; discussion and limitations -> Ch7.
Open risks: scope growth (lock the scope before Step 13), battery tests taking longer than planned, TFLM library version
problems on ESP32-S3, and Wi-Fi/MQTT reliability affecting round timing.
