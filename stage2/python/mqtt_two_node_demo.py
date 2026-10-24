"""Laptop-only two-node MQTT FedAvg demo.

Mosquitto must be running on localhost:1883:
    .venv312\\Scripts\\python.exe stage2/python/mqtt_two_node_demo.py

This uses the development-only synthetic dataset and is not thesis evidence.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import numpy as np
import pandas as pd
import paho.mqtt.client as mqtt
import tf_keras as keras
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ["temperature", "humidity", "pir"]
BROKER = "127.0.0.1"
PORT = 1883
ROUNDS = 3
NODE_COUNT = 2
TOPIC_UP = "tinyfl/dev/node/+/weights"
TOPIC_GLOBAL = "tinyfl/dev/global/weights"


class EventLogger:
    def __init__(self, path):
        self.file = open(path, "w", encoding="utf-8")
        self.lock = threading.Lock()

    def write(self, event, topic, payload):
        serialized = json.dumps(payload)
        record = {"time": time.time(), "event": event, "topic": topic,
                  "bytes": len(serialized.encode("utf-8"))}
        record.update({key: payload[key] for key in ("round", "node_id") if key in payload})
        with self.lock:
            self.file.write(json.dumps(record) + "\n")
            self.file.flush()

    def close(self):
        self.file.close()


def make_model():
    model = keras.Sequential([
        keras.layers.Input(shape=(3,)),
        keras.layers.Dense(16, activation="relu"),
        keras.layers.Dense(8, activation="relu"),
        keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3), loss="binary_crossentropy")
    return model


def pack_weights(weights):
    return [weight.tolist() for weight in weights]


def unpack_weights(payload):
    return [np.asarray(weight, dtype=np.float32) for weight in payload]


class Aggregator:
    def __init__(self, event_logger):
        self.event_logger = event_logger
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tinyfl-aggregator")
        self.received = {}
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.history = []
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(BROKER, PORT, 60)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe(TOPIC_UP)

    def on_message(self, client, userdata, message):
        payload = json.loads(message.payload.decode())
        self.event_logger.write("aggregator_received", message.topic, payload)
        round_number = int(payload["round"])
        node_id = payload["node_id"]
        with self.lock:
            self.received.setdefault(round_number, {})[node_id] = unpack_weights(payload["weights"])
            if len(self.received[round_number]) == NODE_COUNT:
                weights = list(self.received[round_number].values())
                global_weights = [sum(item[index] for item in weights) / NODE_COUNT
                                  for index in range(len(weights[0]))]
                outgoing = {
                    "round": round_number,
                    "weights": pack_weights(global_weights),
                }
                serialized = json.dumps(outgoing)
                self.client.publish(TOPIC_GLOBAL, serialized, qos=1)
                self.event_logger.write("aggregator_published", TOPIC_GLOBAL, outgoing)
                self.history.append({"round": round_number, "nodes": sorted(self.received[round_number])})
                self.ready.set()

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


class Node(threading.Thread):
    def __init__(self, node_id, x, y, initial_weights, event_logger):
        super().__init__(daemon=True)
        self.node_id = node_id
        self.x = x
        self.y = y
        self.event_logger = event_logger
        self.model = make_model()
        self.model.set_weights(initial_weights)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"tinyfl-node-{node_id}")
        self.global_events = {}
        self.lock = threading.Lock()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(BROKER, PORT, 60)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe(TOPIC_GLOBAL)

    def on_message(self, client, userdata, message):
        payload = json.loads(message.payload.decode())
        self.event_logger.write(f"node_{self.node_id}_received", message.topic, payload)
        round_number = int(payload["round"])
        self.model.set_weights(unpack_weights(payload["weights"]))
        with self.lock:
            event = self.global_events.get(round_number)
        if event:
            event.set()

    def run(self):
        for round_number in range(1, ROUNDS + 1):
            negative = max(1, int((self.y == 0).sum()))
            positive = max(1, int((self.y == 1).sum()))
            self.model.fit(self.x, self.y, epochs=1, batch_size=32,
                           class_weight={0: 1.0, 1: negative / positive}, verbose=0)
            event = threading.Event()
            with self.lock:
                self.global_events[round_number] = event
            outgoing = {
                "round": round_number,
                "node_id": self.node_id,
                "rows": len(self.y),
                "weights": pack_weights(self.model.get_weights()),
            }
            topic = f"tinyfl/dev/node/{self.node_id}/weights"
            self.client.publish(topic, json.dumps(outgoing), qos=1)
            self.event_logger.write(f"node_{self.node_id}_published", topic, outgoing)
            if not event.wait(30):
                raise RuntimeError(f"Node {self.node_id} timed out waiting for round {round_number}")

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


def main():
    data_dir = ROOT / "stage2" / "data"
    report_dir = ROOT / "stage2" / "reports" / "phase_b"
    report_dir.mkdir(parents=True, exist_ok=True)
    train = pd.read_csv(data_dir / "DEV_ONLY_train.csv")
    test = pd.read_csv(data_dir / "DEV_ONLY_test.csv")
    with open(ROOT / "stage2" / "models" / "DEV_ONLY_normalizer.json", encoding="utf-8") as file:
        normalizer = json.load(file)
    mean = np.asarray([normalizer["mean"][feature] for feature in FEATURES], dtype=np.float32)
    std = np.asarray([normalizer["std"][feature] for feature in FEATURES], dtype=np.float32)
    x = (train[FEATURES].to_numpy(dtype=np.float32) - mean) / std
    y = train["anomaly"].to_numpy(dtype=np.float32)
    x_test = (test[FEATURES].to_numpy(dtype=np.float32) - mean) / std
    y_test = test["anomaly"].to_numpy(dtype=np.float32)
    x1, x2, y1, y2 = train_test_split(x, y, test_size=0.5, random_state=42, stratify=y)

    seed_model = make_model()
    initial_weights = seed_model.get_weights()
    event_path = data_dir / "mqtt_two_node_events_DEV_ONLY.jsonl"
    event_logger = EventLogger(event_path)
    aggregator = Aggregator(event_logger)
    nodes = [Node(1, x1, y1, initial_weights, event_logger),
             Node(2, x2, y2, initial_weights, event_logger)]
    for node in nodes:
        node.start()
    for node in nodes:
        node.join()
    if len(aggregator.history) != ROUNDS:
        aggregator.close()
        for node in nodes:
            node.close()
        event_logger.close()
        raise RuntimeError(f"MQTT demo incomplete: received rounds {aggregator.history}")

    final_model = make_model()
    final_model.set_weights(nodes[0].model.get_weights())
    probabilities = final_model.predict(x_test, verbose=0).reshape(-1)
    f1 = float(f1_score(y_test, (probabilities >= 0.5).astype(int), zero_division=0))
    summary = {
        "warning": "DEVELOPMENT-ONLY SYNTHETIC DATA. Do not cite in thesis or paper.",
        "nodes": 2,
        "rounds": ROUNDS,
        "broker": f"{BROKER}:{PORT}",
        "mqtt_rounds_received": aggregator.history,
        "mqtt_messages": ROUNDS * NODE_COUNT + ROUNDS,
        "final_global_f1": f1,
        "topic_node_weights": "tinyfl/dev/node/<id>/weights",
        "topic_global_weights": TOPIC_GLOBAL,
    }
    with open(report_dir / "mqtt_two_node_summary_DEV_ONLY.json", "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)
    aggregator.close()
    for node in nodes:
        node.close()
    event_logger.close()
    print("DEVELOPMENT-ONLY MQTT two-node demo: PASS")
    print(f"Rounds received: {aggregator.history}")
    print(f"MQTT messages: {summary['mqtt_messages']}")
    print(f"Event log: {event_path}")
    print(f"Final global F1: {f1:.4f}")


if __name__ == "__main__":
    main()
