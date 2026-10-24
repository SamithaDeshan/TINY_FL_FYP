// ============================================================================
// TinyFL - Stage 1, STEP S1.4: on-device benchmark of the exported Random Forest
// ESP32-S3 only; no sensors required.
//
// Wait for the command 'R' on serial, then:
//   1. runs the model on 500 embedded held-out test vectors (Python predictions stored alongside),
//   2. times every call (esp_timer, 1 us resolution) and a 20-pass batch (ns per inference),
//   3. measures stack used by the work in a dedicated task, and heap before/after,
//   4. prints metadata ('# ...') then CSV rows: i,expected,pred,abs_diff,us
// Variant 0 ('base') removes the model so flash/stack of the model can be found by subtraction.
// Upload and run each of the three variants once (edit VARIANT_CHOICE below, then Upload).
// ============================================================================

// ===== CHOOSE ONE: 0 = base (no model), 1 = model (double literals), 2 = model_f32 (float literals) =====
#ifndef VARIANT_CHOICE
#define VARIANT_CHOICE 2
#endif
#define RUN_MODEL (VARIANT_CHOICE > 0)
#define MODEL_F32 (VARIANT_CHOICE == 2)
// ========================================================================================================
#include <Arduino.h>
#include "esp_timer.h"
#include "test_vectors.h"

#if RUN_MODEL
#if MODEL_F32
#include "smart_light_model_f32.h"
typedef Eloquent::ML::Port::RandomForestRegressorF32 Model;
#define VARIANT "model_f32"
#else
#include "smart_light_model.h"
typedef Eloquent::ML::Port::RandomForestRegressor Model;
#define VARIANT "model"
#endif
#else
#define VARIANT "base"
#endif

static volatile float g_sink;
static float g_pred[TV_N];
static uint32_t g_us[TV_N];

static const uint32_t STACK_BYTES = 4096;
struct TaskRes { volatile bool done; uint32_t used; };

static void __attribute__((noinline)) work() {
#if RUN_MODEL
  Model m;
  for (int i = 0; i < TV_N; i++) {
    float x[4] = {TV_X[i][0], TV_X[i][1], TV_X[i][2], TV_X[i][3]};
    g_sink = m.predict(x);
  }
#else
  for (int i = 0; i < TV_N; i++) g_sink = TV_X[i][1] + TV_Y[i];
#endif
}

static void stackTask(void *p) {
  TaskRes *r = (TaskRes *)p;
  work();
  r->used = STACK_BYTES - uxTaskGetStackHighWaterMark(NULL);  // ESP-IDF reports bytes
  r->done = true;
  vTaskDelete(NULL);
}

static void runBench() {
  Serial.println("# source=hardware");
  Serial.printf("# variant=%s run_model=%d\n", VARIANT, RUN_MODEL);
  Serial.printf("# chip=%s rev=%d cpu_mhz=%d sdk=%s arduino_core=%d.%d.%d\n", ESP.getChipModel(), (int)ESP.getChipRevision(),
                (int)ESP.getCpuFreqMHz(), ESP.getSdkVersion(), ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR,
                ESP_ARDUINO_VERSION_PATCH);
#ifdef __OPTIMIZE_SIZE__
  Serial.println("# optimisation=Os");
#else
  Serial.println("# optimisation=other");
#endif
  Serial.printf("# sketch_bytes=%u free_sketch_bytes=%u flash_chip_bytes=%u\n", (unsigned)ESP.getSketchSize(),
                (unsigned)ESP.getFreeSketchSpace(), (unsigned)ESP.getFlashChipSize());
  uint32_t heap0 = ESP.getFreeHeap(), minheap0 = ESP.getMinFreeHeap();

  TaskRes r = {false, 0};
  xTaskCreate(stackTask, "stk", STACK_BYTES, &r, 5, NULL);
  while (!r.done) delay(10);
  Serial.printf("# stack_used_bytes=%u stack_alloc_bytes=%u\n", (unsigned)r.used, (unsigned)STACK_BYTES);

#if RUN_MODEL
  Model m;
  float x[4];
  for (int i = 0; i < TV_N; i++) {  // warm-up (instruction cache)
    for (int k = 0; k < 4; k++) x[k] = TV_X[i][k];
    g_sink = m.predict(x);
  }
  for (int i = 0; i < TV_N; i++) {
    for (int k = 0; k < 4; k++) x[k] = TV_X[i][k];
    int64_t t0 = esp_timer_get_time();
    float y = m.predict(x);
    int64_t t1 = esp_timer_get_time();
    g_sink = y;
    g_pred[i] = y;
    g_us[i] = (uint32_t)(t1 - t0);
  }
  const int PASSES = 20;
  int64_t b0 = esp_timer_get_time();
  for (int p = 0; p < PASSES; p++)
    for (int i = 0; i < TV_N; i++) {
      for (int k = 0; k < 4; k++) x[k] = TV_X[i][k];
      g_sink = m.predict(x);
    }
  int64_t b1 = esp_timer_get_time();
  Serial.printf("# batch_ns_per_inference=%u passes=%d\n", (unsigned)((b1 - b0) * 1000 / (PASSES * TV_N)), PASSES);
#endif
  uint32_t heap1 = ESP.getFreeHeap();
  Serial.printf("# heap_free_before=%u heap_free_after=%u min_heap_free=%u\n", (unsigned)heap0, (unsigned)heap1,
                (unsigned)minheap0);
#if RUN_MODEL
  Serial.println("i,expected,pred,abs_diff,us");
  for (int i = 0; i < TV_N; i++) {
    Serial.printf("%d,%.6f,%.6f,%.6f,%u\n", i, TV_Y[i], g_pred[i], fabsf(g_pred[i] - TV_Y[i]), (unsigned)g_us[i]);
  }
#endif
  Serial.println("# done");
}

void setup() {
  Serial.begin(115200);
  delay(1500);
}

void loop() {
  static uint32_t last = 0;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == 'R' || c == 'r') runBench();
  }
  if (millis() - last > 2000) {
    last = millis();
    Serial.printf("# ready variant=%s - send R to run\n", VARIANT);
  }
}
