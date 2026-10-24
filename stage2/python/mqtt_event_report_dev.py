"""Report the synthetic two-node MQTT event log.

    .venv312\\Scripts\\python.exe stage2/python/mqtt_event_report_dev.py

The source log is synthetic development data, not physical-node evidence.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / "stage2" / "data" / "mqtt_two_node_events_DEV_ONLY.jsonl"
REPORT_DIR = ROOT / "stage2" / "reports" / "phase_b"


def main():
    events = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    frame = pd.DataFrame(events)
    rounds = sorted(frame["round"].dropna().unique())
    round_rows = []
    for round_number in rounds:
        current = frame[frame["round"] == round_number]
        published = current[current["event"].str.endswith("_published")]
        aggregated = current[current["event"] == "aggregator_published"]
        latency_ms = None
        if len(published) and len(aggregated):
            latency_ms = float((aggregated["time"].min() - published["time"].min()) * 1000)
        round_rows.append({
            "round": int(round_number),
            "node_publishes": int(len(published)),
            "aggregator_updates": int(len(aggregated)),
            "aggregation_latency_ms": latency_ms,
        })

    summary = {
        "warning": "DEVELOPMENT-ONLY SYNTHETIC MQTT LOG. Not physical-node evidence.",
        "events": len(frame),
        "rounds": len(rounds),
        "nodes": sorted(int(value) for value in frame["node_id"].dropna().unique()),
        "message_bytes_mean": float(frame["bytes"].mean()),
        "message_bytes_max": int(frame["bytes"].max()),
        "rounds_detail": round_rows,
        "log": "stage2/data/mqtt_two_node_events_DEV_ONLY.jsonl",
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORT_DIR / "mqtt_event_report_summary_DEV_ONLY.json", "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)
    lines = [
        "# Stage 2 two-node MQTT development log",
        "WARNING: synthetic laptop simulation only; not physical-node evidence.",
        "",
        f"Events: {summary['events']}",
        f"Rounds: {summary['rounds']}",
        f"Nodes: {summary['nodes']}",
        f"Mean message size: {summary['message_bytes_mean']:.1f} bytes",
        f"Maximum message size: {summary['message_bytes_max']} bytes",
        "",
        "| Round | Node publishes | Aggregator updates | Aggregation latency (ms) |",
        "|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {row['round']} | {row['node_publishes']} | {row['aggregator_updates']} | "
        f"{row['aggregation_latency_ms']:.3f} |" for row in round_rows
    )
    (REPORT_DIR / "mqtt_event_report_DEV_ONLY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {REPORT_DIR / 'mqtt_event_report_DEV_ONLY.md'}")
    print(f"Summary: {REPORT_DIR / 'mqtt_event_report_summary_DEV_ONLY.json'}")
    print(f"Events: {len(frame)}; rounds: {len(rounds)}; nodes: {summary['nodes']}")


if __name__ == "__main__":
    main()
