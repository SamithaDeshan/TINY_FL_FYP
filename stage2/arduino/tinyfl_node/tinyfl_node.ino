// TinyFL Stage 2 physical node: sensor inference + MQTT telemetry.
// Copy secrets.h.example to secrets.h and fill in local Wi-Fi credentials.
// Upload the same sketch to both boards, changing NODE_ID to 1 or 2.
// This development firmware uses the synthetic int8 model; do not cite its outputs.
#ifndef NODE_ID
#define NODE_ID 2
#endif

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include "Chirale_TensorFlowLite.h"
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "../../models/DEV_ONLY_model_data.h"
#include "secrets.h"

#define PIR_PIN 4
#define LDR_PIN 1
#define DHT_PIN 5
#define DHT_TYPE DHT11
#define LED_PWM_PIN 6
#define LED_PWM_FREQ 5000
#define LED_PWM_RES 8
#define OLED_SDA 8
#define OLED_SCL 9
#define OLED_ADDR 0x3C
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_RESET -1
#define SAMPLE_PERIOD_MS 2000
#define ECO_SAMPLE_PERIOD_MS 5000
#define CRITICAL_SAMPLE_PERIOD_MS 15000
#define BATTERY_SIM_STEP_MS 3000
#define MQTT_TOPIC "tinyfl/node/result"
#define TENSOR_ARENA_BYTES 8192
#define INPUT_SCALE 0.018108580261468887f
#define INPUT_ZERO_POINT -40
#define OUTPUT_SCALE 0.00390625f
#define OUTPUT_ZERO_POINT -128
#define NORMAL_TEMP_MEAN 27.6385f
#define NORMAL_TEMP_STD 2.4765536032963227f
#define NORMAL_HUM_MEAN 70.33525f
#define NORMAL_HUM_STD 6.496757455646625f
#define NORMAL_PIR_MEAN 0.10025f
#define NORMAL_PIR_STD 0.30033304430248764f

DHT dht(DHT_PIN, DHT_TYPE);
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET);
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
uint8_t tensorArena[TENSOR_ARENA_BYTES];
tflite::AllOpsResolver resolver;
const tflite::Model* tflModel = nullptr;
tflite::MicroInterpreter* interpreter = nullptr;
TfLiteTensor* input = nullptr;
TfLiteTensor* output = nullptr;
uint32_t sampleNumber = 0;
uint32_t lastSample = 0;
bool oledOk = false;
float lastTemperature = NAN;
float lastHumidity = NAN;
float lastProbability = 0.0f;
int lastPir = 0;
int lastLdrRaw = 0;
int lastLdr10 = 0;
int lastAnomaly = 0;
uint8_t simulatedBatteryPct = 100;
uint8_t indicatorPwm = 0;
bool batterySimulationEnabled = false;
uint32_t lastBatteryStep = 0;

static const char* energyMode() {
  if (simulatedBatteryPct <= 20) return "CRITICAL";
  if (simulatedBatteryPct <= 60) return "ECO";
  return "NORMAL";
}

static uint32_t samplePeriodForEnergyMode() {
  if (simulatedBatteryPct <= 20) return CRITICAL_SAMPLE_PERIOD_MS;
  if (simulatedBatteryPct <= 60) return ECO_SAMPLE_PERIOD_MS;
  return SAMPLE_PERIOD_MS;
}

static uint8_t maxIndicatorPwmForEnergyMode() {
  if (simulatedBatteryPct <= 20) return 0;
  if (simulatedBatteryPct <= 60) return 128;
  return 255;
}

static void pwmInit() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(LED_PWM_PIN, LED_PWM_FREQ, LED_PWM_RES);
#else
  ledcSetup(0, LED_PWM_FREQ, LED_PWM_RES);
  ledcAttachPin(LED_PWM_PIN, 0);
#endif
}

static void pwmWriteIndicator(uint8_t duty) {
  indicatorPwm = duty;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(LED_PWM_PIN, duty);
#else
  ledcWrite(0, duty);
#endif
}

static void drawStatus(const char* state) {
  if (!oledOk) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.printf("TinyFL Node %d", NODE_ID);
  display.setCursor(0, 12);
  if (isnan(lastTemperature)) display.printf("T:-- H:-- LDR:%d", lastLdr10);
  else display.printf("T:%.0f H:%.0f LDR:%d", lastTemperature, lastHumidity, lastLdr10);
  display.setCursor(0, 24);
  display.printf("PIR:%d Lraw:%d", lastPir, lastLdrRaw);
  display.setCursor(0, 36);
  display.printf("Anom:%d P:%.2f LED:%u", lastAnomaly, lastProbability, indicatorPwm);
  display.setCursor(0, 48);
  display.printf("BAT:%u%% %s", simulatedBatteryPct, energyMode());
  display.setCursor(0, 56);
  display.printf("%s %s #%lu", WiFi.status() == WL_CONNECTED ? "W+" : "W-",
                mqtt.connected() ? state : "M-", (unsigned long)sampleNumber);
  display.display();
}

static void handleSerialCommands() {
  while (Serial.available()) {
    char command = (char)Serial.read();
    if (command == 'B' || command == 'b') {
      simulatedBatteryPct = 100;
      batterySimulationEnabled = true;
      lastBatteryStep = millis();
      Serial.println("# battery_sim_started percent=100 source=simulated");
      drawStatus("battery_sim");
    } else if (command == 'R' || command == 'r') {
      batterySimulationEnabled = false;
      simulatedBatteryPct = 100;
      pwmWriteIndicator(0);
      Serial.println("# battery_sim_reset percent=100 source=simulated");
      drawStatus("battery_reset");
    }
  }
}

static void updateBatterySimulation() {
  if (!batterySimulationEnabled || millis() - lastBatteryStep < BATTERY_SIM_STEP_MS) return;
  lastBatteryStep = millis();
  const char* previousMode = energyMode();
  int drop = random(1, 6);
  simulatedBatteryPct = drop >= simulatedBatteryPct ? 0 : simulatedBatteryPct - drop;
  const char* currentMode = energyMode();
  Serial.printf("# battery_sim percent=%u drop=%d mode=%s\n", simulatedBatteryPct, drop, currentMode);
  if (strcmp(previousMode, currentMode) != 0) {
    Serial.printf("# energy_mode_changed mode=%s sample_period_ms=%lu\n",
                  currentMode, (unsigned long)samplePeriodForEnergyMode());
  }
  if (simulatedBatteryPct == 0) {
    batterySimulationEnabled = false;
    Serial.println("# battery_sim_empty source=simulated");
  }
}

static void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("# wifi_connecting node=%d\n", NODE_ID);
  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("# wifi_ok ip=%s\n", WiFi.localIP().toString().c_str());
    drawStatus("wifi_ok");
  } else {
    Serial.println("# wifi_failed");
    drawStatus("wifi_fail");
  }
}

static void connectMqtt() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  String clientId = "tinyfl-node-" + String(NODE_ID) + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.printf("# mqtt_connect server=%s port=%d\n", MQTT_SERVER, MQTT_PORT);
  if (mqtt.connect(clientId.c_str())) {
    Serial.println("# mqtt_ok");
    drawStatus("mqtt_ok");
  } else {
    Serial.printf("# mqtt_failed state=%d\n", mqtt.state());
    drawStatus("mqtt_fail");
  }
}

static int8_t quantizeInput(float value) {
  int quantized = (int)lroundf(value / INPUT_SCALE + INPUT_ZERO_POINT);
  return (int8_t)constrain(quantized, -128, 127);
}

static bool setupModel() {
  tflModel = tflite::GetModel(g_model);
  static tflite::MicroInterpreter staticInterpreter(tflModel, resolver, tensorArena,
                                                      TENSOR_ARENA_BYTES, nullptr);
  interpreter = &staticInterpreter;
  if (interpreter->AllocateTensors() != kTfLiteOk) {
    Serial.println("# model_allocate_failed");
    return false;
  }
  input = interpreter->input(0);
  output = interpreter->output(0);
  Serial.printf("# model_ok arena=%d input_scale=%.9f input_zero=%d\n",
                TENSOR_ARENA_BYTES, INPUT_SCALE, INPUT_ZERO_POINT);
  return true;
}

static void publishSample() {
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();
  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("# dht_read_failed");
    return;
  }
  int pir = digitalRead(PIR_PIN);
  int ldrRaw = analogRead(LDR_PIN);
  int ldr10 = ldrRaw >> 2;
  lastPir = pir;
  lastLdrRaw = ldrRaw;
  lastLdr10 = ldr10;
  float normalized[3] = {
    (temperature - NORMAL_TEMP_MEAN) / NORMAL_TEMP_STD,
    (humidity - NORMAL_HUM_MEAN) / NORMAL_HUM_STD,
    (pir - NORMAL_PIR_MEAN) / NORMAL_PIR_STD,
  };
  for (int index = 0; index < 3; index++) input->data.int8[index] = quantizeInput(normalized[index]);
  uint32_t inferenceStart = micros();
  if (interpreter->Invoke() != kTfLiteOk) {
    Serial.println("# model_invoke_failed");
    return;
  }
  uint32_t inferenceUs = micros() - inferenceStart;
  float probability = (output->data.int8[0] - OUTPUT_ZERO_POINT) * OUTPUT_SCALE;
  probability = constrain(probability, 0.0f, 1.0f);
  int anomaly = probability >= 0.5f;
  uint8_t requestedPwm = (uint8_t)constrain((int)lroundf(probability * 255.0f), 0, 255);
  pwmWriteIndicator(min(requestedPwm, maxIndicatorPwmForEnergyMode()));
  lastTemperature = temperature;
  lastHumidity = humidity;
  lastProbability = probability;
  lastAnomaly = anomaly;
  String payload = "{\"node\":" + String(NODE_ID) +
                   ",\"sample\":" + String(sampleNumber++) +
                   ",\"anomaly\":" + String(anomaly) +
                   ",\"confidence\":" + String(probability, 4) +
                   ",\"temperature\":" + String(temperature, 1) +
                   ",\"humidity\":" + String(humidity, 1) +
                   ",\"pir\":" + String(pir) +
                   ",\"ldr_raw\":" + String(ldrRaw) +
                   ",\"ldr10\":" + String(ldr10) +
                   ",\"inference_us\":" + String(inferenceUs) +
                   ",\"battery_pct\":" + String(simulatedBatteryPct) +
                   ",\"battery_source\":\"simulated\"" +
                   ",\"energy_mode\":\"" + String(energyMode()) + "\"" +
                   ",\"indicator_pwm\":" + String(indicatorPwm) +
                   ",\"sample_period_ms\":" + String(samplePeriodForEnergyMode());
  uint32_t publishUs = 0;
  bool publishOk = false;
  if (mqtt.connected()) {
    uint32_t publishStart = micros();
    String mqttPayload = payload + "}";
    publishOk = mqtt.publish(MQTT_TOPIC, mqttPayload.c_str());
    publishUs = micros() - publishStart;
    if (!publishOk) {
      Serial.printf("# mqtt_publish_failed state=%d payload_bytes=%u\n",
                    mqtt.state(), (unsigned)mqttPayload.length());
    }
  } else {
    Serial.println("# mqtt_publish_skipped disconnected");
  }
  payload += ",\"publish_us\":" + String(publishUs) +
             ",\"mqtt_published\":" + String(publishOk ? 1 : 0) + "}";
  Serial.println(payload);
  drawStatus("sample");
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(PIR_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(LDR_PIN, ADC_11db);
  dht.begin();
  pwmInit();
  pwmWriteIndicator(0);
  Wire.begin(OLED_SDA, OLED_SCL);
  oledOk = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  if (oledOk) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.printf("TinyFL Node %d boot", NODE_ID);
    display.display();
  }
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  if (!mqtt.setBufferSize(512)) {
    Serial.println("# mqtt_buffer_resize_failed");
  } else {
    Serial.println("# mqtt_buffer_bytes=512");
  }
  Serial.printf("# source=hardware stage=stage2 node=%d\n", NODE_ID);
  Serial.printf("# oled=%s\n", oledOk ? "ok" : "NOT_FOUND");
  Serial.println("# serial_commands B=start random battery demo R=reset demo");
  if (!setupModel()) return;
  connectWifi();
  connectMqtt();
}

void loop() {
  handleSerialCommands();
  updateBatterySimulation();
  connectWifi();
  connectMqtt();
  mqtt.loop();
  if (millis() - lastSample >= samplePeriodForEnergyMode()) {
    lastSample = millis();
    publishSample();
  }
}
