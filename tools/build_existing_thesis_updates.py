"""Build a KDU-styled companion document with verified thesis chapter updates.

The source thesis is a PDF and is not modified. This file generates ready-to-review
replacement/additional sections for Chapters 3-7 based on saved project reports.
"""
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "Previous Thesis Works" / "KDU_TinyFL_Thesis_Chapter_Updates_Revised.docx"


def font(run, size=12, bold=None, italic=None):
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def paragraph(doc, text, italic=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(6)
    font(p.add_run(text), 12, italic=italic)
    return p


def add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_after = Pt(3)
        font(p.add_run(item), 12)


def heading(doc, text, level=2):
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.keep_with_next = True
    if level == 1:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        font(p.add_run(text.upper()), 14, bold=True)
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        font(p.add_run(text), 12, bold=True)
    return p


def table(doc, caption, headers, rows, size=9.5):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing = 1.0
    font(p.add_run(caption), 10, bold=True)
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, title in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = str(title)
        shade = OxmlElement("w:shd")
        shade.set(qn("w:fill"), "D9E2F3")
        cell._tc.get_or_add_tcPr().append(shade)
        for para in cell.paragraphs:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.line_spacing = 1.0
            for run in para.runs:
                font(run, size, bold=True)
    for row in rows:
        cells = t.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = str(value)
            for para in cells[i].paragraphs:
                para.paragraph_format.line_spacing = 1.0
                for run in para.runs:
                    font(run, size)
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return t


def add_page_number(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run()
    begin = OxmlElement("w:fldChar"); begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText"); instruction.set(qn("xml:space"), "preserve"); instruction.text = " PAGE "
    separate = OxmlElement("w:fldChar"); separate.set(qn("w:fldCharType"), "separate")
    value = OxmlElement("w:t"); value.text = "1"
    end = OxmlElement("w:fldChar"); end.set(qn("w:fldCharType"), "end")
    for item in (begin, instruction, separate, value, end):
        run._r.append(item)
    font(run, 10)


def new_document():
    doc = Document()
    for section in doc.sections:
        section.page_width = Mm(210)
        section.page_height = Mm(297)
        section.left_margin = Mm(40)
        section.bottom_margin = Mm(40)
        section.top_margin = Mm(25)
        section.right_margin = Mm(25)
        add_page_number(section)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for name, size, centered in (("Heading 1", 14, True), ("Heading 2", 12, False), ("Heading 3", 12, False)):
        style = doc.styles[name]
        style.font.name = "Times New Roman"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER if centered else WD_ALIGN_PARAGRAPH.LEFT
    return doc


def build():
    doc = new_document()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(140)
    font(p.add_run("CHAPTER-BY-CHAPTER THESIS UPDATES"), 16, bold=True)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(p.add_run("For: TinyFL: Edge-Based Secure and Energy-Aware Lightweight Federated Learning for Homogeneous IoT Sensor Nodes"), 12)
    paragraph(doc, "Companion update for the existing thesis PDF. The PDF itself is preserved. Review and insert the replacement sections into an editable master copy; retain supervisor-approved text and references not superseded here.", italic=True)
    heading(doc, "How to use this update", 2)
    paragraph(doc, "Replace the corresponding Stage 1 results and pending Stage 2 sections in Chapters 3-7 with the sections below. Do not replace Chapters 1-2 wholesale: update their objectives, architecture, and scope statements only where they promise measurements or features that were not completed. Keep all generated-data findings explicitly described as synthetic. Project reports cited below are local evidence artifacts; move them into the thesis appendices or repository archive as required by the supervisor.")
    paragraph(doc, "Evidence boundary: Stage 1 regression data and Stage 2 anomaly labels are synthetic. S1.4, S1.5, S1.6, and the later Stage 2 MQTT telemetry are physical-device observations, but their meaning is limited to the checks described. The Stage 2 battery percentage is simulated, not measured battery state.", italic=True)

    # Chapter 3 replacement/addition sections
    doc.add_page_break(); heading(doc, "CHAPTER 3 — METHODOLOGY UPDATES", 1)
    heading(doc, "Replace Section 3.5.1 — Stage 1 Synthetic Lighting Dataset", 2)
    paragraph(doc, "The Stage 1 lighting dataset was generated in software because no labelled real-room dataset mapping PIR, LDR, temperature, humidity, and preferred LED brightness was available. The deterministic generator created 10,000 rows using seed 42. Occupancy was sampled with probability 0.5; true LDR was sampled over 0–1023, temperature over 15–35 °C, and humidity over 30–80%. The target PWM was derived from an occupancy-gated daylight-harvesting rule with a temperature/humidity comfort adjustment and Gaussian label noise, then clipped and rounded to the 0–255 range. Sensor features included noise, a 2% PIR flip probability, and integer DHT11-style temperature and humidity values. These parameters are model assumptions, not empirical user preferences.")
    paragraph(doc, "The resulting dataset had no missing values, binary PIR values, and all generated values within the configured ranges. It contained 10,000 records; the saved S1.1 report records PIR high in 50.12%, PWM zero in 37.73%, and PWM full scale in 7.69%. The target correlation was +0.596 with PIR and −0.521 with LDR. These statistics characterize the synthetic generator only.")

    heading(doc, "Replace/extend Section 3.5.2 — Stage 2 Synthetic Anomaly Data", 2)
    paragraph(doc, "The Stage 2 development dataset was generated as a reproducible pipeline test because the project folder did not contain the previously referenced anomaly CSV. It contains 5,000 rows, with a requested anomaly rate of 8%, and a stratified 80/20 split (4,000 training and 1,000 test rows). Features are integer temperature, integer humidity, and binary PIR. The simulator defines normal conditions as 24–31 °C, 60–80% RH, with PIR high at 8% probability; the generated anomaly groups are temperature events (32–35 °C), humidity events (81–90% RH), and PIR bursts. The generated labels are not measured ground truth. All scores trained or evaluated on this data are simulation results and must not be described as real-world anomaly detection accuracy.")

    heading(doc, "Add Section 3.5.3 — Physical MQTT Telemetry Collection", 2)
    paragraph(doc, "Earlier telemetry datasets were collected with firmware that published raw temperature, humidity, PIR, and LDR readings over MQTT; the Python collector added receive timestamps, scenario/session metadata, and simulated energy-policy fields. Those historical CSVs remain centralized telemetry evidence and must not be described as private FL. The 61-message pilot and 101-message energy-policy capture were produced by that earlier path. The revised node sketch removes sensor-result MQTT publication: readings remain local for OLED display/inference, while MQTT is used for FL control, weight/sample-count updates, global weights, and acknowledgements. The revised sketch compiled but had not yet been reflashed and rerun on both nodes at the time of this update. The battery percentage remains simulated, not ADC-measured.")

    # Chapter 4
    doc.add_page_break(); heading(doc, "CHAPTER 4 — TECHNOLOGY AND DESIGN CORRECTIONS", 1)
    heading(doc, "Replace Section 4.6 — Energy Management Technology", 2)
    paragraph(doc, "The prototype did not include a battery-voltage divider or physical battery monitor during the recorded tests. To exercise the software policy, firmware provides a serial-triggered simulated battery percentage starting at 100% and randomly decreasing by 1–5 percentage points every three seconds. The policy enters NORMAL above 60%, ECO at 60% or below, and CRITICAL at 20% or below. The configured sample intervals are 2 s, 5 s, and 15 s, respectively; the confidence-indicator LED PWM is capped at 255, 128, and 0. This is a functional simulation of policy transitions only. It does not measure battery voltage, current, discharge curve, node lifetime, or energy savings.")
    heading(doc, "Add note to the Stage 2 node design", 2)
    paragraph(doc, "The Stage 2 TFLite inference model uses temperature, humidity, and PIR; GPIO6 is a confidence indicator, not a lighting-control prediction. The revised node sketch keeps sensor values local for OLED display/inference and publishes no sensor-result records. On MQTT START, each ESP32 trains a four-parameter logistic model and sends model weights plus local sample count; the laptop sample-weights updates, returns global weights, and receives node acknowledgements. SYNTHETIC mode is the default; its deterministic anomaly examples are generated locally. SENSOR_RULE remains an optional local pseudo-label mode. Earlier physical run 04bbb7f13378 used sensor-rule labels over plaintext. The revised firmware uses CA-verified MQTT TLS on port 8883 and a simulated NORMAL/ECO/CRITICAL policy that changes sample interval and caps local steps at 5/3/1. Physical run df216f34a23b then completed three TLS rounds in SYNTHETIC/SIMULATED mode, beginning at simulated 55%: both nodes ACKed all globals, and ECO reduced node 2's round-3 contribution to one sample versus node 1's three. The sketch compiled in the default partition using 1,124,192/1,310,720 bytes of program storage (85%) and 56,724/327,680 bytes of dynamic memory (17%). TLS encrypts the link and verifies the broker; TLS clients remain anonymous, while the legacy plaintext listener has been stopped and its config is loopback-only. Differential privacy and secure aggregation are absent. The logistic FedAvg model is separate from the int8 TFLite model.")

    # Chapter 5
    doc.add_page_break(); heading(doc, "CHAPTER 5 — RESULTS REPLACEMENTS", 1)
    heading(doc, "Replace Sections 5.1.1–5.1.3 — Stage 1 Results", 2)
    paragraph(doc, "The Stage 1 test results below are from the saved S1.2 report and use the project’s synthetic 10,000-row lighting dataset (8,000 training; 2,000 test records). They supersede older figures in the earlier paper draft that referred to a different generator. The selected 10-tree, depth-5 Random Forest had mean five-fold cross-validation R² 0.9403 (SD 0.0138); held-out test R² was 0.9380, RMSE 24.17 PWM, and MAE 7.13 PWM. A depth-5 decision tree achieved similar test R² (0.9383), so the saved results do not support a strong claim of large accuracy gain from ensembling on this generator.")
    table(doc, "Table 5.1: Stage 1 candidate model performance on the held-out synthetic test set", ["Model", "RMSE", "MAE", "R²"], [
        ["Random Forest, 10 trees/depth 5", "24.17", "7.13", "0.9380"],
        ["Decision Tree, depth 5", "24.12", "7.18", "0.9383"],
        ["Linear Regression", "58.82", "51.95", "0.6330"],
        ["KNN, unscaled", "85.02", "57.63", "0.2332"],
        ["KNN, standardized", "26.44", "7.65", "0.9258"],
    ])
    paragraph(doc, "The Random Forest feature importances were LDR 0.617, PIR 0.380, temperature 0.0018, and humidity 0.0013. These are importances for the synthetic regression task, not causal effects in a real room.")

    heading(doc, "Replace Stage 1 On-Device Deployment Results", 2)
    paragraph(doc, "The exported forest contains 10 trees, maximum depth 5, and 618 nodes. On the ESP32-S3, each literal variant ran 500 embedded held-out vectors. Both variants had maximum absolute prediction difference 3.1×10⁻⁵ and 100% equality after rounding to 8-bit PWM. Mean per-call latency was 2.282 μs for double literals and 2.284 μs for float literals; batch means were 1.575 and 1.576 μs per inference. The model added 9,104 bytes of flash and 52 bytes of stack versus the base build; free heap did not change. A static-RAM delta was not supplied, so the older <1 KB SRAM assertion is not supported by this measured report.")
    table(doc, "Table 5.2: S1.4 ESP32-S3 parity and resource results", ["Variant", "Vectors", "Max diff", "uint8 equality", "Mean latency", "Flash delta", "Stack delta"], [
        ["Double literals", "500", "3.1×10⁻⁵", "100%", "2.282 μs", "9,104 B", "52 B"],
        ["Float literals", "500", "3.1×10⁻⁵", "100%", "2.284 μs", "9,104 B", "52 B"],
    ])

    heading(doc, "Add Stage 1 Sensor Characterization and Closed-Loop Results", 2)
    paragraph(doc, "S1.5 produced 4,372 usable rows over 437.1 s with a 100 ms median and p99 logging interval. DHT11 read success was 219/219 (100%); observed temperature was 32.8–33.2 °C and humidity 41–44%. OLED detection, PIR motion response, non-saturation, and logging period passed. LDR dark/ambient/bright separation and noise failed (not monotonic; worst SD 9.78% full scale); PIR stillness failed (16.2% high against a 5% criterion); the PWM ramp check failed because logged maximum duty was zero. Preserve these findings as limitations.")
    paragraph(doc, "In S1.6, calibrated LDR references were dark raw 4057 and bright raw 119, consistent with the inverse divider response. Three physical sensor sessions yielded 18,003 rows. Calibration was valid for 100% of rows; calibrated LDR10 ranged 0–1023; temperature ranged 31.0–31.7 °C and humidity 64–68%. The model-versus-rule PWM MAE was 1.37 and correlation 0.9966; PIR was off in 93.30% of rows. The rule is a designed comparator, not ground truth or a user-preference label.")
    table(doc, "Table 5.3: S1.5 and S1.6 physical prototype results", ["Test", "Result", "Evidence/limitation"], [
        ["DHT11 and OLED", "PASS", "219/219 DHT reads; OLED at 0x3C"],
        ["LDR characterization", "FAIL criteria", "Not monotonic; worst SD 9.78% FS"],
        ["PIR stillness", "FAIL criterion", "16.2% high; threshold ≤5%"],
        ["S1.6 model/rule comparison", "Measured", "MAE 1.37; r=0.9966; comparator only"],
        ["S1.6 rows", "18,003", "Three sessions; 100% calibration-valid"],
    ])

    heading(doc, "Replace Sections 5.2–5.3 — Stage 2 Current Results", 2)
    paragraph(doc, "The Stage 2 anomaly dataset and labels are generated by software. On its 1,000-row held-out split, the Random Forest baseline achieved accuracy 0.940, anomaly precision 0.602, recall 0.738, F1 0.663, and ROC-AUC 0.979. The 209-parameter Dense(16)-Dense(8)-Dense(1) neural network achieved accuracy 0.933, precision 0.544, recall 1.000, F1 0.705, and ROC-AUC 0.979. After 10 QAT fine-tuning epochs, full-int8 TFLite conversion yielded a 3,080-byte model and held-out accuracy/F1 equal to the QAT model (0.933/0.705; ROC-AUC 0.980). These are simulation metrics only.")
    table(doc, "Table 5.4: Stage 2 synthetic anomaly-classification results", ["Model", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC"], [
        ["Random Forest", "0.940", "0.602", "0.738", "0.663", "0.979"],
        ["Neural network", "0.933", "0.544", "1.000", "0.705", "0.979"],
        ["QAT / full-int8 TFLite", "0.933", "0.544", "1.000", "0.705", "0.980"],
    ])
    paragraph(doc, "A two-node laptop FedAvg simulation used two disjoint 2,000-row training partitions and five rounds. The saved final global synthetic-test metrics were precision 0.472, recall 0.950, F1 0.631, and ROC-AUC 0.961. A separate three-round MQTT simulation logged 21 software events; those values are not physical-node network latency results. Earlier physical FedAvg run 04bbb7f13378 used sensor-rule pseudo-labels over plaintext. The revised physical run df216f34a23b used CA-verified TLS, local SYNTHETIC training, and SIMULATED energy starting at 55%; it completed three rounds with six updates and six ACKs in 54.648 seconds. Local samples by round were Node 1/Node 2: 3/3, 3/3, and 3/1, demonstrating energy-adaptive sample weighting. Aggregator-observed round windows were 14.523, 14.998, and 25.125 seconds; global publish-to-last-ACK intervals were 39.7, 36.4, and 162.7 ms. These are host-observed end-to-end intervals; round time includes local work and is not network latency. Neither run establishes anomaly accuracy because labels are pseudo-labels. Historical telemetry CSVs were collected with the older raw-publication firmware.")

    # Chapter 6
    doc.add_page_break(); heading(doc, "CHAPTER 6 — EVALUATION REPLACEMENTS", 1)
    heading(doc, "Replace Section 6.1 — Evaluation Criteria and Evidence", 2)
    paragraph(doc, "Evaluation is separated by evidence type. Stage 1 synthetic held-out metrics evaluate fidelity to a designed PWM generator; S1.4 evaluates embedded parity and resource use; S1.5 evaluates sensor checks; and S1.6 compares model output with a rule baseline. Stage 2 classifier metrics remain synthetic. Earlier physical FedAvg run 04bbb7f13378 used sensor-rule pseudo-labels. Revised physical run df216f34a23b completed three rounds over CA-verified TLS in SYNTHETIC/SIMULATED mode: both nodes updated and ACKed every round, with local samples 3/3, 3/3, and 3/1 as the simulated energy budget adapted. This establishes physical synthetic-mode weight aggregation and TLS transport, not ground-truth anomaly accuracy or measured energy savings.")
    heading(doc, "Replace Section 6.2 — Stage 1 Evaluation", 2)
    paragraph(doc, "The ESP32-S3 feasibility objective is supported for the tested Random Forest: 100% uint8-rounded parity over 500 board vectors, maximum difference 3.1×10⁻⁵, mean latency about 2.28 μs, and 9,104 bytes of incremental flash. Static SRAM delta was not measured in the saved report. Sensor validation was mixed: DHT11, OLED, timing, and motion-response checks passed, while LDR separation/noise, PIR stillness, and PWM/LDR ramp checks failed. S1.6 confirmed calibrated closed-loop operation and close agreement with the specified rule, but did not provide ground-truth user-preference accuracy.")
    heading(doc, "Replace Section 6.3–6.4 — Stage 2 Evaluation and Baseline", 2)
    paragraph(doc, "The synthetic Stage 2 classifier experiments validate the software pipeline only. Earlier physical FedAvg run 04bbb7f13378 used sensor-rule labels. Revised physical run df216f34a23b completed three ESP32 rounds over CA-verified TLS using local SYNTHETIC examples and a SIMULATED energy policy starting at 55%. Both nodes sent and ACKed every global update; local sample counts were 3/3, 3/3, and 3/1, and all events carry ISO-UTC timestamps. The new firmware removes sensor-result MQTT publication. This demonstrates model-only physical aggregation with energy-adaptive sample counts; it does not provide ground-truth anomaly accuracy. TLS clients remain anonymous; the legacy plaintext listener has been stopped and its config is loopback-only. Differential privacy and secure aggregation are not implemented. The logistic FedAvg model does not update the int8 TFLite artifact.")
    heading(doc, "Replace Section 6.6 — Threats to Validity and Limitations", 2)
    paragraph(doc, "The principal validity threat is synthetic/pseudo-label construction: Stage 1 labels come from a lighting-rule generator, Stage 2 classifier scores use generated anomaly labels, and physical runs 04bbb7f13378/df216f34a23b use rule-generated labels. Run df216f34a23b validates the revised TLS, local-only sensor transport, synthetic mode, and simulated energy policy on both boards, but not real anomaly accuracy or measured energy savings. S1.6’s rule baseline is not independent ground truth, and S1.5 documented LDR/PIR limitations. Historical telemetry captures sent raw readings; the new firmware does not publish sensor-result records. TLS on port 8883 encrypts traffic and verifies the broker, but TLS clients remain anonymous; the legacy plaintext listener has been stopped and its config is loopback-only. Differential privacy and secure aggregation are not implemented. Battery state is simulated; TFLite OTA and ground-truth anomaly accuracy remain unverified. Inherited references require verification.")

    # Chapter 7
    doc.add_page_break(); heading(doc, "CHAPTER 7 — DISCUSSION AND CONCLUSION REPLACEMENT", 1)
    heading(doc, "7.1 Discussion", 2)
    paragraph(doc, "The project establishes an engineering path from synthetic dataset generation to ESP32-S3 inference and physical two-node FL. The strongest measured hardware result remains the S1.4 parity test, with 100% rounded parity over the tested vectors at approximately 2.28 μs mean inference time. S1.5 exposed LDR/PIR issues, and S1.6 compares lighting output with a designed rule rather than human preference labels. Physical run df216f34a23b completed three rounds on both ESP32s with CA-verified TLS, local synthetic training, and simulated energy adaptation; Node 2's round-3 sample count fell to one while Node 1 used three. Fixed-policy control run 8f75883f0472 kept five samples per node per round and completed faster. The firmware keeps sensor data local. TLS protects transport, and the legacy plaintext broker is now loopback-only, but TLS clients remain anonymous; this is not a complete privacy guarantee.")
    paragraph(doc, "Stage 2 includes the 3,080-byte synthetic int8 TFLite inference model, synthetic laptop experiments, historical telemetry, and two completed physical FedAvg runs, including the TLS/energy comparison. Energy adaptation uses simulated battery state; the fixed-versus-simulated comparison is not measured energy savings. No real-label anomaly accuracy, battery current/voltage measurement, or physical TFLite OTA update is established.")
    heading(doc, "7.2 Conclusion", 2)
    paragraph(doc, "The ESP32-S3 successfully ran the exported Stage 1 Random Forest with measured parity and low inference latency. Stage 2 includes synthetic classifier/QAT results, physical telemetry, and physical FedAvg run df216f34a23b: three TLS-protected rounds, six updates, six ACKs, and energy-adaptive sample counts based on simulated battery state. This demonstrates physical model aggregation and update return while keeping sensor values off MQTT. Field anomaly accuracy, client authentication, formal privacy, measured energy savings, TFLite model updates, and user benefit require further evidence.")
    heading(doc, "7.3 Recommendations", 2)
    paragraph(doc, "Future work should (1) define an independently labelled anomaly protocol and evaluate session-separated data, (2) validate LDR/PIR reliability, (3) repeat TLS FedAvg runs under varied node distributions and archive both serial/MQTT evidence sets, (4) configure broker authentication/ACLs because TLS permits anonymous clients, (5) measure battery voltage/current before energy claims, and (6) verify inherited citations and references.")

    doc.add_page_break(); heading(doc, "APPENDIX — VERIFIED EVIDENCE FILES", 1)
    paragraph(doc, "Stage 1 source reports: reports/s1_1 through reports/s1_6. Stage 2 synthetic reports: stage2/reports/phase_a and stage2/reports/phase_b. Physical Stage 2 telemetry files include the pilot sessions, energy-policy simulation, and the completed eight-hour unlabeled baseline at stage2/data/physical_overnight_unlabeled_20261025.csv.")
    doc.add_page_break(); heading(doc, "APPENDIX — PROJECT CONTINUATION STATUS (25 OCTOBER 2026)", 1)
    heading(doc, "Physical Stage 2 telemetry recorded", 2)
    paragraph(doc, "Privacy/federation clarification: historical telemetry CSVs and physical run 04bbb7f13378 used earlier firmware; that run sent weights/sample counts without raw examples but used sensor-rule pseudo-labels and plaintext MQTT. Revised physical runs df216f34a23b and 8f75883f0472 used CA-verified TLS, with synthetic labels and simulated energy policy or fixed policy, respectively. The current firmware sends no sensor-result records. The legacy plaintext broker process has been stopped and its configuration now binds port 1883 to 127.0.0.1 only. TLS clients remain anonymous, so broker authentication/ACLs are still required for access control. No differential privacy or secure aggregation is implemented.")
    heading(doc, "Federated learning: implemented scope and next steps", 2)
    paragraph(doc, "The software-only Stage 2 experiment trains two logical nodes on disjoint synthetic partitions and exchanges neural-network weights through local MQTT. Separately, the physical FedAvg path is implemented in the ESP32 firmware and laptop aggregator: nodes perform local logistic-model updates from sensor samples, the laptop computes sample-count-weighted FedAvg, and nodes apply and acknowledge each global update. A three-round test with temporary MQTT clients verified START, update, aggregation, ACK, and STOP behavior. It did not exercise ESP32 hardware. The deployed int8 TensorFlow Lite Micro artifact remains inference-only and is not updated by this separate logistic model.")
    paragraph(doc, "Physical run 04bbb7f13378 completed three ESP32-to-laptop-to-ESP32 rounds using sensor-rule pseudo-labels over the earlier plaintext firmware. Revised TLS/energy run df216f34a23b completed three rounds using SYNTHETIC data and SIMULATED energy starting at 55%; both nodes ACKed every global model. Fixed-policy TLS run 8f75883f0472 also completed three rounds with five samples per node per round. The LAN plaintext broker process has been stopped and its config is loopback-only. TLS clients remain anonymous, so broker authentication/ACLs are still needed for access control. The fixed-versus-simulated comparison shows a sample-count/runtime tradeoff, not measured energy savings. Neither synthetic pseudo-label mode establishes ground-truth anomaly accuracy; no differential privacy or secure aggregation is present.")
    paragraph(doc, "The 60-second MQTT pilot file stage2/data/pilot_unlabeled.csv contains 61 physical-node messages: Node 1 contributed 30 and Node 2 contributed 31. The records include UTC receive time, temperature, humidity, PIR, LDR raw and 10-bit values, model anomaly/confidence, inference time, and the firmware's battery/energy-policy fields. Both nodes were recorded in NORMAL mode with simulated battery percentage 100%. Ground truth is blank/unknown; the model anomaly field must not be treated as the ground-truth label.")
    paragraph(doc, "A later 60-second collection-status pilot, stage2/data/pilot_collection_status.csv, contains 57 physical MQTT messages: Node 1 contributed 30 and Node 2 contributed 27. The rows share collection ID 33e60a960569 and scenario pilot_collection_status; ground truth remains unknown. The collector displayed its COLLECTING session message and received samples from both nodes. OLED capture-indicator visibility was not independently recorded in this session.")
    paragraph(doc, "The energy-policy session stage2/data/energy_policy_sim.csv contains 101 physical-node telemetry messages: Node 1 contributed 50 and Node 2 contributed 51. The recorded span across the nodes is 822.3 s. Both nodes traversed NORMAL, ECO, and CRITICAL modes. Observed median intervals were approximately 2,000 ms in NORMAL, 5,000 ms in ECO, and 15,000 ms in CRITICAL. All logged indicator-PWM values respected the configured caps (255, 128, and 0, respectively). The battery field is explicitly simulated, starting at 79% in the captured rows and reaching 0%; this is not voltage, current, energy, or lifetime evidence.")
    paragraph(doc, "A first overnight attempt was interrupted after approximately 11.3 minutes and is preserved at stage2/data/physical_overnight_unlabeled.csv: 512 messages (Node 1: 339; Node 2: 173), one session ID, all in NORMAL mode. It is a partial unlabeled baseline, not an eight-hour session.")
    paragraph(doc, "The eight-hour unlabeled collection completed on 25 October 2026 at stage2/data/physical_overnight_unlabeled_20261025.csv under session ID 94881a73da1c. It contains 28,765 MQTT rows over 28,799.6 seconds: Node 1 contributed 14,368 rows over 28,797.4 seconds; Node 2 contributed 14,397 rows over 28,799.6 seconds. No duplicate (node, sample) pairs were found. All sensor and inference fields were populated; the ground-truth label is blank for every row by design, and the battery source is simulated.")
    table(doc, "Appendix Table C.1: Overnight unlabeled baseline data quality and sensor ranges", ["Node", "Rows", "Duration", "Median interval", "Temp mean (range)", "RH mean (range)", "PIR high", "LDR10 range"], [
        ["1", "14,368", "7.999 h", "1,999.9 ms", "29.87 (29.4–30.5) °C", "72.16 (70–76)%", "4.27%", "103–1023"],
        ["2", "14,397", "8.000 h", "2,000.0 ms", "31.90 (30.2–33.4) °C", "43.62 (40–52)%", "16.93%", "18–935"],
    ], size=8.0)
    table(doc, "Appendix Table C.2: Model outputs and inference timing on unlabeled overnight telemetry", ["Node", "Mean confidence", "Model-predicted anomaly rows", "Mean inference time", "Ground-truth labels"], [
        ["1", "0.0369", "4.27%", "152.1 μs", "None"],
        ["2", "0.7413", "75.51%", "193.2 μs", "None"],
    ], size=8.5)
    paragraph(doc, "The two nodes recorded different environmental distributions, particularly humidity (Node 1 mean 72.16%, range 70–76%; Node 2 mean 43.62%, range 40–52%) and PIR-high fraction (4.27% versus 16.93%). The synthetic Stage 2 training generator uses humidity values from 60–90%; therefore Node 2's overnight humidity is outside the training support. The much higher model-predicted anomaly rate on Node 2 (75.51% versus 4.27%) is an observed model output under distribution shift, not evidence that 75.51% of Node 2 readings are truly anomalous. No ground-truth labels were collected. Check sensor placement/calibration and treat this as a domain-shift finding; do not score model accuracy from it.")
    paragraph(doc, "Both nodes remained in NORMAL mode for the full session with simulated battery percentage fixed at 100%. Model-generated anomaly/confidence outputs were recorded but are not ground-truth labels. This dataset supports physical sensor-distribution, message continuity, and inference-latency characterization; it does not support supervised anomaly-accuracy claims.")
    paragraph(doc, "In-progress checkpoint at approximately 00:54 local time on 25 October 2026: the active file contained 202 rows, balanced as Node 1 = 101 and Node 2 = 101, with session ID 94881a73da1c. The captured UTC range at that checkpoint was 2026-10-24 19:21:12 to 19:24:33. A separate live Mosquitto subscriber also received Node 2 sample 133. This is an interim connectivity/progress check, not the completed eight-hour dataset.")
    paragraph(doc, "Historical telemetry collection used a collection-visibility feature: the Python collector published retained start/stop status events on tinyfl/collection/status, and that earlier firmware subscribed to the status topic. CSV rows received a collection_id. The current model-only firmware no longer subscribes to collection-status or publishes sensor-result records; sensor values remain local on the OLED. The prior OLED parser correction remains documented as historical telemetry-path behavior.")
    paragraph(doc, "Physical FedAvg implementation status (25 October 2026): physical run 04bbb7f13378 completed three ESP32-to-laptop-to-ESP32 rounds. Both nodes supplied five locally pseudo-labelled samples per round, all six updates were received, and all six global-weight acknowledgements were recorded. The run took 29.613 seconds from START publication to STOP publication. The earlier run 30bd43f43801 timed out because neither node supplied an update; it is retained as a setup diagnostic, not a result. The FedAvg model is separate from the int8 TFLite anomaly model, and pseudo-label updates do not establish ground-truth classification accuracy.")
    table(doc, "Appendix Table C.3: Physical FedAvg run 04bbb7f13378", ["Round", "Local samples (Node 1 / Node 2)", "Global wT", "Global wH", "Global wPIR", "Global bias", "ACKs"], [
        ["1", "5 / 5", "-0.015318", "-0.191060", "0.080222", "-0.040899", "2 / 2"],
        ["2", "5 / 5", "-0.059738", "-0.319834", "0.122710", "-0.093636", "2 / 2"],
        ["3", "5 / 5", "-0.107412", "-0.427083", "0.140336", "-0.146596", "2 / 2"],
    ], size=7.5)
    paragraph(doc, "Latency measurement note: timestamps are from the laptop aggregator event log. Round windows are measured from START (round 1) or the preceding round completion to the current round completion; they include local sampling/training and MQTT exchange. Global publish-to-last-ACK is the time from the laptop publishing the global update until it records the second node ACK. These are end-to-end protocol intervals, not isolated one-way network latency measurements.")
    table(doc, "Appendix Table C.4: Aggregator-observed physical FedAvg timings", ["Round", "Round window (s)", "Node update arrival skew (ms)", "Global publish to final ACK (ms)"], [
        ["1", "9.539", "354.9", "144.2"],
        ["2", "10.034", "377.4", "172.5"],
        ["3", "10.038", "377.9", "209.8"],
    ], size=8.5)
    paragraph(doc, "Physical TLS/energy-aware FedAvg run df216f34a23b completed three rounds over MQTT TLS with SYNTHETIC data and SIMULATED energy policy starting at 55%. Both node IDs updated and ACKed every global model; ISO-UTC timestamps were written for all aggregator events. The START-to-STOP duration was 54.648 s. Local sample counts were Node 1/Node 2 = 3/3, 3/3, and 3/1, demonstrating reduced Node 2 contribution in simulated CRITICAL mode.")
    table(doc, "Appendix Table C.5: Physical TLS/energy FedAvg run df216f34a23b", ["Round", "Samples (Node 1 / Node 2)", "Round window (s)", "Global publish to final ACK (ms)", "ACKs"], [
        ["1", "3 / 3", "14.523", "39.7", "2 / 2"],
        ["2", "3 / 3", "14.998", "36.4", "2 / 2"],
        ["3", "3 / 1", "25.125", "162.7", "2 / 2"],
    ], size=8.0)
    paragraph(doc, "A fixed-policy TLS comparison, run 8f75883f0472, used the same 3-round SYNTHETIC configuration with energy adaptation disabled. Both nodes contributed five samples in every round (30 total) and all six global updates were acknowledged. Its START-to-STOP duration was 29.004 seconds, compared with 54.648 seconds and 16 total local samples in simulated-energy run df216f34a23b. These are two run-specific execution observations, not measured energy consumption or savings; both use synthetic labels.")
    table(doc, "Appendix Table C.6: Fixed versus simulated-energy TLS FedAvg", ["Run", "Energy policy / start", "Samples per round (Node 1 / Node 2)", "Total local samples", "START-to-STOP (s)", "Rounds / ACKs"], [
        ["df216f34a23b", "SIMULATED / 55%", "3/3; 3/3; 3/1", "16", "54.648", "3 / 6 of 6"],
        ["8f75883f0472", "FIXED", "5/5; 5/5; 5/5", "30", "29.004", "3 / 6 of 6"],
    ], size=8.0)
    paragraph(doc, "Comparison evidence: stage2/reports/phase_b/physical_fedavg_energy_comparison_20261025.md; run event/summary pairs are physical_fedavg_df216f34a23b_* and physical_fedavg_8f75883f0472_* under stage2/data/ and stage2/reports/phase_b/.")
    paragraph(doc, "Pre-collection connectivity check (25 October 2026): Mosquitto was confirmed listening on port 1883, and a live subscriber received one telemetry message from each node on tinyfl/node/result. Both messages reported NORMAL mode, simulated battery 100%, and a 2,000 ms sample interval. These two transient messages verified connectivity only and were not appended to a dataset or used as model-evaluation evidence.")
    heading(doc, "Validation Status", 2)
    add_bullets(doc, [
        "Physical TLS/SYNTHETIC/SIMULATED-energy run df216f34a23b and fixed-policy control run 8f75883f0472 both completed three ESP32 rounds with six ACKs; the observed sample and duration tradeoff is summarized in Appendix Table C.6 and is not battery-energy evidence. The earlier run 04bbb7f13378 used the previous sensor-rule/plaintext configuration.",
        "The overnight capture is unlabeled; define and collect separate supervisor-approved ground-truth scenarios before supervised anomaly-accuracy evaluation.",
        "No supervisor-approved ground-truth labels for Stage 2 anomaly events have been collected; physical-node accuracy/F1 cannot yet be reported.",
        "The physical FedAvg demo uses a separate small logistic model and rule-based pseudo-labels; it is not an update to the deployed int8 TFLite model and is not ground-truth anomaly evaluation.",
        "The legacy plaintext broker process has been stopped and its config binds port 1883 to 127.0.0.1 only. The TLS listener still permits anonymous clients; add broker authentication/ACLs before claiming access-controlled deployment. TLS provides transport encryption and broker identity verification only.",
        "No physical battery-voltage/current measurement or battery-life experiment has been performed; energy-mode results verify only the simulated firmware policy.",
        "The current sketch defaults to NODE_ID 2; continue building/flashing distinct node identities and preserve both serial logs with each run.",
    ])
    paragraph(doc, "When new collection files are produced, regenerate this companion update and its evidence inventory. Preserve the original thesis PDF; merge the reviewed updates into an editable thesis copy only after supervisor review.", italic=True)

    doc.save(DEST)
    print(f"Saved chapter updates: {DEST}")


if __name__ == "__main__":
    build()
