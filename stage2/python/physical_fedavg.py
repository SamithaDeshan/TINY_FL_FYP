"""Run two-node FedAvg over TLS MQTT; synthetic pseudo-label training is the default.

Usage after both ESP32 nodes are online with the physical-FedAvg firmware:
    .venv312\\Scripts\\python.exe stage2/python/physical_fedavg.py \\
        --host 172.20.10.7 --rounds 3 --local-steps 5

Sensor values remain local. Each node sends only weights and local sample count.
Synthetic labels are generated locally by a documented rule and are not ground
truth. The default transport verifies the Mosquitto certificate with a local CA.
"""
import argparse
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[2]
NODE_COUNT = 2
CONTROL_TOPIC = "tinyfl/fl/control"
UPDATE_TOPIC = "tinyfl/fl/node/update"
ACK_TOPIC = "tinyfl/fl/node/ack"
GLOBAL_TOPIC = "tinyfl/fl/global"


def weighted_average(updates):
    total = sum(item["samples"] for item in updates)
    if total <= 0:
        raise ValueError("Received updates with no local samples")
    return [
        sum(item["weights"][index] * item["samples"] for item in updates) / total
        for index in range(4)
    ]


class PhysicalFedAvg:
    def __init__(self, host, port, run_id, rounds, local_steps, timeout, log_path,
                 data_mode, energy_policy, battery_start_pct, tls_ca=None):
        self.host = host
        self.port = port
        self.run_id = run_id
        self.rounds = rounds
        self.local_steps = local_steps
        self.timeout = timeout
        self.data_mode = data_mode
        self.energy_policy = energy_policy
        self.battery_start_pct = battery_start_pct
        self.tls_ca = Path(tls_ca) if tls_ca else None
        self.log_file = open(log_path, "w", encoding="utf-8")
        self.lock = threading.Lock()
        self.connected = threading.Event()
        self.subscribed = threading.Event()
        self.round_updates = {}
        self.round_acks = {}
        self.round_done = {round_number: threading.Event() for round_number in range(1, rounds + 1)}
        self.round_results = []
        self.run_started = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"tinyfl-physical-aggregator-{run_id}")
        if self.tls_ca:
            self.client.tls_set(ca_certs=str(self.tls_ca))
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message

    def log(self, event, **details):
        now = datetime.now(timezone.utc)
        record = {
            "time_utc": now.timestamp(),
            "time_utc_iso": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "run_id": self.run_id,
            "event": event,
        }
        record.update(details)
        self.log_file.write(json.dumps(record, separators=(",", ":")) + "\n")
        self.log_file.flush()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            self.log("broker_connect_failed", reason=str(reason_code))
            return
        client.subscribe([(UPDATE_TOPIC, 1), (ACK_TOPIC, 1)])
        self.connected.set()

    def on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        if reason_code_list and all(not reason.is_failure for reason in reason_code_list):
            self.subscribed.set()
        else:
            self.log("broker_subscribe_failed", reasons=[str(reason) for reason in reason_code_list])

    def on_message(self, client, userdata, message):
        try:
            fields = message.payload.decode("utf-8").split("|")
            if message.topic == UPDATE_TOPIC:
                if len(fields) != 9 or fields[0] != "UPDATE":
                    self.log("invalid_update", topic=message.topic)
                    return
                _, run_id, node_text, round_text, samples_text, *weight_text = fields
                node_id, round_number, samples = int(node_text), int(round_text), int(samples_text)
                weights = [float(value) for value in weight_text]
                if run_id != self.run_id or node_id not in (1, 2) or round_number not in self.round_done or samples <= 0:
                    self.log("rejected_update", node=node_id, round=round_number, samples=samples)
                    return
                with self.lock:
                    updates = self.round_updates.setdefault(round_number, {})
                    updates[node_id] = {
                        "samples": samples,
                        "weights": weights,
                        "update_payload_bytes": len(message.payload),
                    }
                    self.log("node_update_received", node=node_id, round=round_number, samples=samples,
                             update_bytes=len(message.payload))
                    if len(updates) == NODE_COUNT and round_number not in {x["round"] for x in self.round_results}:
                        ordered = [updates[node] for node in sorted(updates)]
                        global_weights = weighted_average(ordered)
                        global_payload = "|".join([
                            "GLOBAL", self.run_id, str(round_number),
                            *(f"{value:.7f}" for value in global_weights),
                        ])
                        info = self.client.publish(GLOBAL_TOPIC, global_payload, qos=1, retain=False)
                        if info.rc != mqtt.MQTT_ERR_SUCCESS:
                            self.log("global_publish_failed", round=round_number, rc=info.rc)
                            return
                        self.round_results.append({
                            "round": round_number,
                            "node_samples": {str(node): updates[node]["samples"] for node in sorted(updates)},
                            "global_weights": global_weights,
                            "update_payload_bytes": [updates[node]["update_payload_bytes"]
                                                     for node in sorted(updates)],
                        })
                        self.log("global_weights_sent", round=round_number, weights=global_weights,
                                 recipients_expected=NODE_COUNT, update_bytes=len(global_payload.encode("utf-8")))
            elif message.topic == ACK_TOPIC:
                if len(fields) != 4 or fields[0] != "ACK":
                    self.log("invalid_ack", topic=message.topic)
                    return
                _, run_id, node_text, round_text = fields
                node_id, round_number = int(node_text), int(round_text)
                if run_id != self.run_id or node_id not in (1, 2) or round_number not in self.round_done:
                    self.log("rejected_ack", node=node_id, round=round_number)
                    return
                with self.lock:
                    self.round_acks.setdefault(round_number, set()).add(node_id)
                    self.log("global_update_acknowledged", node=node_id, round=round_number)
                    if self.round_acks[round_number] == {1, 2}:
                        self.round_done[round_number].set()
        except (UnicodeDecodeError, ValueError) as error:
            self.log("invalid_message", topic=message.topic, error=str(error))

    def run(self):
        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()
        if not self.connected.wait(15) or not self.subscribed.wait(15):
            raise RuntimeError("Aggregator could not connect/subscribe to the MQTT broker")
        self.log("aggregator_ready", rounds=self.rounds, local_steps=self.local_steps,
                                 data_mode=self.data_mode, energy_policy=self.energy_policy,
                                 battery_start_pct=self.battery_start_pct,
               transport="tls" if self.tls_ca else "plaintext")
        control = (f"START|{self.run_id}|{self.rounds}|{self.local_steps}|"
                                     f"{self.data_mode}|{self.energy_policy}|{self.battery_start_pct}")
        start_info = self.client.publish(CONTROL_TOPIC, control, qos=1, retain=False)
        start_info.wait_for_publish(timeout=5)
        if start_info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Failed to send FedAvg START command: rc={start_info.rc}")
        self.run_started = True
        self.log("start_command_sent", topic=CONTROL_TOPIC, command_bytes=len(control.encode("utf-8")))

        for round_number in range(1, self.rounds + 1):
            if not self.round_done[round_number].wait(self.timeout):
                missing_updates = sorted({1, 2} - set(self.round_updates.get(round_number, {})))
                missing_acks = sorted({1, 2} - self.round_acks.get(round_number, set()))
                self.log("round_timeout", round=round_number, missing_updates=missing_updates,
                         missing_global_acks=missing_acks)
                raise TimeoutError(f"Round {round_number} timeout; missing updates {missing_updates}, acks {missing_acks}")
            self.log("round_complete", round=round_number, nodes=[1, 2])
            print(f"FedAvg round {round_number}/{self.rounds} complete; both nodes applied global weights")

        summary = {
            "run_id": self.run_id,
            "nodes": 2,
            "rounds_completed": len(self.round_results),
            "local_steps_per_node_per_round": self.local_steps,
            "data_mode": self.data_mode,
            "energy_policy": self.energy_policy,
            "battery_start_pct": self.battery_start_pct if self.energy_policy == "SIMULATED" else None,
            "updates": self.round_results,
            "energy_note": "SIMULATED policy adapts sample interval and local steps using a simulated battery percentage; it is not a battery measurement or energy-consumption result.",
            "privacy_note": "The node keeps sensor readings local and MQTT is configured to verify the broker certificate using TLS. FL messages carry model updates, global weights, control, and acknowledgements only. No differential privacy or secure aggregation is implemented.",
            "label_note": "Pseudo-label rule: temperature >= 32 C OR humidity >= 81% OR PIR == 1; this is not ground truth.",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
        return summary

    def close(self):
        if self.run_started and self.client.is_connected():
            stop_message = f"STOP|{self.run_id}"
            self.client.publish(CONTROL_TOPIC, stop_message, qos=1, retain=False).wait_for_publish(timeout=5)
            self.log("stop_command_sent", topic=CONTROL_TOPIC)
            self.run_started = False
        self.client.loop_stop()
        self.client.disconnect()
        self.log_file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="172.20.10.7")
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--tls-ca", type=Path, default=ROOT / "stage2" / "mqtt" / "certs" / "local" / "ca.crt",
                        help="trusted CA certificate for broker TLS")
    parser.add_argument("--plain-mqtt", action="store_true",
                        help="disable TLS for local testing only; pair with --port 1883")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--local-steps", type=int, default=5)
    parser.add_argument("--data-mode", choices=("SYNTHETIC", "SENSOR_RULE"), default="SYNTHETIC",
                        help="train on deterministic synthetic anomaly examples or local sensor-rule pseudo-labels")
    parser.add_argument("--energy-policy", choices=("SIMULATED", "FIXED"), default="SIMULATED",
                        help="adapt local sampling and step budget using simulated battery state, or hold full rate")
    parser.add_argument("--battery-start-pct", type=int, default=100,
                        help="starting simulated battery percentage for energy-policy testing (0-100)")
    parser.add_argument("--timeout", type=int, default=180, help="seconds allowed for each round")
    parser.add_argument("--run-id", default=uuid.uuid4().hex[:12])
    args = parser.parse_args()
    if not 1 <= args.rounds <= 100 or not 1 <= args.local_steps <= 100:
        parser.error("rounds and local-steps must each be between 1 and 100")
    if not 0 <= args.battery_start_pct <= 100:
        parser.error("battery-start-pct must be between 0 and 100")
    if not args.plain_mqtt and not args.tls_ca.is_file():
        parser.error(f"TLS CA certificate not found: {args.tls_ca}; run stage2/mqtt/generate_mqtt_tls.py")
    if args.plain_mqtt and args.port != 1883:
        parser.error("--plain-mqtt is for the legacy plaintext listener; use --port 1883")

    output_dir = ROOT / "stage2" / "data"
    report_dir = ROOT / "stage2" / "reports" / "phase_b"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / f"physical_fedavg_{args.run_id}_events.jsonl"
    summary_path = report_dir / f"physical_fedavg_{args.run_id}_summary.json"
    aggregator = PhysicalFedAvg(args.host, args.port, args.run_id, args.rounds,
                                args.local_steps, args.timeout, events_path,
                                args.data_mode, args.energy_policy, args.battery_start_pct,
                                None if args.plain_mqtt else args.tls_ca)
    try:
        summary = aggregator.run()
    finally:
        aggregator.close()
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)
    print(f"Physical FedAvg demo complete: run={args.run_id} rounds={summary['rounds_completed']}")
    print(f"Events: {events_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
