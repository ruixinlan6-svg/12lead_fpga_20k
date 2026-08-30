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
        if len(token) == 2 and token[0] in "PSD" and token[1] in "01":
            result[token[0]] = token[1] == "1"
        elif token.startswith("L=") and len(token) == 4 and all(ch in "0123456789ABCDEF" for ch in token[2:].upper()):
            result.setdefault("logits", []).append(signed_byte(int(token[2:], 16)))
        elif len(token) == 2 and all(ch in "0123456789ABCDEF" for ch in token.upper()):
            result.setdefault("logits", []).append(signed_byte(int(token, 16)))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--port", default="COM10")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--burst-pause",
        type=float,
        default=0.005,
        help="seconds to pause after each 100-byte weight chunk while SDRAM is checked",
    )
    parser.add_argument(
        "--wait-done",
        action="store_true",
        help="ignore intermediate ECG frames and wait for one with D1 (useful for debug images)",
    )
    parser.add_argument(
        "--wait-ack",
        action="store_true",
        help="wait for one debug ECG frame after each 100-byte chunk before sending the next",
    )
    parser.add_argument(
        "--input-pause",
        type=float,
        default=0.0,
        help="seconds to wait after the 12,000-byte input stream before the first weight chunk",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    model_mem = args.run / "hex"
    input_bytes = read_hex(model_mem / "input.hex")
    weight_bytes = b"".join(read_hex(model_mem / name) for name in WEIGHT_FILES)
    expected = [signed_byte(value) for value in read_hex(model_mem / "expected_logits.hex")]
    if len(input_bytes) != 12000 or len(weight_bytes) != 10293:
        raise SystemExit(f"payload size mismatch: input={len(input_bytes)} weights={len(weight_bytes)}")

    started = datetime.now(timezone.utc).isoformat()
    with serial.Serial(args.port, args.baud, timeout=0.25) as ser:
        time.sleep(0.2)
        ser.reset_input_buffer()
        # Input samples are consumed directly by the CNN input BRAM.  Weights
        # are sent in 100-byte chunks because the FPGA keeps only one active
        # SDRAM burst on chip; after each chunk it writes, reads, compares, and
        # drains the burst before accepting the next chunk.
        ser.write(b"ECG0")
        ser.flush()
        time.sleep(0.01)
        for offset in range(0, len(input_bytes), 100):
            ser.write(input_bytes[offset : offset + 100])
            ser.flush()
            if args.burst_pause:
                time.sleep(args.burst_pause)
        if args.input_pause:
            time.sleep(args.input_pause)
        received = bytearray()

        def wait_for_chunk_ack(expected_weight_low: int) -> None:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                chunk = ser.read(256)
                if not chunk:
                    continue
                received.extend(chunk)
                lines = received.splitlines(keepends=True)
                for candidate in lines[:-1]:
                    if candidate.startswith(b"ECG "):
                        # Match the low byte of the accepted weight count so
                        # an input-complete/state-transition frame cannot be
                        # mistaken for the acknowledgement of this chunk.
                        try:
                            fields = candidate.decode("ascii", "replace").split("L=", 1)[1].split()
                            accepted_low = int(fields[2], 16)
                        except (IndexError, ValueError):
                            continue
                        if accepted_low == expected_weight_low:
                            del received[: received.find(candidate) + len(candidate)]
                            return
            raise TimeoutError(
                "timed out waiting for debug chunk acknowledgement; "
                f"recent={bytes(received[-512:])!r}"
            )

        for offset in range(0, len(weight_bytes), 100):
            ser.write(weight_bytes[offset : offset + 100])
            ser.flush()
            if args.wait_ack:
                wait_for_chunk_ack((offset + 100) & 0xFF)
            else:
                time.sleep(args.burst_pause)
        deadline = time.monotonic() + args.timeout
        frame = b""
        last_frame = b""
        while time.monotonic() < deadline:
            chunk = ser.read(256)
            if chunk:
                received.extend(chunk)
                lines = received.splitlines(keepends=True)
                for candidate in lines[:-1]:
                    if candidate.startswith(b"ECG "):
                        last_frame = bytes(candidate)
                        if not args.wait_done or b" D1 " in candidate:
                            frame = last_frame
                            break
                if frame:
                    break
        if not frame and args.wait_done:
            frame = last_frame

    parsed = parse_frame(frame) if frame else {"raw": "", "valid_prefix": False}
    actual = parsed.get("logits", [])
    result = {
        "started_utc": started,
        "port": args.port,
        "baud": args.baud,
        "payload_bytes": 4 + len(input_bytes) + len(weight_bytes),
        "weight_chunk_bytes": 100,
        "burst_pause_s": args.burst_pause,
        "wait_done": args.wait_done,
        "wait_ack": args.wait_ack,
        "input_pause_s": args.input_pause,
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
