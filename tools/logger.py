"""Serial logger for the TinyFL Stage 1 firmware.

Usage (Windows example):
    python tools/logger.py --list
    python tools/logger.py --port COM5 --out data/s1_5_session1.csv

While logging, type a command and press Enter to send it to the board, e.g.
    L dark       -> label following rows 'dark'
    L motion
    R            -> run a PWM ramp
Press Ctrl+C (or use --duration / --until) to stop. Lines starting with '#' are metadata and
are kept in the CSV as comment lines (the report generator reads them).
"""
import argparse
import sys
import threading
import time

import serial
from serial.tools import list_ports


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", default="data/session.csv")
    ap.add_argument("--duration", type=float, default=0, help="seconds, 0 = until Ctrl+C")
    ap.add_argument("--list", action="store_true", help="list serial ports and exit")
    ap.add_argument("--send", default="", help="command to send ~3 s after opening the port (e.g. R)")
    ap.add_argument("--until", default="", help="stop automatically when a line starts with this text (e.g. '# done')")
    a = ap.parse_args()

    if a.list:
        for p in list_ports.comports():
            print(p.device, "-", p.description)
        return
    if not a.port:
        sys.exit("Give --port (use --list to see ports)")

    ser = serial.Serial(a.port, a.baud, timeout=0.2)
    stop = threading.Event()

    def sender():
        for line in sys.stdin:
            ser.write((line.strip() + "\n").encode())
            if stop.is_set():
                break

    threading.Thread(target=sender, daemon=True).start()
    t0 = time.time()
    rows = 0
    sent = not a.send
    with open(a.out, "w", newline="") as f:
        print(f"Logging {a.port} -> {a.out}  (Ctrl+C to stop)")
        try:
            while not stop.is_set():
                raw = ser.readline()
                if raw:
                    txt = raw.decode(errors="replace").rstrip("\r\n")
                    f.write(txt + "\n")
                    f.flush()
                    if not txt.startswith("#") and not txt.startswith("ms,"):
                        rows += 1
                        if rows % 50 == 0:
                            print(f"\r{rows} rows  {txt[:70]}", end="")
                    elif txt.startswith("#"):
                        print("\n" + txt)
                if not sent and time.time() - t0 >= 3:
                    ser.write((a.send + "\n").encode()); sent = True
                if a.until and raw and raw.decode(errors="replace").startswith(a.until):
                    break
                if a.duration and time.time() - t0 >= a.duration:
                    break
        except KeyboardInterrupt:
            pass
    stop.set()
    ser.close()
    print(f"\nDone. {rows} data rows saved to {a.out}")


if __name__ == "__main__":
    main()
