// TinyFL Stage 2 physical node: sensor inference + MQTT telemetry.
// Copy secrets.h.example to secrets.h and fill in local Wi-Fi credentials.
// Upload the same sketch to both boards, changing NODE_ID to 1 or 2.
// This development firmware uses the synthetic int8 model; do not cite its outputs.
#ifndef NODE_ID
#define NODE_ID 1
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
#define DHT_PIN 5
#define DHT_TYPE DHT11
#define OLED_SDA 8
#define OLED_SCL 9
#define OLED_ADDR 0x3C
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_RESET -1
#define SAMPLE_PERIOD_MS 2000
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
int lastAnomaly = 0;

static void drawStatus(const char* state) {
  if (!oledOk) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.printf("TinyFL Node %d", NODE_ID);
  display.setCursor(0, 12);
  display.printf("WiFi:%s MQTT:%s", WiFi.status() == WL_CONNECTED ? "OK" : "--",
                mqtt.connected() ? "OK" : "--");
  display.setCursor(0, 24);
  if (isnan(lastTemperature)) display.printf("T:-- H:-- PIR:%d", lastPir);
  else display.printf("T:%.0f H:%.0f PIR:%d", lastTemperature, lastHumidity, lastPir);
  display.setCursor(0, 36);
  display.printf("Anom:%d P:%.2f", lastAnomaly, lastProbability);
  display.setCursor(0, 48);
  display.printf("%s #%lu", state, (unsigned long)sampleNumber);
  display.display();
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
  lastPir = pir;
  float normalized[3] = {
    (temperature - NORMAL_TEMP_MEAN) / NORMAL_TEMP_STD,
    (humidity - NORMAL_HUM_MEAN) / NORMAL_HUM_STD,
    (pir - NORMAL_PIR_MEAN) / NORMAL_PIR_STD,
  };
  for (int index = 0; index < 3; index++) input->data.int8[index] = quantizeInput(normalized[index]);
  if (interpreter->Invoke() != kTfLiteOk) {
    Serial.println("# model_invoke_failed");
    return;
  }
  float probability = (output->data.int8[0] - OUTPUT_ZERO_POINT) * OUTPUT_SCALE;
  probability = constrain(probability, 0.0f, 1.0f);
  int anomaly = probability >= 0.5f;
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
                   ",\"pir\":" + String(pir) + "}";
  if (mqtt.connected()) mqtt.publish(MQTT_TOPIC, payload.c_str());
  Serial.println(payload);
  drawStatus("sample");
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(PIR_PIN, INPUT);
  dht.begin();
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
  Serial.printf("# source=hardware stage=stage2 node=%d\n", NODE_ID);
  Serial.printf("# oled=%s\n", oledOk ? "ok" : "NOT_FOUND");
  if (!setupModel()) return;
  connectWifi();
  connectMqtt();
}

void loop() {
  connectWifi();
  connectMqtt();
  mqtt.loop();
  if (millis() - lastSample >= SAMPLE_PERIOD_MS) {
    lastSample = millis();
    publishSample();
  }
}
