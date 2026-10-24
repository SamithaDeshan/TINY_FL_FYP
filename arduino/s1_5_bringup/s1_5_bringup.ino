//cd "C:\Users\Sammy's WorkStation\Desktop\TINY_FL_FYP"
//& c:\python314\python.exe "C:/Users/Sammy's WorkStation/Desktop/TINY_FL_FYP/TinyFL_Hardware/tools/logger.py" --port COM9 --out TinyFL_Hardware/data/s1_5_session1.csv// ============================================================================
// TinyFL - Stage 1 hardware validation
// STEP S1.5 (Arduino IDE sketch): Bring-up + sensor characterisation logger (ESP32-S3)
//
// Streams one CSV row every 100 ms over serial:
//   ms,label,pir,ldr_raw,ldr10,temp_c,hum_pct,dht_status,pwm
//
//   ldr_raw    : 12-bit ADC (0-4095) - native ESP32-S3 resolution
//   ldr10      : ldr_raw >> 2 (0-1023) - the scale used in the Stage 1 paper/model
//   dht_status : 1 = new valid reading this row, 0 = no new reading this row,
//               -1 = read attempted and FAILED this row
//   pwm        : current LED duty (0-255)
//
// Serial commands (type in the monitor/logger, press Enter):
//   L <name>   set the label written into the CSV (e.g. L dark, L motion)
//   P <0-255>  set LED PWM manually
//   R          run a 0 -> 255 -> 0 PWM ramp (about 10 s)
//   I          print info/metadata lines again
// ============================================================================
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include "../s1_4_benchmark/smart_light_model_f32.h"

typedef Eloquent::ML::Port::RandomForestRegressorF32 Model;

// ---------- PIN DEFINITIONS ----------
#define OLED_SDA 8
#define OLED_SCL 9
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDR 0x3C

#define PIR_PIN 4
#define LDR_PIN 1
#define DHT_PIN 5
#define DHT_TYPE DHT11

#define LED_PWM_PIN 6
#define LED_PWM_FREQ 5000
#define LED_PWM_RES 8
#define LED_PWM_CH 0  // only used on core 2.x

// ---------- TIMING ----------
#define LOG_PERIOD_MS 100
#define DHT_PERIOD_MS 2000  // DHT11 max rate is 1 Hz; 2 s is safe
#define OLED_PERIOD_MS 250

Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET);
DHT dht(DHT_PIN, DHT_TYPE);

bool oledOk = false;
String label = "none";
uint8_t pwmValue = 0;
float tempC = NAN, hum = NAN;

// automatic LED/LDR validation state
bool autoBrightCheck = false;
uint32_t autoCheckStart = 0;

// random model test state
Model model;
bool randomModelTest = false;
uint32_t randomModelNext = 0;
uint8_t randomModelSamples = 0;

// ramp state
bool rampActive = false;
uint32_t rampStart = 0;

static void pwmInit() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(LED_PWM_PIN, LED_PWM_FREQ, LED_PWM_RES);
#else
  ledcSetup(LED_PWM_CH, LED_PWM_FREQ, LED_PWM_RES);
  ledcAttachPin(LED_PWM_PIN, LED_PWM_CH);
#endif
}

static void pwmWrite(uint8_t v) {
  pwmValue = v;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(LED_PWM_PIN, v);
#else
  ledcWrite(LED_PWM_CH, v);
#endif
}

static void printMeta() {
  Serial.println("# source=hardware");
  Serial.printf("# chip=%s rev=%d cores=%d cpu_mhz=%d\n", ESP.getChipModel(),
                (int)ESP.getChipRevision(), (int)ESP.getChipCores(),
                (int)ESP.getCpuFreqMHz());
  Serial.printf("# flash_chip_bytes=%u sketch_bytes=%u free_sketch_bytes=%u\n",
                (unsigned)ESP.getFlashChipSize(), (unsigned)ESP.getSketchSize(),
                (unsigned)ESP.getFreeSketchSpace());
  Serial.printf("# heap_total=%u heap_free=%u min_heap_free=%u\n",
                (unsigned)ESP.getHeapSize(), (unsigned)ESP.getFreeHeap(),
                (unsigned)ESP.getMinFreeHeap());
  Serial.printf("# pins pir=%d ldr=%d dht=%d led_pwm=%d oled_sda=%d oled_scl=%d\n",
                PIR_PIN, LDR_PIN, DHT_PIN, LED_PWM_PIN, OLED_SDA, OLED_SCL);
  Serial.printf("# dht_type=DHT11 pwm_freq=%d pwm_res_bits=%d oled=%s\n",
                LED_PWM_FREQ, LED_PWM_RES, oledOk ? "ok" : "NOT_FOUND");
  Serial.println("# columns=ms,label,pir,ldr_raw,ldr10,temp_c,hum_pct,dht_status,pwm");
}

static void handleSerial() {
  static String line;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c != '\n') { line += c; continue; }

    line.trim();
    if (line.length() > 0) {
      char cmd = toupper(line[0]);
      String arg = line.substring(1);
      arg.trim();

      if (cmd == 'L' && arg.length() > 0) {
        arg.replace(',', '_');
        arg.replace(' ', '_');
        label = arg;
        Serial.printf("# label=%s\n", label.c_str());
      }
      else if (cmd == 'P') {
        rampActive = false;
        autoBrightCheck = false;
        randomModelTest = false;
        pwmWrite((uint8_t)constrain(arg.toInt(), 0, 255));
        Serial.printf("# pwm_set=%d\n", pwmValue);
      }
      else if (cmd == 'H') {   // maximum brightness test
        rampActive = false;
        autoBrightCheck = false;
        randomModelTest = false;
        pwmWrite(255);
        Serial.println("# led_full_brightness");
      }
      else if (cmd == 'A') {   // automatic dark/bright check
        rampActive = false;
        randomModelTest = false;
        autoBrightCheck = true;
        autoCheckStart = millis();
        pwmWrite(0);
        Serial.println("# auto_brightness_check_start");
      }
      else if (cmd == 'T') {   // run 20 random in-range model inputs
        rampActive = false;
        autoBrightCheck = false;
        randomModelTest = true;
        randomModelSamples = 0;
        randomModelNext = millis();
        label = "random_model";
        Serial.println("# random_model_test_start samples=20");
      }
      else if (cmd == 'R') {
        rampActive = true;
        autoBrightCheck = false;
        randomModelTest = false;
        rampStart = millis();
        Serial.println("# ramp_start");
      }
      else if (cmd == 'I') {
        printMeta();
      }
    }
    line = "";
  }
}

static void updateRamp() {
  if (!rampActive) return;
  uint32_t t = millis() - rampStart;  // 0..10000 ms
  if (t >= 10000) {
    rampActive = false;
    pwmWrite(0);
    Serial.println("# ramp_end");
    return;
  }
  uint32_t v = (t < 5000) ? (t * 255UL / 5000UL) : ((10000 - t) * 255UL / 5000UL);
  pwmWrite((uint8_t)v);
}

static void updateAutoBrightnessCheck() {
  if (!autoBrightCheck) return;

  uint32_t t = millis() - autoCheckStart;
  if (t < 1500) {
    pwmWrite(0);
    return;
  }
  if (t < 3000) {
    pwmWrite(255);
    Serial.println("# auto_check_bright");
    return;
  }
  if (t < 4500) {
    pwmWrite(0);
    Serial.println("# auto_check_dark");
    return;
  }

  autoBrightCheck = false;
  pwmWrite(0);
  Serial.println("# auto_brightness_check_done");
}

static void updateRandomModelTest() {
  if (!randomModelTest || (int32_t)(millis() - randomModelNext) < 0) return;

  randomModelNext = millis() + 2000;
  int pir = random(0, 2);
  int ldr = random(0, 1024);
  int temp = random(15, 36);
  int hum = random(30, 81);
  float features[4] = {(float)pir, (float)ldr, (float)temp, (float)hum};
  float prediction = model.predict(features);
  uint8_t duty = (uint8_t)constrain((int)(prediction + 0.5f), 0, 255);
  pwmWrite(duty);
  randomModelSamples++;
  Serial.printf("# random_model_sample=%u,pir=%d,ldr=%d,temp=%d,hum=%d,pred_pwm=%.2f,applied_pwm=%u\n",
                randomModelSamples, pir, ldr, temp, hum, prediction, duty);

  if (randomModelSamples >= 20) {
    randomModelTest = false;
    Serial.println("# random_model_test_done");
  }
}

static void drawOled(int pir, int ldr10) {
  if (!oledOk) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.printf("TinyFL S1 bring-up");
  display.setCursor(0, 12);
  display.printf("PIR:%d  LDR:%4d", pir, ldr10);
  display.setCursor(0, 24);
  if (isnan(tempC)) display.printf("T: --   H: --");
  else display.printf("T:%.0fC  H:%.0f%%", tempC, hum);
  display.setCursor(0, 36);
  display.printf("PWM:%3u", pwmValue);
  display.setCursor(0, 48);
  display.printf("L:%.16s", label.c_str());
  display.display();
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  randomSeed((uint32_t)analogRead(LDR_PIN) ^ micros());

  pinMode(PIR_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(LDR_PIN, ADC_11db);  // full ~0-3.1 V range
  pwmInit();
  pwmWrite(0);

  Wire.begin(OLED_SDA, OLED_SCL);
  oledOk = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  dht.begin();

  printMeta();
  Serial.println("ms,label,pir,ldr_raw,ldr10,temp_c,hum_pct,dht_status,pwm");
}

void loop() {
  static uint32_t tLog = 0, tDht = 0, tOled = 0;
  uint32_t now = millis();

  handleSerial();
  updateRamp();
  updateAutoBrightnessCheck();
  updateRandomModelTest();

  static int8_t pendingDht = 0;  // held until the next CSV row consumes it
  if (now - tDht >= DHT_PERIOD_MS) {
    tDht = now;
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (isnan(h) || isnan(t)) {
      pendingDht = -1;
    } else {
      hum = h;
      tempC = t;
      pendingDht = 1;
    }
  }

  if (now - tLog >= LOG_PERIOD_MS) {
    tLog = now;
    int pir = digitalRead(PIR_PIN);
    int ldrRaw = analogRead(LDR_PIN);
    int ldr10 = ldrRaw >> 2;
    Serial.printf("%u,%s,%d,%d,%d,", (unsigned)now, label.c_str(), pir, ldrRaw, ldr10);
    if (isnan(tempC)) Serial.print("nan,nan,");
    else Serial.printf("%.1f,%.1f,", tempC, hum);
    Serial.printf("%d,%u\n", pendingDht, pwmValue);
    pendingDht = 0;

    if (now - tOled >= OLED_PERIOD_MS) {
      tOled = now;
      drawOled(pir, ldr10);
    }
  }
}
