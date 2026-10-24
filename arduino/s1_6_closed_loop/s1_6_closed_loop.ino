// TinyFL Stage 1.6: closed-loop model versus rule baseline.
// Commands: D = record current dark LDR raw value, B = record bright value,
// S = print calibration, X = clear calibration.
// Calibrate in a stable setup before collecting sessions.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include "../../arduino/s1_4_benchmark/smart_light_model_f32.h"

#define OLED_SDA 8
#define OLED_SCL 9
#define OLED_ADDR 0x3C
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_RESET -1
#define PIR_PIN 4
#define LDR_PIN 1
#define DHT_PIN 5
#define DHT_TYPE DHT11
#define LED_PWM_PIN 6
#define LED_PWM_FREQ 5000
#define LED_PWM_RES 8
#define LED_PWM_CH 0
#define LOG_PERIOD_MS 100
#define DHT_PERIOD_MS 2000

Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET);
DHT dht(DHT_PIN, DHT_TYPE);
Eloquent::ML::Port::RandomForestRegressorF32 model;

bool oledOk = false;
float tempC = NAN, hum = NAN;
uint8_t modelPwm = 0, rulePwm = 0;
int darkRaw = -1;
int brightRaw = -1;
bool calibrationHold = false;

static void pwmInit() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(LED_PWM_PIN, LED_PWM_FREQ, LED_PWM_RES);
#else
  ledcSetup(LED_PWM_CH, LED_PWM_FREQ, LED_PWM_RES);
  ledcAttachPin(LED_PWM_PIN, LED_PWM_CH);
#endif
}

static void pwmWrite(uint8_t value) {
  modelPwm = value;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(LED_PWM_PIN, value);
#else
  ledcWrite(LED_PWM_CH, value);
#endif
}

static int calibratedLdr10(int raw) {
  if (darkRaw < 0 || brightRaw < 0 || darkRaw == brightRaw) return raw >> 2;
  long numerator = (long)(darkRaw - raw) * 1023L;
  long denominator = darkRaw - brightRaw;
  return constrain((int)(numerator / denominator), 0, 1023);
}

static uint8_t rulePrediction(int pir, int ldr10) {
  if (!pir) return 0;
  if (ldr10 <= 300) return 255;
  if (ldr10 >= 700) return 0;
  return (uint8_t)((700 - ldr10) * 255L / 400L);
}

static void printCalibration() {
  Serial.printf("# calibration_dark_raw=%d bright_raw=%d valid=%d\n",
                darkRaw, brightRaw, darkRaw >= 0 && brightRaw >= 0 && darkRaw != brightRaw);
}

static void handleSerial() {
  while (Serial.available()) {
    char command = (char)Serial.read();
    if (command == '\r' || command == '\n') continue;
    if (command == 'D' || command == 'd') {
      calibrationHold = true;
      pwmWrite(0);
      darkRaw = analogRead(LDR_PIN);
      Serial.printf("# set_dark_raw=%d\n", darkRaw);
    } else if (command == 'B' || command == 'b') {
      calibrationHold = true;
      pwmWrite(0);
      brightRaw = analogRead(LDR_PIN);
      Serial.printf("# set_bright_raw=%d\n", brightRaw);
    } else if (command == 'G' || command == 'g') {
      calibrationHold = false;
      Serial.println("# closed_loop_start");
    } else if (command == 'S' || command == 's') {
      printCalibration();
    } else if (command == 'X' || command == 'x') {
      darkRaw = -1;
      brightRaw = -1;
      Serial.println("# calibration_cleared");
    }
  }
}

static void drawOled(int pir, int ldr10) {
  if (!oledOk) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.printf("TinyFL S1.6 closed loop");
  display.setCursor(0, 12);
  display.printf("PIR:%d LDR:%4d", pir, ldr10);
  display.setCursor(0, 24);
  display.printf("M:%3u R:%3u", modelPwm, rulePwm);
  display.setCursor(0, 36);
  if (isnan(tempC)) display.printf("T:-- H:--");
  else display.printf("T:%.0fC H:%.0f%%", tempC, hum);
  display.setCursor(0, 48);
  display.printf("cal:%d/%d", darkRaw, brightRaw);
  display.display();
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  pinMode(PIR_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(LDR_PIN, ADC_11db);
  pwmInit();
  pwmWrite(0);
  Wire.begin(OLED_SDA, OLED_SCL);
  oledOk = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  dht.begin();
  Serial.println("# source=hardware");
  Serial.println("# stage=s1_6_closed_loop");
  Serial.println("# columns=ms,pir,ldr_raw,ldr10,temp_c,hum_pct,model_pwm,rule_pwm,cal_valid");
  printCalibration();
  Serial.println("ms,pir,ldr_raw,ldr10,temp_c,hum_pct,model_pwm,rule_pwm,cal_valid");
}

void loop() {
  static uint32_t lastLog = 0, lastDht = 0, lastOled = 0;
  uint32_t now = millis();
  handleSerial();
  if (now - lastDht >= DHT_PERIOD_MS) {
    lastDht = now;
    float nextHum = dht.readHumidity();
    float nextTemp = dht.readTemperature();
    if (!isnan(nextHum) && !isnan(nextTemp)) {
      hum = nextHum;
      tempC = nextTemp;
    }
  }
  if (now - lastLog < LOG_PERIOD_MS) return;
  lastLog = now;

  int pir = digitalRead(PIR_PIN);
  int raw = analogRead(LDR_PIN);
  int ldr10 = calibratedLdr10(raw);
  int calValid = darkRaw >= 0 && brightRaw >= 0 && darkRaw != brightRaw;
  if (calibrationHold) {
    pwmWrite(0);
    Serial.printf("%u,%d,%d,%d,", (unsigned)now, pir, raw, ldr10);
    if (isnan(tempC)) Serial.print("nan,nan,");
    else Serial.printf("%.1f,%.1f,", tempC, hum);
    Serial.printf("0,0,%d\n", calValid);
    return;
  }
  float features[4] = {(float)pir, (float)ldr10, isnan(tempC) ? 25.0f : tempC, isnan(hum) ? 55.0f : hum};
  float prediction = model.predict(features);
  modelPwm = (uint8_t)constrain((int)(prediction + 0.5f), 0, 255);
  rulePwm = rulePrediction(pir, ldr10);
  pwmWrite(modelPwm);

  Serial.printf("%u,%d,%d,%d,", (unsigned)now, pir, raw, ldr10);
  if (isnan(tempC)) Serial.print("nan,nan,");
  else Serial.printf("%.1f,%.1f,", tempC, hum);
  Serial.printf("%u,%u,%d\n", modelPwm, rulePwm, calValid);

  if (now - lastOled >= 250) {
    lastOled = now;
    drawOled(pir, ldr10);
  }
}
