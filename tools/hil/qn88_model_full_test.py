#!/usr/bin/env python3
"""Volatile QN88 HIL check for the model-level ECG path.

The script only opens the documented UART. FPGA programming is intentionally
left to the Gowin SRAM flow so this test cannot write configuration Flash.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import serial


WEIGHT_FILES = (
    "features_0_weight.hex",
    "features_0_bias.hex",
    "features_3_weight.hex",
    "features_3_bias.hex",
    "features_6_weight.hex",
    "features_6_bias.hex",
    "head_weight.hex",
    "head_bias.hex",
)


def read_hex(path: Path) -> bytes:
    values = []
    for line in path.read_text(encoding="ascii").splitlines():
        line = line.strip()
        if line:
            values.append(int(line, 16) & 0xFF)
    return bytes(values)


def signed_byte(value: int) -> int:
    return value - 256 if value >= 128 else value


def parse_frame(frame: bytes) -> dict:
    text = frame.decode("ascii", errors="replace").strip()
    tokens = text.split()
    result = {"raw": text, "valid_prefix": bool(tokens and tokens[0] == "ECG")}
    for token in tokens[1:]:
        if len(token) == 2 and all(ch in "0123456789ABCDEF" for ch in token.upper()):
            result.setdefault("logits", []).append(signed_byte(int(token, 16)))
        elif len(token) == 2 and token[0] in "PSD" and token[1] in "01":
            result[token[0]] = token[1] == "1"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--port", default="COM10")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    model_mem = args.run / "hex"
    input_bytes = read_hex(model_mem / "input.hex")
    weight_bytes = b"".join(read_hex(model_mem / name) for name in WEIGHT_FILES)
    expected = [signed_byte(value) for value in read_hex(model_mem / "expected_logits.hex")]
    if len(input_bytes) != 12000 or len(weight_bytes) != 10293:
        raise SystemExit(f"payload size mismatch: input={len(input_bytes)} weights={len(weight_bytes)}")

    payload = b"ECG0" + input_bytes + weight_bytes
    started = datetime.now(timezone.utc).isoformat()
    with serial.Serial(args.port, args.baud, timeout=0.25) as ser:
        time.sleep(0.2)
        ser.reset_input_buffer()
        ser.write(payload)
        ser.flush()
        deadline = time.monotonic() + args.timeout
        received = bytearray()
        frame = b""
        while time.monotonic() < deadline:
            chunk = ser.read(256)
            if chunk:
                received.extend(chunk)
                if b"ECG " in received and b"\n" in received:
                    begin = received.find(b"ECG ")
                    end = received.find(b"\n", begin) + 1
                    frame = bytes(received[begin:end])
                    break

    parsed = parse_frame(frame) if frame else {"raw": "", "valid_prefix": False}
    actual = parsed.get("logits", [])
    result = {
        "started_utc": started,
        "port": args.port,
        "baud": args.baud,
        "payload_bytes": len(payload),
        "expected_logits": expected,
        "actual_logits": actual,
        "frame": parsed,
        "logits_equal": actual == expected,
        "pass": bool(parsed.get("valid_prefix") and parsed.get("P") and parsed.get("S") and parsed.get("D") and actual == expected),
    }
    out = args.out or (args.run / "qn88_model_full_hil.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
