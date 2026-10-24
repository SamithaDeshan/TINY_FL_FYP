"""Collect physical ESP32 Stage 2 MQTT readings into a labeled CSV.

Example normal baseline collection (8 hours):
    .venv312\\Scripts\\python.exe stage2/python/collect_node_data.py \\
        --scenario overnight_unlabeled_baseline --ground-truth unknown --duration 28800 \\
        --out stage2/data/physical_overnight_unlabeled.csv

The ground-truth label describes the controlled session, not the model output.
"""
import argparse
import csv
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[2]
FIELDS = [
    "received_at_utc", "scenario", "ground_truth_anomaly", "node", "sample",
    "temperature", "humidity", "pir", "ldr_raw", "ldr10", "anomaly", "confidence", "inference_us",
    "battery_pct", "battery_source", "energy_mode", "indicator_pwm", "sample_period_ms",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="172.20.10.7")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--topic", default="tinyfl/node/result")
    parser.add_argument("--scenario", required=True, help="controlled session label, e.g. normal_baseline")
    parser.add_argument("--ground-truth", choices=("0", "1", "unknown"), default="unknown")
    parser.add_argument("--duration", type=int, default=0, help="seconds; 0 collects until Ctrl+C")
    parser.add_argument("--out", default="stage2/data/physical_session.csv")
    args = parser.parse_args()

    output_path = Path(args.out)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    connected = threading.Event()
    subscribed = threading.Event()
    count_lock = threading.Lock()
    count = 0

    with open(output_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        file.flush()

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code == 0:
                client.subscribe(args.topic, qos=1)
                connected.set()
                print(f"Connected to {args.host}:{args.port}; subscribing to {args.topic}")
            else:
                print(f"MQTT connection rejected: {reason_code}", file=sys.stderr)
                stop.set()

        def on_subscribe(client, userdata, mid, reason_code_list, properties):
            if reason_code_list and not reason_code_list[0].is_failure:
                subscribed.set()
                print(f"Subscription ready: {args.topic}")
            else:
                print(f"Subscription rejected: {args.topic}", file=sys.stderr)
                stop.set()

        def on_message(client, userdata, message):
            nonlocal count
            try:
                payload = json.loads(message.payload.decode("utf-8"))
                row = {key: payload.get(key, "") for key in FIELDS}
                row["received_at_utc"] = datetime.now(timezone.utc).isoformat()
                row["scenario"] = args.scenario
                row["ground_truth_anomaly"] = "" if args.ground_truth == "unknown" else args.ground_truth
                writer.writerow(row)
                file.flush()
                with count_lock:
                    count += 1
                    current = count
                if current == 1 or current % 100 == 0:
                    print(f"{current} messages; latest node={row['node']} sample={row['sample']}")
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                print(f"Skipped invalid MQTT payload: {error}", file=sys.stderr)

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tinyfl-data-collector")
        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.connect(args.host, args.port, 60)
        client.loop_start()
        try:
            if not connected.wait(15):
                raise RuntimeError(f"Could not connect to MQTT broker {args.host}:{args.port}")
            if not subscribed.wait(15):
                raise RuntimeError(f"Broker did not acknowledge subscription to {args.topic}")
            if args.duration > 0:
                stop.wait(args.duration)
            else:
                print("Collecting until Ctrl+C")
                while not stop.wait(1):
                    pass
        except KeyboardInterrupt:
            print("Stopping collection...")
        finally:
            client.loop_stop()
            client.disconnect()
            file.flush()

    print(f"Saved {count} MQTT rows to {output_path}")


if __name__ == "__main__":
    main()
