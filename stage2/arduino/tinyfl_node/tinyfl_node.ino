// TinyFL Stage 2 physical node: local sensor display/inference + model-only MQTT FedAvg.
// Copy secrets.h.example to secrets.h and fill in local Wi-Fi credentials.
// Upload the same sketch to both boards, changing NODE_ID to 1 or 2.
// This development firmware uses the synthetic int8 model; do not cite its outputs.
#ifndef NODE_ID
#define NODE_ID 1
#endif

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include "Chirale_TensorFlowLite.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "../../models/DEV_ONLY_model_data.h"
#include "mqtt_ca.h"
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
#define FL_CONTROL_TOPIC "tinyfl/fl/control"
#define FL_GLOBAL_TOPIC "tinyfl/fl/global"
#define FL_UPDATE_TOPIC "tinyfl/fl/node/update"
#define FL_ACK_TOPIC "tinyfl/fl/node/ack"
#define FL_MAX_LOCAL_STEPS 100
#define FL_LEARNING_RATE 0.08f
#define FL_L2 0.001f
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
WiFiClientSecure wifiClient;
PubSubClient mqtt(wifiClient);
uint8_t tensorArena[TENSOR_ARENA_BYTES];
tflite::MicroMutableOpResolver<2> resolver;
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
bool federatedMode = false;
bool federatedTraining = false;
bool federatedWaitingGlobal = false;
bool federatedSyntheticData = true;
bool federatedEnergyAware = true;
char federatedRunId[32] = {0};
uint16_t federatedRounds = 0;
uint16_t federatedCurrentRound = 0;
uint16_t federatedLocalSteps = 0;
uint16_t federatedLocalStep = 0;
uint16_t federatedRoundLocalTarget = 0;
float federatedWeights[3] = {0.0f, 0.0f, 0.0f};
float federatedBias = 0.0f;

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

static uint16_t localStepBudgetForEnergyMode() {
  if (!federatedEnergyAware) return federatedLocalSteps;
  if (simulatedBatteryPct <= 20) return min((uint16_t)1, federatedLocalSteps);
  if (simulatedBatteryPct <= 60) return min((uint16_t)3, federatedLocalSteps);
  return federatedLocalSteps;
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
  if (federatedMode && federatedSyntheticData) display.printf("SIM p:%.2f LED:%u", lastProbability, indicatorPwm);
  else display.printf("Anom:%d P:%.2f LED:%u", lastAnomaly, lastProbability, indicatorPwm);
  display.setCursor(0, 48);
  display.printf("BAT:%u%% %s", simulatedBatteryPct, energyMode());
  display.setCursor(0, 56);
  if (federatedMode) {
    const char* flState = federatedWaitingGlobal ? "WAIT" : (federatedTraining ? "TRAIN" : "DONE");
    display.printf("FL%s %s R%u %u/%u", federatedSyntheticData ? "-SIM" : "", flState, federatedCurrentRound,
             federatedLocalStep, federatedRoundLocalTarget);
  } else display.printf("LOCAL %s", mqtt.connected() ? state : "MQTT--");
  display.display();
}

static void onMqttMessage(char* topic, uint8_t* payload, unsigned int length) {
  char message[128];
  unsigned int copyLength = min(length, (unsigned int)(sizeof(message) - 1));
  memcpy(message, payload, copyLength);
  message[copyLength] = '\0';
  if (strcmp(topic, FL_CONTROL_TOPIC) == 0) {
    char* context = nullptr;
    char* kind = strtok_r(message, "|", &context);
    if (kind && strcmp(kind, "START") == 0) {
      char* runId = strtok_r(nullptr, "|", &context);
      char* rounds = strtok_r(nullptr, "|", &context);
      char* steps = strtok_r(nullptr, "|", &context);
      char* mode = strtok_r(nullptr, "|", &context);
      char* energyPolicy = strtok_r(nullptr, "|", &context);
      char* batteryStartText = strtok_r(nullptr, "|", &context);
      if (!runId || !rounds || !steps) return;
      if (mode && strcmp(mode, "SYNTHETIC") != 0 && strcmp(mode, "SENSOR_RULE") != 0) return;
      if (energyPolicy && strcmp(energyPolicy, "SIMULATED") != 0 && strcmp(energyPolicy, "FIXED") != 0) return;
      int batteryStart = batteryStartText ? atoi(batteryStartText) : 100;
      if (batteryStart < 0 || batteryStart > 100) return;
      strlcpy(federatedRunId, runId, sizeof(federatedRunId));
      federatedRounds = constrain(atoi(rounds), 1, 100);
      federatedLocalSteps = constrain(atoi(steps), 1, FL_MAX_LOCAL_STEPS);
      federatedSyntheticData = !mode || strcmp(mode, "SYNTHETIC") == 0;
      federatedEnergyAware = !energyPolicy || strcmp(energyPolicy, "SIMULATED") == 0;
      federatedCurrentRound = 1;
      federatedLocalStep = 0;
      federatedWeights[0] = federatedWeights[1] = federatedWeights[2] = 0.0f;
      federatedBias = 0.0f;
      federatedMode = true;
      federatedTraining = true;
      federatedWaitingGlobal = false;
      simulatedBatteryPct = federatedEnergyAware ? (uint8_t)batteryStart : 100;
      batterySimulationEnabled = federatedEnergyAware;
      lastBatteryStep = millis();
      federatedRoundLocalTarget = localStepBudgetForEnergyMode();
      Serial.printf("# fedavg_start local_ms=%lu run=%s rounds=%u local_steps=%u data_mode=%s energy_policy=%s battery_pct=%u battery_source=simulated label_source=%s\n",
            (unsigned long)millis(), federatedRunId, federatedRounds, federatedLocalSteps,
            federatedSyntheticData ? "SYNTHETIC" : "SENSOR_RULE",
        federatedEnergyAware ? "SIMULATED" : "FIXED",
        simulatedBatteryPct,
            federatedSyntheticData ? "synthetic_rule" : "local_sensor_rule");
    } else if (kind && strcmp(kind, "STOP") == 0) {
      char* runId = strtok_r(nullptr, "|", &context);
      if (runId && federatedMode && strcmp(runId, federatedRunId) == 0) {
        federatedMode = false;
        federatedTraining = false;
        federatedWaitingGlobal = false;
        federatedRunId[0] = '\0';
        federatedSyntheticData = true;
        federatedEnergyAware = true;
        batterySimulationEnabled = false;
        Serial.printf("# fedavg_stopped local_ms=%lu returning_to_local_monitor\n", (unsigned long)millis());
      }
    }
  } else if (strcmp(topic, FL_GLOBAL_TOPIC) == 0 && federatedMode && federatedWaitingGlobal) {
    char* context = nullptr;
    char* kind = strtok_r(message, "|", &context);
    char* runId = strtok_r(nullptr, "|", &context);
    char* roundText = strtok_r(nullptr, "|", &context);
    char* w0 = strtok_r(nullptr, "|", &context);
    char* w1 = strtok_r(nullptr, "|", &context);
    char* w2 = strtok_r(nullptr, "|", &context);
    char* bias = strtok_r(nullptr, "|", &context);
    if (!kind || !runId || !roundText || !w0 || !w1 || !w2 || !bias || strcmp(kind, "GLOBAL") != 0) return;
    uint16_t roundNumber = (uint16_t)atoi(roundText);
    if (strcmp(runId, federatedRunId) != 0 || roundNumber != federatedCurrentRound) return;
    federatedWeights[0] = atof(w0);
    federatedWeights[1] = atof(w1);
    federatedWeights[2] = atof(w2);
    federatedBias = atof(bias);
    mqtt.publish(FL_ACK_TOPIC, (String("ACK|") + federatedRunId + "|" + String(NODE_ID) + "|" + String(roundNumber)).c_str());
    Serial.printf("# fedavg_global_applied local_ms=%lu round=%u w=[%.4f,%.4f,%.4f] b=%.4f\n",
            (unsigned long)millis(), roundNumber, federatedWeights[0],
            federatedWeights[1], federatedWeights[2], federatedBias);
    federatedWaitingGlobal = false;
    if (federatedCurrentRound >= federatedRounds) {
      federatedTraining = false;
      batterySimulationEnabled = false;
      Serial.printf("# fedavg_training_complete local_ms=%lu inference_only=true battery_source=simulated\n",
                    (unsigned long)millis());
    } else {
      federatedCurrentRound++;
      federatedLocalStep = 0;
      federatedRoundLocalTarget = localStepBudgetForEnergyMode();
      Serial.printf("# fedavg_energy_budget local_ms=%lu node=%d round=%u local_steps=%u mode=%s battery_source=simulated\n",
                    (unsigned long)millis(), NODE_ID, federatedCurrentRound,
                    federatedRoundLocalTarget, energyMode());
    }
  }
  drawStatus(federatedMode ? "fedavg" : "local");
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
    } else if (command == 'X' || command == 'x') {
      federatedMode = false;
      federatedTraining = false;
      federatedWaitingGlobal = false;
      federatedSyntheticData = true;
      federatedEnergyAware = true;
      batterySimulationEnabled = false;
      Serial.printf("# fedavg_mode_stopped local_ms=%lu returning_to_local_monitor\n", (unsigned long)millis());
      drawStatus("local");
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
  Serial.printf("# battery_sim local_ms=%lu percent=%u drop=%d mode=%s source=simulated\n",
                (unsigned long)millis(), simulatedBatteryPct, drop, currentMode);
  if (strcmp(previousMode, currentMode) != 0) {
    Serial.printf("# energy_mode_changed local_ms=%lu mode=%s sample_period_ms=%lu source=simulated\n",
                  (unsigned long)millis(), currentMode, (unsigned long)samplePeriodForEnergyMode());
    if (federatedMode && federatedTraining && !federatedWaitingGlobal) {
      federatedRoundLocalTarget = localStepBudgetForEnergyMode();
      Serial.printf("# fedavg_energy_budget local_ms=%lu node=%d round=%u local_steps=%u mode=%s source=simulated\n",
                    (unsigned long)millis(), NODE_ID, federatedCurrentRound,
                    federatedRoundLocalTarget, currentMode);
    }
  }
  if (simulatedBatteryPct == 0) {
    batterySimulationEnabled = false;
    Serial.printf("# battery_sim_empty local_ms=%lu source=simulated\n", (unsigned long)millis());
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
    mqtt.subscribe(FL_CONTROL_TOPIC, 1);
    mqtt.subscribe(FL_GLOBAL_TOPIC, 1);
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
  if (resolver.AddFullyConnected() != kTfLiteOk || resolver.AddLogistic() != kTfLiteOk) {
    Serial.println("# model_resolver_setup_failed");
    return false;
  }
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
  sampleNumber++;
  Serial.printf("# local_inference local_ms=%lu node=%d sample=%lu confidence=%.4f anomaly=%d inference_us=%lu\n",
                (unsigned long)millis(), NODE_ID, (unsigned long)sampleNumber,
                probability, anomaly, (unsigned long)inferenceUs);
  drawStatus("local");
}

static void syntheticTrainingExample(float* features, int* label) {
  uint16_t pattern = (uint16_t)(federatedLocalStep +
                                (federatedCurrentRound - 1) * 2 +
                                (NODE_ID - 1) * 3) % 6;
  float temperature;
  float humidity;
  int pir;
  switch (pattern) {
    case 0: temperature = 27.0f; humidity = 70.0f; pir = 0; break;
    case 1: temperature = 33.0f; humidity = 70.0f; pir = 0; break;
    case 2: temperature = 30.0f; humidity = 75.0f; pir = 0; break;
    case 3: temperature = 27.0f; humidity = 85.0f; pir = 0; break;
    case 4: temperature = 25.0f; humidity = 63.0f; pir = 0; break;
    default: temperature = 27.0f; humidity = 70.0f; pir = 1; break;
  }
  features[0] = (temperature - NORMAL_TEMP_MEAN) / NORMAL_TEMP_STD;
  features[1] = (humidity - NORMAL_HUM_MEAN) / NORMAL_HUM_STD;
  features[2] = (pir - NORMAL_PIR_MEAN) / NORMAL_PIR_STD;
  *label = (temperature >= 32.0f || humidity >= 81.0f || pir == 1) ? 1 : 0;
}

static float fedSigmoid(float value) {
  value = constrain(value, -12.0f, 12.0f);
  return 1.0f / (1.0f + expf(-value));
}

static float fedPredict(const float* features) {
  float value = federatedBias;
  for (int i = 0; i < 3; i++) value += federatedWeights[i] * features[i];
  return fedSigmoid(value);
}

static bool publishFedUpdate() {
  String update = String("UPDATE|") + federatedRunId + "|" + String(NODE_ID) + "|" +
                  String(federatedCurrentRound) + "|" + String(federatedLocalStep) + "|" +
                  String(federatedWeights[0], 6) + "|" + String(federatedWeights[1], 6) + "|" +
                  String(federatedWeights[2], 6) + "|" + String(federatedBias, 6);
  bool sent = mqtt.connected() && mqtt.publish(FL_UPDATE_TOPIC, update.c_str());
  if (sent) {
    federatedWaitingGlobal = true;
    Serial.printf("# fedavg_update_sent local_ms=%lu node=%d round=%u local_samples=%u bytes=%u\n",
            (unsigned long)millis(), NODE_ID, federatedCurrentRound,
            federatedLocalStep, (unsigned)update.length());
  } else {
    Serial.printf("# fedavg_update_failed mqtt=%d bytes=%u\n", mqtt.connected(), (unsigned)update.length());
  }
  return sent;
}

static void federatedSample() {
  if (federatedWaitingGlobal) return;
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();
  bool sensorValuesValid = !isnan(humidity) && !isnan(temperature);
  if (!sensorValuesValid && !federatedSyntheticData) {
    Serial.println("# fedavg_dht_read_failed");
    return;
  }
  int pir = digitalRead(PIR_PIN);
  int ldrRaw = analogRead(LDR_PIN);
  int ldr10 = ldrRaw >> 2;
  lastTemperature = sensorValuesValid ? temperature : NAN;
  lastHumidity = sensorValuesValid ? humidity : NAN;
  lastPir = pir;
  lastLdrRaw = ldrRaw;
  lastLdr10 = ldr10;

  float features[3];
  int label;
  if (federatedSyntheticData) {
    syntheticTrainingExample(features, &label);
  } else {
    features[0] = (temperature - NORMAL_TEMP_MEAN) / NORMAL_TEMP_STD;
    features[1] = (humidity - NORMAL_HUM_MEAN) / NORMAL_HUM_STD;
    features[2] = (pir - NORMAL_PIR_MEAN) / NORMAL_PIR_STD;
    label = (temperature >= 32.0f || humidity >= 81.0f || pir == 1) ? 1 : 0;
  }
  float probability = fedPredict(features);
  lastProbability = probability;
  lastAnomaly = probability >= 0.5f;
  uint8_t requestedPwm = (uint8_t)constrain((int)lroundf(probability * 255.0f), 0, 255);
  pwmWriteIndicator(min(requestedPwm, maxIndicatorPwmForEnergyMode()));
  sampleNumber++;

  if (federatedTraining) {
    float error = probability - label;
    for (int i = 0; i < 3; i++) {
      federatedWeights[i] -= FL_LEARNING_RATE * (error * features[i] + FL_L2 * federatedWeights[i]);
    }
    federatedBias -= FL_LEARNING_RATE * error;
    federatedLocalStep++;
    Serial.printf("# fedavg_local local_ms=%lu node=%d round=%u step=%u label=%d label_source=%s confidence=%.3f\n",
            (unsigned long)millis(), NODE_ID, federatedCurrentRound,
            federatedLocalStep, label,
            federatedSyntheticData ? "synthetic_rule" : "local_sensor_rule", probability);
    if (federatedLocalStep >= federatedRoundLocalTarget) publishFedUpdate();
  } else {
    Serial.printf("# fedavg_inference node=%d round=%u confidence=%.3f anomaly=%d\n",
                  NODE_ID, federatedCurrentRound, probability, lastAnomaly);
  }
  drawStatus(federatedWaitingGlobal ? "FL wait" : (federatedTraining ? "FL train" : "FL local"));
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
  wifiClient.setCACert(MQTT_CA_CERT);
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  if (!mqtt.setBufferSize(512)) {
    Serial.println("# mqtt_buffer_resize_failed");
  } else {
    Serial.println("# mqtt_buffer_bytes=512");
  }
  Serial.printf("# source=hardware stage=stage2 node=%d\n", NODE_ID);
  Serial.printf("# oled=%s\n", oledOk ? "ok" : "NOT_FOUND");
  Serial.println("# serial_commands B=start random battery demo R=reset demo X=stop FedAvg");
  Serial.println("# data_policy=sensor readings stay local/on OLED; MQTT sends model updates, globals, and ACKs only");
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
    if (federatedMode) federatedSample();
    else publishSample();
  }
}
