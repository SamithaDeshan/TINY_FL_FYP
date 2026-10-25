"""Build a separate KDU-style thesis draft from the verified project evidence.

This does not overwrite the source IEEE paper. All Stage 2 generated-data claims
remain explicitly marked as simulated/development-only.
"""
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "Previous Thesis Works"
OUTPUT = SOURCE_DIR / "KDU_Thesis_Draft_Edge_AI_Smart_Lighting_2026.docx"

TITLE = "EDGE AI-ENABLED SMART LIGHTING: TINYML IMPLEMENTATION OF RANDOM FOREST REGRESSION ON ESP32-S3"
CANDIDATE = "B.D.S.D. Douglas"
REG_NO = "40-BCE-0002 (confirm official registration number)"
SUPERVISOR = "D.V.D.S. Abeysinghe (confirm official name and title)"
DEGREE = "BSc (Hons) in Computer Engineering"
DEPARTMENT = "Department of Computer Engineering"
UNIVERSITY = "General Sir John Kotelawala Defence University"


def set_cell_shading(cell, fill="D9E2F3"):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_run_font(run, size=12, bold=None, italic=None):
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def add_page_field(paragraph):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(separate)
    run._r.append(text)
    run._r.append(end)
    set_run_font(run, 10)


def configure_section(section, page_format=None, page_start=None, footer_align=None):
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(40)
    section.bottom_margin = Mm(40)
    section.top_margin = Mm(25)
    section.right_margin = Mm(25)
    if page_format:
        pg_num = section._sectPr.find(qn("w:pgNumType"))
        if pg_num is None:
            pg_num = OxmlElement("w:pgNumType")
            section._sectPr.append(pg_num)
        pg_num.set(qn("w:fmt"), page_format)
        if page_start is not None:
            pg_num.set(qn("w:start"), str(page_start))
        section.footer.is_linked_to_previous = False
        paragraph = section.footer.paragraphs[0]
        paragraph.alignment = footer_align
        add_page_field(paragraph)


def add_body(doc, text, style=None):
    paragraph = doc.add_paragraph(style=style)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.line_spacing = 1.5
    paragraph.paragraph_format.space_after = Pt(6)
    run = paragraph.add_run(text)
    set_run_font(run, 12)
    return paragraph


def add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_after = Pt(3)
        set_run_font(p.add_run(item), 12)


def add_numbered(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Number")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_after = Pt(3)
        set_run_font(p.add_run(item), 12)


def add_chapter(doc, number, title):
    heading = doc.add_paragraph(style="Heading 1")
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.paragraph_format.page_break_before = True
    set_run_font(heading.add_run(f"CHAPTER {number}\n{title.upper()}"), 14, bold=True)


def add_table(doc, number, title, headers, rows):
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.line_spacing = 1.0
    set_run_font(cap.add_run(f"Table {number}: {title}"), 10, bold=True)
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    for index, label in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = str(label)
        set_cell_shading(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.line_spacing = 1.0
            for run in p.runs:
                set_run_font(run, 10, bold=True)
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = str(value)
            cells[index].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for p in cells[index].paragraphs:
                p.paragraph_format.line_spacing = 1.0
                for run in p.runs:
                    set_run_font(run, 9.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return table


def add_figure(doc, number, caption, path, width=5.8):
    path = ROOT / path
    if not path.exists():
        add_body(doc, f"[Figure {number} pending: source image not found at {path}]")
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(width))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.line_spacing = 1.0
    set_run_font(cap.add_run(f"Figure {number}: {caption}"), 10, italic=True)


def add_toc_field(doc):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run()
    begin = OxmlElement("w:fldChar"); begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '
    separate = OxmlElement("w:fldChar"); separate.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t"); placeholder.text = "Right-click and update this field in Word to populate the table of contents."
    end = OxmlElement("w:fldChar"); end.set(qn("w:fldCharType"), "end")
    for element in (begin, instr, separate, placeholder, end):
        r._r.append(element)
    set_run_font(r, 12)


def setup_styles(doc):
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Times New Roman"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for name, size, centered in (("Heading 1", 14, True), ("Heading 2", 12, False), ("Heading 3", 12, False)):
        style = styles[name]
        style.font.name = "Times New Roman"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER if centered else WD_ALIGN_PARAGRAPH.LEFT
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.line_spacing = 1.5


def add_section_text(doc, heading, paragraphs):
    doc.add_heading(heading, level=2)
    for text in paragraphs:
        add_body(doc, text)


def build():
    doc = Document()
    setup_styles(doc)
    for section in doc.sections:
        configure_section(section)

    # Cover page; final gold binding/lettering is a print-stage requirement.
    cover = doc.sections[0]
    configure_section(cover)
    for _ in range(3): doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(p.add_run(TITLE), 18, bold=True)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(p.add_run("WORKING THESIS DRAFT — OCTOBER 2026"), 12, bold=True)
    for _ in range(2): doc.add_paragraph()
    for text in ("A Thesis by", CANDIDATE, REG_NO, "Supervised by", SUPERVISOR,
                 f"Submitted in partial fulfilment of the requirements for the award of {DEGREE}",
                 DEPARTMENT, "Faculty of Computing", UNIVERSITY, "Sri Lanka", "October 2026"):
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(p.add_run(text), 12, bold=text in (CANDIDATE,))

    # Separate title page without pagination.
    title_section = doc.add_section(WD_SECTION.NEW_PAGE)
    configure_section(title_section)
    for _ in range(4): doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(p.add_run(TITLE), 16, bold=True)
    for _ in range(3): doc.add_paragraph()
    for text in (CANDIDATE, REG_NO, f"A thesis submitted for {DEGREE}", DEPARTMENT, UNIVERSITY, "October 2026"):
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(p.add_run(text), 12)

    # Preliminary pages with lower-case Roman page numbering.
    prelim = doc.add_section(WD_SECTION.NEW_PAGE)
    configure_section(prelim, "lowerRoman", 1, WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_heading("DECLARATION OF THE CANDIDATE AND SUPERVISOR", level=1)
    add_body(doc, "DRAFT TEMPLATE: The candidate must review this declaration, confirm its accuracy, and sign/date it before submission. Do not submit this placeholder as a signed declaration.")
    add_body(doc, "I declare that this thesis is my own work and does not incorporate, without acknowledgement, material previously submitted for a degree or diploma at another institution. To the best of my knowledge, it contains no material previously published or written by another person except where acknowledgement is made in the text. I grant the University the non-exclusive right to reproduce and distribute this thesis, in whole or in part, in print, electronic, or other media, while retaining the right to reuse its content in future works.")
    add_body(doc, "Candidate signature: ______________________________    Date: __________________")
    add_body(doc, f"Candidate: {CANDIDATE}    Registration: {REG_NO}")
    add_body(doc, "Supervisor statement: The candidate has carried out research for partial fulfilment of the degree under my supervision.")
    add_body(doc, f"Supervisor: {SUPERVISOR}    Signature: __________________    Date: __________________")

    doc.add_page_break()
    doc.add_heading("ABSTRACT", level=1)
    abstract = (
        "This thesis documents an ESP32-S3 smart-lighting prototype and physical two-node federated learning. The Stage 1 Random Forest was trained on 10,000 synthetic records and achieved held-out R² = 0.9380 and MAE = 7.13 PWM units; 500 ESP32-S3 vectors matched Python after 8-bit rounding, with maximum difference 3.1×10⁻⁵ and mean inference latency near 2.28 μs. Sensor bring-up exposed LDR, PIR, and PWM-response limitations; three closed-loop sessions showed agreement with a designed rule baseline, not user-preference accuracy. An earlier physical FedAvg run used sensor-rule pseudo-labels. Revised run df216f34a23b completed three rounds over CA-verified TLS using local synthetic examples and simulated energy adaptation: both nodes ACKed all global updates, with per-round contributions of 3/3, 3/3, and 3/1 samples. Pseudo-labels are not ground truth, and simulated energy is not a battery measurement."
    )
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.line_spacing = 1.0
    set_run_font(p.add_run(abstract), 11)
    word_count = len(abstract.split())
    p = doc.add_paragraph(); p.paragraph_format.line_spacing = 1.0
    set_run_font(p.add_run(f"Word count: {word_count} (KDU limit: 300)."), 10, italic=True)
    p = doc.add_paragraph(); p.paragraph_format.line_spacing = 1.0
    set_run_font(p.add_run("Keywords: TinyML; Random Forest; ESP32-S3; synthetic dataset; federated learning"), 11)

    doc.add_page_break(); doc.add_heading("ACKNOWLEDGEMENTS", level=1)
    add_body(doc, "DRAFT PLACEHOLDER: Acknowledge the supervisor, Department of Computer Engineering, laboratory staff, collaborators, and any external support actually received. The candidate should edit this section to reflect the assistance provided; no individual or funding source has been invented here.")

    doc.add_page_break(); doc.add_heading("TABLE OF CONTENTS", level=1); add_toc_field(doc)
    doc.add_page_break(); doc.add_heading("LIST OF FIGURES", level=1)
    for text in (
        "Figure 3.1: Stage 1 synthetic smart-lighting dataset overview",
        "Figure 3.2: Stage 2 synthetic anomaly-data distributions (development only)",
        "Figure 6.1: Random Forest feature importance",
        "Figure 6.2: On-device inference latency distribution",
        "Figure 6.3: S1.5 LDR readings by characterization label",
        "Figure 6.4: S1.6 model and rule-baseline PWM traces",
        "Figure 7.1: Synthetic two-node FedAvg development result (simulation only)",
        "Figure 7.2: Simulated energy-policy modes from physical-node telemetry",
    ):
        add_body(doc, text)
    add_body(doc, "Update figure page numbers and captions after final layout in Word.")

    doc.add_page_break(); doc.add_heading("LIST OF TABLES", level=1)
    for text in (
        "Table P.1: Abbreviations",
        "Table 3.1: Stage 1 synthetic dataset generation assumptions",
        "Table 3.2: Stage 2 synthetic anomaly scenario assumptions",
        "Table 4.1: Verified hardware pin map",
        "Table 6.1: Stage 1 model comparison on synthetic data",
        "Table 6.2: ESP32-S3 parity and resource benchmark",
        "Table 6.3: S1.5 sensor checks",
        "Table 6.4: S1.6 real-sensor closed-loop results",
        "Table 7.1: Stage 2 synthetic classifier results",
        "Table 7.2: Stage 2 two-node and MQTT simulation results",
    ):
        add_body(doc, text)
    add_body(doc, "Update table page numbers after final layout in Word.")

    doc.add_page_break(); doc.add_heading("LIST OF ABBREVIATIONS", level=1)
    abbreviations = [
        ("ADC", "Analogue-to-Digital Converter"), ("AI", "Artificial Intelligence"),
        ("DHT11", "Digital Humidity and Temperature Sensor 11"), ("ESP32-S3", "Espressif Systems ESP32-S3 microcontroller"),
        ("FL", "Federated Learning"), ("IoT", "Internet of Things"), ("KNN", "K-Nearest Neighbours"),
        ("LDR", "Light-Dependent Resistor"), ("MAE", "Mean Absolute Error"), ("ML", "Machine Learning"),
        ("MQTT", "Message Queuing Telemetry Transport"), ("MSE", "Mean Squared Error"),
        ("PIR", "Passive Infrared sensor"), ("PWM", "Pulse-Width Modulation"),
        ("QAT", "Quantization-Aware Training"), ("RF", "Random Forest"),
        ("RMSE", "Root Mean Squared Error"), ("ROC-AUC", "Receiver Operating Characteristic Area Under the Curve"),
        ("SRAM", "Static Random-Access Memory"), ("TFLite", "TensorFlow Lite"),
        ("TinyML", "Tiny Machine Learning"),
    ]
    add_table(doc, "P.1", "Abbreviations", ["Abbreviation", "Meaning"], abbreviations)

    # Main body starts on page 1 with Arabic numbering at the bottom-right.
    body = doc.add_section(WD_SECTION.NEW_PAGE)
    configure_section(body, "decimal", 1, WD_ALIGN_PARAGRAPH.RIGHT)

    # CHAPTER 1
    add_chapter(doc, 1, "Introduction")
    add_section_text(doc, "1.1 Background", [
        "Lighting control is a practical building-automation problem in which occupancy, ambient illumination, and environmental conditions influence the desired artificial light output. Fixed thresholds are simple, but combining several sensor signals and producing a smooth 8-bit LED duty command creates an opportunity to evaluate compact machine-learning inference at the edge. This project investigates an ESP32-S3 prototype and treats locally generated PWM as the target of a Random Forest regression model.",
        "The work has two distinct stages. Stage 1 concerns smart-lighting regression and physical ESP32-S3 deployment. Stage 2 is a separate development extension concerning anomaly classification from temperature, humidity, and PIR, combining synthetic classifier experiments with a physical two-node FedAvg implementation. The Stage 2 anomaly task must not be conflated with the Stage 1 lighting-PWM task."
    ])
    add_section_text(doc, "1.2 Problem Statement", [
        "A small microcontroller must collect sensor inputs, run a prediction, and drive an actuator while respecting limited memory and timing budgets. At the same time, the initial project had no labelled real-room dataset mapping PIR, LDR, temperature, and humidity to a preferred PWM value. Consequently, the regression model was initially evaluated against a deterministic synthetic target function, and the physical prototype was used for deployment, sensor, and closed-loop engineering checks rather than for measuring user preference."
    ])
    add_section_text(doc, "1.3 Aim and Objectives", [
        "Aim: to implement and characterize an ESP32-S3 edge-inference prototype for smart lighting, and to implement a separate two-node physical FedAvg workflow for Stage 2 anomaly-model development."
    ])
    add_bullets(doc, [
        "Generate and document a reproducible synthetic lighting dataset and compare regression models.",
        "Export the selected Random Forest and measure host and ESP32-S3 prediction parity, latency, flash, stack, and heap behaviour.",
        "Characterize the PIR, LDR, DHT11, OLED, and PWM path; record the observed failures as well as successful checks.",
        "Evaluate real-sensor closed-loop model outputs against a designed rule baseline, without treating that baseline as ground truth.",
        "Build a separate synthetic Stage 2 anomaly-detection pipeline and implement two-node physical FedAvg/MQTT training and aggregation.",
        "Implement local pseudo-label training, weight-only MQTT updates, sample-weighted aggregation, global-weight acknowledgements, and STOP handling for physical two-node FedAvg; distinguish host tests from board validation.",
    ])
    add_section_text(doc, "1.4 Research Questions", [
        "RQ1: Can a shallow Random Forest trained on the project’s synthetic lighting rules be exported and executed on an ESP32-S3 with prediction parity and low inference latency?",
        "RQ2: What sensor and actuator limitations are observed during physical bring-up and closed-loop operation?",
        "RQ3: Can two ESP32-S3 nodes perform local model updates and complete sample-weighted FedAvg rounds with a laptop aggregator? A three-round physical run was completed and is reported in Chapter 6."
    ])
    add_section_text(doc, "1.5 Scope and Limitations", [
        "The Stage 1 regression labels are synthetic; therefore, test-set accuracy measures recovery of the designed generator, not user-preferred lighting. Stage 1 hardware measurements characterize the implementation but do not establish occupant satisfaction or energy savings. Stage 2 classifier labels are synthetic, and physical FedAvg run 04bbb7f13378 used sensor-rule pseudo-labels rather than ground truth. Revised physical run df216f34a23b completed three CA-verified TLS rounds using local synthetic data and simulated energy adaptation. The final sketch uses 85% of flash and 17% of dynamic memory. Battery percentage remains simulated, not a voltage/current measurement."
    ])
    add_section_text(doc, "1.6 Thesis Organization", [
        "Chapter 2 reviews the source literature carried in the project paper. Chapter 3 describes the separate Stage 1 and Stage 2 methods. Chapter 4 presents system analysis and design. Chapter 5 describes the technologies. Chapter 6 documents implementation and testing. Chapter 7 evaluates the recorded results and their limits. Chapter 8 concludes and recommends further work."
    ])

    # CHAPTER 2
    add_chapter(doc, 2, "Literature Review")
    add_section_text(doc, "2.1 Smart Lighting and Occupancy", [
        "The source paper frames smart lighting around occupancy sensing and daylight harvesting. PIR sensing supplies a binary motion signal, while an LDR provides an analogue proxy for ambient illumination. Existing references in the source manuscript discuss occupancy-based control and sensor-network approaches [1], [2]. These works motivate the project’s rule-based target design, but they do not turn the project’s generated labels into observed user preferences."
    ])
    add_section_text(doc, "2.2 Edge Machine Learning and TinyML", [
        "The project’s source bibliography surveys the use of machine learning on constrained devices and the broader TinyML field [3]–[5]. Edge inference can reduce dependence on continuous cloud connectivity, but feasibility must be demonstrated on the target hardware rather than inferred from desktop test scores. This thesis therefore reports separately the host parity test and ESP32-S3 resource measurements."
    ])
    add_section_text(doc, "2.3 Tree Ensembles for Embedded Regression", [
        "Random Forests combine decision trees to model nonlinear relationships [6]. The project compares the forest with a depth-limited tree, linear regression, and KNN using the same generated split. Tree thresholds are suitable for source-code export; however, model fit to a designed synthetic rule should be interpreted as a software experiment, not as evidence that the rule captures real occupants’ preferences."
    ])
    add_section_text(doc, "2.4 Federated Learning Extension", [
        "Federated learning motivates collaborative model training while keeping data partitions local [7]. The earlier physical run 04bbb7f13378 used sensor-rule labels. Revised physical run df216f34a23b used TLS, local synthetic examples, and simulated energy adaptation; both ESP32s applied and acknowledged all three global updates. The run's local sample counts were 3/3, 3/3, and 3/1, demonstrating the simulated ECO/CRITICAL budget. This establishes physical weight exchange and energy-policy behavior, not ground-truth anomaly accuracy or measured energy savings. The TLS listener currently allows anonymous clients, and the legacy 1883 listener remains plaintext. The original project references should be checked against the cited publications before final submission."
    ])
    add_section_text(doc, "2.5 Research Gap and Project Position", [
        "The verified contribution is an end-to-end engineering characterization of a synthetic-data smart-lighting model on an ESP32-S3, plus physical two-node FedAvg demonstrated in run 04bbb7f13378. Claims are intentionally bounded: S1.4 supplies target-board parity and timing; S1.5 reveals sensor limitations; S1.6 supplies a rule-baseline comparison; Stage 2 classifier metrics are synthetic; and the physical FedAvg labels are rule-generated pseudo-labels rather than ground truth."
    ])

    # CHAPTER 3
    add_chapter(doc, 3, "Methodology and Approach")
    add_section_text(doc, "3.1 Stage 1 Synthetic Lighting Dataset", [
        "The Stage 1 dataset contains 10,000 generated records with seed 42. The generator draws occupancy with probability 0.5, true LDR uniformly over 0–1023, temperature over 15–35 °C, and humidity over 30–80%. A daylight factor is computed as clip((700 − LDR)/400, 0, 1). The PWM target combines occupancy, this daylight factor, a small temperature/humidity adjustment, Gaussian label noise with standard deviation 3, clipping to 0–255, and integer rounding. Sensor features include specified noise and a 2% PIR flip probability; temperature and humidity are integer-quantized to match the DHT11. These are explicit simulation assumptions, not measured values."
    ])
    add_table(doc, "3.1", "Stage 1 generator assumptions", ["Variable", "Generation rule", "Evidence type"], [
        ["Occupancy/PIR", "Bernoulli(0.5); sensor PIR can flip with 2% probability", "Synthetic"],
        ["LDR", "True value U(0,1023); feature noise SD 10", "Synthetic"],
        ["Temperature", "True value U(15,35) °C; feature noise SD 0.5; integer quantization", "Synthetic"],
        ["Humidity", "True value U(30,80)%; feature noise SD 2; integer quantization", "Synthetic"],
        ["PWM target", "Occupancy × daylight/comfort rule + Gaussian noise SD 3; clip/round to 0–255", "Synthetic"],
    ])
    add_section_text(doc, "3.2 Stage 1 Model Training", [
        "The fixed split contains 8,000 training and 2,000 test records. The selected Random Forest uses 10 estimators, maximum depth 5, and random state 42. Five-fold cross-validation was used for model comparison. Models include Random Forest, Decision Tree, Linear Regression, and KNN with and without standardized inputs. Metrics include MSE, RMSE, MAE, R², explained variance, maximum absolute error, and cross-validation spread."
    ])
    add_section_text(doc, "3.3 Export and Embedded Verification", [
        "The trained forest was converted into dependency-free C++ headers, including a float-literal variant. Host parity was checked against the same held-out records. On the ESP32-S3, 500 embedded test vectors were compared against Python predictions. Per-call timing used the ESP timer, and a repeated batch provided a higher-resolution mean. Flash and stack deltas were computed against a model-free base build; static RAM compiler output was not supplied in the saved report."
    ])
    add_section_text(doc, "3.4 Stage 1 Physical Sensor and Closed-Loop Protocol", [
        "S1.5 logged one row every 100 ms with PIR, 12-bit LDR raw value, LDR converted to 10-bit scale by right shift of two, DHT11 readings, DHT status, label, and PWM. Acceptance checks covered LDR separation/noise/saturation, PIR stillness and motion, DHT success/range, PWM ramp response, logging period, and OLED detection. S1.6 calibrated dark and bright LDR raw values, mapped the inverse-response divider onto 0–1023, ran the lighting model, calculated a designed rule baseline, and logged three 10-minute sessions. The rule baseline is a comparator, not ground truth."
    ])
    add_section_text(doc, "3.5 Stage 2 Synthetic Anomaly Dataset and Model", [
        "The Stage 2 development dataset contains 5,000 generated rows with an 8% anomaly prevalence and a stratified 80/20 split. Features are temperature, humidity, and PIR. Normal and anomaly categories are created by explicit simulator rules for temperature events, humidity events, and PIR bursts; DHT values are integers. Z-score normalization statistics were fitted on the 4,000 training rows only. All Stage 2 model scores in this thesis draft are development-only simulation results."
    ])
    add_table(doc, "3.2", "Stage 2 synthetic scenario rules", ["Scenario", "Generated condition", "Label"], [
        ["Normal", "24–31 °C; 60–80% RH; PIR high probability 8%", "0"],
        ["Temperature event", "32–35 °C; 60–80% RH", "1"],
        ["Humidity event", "24–31 °C; 81–90% RH", "1"],
        ["PIR burst", "Nominal temperature/humidity; PIR high", "1"],
    ])
    add_figure(doc, "3.1", "Stage 1 synthetic smart-lighting dataset overview.", "reports/s1_1/fig_overview.png")
    add_figure(doc, "3.2", "Stage 2 synthetic anomaly feature distributions (development data only).",
               "stage2/reports/phase_a/fig_dev_data_distributions.png")
    add_section_text(doc, "3.6 Stage 2 Neural, Quantized, and Federated Simulation", [
        "The neural network is Dense(16, ReLU) → Dense(8, ReLU) → Dense(1, sigmoid), trained with class weighting and early stopping. Quantization-aware fine-tuning ran for 10 epochs; full-int8 TFLite conversion used 300 representative normalized training rows. One two-node FedAvg experiment uses disjoint synthetic partitions of 2,000 rows per node and runs in laptop software. A separate physical-FedAvg path uses a four-parameter logistic model: each ESP32 locally trains on normalized temperature, humidity, and PIR using the rule temperature ≥32 °C OR humidity ≥81% OR PIR=1; only model weights and local sample counts are sent. In run 04bbb7f13378, both ESP32 nodes completed three rounds, sent six total updates, applied sample-weighted global weights, and acknowledged all six global updates. This is a physical weight-exchange demonstration using pseudo-labels, not ground-truth anomaly learning."
    ])

    # CHAPTER 4
    add_chapter(doc, 4, "Analysis and Design")
    add_section_text(doc, "4.1 Stage 1 Requirements", [
        "The Stage 1 system must sample PIR, LDR, and DHT11 inputs; run a compact regression model locally; map the prediction to an 8-bit PWM command; and expose status through an OLED and serial log. Functional checks include model parity, sensor read validity, deterministic report generation, and actuator response. The design must keep synthetic training evidence distinguishable from physical measurements."
    ])
    add_section_text(doc, "4.2 Stage 1 Architecture", [
        "The ESP32-S3 reads PIR on GPIO4, LDR on GPIO1, DHT11 data on GPIO5, drives the LED through GPIO6 at 5 kHz/8-bit PWM, and uses an SSD1306 OLED on SDA GPIO8/SCL GPIO9 at I²C address 0x3C. ESP32-S3 ADC readings are 12-bit; S1.5 logs a paper-scale LDR value using raw >> 2. The source manuscript contained outdated component designations; this thesis draft uses the hardware actually present on the rig."
    ])
    add_table(doc, "4.1", "Verified hardware pin map", ["Component", "Pin/interface", "Verified configuration"], [
        ["PIR", "GPIO4", "Digital input"], ["LDR", "GPIO1 / ADC", "12-bit raw; 10-bit value raw >> 2"],
        ["DHT11", "GPIO5", "Temperature and relative humidity"],
        ["LED indicator/actuator", "GPIO6", "LEDC 5 kHz, 8-bit"],
        ["OLED", "SDA 8 / SCL 9", "SSD1306, 128×64, 0x3C"],
    ])
    add_section_text(doc, "4.3 Stage 2 Architecture", [
        "Earlier telemetry collection firmware published temperature, humidity, PIR, and LDR readings to tinyfl/node/result; the historical CSVs therefore contain centralized raw telemetry. The revised node sketch removes sensor-result MQTT publication and retains sensor display/inference locally on the OLED. MQTT is reserved for START/STOP, model weights plus sample counts, global weights, and ACKs. The laptop aggregator defaults to SYNTHETIC mode; each node generates deterministic anomaly examples locally, performs logistic SGD, and transmits no sensor examples. The earlier physical run 04bbb7f13378 completed three rounds using sensor-rule pseudo-labels. The revised sketch compiled for ESP32-S3 with 1,243,812/1,310,720 bytes of configured program storage (94%) and 61,820/327,680 bytes of dynamic memory (18%); an isolated fake-node protocol smoke test passed with timestamped aggregator records. This revised firmware/mode has not yet been reflashed and physically rerun. Battery percentage remains simulated, not a battery measurement."
    ])
    add_section_text(doc, "4.3.1 Intermediate Host Validation (Superseded)", [
        "An intermediate TLS firmware build and host-client protocol test preceded the physical run recorded below. The final firmware build and subsequent TLS/energy physical result supersede the earlier pending-reflash status."
    ])
    add_section_text(doc, "4.3.2 Final TLS Build and Energy Policy", [
        "The final sketch uses CA-verified MQTT TLS and a MicroMutableOpResolver containing only the deployed model's FULLY_CONNECTED and LOGISTIC operators. It compiled in the default ESP32-S3 app partition at 1,124,192/1,310,720 bytes of flash (85%) and 56,724/327,680 bytes of dynamic memory (17%). Its simulated energy policy adapts sampling and local-step budgets; battery percentage is not measured."
    ])
    add_section_text(doc, "4.3.3 Physical TLS/Energy Run", [
        "Physical run df216f34a23b completed three rounds on both ESP32 nodes over CA-verified TLS, using local SYNTHETIC examples and SIMULATED energy policy starting at 55%. Both nodes updated and acknowledged all global models. Local samples were Node 1/Node 2 = 3/3, 3/3, and 3/1; START-to-STOP took 54.648 s. Fixed-policy control run 8f75883f0472 used 5/5 samples per round and completed in 29.004 s. The comparison shows a protocol/sample-budget tradeoff, not measured energy savings or anomaly accuracy."
    ])
    add_section_text(doc, "4.4 Design Limitations", [
        "The initial Stage 1 sensor test found unreliable LDR separation and PIR false positives during stillness. Later dark/bright calibration demonstrated inverse LDR polarity (dark raw 4057; bright raw 119), but it does not retroactively make the S1.5 statistical checks pass. S1.6’s LDR was mapped from calibrated values, while the broader lighting model still needs validation against ground-truth user labels."
    ])

    # CHAPTER 5
    add_chapter(doc, 5, "Technology")
    add_section_text(doc, "5.1 Hardware Platform", [
        "The target is an ESP32-S3 development board. The S1.4 measurement identified a 240 MHz CPU, 16 MB flash chip, ESP-IDF SDK 5.5.2 build, and Arduino core 3.3.7. The sensing rig contains HC-SR501 PIR, GL5528 LDR divider, DHT11, SSD1306 OLED, and an LED driven with LEDC PWM. Flash-chip capacity is not the same as available sketch space; benchmark comparisons use the measured firmware-size delta."
    ])
    add_section_text(doc, "5.2 Software Stack", [
        "Stage 1 development used Python, NumPy, pandas, scikit-learn, matplotlib, python-docx, joblib, and micromlgen. The embedded Stage 1 forest is generated C++. Stage 2 development used Python 3.12, TensorFlow 2.21, TensorFlow Model Optimization 0.8.1, tf_keras, scikit-learn, Paho MQTT 2.1.0, and Mosquitto 2.1.2. The physical Stage 2 sketch uses Wi-Fi, PubSubClient, DHT, SSD1306, and the Chirale TensorFlow Lite Arduino library. Exact installed versions should be rechecked before final reproducibility claims."
    ])
    add_section_text(doc, "5.3 Model Artifacts", [
        "The Stage 1 deployed forest has 10 trees, depth 5, and 618 nodes. The Stage 2 int8 TFLite development model occupies 3,080 bytes. Its recorded input quantization is scale 0.01810858 and zero point −40; output quantization is scale 0.00390625 and zero point −128. This model was trained against synthetic anomaly labels and should be named and discussed as development-only."
    ])

    # CHAPTER 6
    add_chapter(doc, 6, "Implementation and Testing")
    add_section_text(doc, "6.1 Stage 1 Dataset, Training, and Export", [
        "S1.1 generated and integrity-checked the synthetic lighting dataset. S1.2 compared candidate regressors and selected the 10-tree, depth-5 forest. S1.3 exported double- and float-literal C++ headers and verified host parity on all 2,000 held-out rows. The complete reports are stored under reports/s1_1, reports/s1_2, and reports/s1_3."
    ])
    add_table(doc, "6.1", "Stage 1 held-out regression results (synthetic target)", ["Model", "Test RMSE", "Test MAE", "Test R²"], [
        ["Random Forest (10 trees, depth 5)", "24.17", "7.13", "0.9380"],
        ["Decision Tree (depth 5)", "24.12", "7.18", "0.9383"],
        ["Linear Regression", "58.82", "51.95", "0.6330"],
        ["KNN (unscaled)", "85.02", "57.63", "0.2332"],
        ["KNN (standardized)", "26.44", "7.65", "0.9258"],
    ])
    add_figure(doc, "6.1", "Random Forest feature importance from the Stage 1 synthetic dataset.", "reports/s1_2/fig_importance.png")
    add_section_text(doc, "6.2 ESP32-S3 Benchmark", [
        "S1.4 ran 500 held-out vectors for each embedded model variant. Both variants met the parity criterion: 100% equality after uint8 rounding, with maximum absolute difference 3.1×10⁻⁵. Measured per-call latency was approximately 2.28 μs. The model build added 9,104 bytes of flash and 52 bytes to measured task stack use relative to the base. The report did not contain a static-RAM delta, so no static-RAM figure is claimed."
    ])
    add_table(doc, "6.2", "S1.4 on-device measurements", ["Variant", "Rows", "Max difference", "uint8 equality", "Mean latency", "Flash delta", "Stack delta"], [
        ["Double literals", "500", "3.1×10⁻⁵", "100%", "2.282 μs", "9,104 B", "52 B"],
        ["Float literals", "500", "3.1×10⁻⁵", "100%", "2.284 μs", "9,104 B", "52 B"],
    ])
    add_figure(doc, "6.2", "Distribution of ESP32-S3 per-call inference latency.", "reports/s1_4/fig_latency.png", 5.2)
    add_section_text(doc, "6.3 Sensor Bring-Up", [
        "The S1.5 hardware log contains 4,372 usable rows over 437.1 s at a median interval of 100 ms. DHT11 reads succeeded in 219 of 219 attempts, and the OLED was detected at 0x3C. The PIR responded to motion, but the still-label high rate was 16.2%, above the 5% criterion. LDR dark/ambient/bright separation and steady-label noise checks failed; LDR saturation passed at 0%. The PWM ramp check failed because maximum logged duty was 0. These failures are retained as findings rather than omitted."
    ])
    add_table(doc, "6.3", "S1.5 hardware acceptance checks", ["Check", "Result", "Recorded evidence"], [
        ["DHT11 successful reads", "PASS", "219/219 (100%)"],
        ["DHT11 range", "PASS", "32.8–33.2 °C; RH 41–44%"],
        ["OLED detection", "PASS", "Detected at 0x3C"],
        ["Logging period", "PASS", "Median/p99 100 ms"],
        ["PIR motion response", "PASS", "20.9% high; 9 rising edges"],
        ["PIR quiet while still", "FAIL", "16.2% high; criterion ≤5%"],
        ["LDR level separation/noise", "FAIL", "Not monotonic; worst SD 9.78% full-scale"],
        ["PWM ramp response", "FAIL", "Maximum logged duty 0"],
    ])
    add_figure(doc, "6.3", "S1.5 LDR readings grouped by recorded characterization label.", "reports/s1_5/fig_ldr_time.png")
    add_section_text(doc, "6.4 Closed-Loop Lighting Test", [
        "The S1.6 firmware calibrated the inverse LDR response with dark raw 4057 and bright raw 119. Three physical-sensor sessions supplied 18,003 rows. Across the recorded sessions, calibration was valid in 100% of rows, model-versus-rule PWM MAE was 1.37, correlation was 0.9966, PIR was low in 93.30% of rows, temperature ranged 31.0–31.7 °C, humidity 64–68%, and calibrated LDR10 covered 0–1023. The zero-second median and p95 change time reflect the 100-ms logging resolution and must be described as below/within one sampling interval, not literally instantaneous."
    ])
    add_table(doc, "6.4", "S1.6 physical closed-loop summary", ["Metric", "Recorded result", "Interpretation"], [
        ["Sessions / rows", "3 / 18,003", "Three 10-minute captures"],
        ["LDR calibration validity", "100%", "Using recorded dark/bright references"],
        ["Model-rule PWM MAE", "1.37", "Agreement with designed baseline, not ground truth"],
        ["Model-rule correlation", "0.9966", "Strong similarity to designed baseline"],
        ["PIR off fraction", "93.30%", "Across the three sessions"],
        ["Temperature / humidity", "31.0–31.7 °C / 64–68%", "Observed session ranges"],
    ])
    add_figure(doc, "6.4", "Closed-loop model PWM and rule-baseline traces.", "reports/s1_6/fig_closed_loop.png")
    add_section_text(doc, "6.5 Stage 2 Software and Physical-Node Implementation", [
        "The Stage 2 synthetic workflow generated 5,000 rows, a stratified 4,000/1,000 split, a weighted Random Forest baseline, a 209-parameter neural classifier, a 3,080-byte full-int8 TFLite model, and a two-node FedAvg simulation. Earlier physical run 04bbb7f13378 used sensor-rule pseudo-labels. Revised TLS/SYNTHETIC/SIMULATED run df216f34a23b completed three rounds with 3/3, 3/3, and 3/1 local samples in 54.648 seconds. Fixed-policy TLS run 8f75883f0472 completed three rounds with 5/5 samples per round in 29.004 seconds. Both runs had all six updates and ACKs. The new model-only firmware uses an 85%-flash/17%-RAM build. This comparison shows protocol sample/runtime tradeoffs, not measured energy savings. Ground-truth anomaly evaluation and TFLite OTA remain unverified."
    ])

    add_section_text(doc, "6.5.1 TLS and Energy-Policy Verification", [
        "The final firmware revision uses a two-op TFLM resolver and CA-verified MQTT TLS on port 8883. It compiled in the default app partition at 1,124,192/1,310,720 bytes (85%) flash and 56,724/327,680 bytes (17%) dynamic memory. Physical run df216f34a23b completed three TLS FedAvg rounds with simulated 55% start and local samples 3/3, 3/3, and 3/1; fixed-policy run 8f75883f0472 used 5/5 throughout. The LAN plaintext broker was stopped and its config is now loopback-only. The TLS listener remains anonymous; broker authentication/ACLs are needed for client access control. Simulated battery state is not measured."
    ])

    # CHAPTER 7
    add_chapter(doc, 7, "Evaluation")
    add_section_text(doc, "7.1 Evaluation of Stage 1 Regression", [
        "The 10-tree forest achieved cross-validation R² 0.9403±0.0138 and held-out R² 0.9380 on the synthetic lighting target. A single depth-5 tree obtained a similar held-out R² of 0.9383, so the ensemble's benefit is small for this generated dataset. This weakens any claim that ten trees are necessary solely for predictive accuracy; embedded cost and implementation constraints remain relevant. The very large maximum absolute error (250.55 PWM units) also means that a low MAE alone does not describe all failure cases."
    ])
    add_section_text(doc, "7.2 Embedded Feasibility", [
        "S1.4 provides direct evidence that the exported model reproduces Python predictions on the tested vectors and executes quickly on the ESP32-S3. The correct measured flash delta is 9,104 bytes, not the earlier paper estimate of 3.2 KB. Mean per-call latency was approximately 2.28 μs under the stated build. Static RAM comparison was not available in the summary, so the earlier '<1 KB RAM' claim is not substantiated by this experiment."
    ])
    add_section_text(doc, "7.3 Sensor and Closed-Loop Evaluation", [
        "S1.5 shows that DHT11, OLED, and logging cadence were reliable in the tested session, but the LDR's statistical separation/noise and PIR false-trigger behavior did not satisfy the stated criteria. S1.6 demonstrates that, after calibration, the model outputs were close to the chosen rule baseline over the recorded input range. Because the baseline is itself an engineered rule, the low MAE and high correlation cannot be interpreted as model accuracy against user-preferred lighting. No lux meter, controlled illuminance reference, user study, or energy meter was used."
    ])
    add_section_text(doc, "7.4 Stage 2 Development Simulation", [
        "On the generated anomaly split, the Random Forest achieved accuracy 0.94, anomaly precision 0.602, recall 0.738, F1 0.663, and ROC-AUC 0.979. The neural model achieved accuracy 0.933, precision 0.544, recall 1.000, F1 0.705, and ROC-AUC 0.979; the int8 model preserved these threshold metrics and used 3,080 bytes. In the five-round synthetic two-node simulation, final global F1 was 0.631 and ROC-AUC 0.961. Earlier physical run 04bbb7f13378 used sensor-rule labels over plaintext. Revised TLS run df216f34a23b completed three rounds in 54.648 seconds with sample counts 3/3, 3/3, and 3/1 (16 total). Fixed-policy TLS run 8f75883f0472 completed three rounds in 29.004 seconds with 5/5 samples per round (30 total). Both had six global ACKs. These run-specific sample/runtime differences demonstrate the simulated policy tradeoff, not measured energy savings; round times include local sampling/training, not just network latency. Neither run establishes anomaly accuracy."
    ])
    add_table(doc, "7.1", "Stage 2 synthetic classifier results", ["Model", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "Test rows"], [
        ["Random Forest", "0.940", "0.602", "0.738", "0.663", "0.979", "1,000"],
        ["Neural network", "0.933", "0.544", "1.000", "0.705", "0.979", "1,000"],
        ["QAT / int8 TFLite", "0.933", "0.544", "1.000", "0.705", "0.980", "1,000"],
    ])
    add_table(doc, "7.2", "Stage 2 two-node development summary", ["Experiment", "Nodes", "Rounds", "Key result", "Evidence type"], [
        ["FedAvg", "2 simulated", "5", "Global F1 0.631; ROC-AUC 0.961", "Synthetic Python simulation"],
        ["MQTT weight exchange", "2 simulated", "3", "21 logged events; aggregation intervals 137.6/3.0/3.0 ms", "Synthetic laptop simulation"],
        ["Physical FedAvg (earlier firmware)", "2 ESP32-S3", "3", "5 sensor-rule samples/node/round; 6 updates and 6 ACKs; 29.613 s START-to-STOP", "Physical run 04bbb7f13378; pseudo-labels"],
        ["Physical TLS/energy FedAvg", "2 ESP32-S3", "3", "Samples/node 3/3, 3/3, 3/1; 6 ACKs; 54.648 s; TLS", "Physical run df216f34a23b; synthetic labels/energy"],
        ["Physical TLS fixed-policy control", "2 ESP32-S3", "3", "5/5 samples/node/round; 6 ACKs; 29.004 s", "Physical run 8f75883f0472; synthetic labels; fixed policy"],
        ["TLS firmware build", "2 ESP32-S3 target", "N/A", "1,124,192 B flash (85%); 56,724 B RAM (17%)", "Default partition; TLS port 8883"],
        ["Earlier ESP32-S3 firmware build", "1 compiled sketch", "N/A", "1,245,724 B flash (95%); 61,820 B dynamic memory (18%)", "Prior firmware configuration"],
        ["Physical telemetry/energy policy", "2 ESP32-S3", "101 received rows", "Both node IDs; 100% mode PWM-cap compliance", "Physical sensor telemetry; battery simulated"],
    ])
    add_figure(doc, "7.1", "Global anomaly F1 across simulated two-node FedAvg rounds (synthetic data only).",
               "stage2/reports/phase_b/fig_two_node_fedavg.png")
    add_figure(doc, "7.2", "Samples per node and simulated battery-policy mode; battery values are not measured.",
               "stage2/reports/energy_policy/fig_energy_policy_modes.png")
    add_section_text(doc, "7.5 Threats to Validity", [
        "Internal validity is limited by rule-generated labels and potentially optimistic agreement with the same assumptions used in training. External validity is limited to one prototype environment and a small set of sensor positions. Stage 2 anomaly data does not represent measured prevalence or field ground truth. The fixed-versus-simulated energy runs compare local sample counts and completion times using a simulated battery state; they do not measure current, voltage, joules, battery life, or energy savings. MQTT timing is aggregator-observed and includes local sampling/training."
    ])

    # CHAPTER 8
    add_chapter(doc, 8, "Conclusion and Recommendations")
    add_section_text(doc, "8.1 Conclusion", [
        "The project implemented and measured an ESP32-S3 smart-lighting inference path and documented both successful checks and hardware limitations. The selected synthetic-data Random Forest was exported successfully, matched Python after 8-bit rounding on 500 board test vectors, and had measured mean inference latency near 2.28 μs. The sensor bring-up revealed LDR/PIR limitations, while calibrated closed-loop sessions showed agreement with a designed rule comparator. Stage 2 includes synthetic anomaly experiments and two physical FedAvg demonstrations; the latest run df216f34a23b completed three TLS rounds with simulated energy adaptation and local-only sensor transport. It demonstrates physical aggregation and global-update return, not real-world anomaly accuracy. MQTT client authentication, formal privacy, measured energy savings, and TFLite OTA remain unverified."
    ])
    add_section_text(doc, "8.2 Recommendations", [
        "First, configure broker authentication/ACLs because the TLS listener permits anonymous clients, then repeat TLS runs under varied node data distributions and preserve serial/ISO-UTC logs. Obtain independent ground-truth labels before making anomaly-accuracy claims. Improve and repeat LDR/PIR characterization, measure actual battery voltage/current before energy claims, and verify references and KDU formatting before submission."
    ])

    # References carried forward from the source paper; check metadata before submission.
    doc.add_page_break(); doc.add_heading("REFERENCE LIST", level=1)
    add_body(doc, "DRAFT NOTE: These references were carried forward from the source paper. Verify each title, author list, publication venue, volume, pages, and DOI against the original publication before final submission. The KDU guide permits APA or IEEE referencing; the entries below are formatted in a consistent numbered style for this draft.")
    references = [
        "[1] M. S. Pan, T. C. Tsai, and Y. C. Tseng, ‘An intelligent lighting control system based on occupancy detection and wireless sensor networks,’ IEEE Sensors Journal, vol. 13, no. 12, pp. 4824–4831, 2013.",
        "[2] B. Dong and K. P. Lam, ‘Building energy and comfort management through occupant behaviour pattern detection based on a large-scale environmental sensor network,’ Journal of Building Performance Simulation, vol. 4, no. 4, pp. 359–369, 2011.",
        "[3] Y. Abadade et al., ‘A comprehensive survey on TinyML,’ IEEE Access, vol. 11, pp. 96892–96922, 2023.",
        "[4] N. N. Alajlan and D. M. Ibrahim, ‘TinyML: enabling inference deep learning models on ultra-low-power IoT edge devices for AI applications,’ Micromachines, vol. 13, no. 6, p. 851, 2022.",
        "[5] Y. Xu, C. Lu, and S. Wang, ‘TinyML for IoT: enabling on-device intelligence for smart environments,’ IEEE Internet of Things Journal, vol. 9, no. 15, pp. 13380–13392, 2022.",
        "[6] L. Breiman, ‘Random Forests,’ Machine Learning, vol. 45, no. 1, pp. 5–32, 2001.",
        "[7] R. Abdel Sater and A. Ben Hamza, ‘A federated learning approach to anomaly detection in smart buildings,’ ACM Transactions on Internet of Things, vol. 2, no. 1, pp. 1–23, 2021.",
        "[8] F. Pedregosa et al., ‘Scikit-learn: Machine Learning in Python,’ Journal of Machine Learning Research, vol. 12, pp. 2825–2830, 2011.",
        "[9] Espressif Systems, ESP32-S3 Technical Reference Manual, version 1.0, 2021.",
        "[10] S. Jain and V. Garg, ‘Occupancy detection and localization for smart building using passive infrared sensor network,’ in Proc. IEEE ICSET, pp. 346–351, 2019.",
        "[11] N. D. Lane et al., ‘An early resource characterization of deep learning on wearables, smartphones and internet-of-things devices,’ in Proc. IoT-App, pp. 7–12, 2015.",
        "[12] A. Williams, S. Martinez, and R. Johnson, ‘Energy-efficient smart lighting control using machine learning,’ IEEE Transactions on Smart Grid, vol. 10, no. 4, pp. 3712–3721, 2019.",
    ]
    for reference in references:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_after = Pt(12)
        set_run_font(p.add_run(reference), 11)

    doc.add_page_break(); doc.add_heading("APPENDIX A: VERIFIED REPORT INVENTORY", level=1)
    add_bullets(doc, [
        "Stage 1 reports: reports/s1_1 through reports/s1_6, each with DOCX and summary JSON.",
        "Stage 2 synthetic reports: stage2/reports/phase_a and stage2/reports/phase_b; clearly marked DEV_ONLY.",
        "Physical Stage 2 pilot: stage2/data/pilot_unlabeled.csv (61 messages: Node 1 = 30, Node 2 = 31).",
        "Physical Stage 2 energy-policy pilot: stage2/data/energy_policy_sim.csv (101 messages: Node 1 = 50, Node 2 = 51); battery source is simulated.",
        "Physical FedAvg run 04bbb7f13378: stage2/data/physical_fedavg_04bbb7f13378_events.jsonl and stage2/reports/phase_b/physical_fedavg_04bbb7f13378_summary.json; three ESP32 rounds with both node updates and acknowledgements recorded. No physical Stage 2 ground-truth anomaly dataset is present.",
        "Physical TLS/energy run df216f34a23b: stage2/data/physical_fedavg_df216f34a23b_events.jsonl and stage2/reports/phase_b/physical_fedavg_df216f34a23b_summary.json; three TLS rounds, ISO-UTC events, simulated starting battery at 55%, sample counts 3/3, 3/3, 3/1, and all six ACKs recorded.",
        "Fixed-policy TLS control run 8f75883f0472 and comparison: stage2/data/physical_fedavg_8f75883f0472_events.jsonl, stage2/reports/phase_b/physical_fedavg_8f75883f0472_summary.json, and stage2/reports/phase_b/physical_fedavg_energy_comparison_20261025.md.",
    ])
    doc.add_heading("APPENDIX B: DRAFT COMPLETION CHECKLIST", level=1)
    add_bullets(doc, [
        "Confirm official candidate name/registration number and supervisor name/title.",
        "Replace draft cover/title details and obtain signed candidate/supervisor declarations.",
        "Review Stage 1 S1.5 failed checks and avoid describing them as passes.",
        "Keep synthetic model and MQTT results explicitly labelled as simulation evidence.",
        "Update the automatic table of contents and page references in Microsoft Word.",
        "Verify citations and references; add no unsourced numeric claims.",
        "Add original, permission-cleared prototype photographs and update lists of figures/tables.",
        "Confirm final KDU submission details with the department/supervisor.",
    ])

    settings = doc.settings._element
    update_fields = OxmlElement("w:updateFields")
    update_fields.set(qn("w:val"), "true")
    settings.append(update_fields)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(f"Saved thesis draft: {OUTPUT}")
    print(f"Abstract words: {word_count}")
    print(f"Sections: {len(doc.sections)}; tables: {len(doc.tables)}; paragraphs: {len(doc.paragraphs)}")


if __name__ == "__main__":
    build()
