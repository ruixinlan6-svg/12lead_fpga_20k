#!/usr/bin/env python3
"""Download PTB-XL metadata and 100 Hz low-resolution records.

The script is intentionally explicit: it never deletes an existing file and
never downloads the 500 Hz tree unless the caller changes the URL in source.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import pathlib
import sys
import urllib.request


BASE_URL = "https://physionet.org/files/ptb-xl/1.0.3/"
METADATA = ("ptbxl_database.csv", "scp_statements.csv", "RECORDS")


def fetch(url: str, destination: pathlib.Path, announce: bool = True) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if announce:
            print(f"[reuse] {destination} sha256={digest}")
        return digest

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "12lead_fpga_20k/0.1 (research use)"},
    )
    digest = hashlib.sha256()
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as out:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                out.write(block)
                digest.update(block)
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

    result = digest.hexdigest()
    if announce:
        print(f"[download] {url} -> {destination} sha256={result}")
    return result


def read_records(path: pathlib.Path, limit: int | None) -> list[str]:
    records = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        relative = raw.strip()
        if relative.startswith("records100/") and relative.endswith("_lr"):
            records.append(relative)
    records.sort()
    return records if limit is None else records[:limit]


def download_record(args: tuple[str, pathlib.Path]) -> tuple[str, str | None]:
    record, root = args
    try:
        for extension in (".hea", ".dat"):
            fetch(BASE_URL + record + extension, root / (record + extension), announce=False)
        return record, None
    except Exception as exc:  # keep other workers alive and report all failures
        return record, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--limit-records", type=int, default=None)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    args.root.mkdir(parents=True, exist_ok=True)
    for filename in METADATA:
        fetch(BASE_URL + filename, args.root / filename)

    if args.metadata_only:
        return 0

    records = read_records(args.root / "RECORDS", args.limit_records)
    print(f"[info] selected {len(records)} records100 low-resolution records")
    if args.workers < 1 or args.workers > 64:
        raise ValueError("--workers must be between 1 and 64")
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = pool.map(download_record, ((record, args.root) for record in records))
        for index, (record, error) in enumerate(jobs, start=1):
            if error:
                failures.append((record, error))
                print(f"[error] {record}: {error}")
            if index % 250 == 0 or index == len(records):
                print(f"[progress] {index}/{len(records)} records; failures={len(failures)}")
    if failures:
        failure_log = args.root / "download_failures.txt"
        failure_log.write_text("\n".join(f"{record}\t{error}" for record, error in failures) + "\n", encoding="utf-8")
        print(f"[error] {len(failures)} records failed; retry with the same command. Details: {failure_log}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
