# TinyFL MQTT TLS and Energy-Aware FedAvg

## Generate Local TLS Material

From the project root, install the certificate helper dependency and generate a local CA, broker certificate, and ESP32 CA header:

```powershell
.venv312\Scripts\python.exe -m pip install -r stage2\mqtt\requirements-tls.txt
.venv312\Scripts\python.exe stage2\mqtt\generate_mqtt_tls.py --host 172.20.10.7
```

The generated CA and broker private keys are stored under `stage2/mqtt/certs/local/`; that directory is ignored by Git. `stage2/arduino/tinyfl_node/mqtt_ca.h` contains the public CA certificate used by the firmware. Do not share the private keys. If certificates are regenerated with `--force`, recompile and reflash both nodes because their trusted CA changes.

## Start the TLS Listener

The generated config adds a TLS listener at `0.0.0.0:8883`. The legacy plaintext config is now bound to `127.0.0.1:1883`, so it is available only to programs on the laptop:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c "stage2\mqtt\certs\local\mosquitto_tls.conf" -v
```

Start the TLS listener once. The former network-accessible plaintext broker on port 1883 has been stopped; if restarted with `stage2/mqtt/mosquitto.conf`, it binds to loopback only. ESP32 nodes must connect to port 8883.

TLS encrypts traffic in transit and verifies the broker certificate. The TLS listener still permits anonymous LAN clients, so it does not authenticate nodes or authorize topic access. Differential privacy and secure aggregation are also not implemented.

## Flash and Run

The generated `secrets.h` should use broker IP `172.20.10.7` and port `8883`. Compile/upload the sketch to each ESP32-S3 with distinct `NODE_ID` values (`1` and `2`). The sketch trusts the generated CA. Sensor readings remain on the ESP32 and OLED; MQTT carries FedAvg control, model weights/sample counts, global weights, and acknowledgements only.

With both nodes connected to the TLS listener, run:

```powershell
.venv312\Scripts\python.exe stage2\python\physical_fedavg.py --host 172.20.10.7 --port 8883 --rounds 3 --local-steps 5 --data-mode SYNTHETIC --energy-policy SIMULATED
```

`SYNTHETIC` generates anomaly examples locally using a deterministic rule; it is not ground truth. `SIMULATED` energy policy adapts sample interval and local steps from a simulated battery percentage (5/3/1 local steps at NORMAL/ECO/CRITICAL). Choose `--battery-start-pct 55` to begin in ECO or `--battery-start-pct 20` to begin in CRITICAL. This is a policy demonstration, not measured energy use. Use `--energy-policy FIXED` for a fixed local-step budget.

To run the fixed-policy control with the same number of rounds and configured local steps:

```powershell
.venv312\Scripts\python.exe stage2\python\physical_fedavg.py --host 172.20.10.7 --port 8883 --rounds 3 --local-steps 5 --data-mode SYNTHETIC --energy-policy FIXED
```

The physical simulated-energy run `df216f34a23b` and fixed-policy control `8f75883f0472` completed on 25 October 2026. The comparison is recorded at `stage2/reports/phase_b/physical_fedavg_energy_comparison_20261025.md`; both run-specific event logs and summaries remain under `stage2/data/` and `stage2/reports/phase_b/`. Verify both node IDs have updates and ACKs for every round. Battery state is simulated, so sample/runtime differences are not measured energy savings. Node serial logs are needed to confirm the exact energy-state transition behind a reduced sample count.