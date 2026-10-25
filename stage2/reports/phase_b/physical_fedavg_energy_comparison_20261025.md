# Physical FedAvg Energy-Policy Comparison

Date: 25 October 2026
Transport: CA-verified MQTT TLS on port 8883
Training data mode: SYNTHETIC on both runs
Both runs: two ESP32-S3 nodes, three rounds, five configured local steps, six global-update acknowledgements.

Broker exposure at report time: TLS port 8883 is the only network listener. The legacy plaintext Mosquitto process on port 1883 was stopped, and its config is restricted to loopback. The TLS listener still allows anonymous clients, so authentication/ACLs remain future work.

## Runs

| Run | Policy | Starting battery | Samples per round (Node 1 / Node 2) | Total local samples | START-to-STOP |
|---|---|---:|---|---:|---:|
| `df216f34a23b` | SIMULATED | 55% simulated | 3/3, 3/3, 3/1 | 16 | 54.648 s |
| `8f75883f0472` | FIXED | Not used | 5/5, 5/5, 5/5 | 30 | 29.004 s |

The simulated-policy run used 14 fewer local samples than the fixed-policy control (46.7% fewer relative to the fixed run) and took 25.644 seconds longer. Aggregator-observed round windows were 14.523/14.998/25.125 seconds for the simulated run and 8.947/10.020/10.035 seconds for the fixed run. These windows include local sampling/training and MQTT exchange; they are not network-only latency.

The node update counts demonstrate that the configured policy changed local participation. The reduced Node 2 count in round 3 is consistent with its simulated energy budget; confirm the precise NORMAL/ECO/CRITICAL transition using the node serial log before attributing that round to a particular state.

## Interpretation Limits

The battery percentage and energy policy are simulated. These runs do not measure current, voltage, joules, or battery-life savings. They show the protocol-level tradeoff between fewer local updates and longer completion time under the configured simulated policy. The synthetic pseudo-labels are not ground truth and these results do not establish anomaly accuracy.

The event logs and summaries are preserved at:

- `stage2/data/physical_fedavg_df216f34a23b_events.jsonl`
- `stage2/reports/phase_b/physical_fedavg_df216f34a23b_summary.json`
- `stage2/data/physical_fedavg_8f75883f0472_events.jsonl`
- `stage2/reports/phase_b/physical_fedavg_8f75883f0472_summary.json`
