#!/usr/bin/env python3
"""High-throughput, resumable PTB-XL 100 Hz downloader.

The PhysioNet tree contains many small files.  This variant keeps one async
HTTP session, verifies every file against the published SHA256SUMS.txt, and
reuses only files whose digest matches.  It never writes raw data to Git.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import pathlib
import re
import sys

import aiohttp


BASE_URL = "https://physionet.org/files/ptb-xl/1.0.3/"
METADATA = ("ptbxl_database.csv", "scp_statements.csv", "RECORDS", "SHA256SUMS.txt")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def expected_hashes(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) >= 2 and len(fields[0]) == 64:
            values[fields[-1].replace("\\", "/")] = fields[0].lower()
    return values


async def fetch(
    session: aiohttp.ClientSession,
    url: str,
    destination: pathlib.Path,
    expected: str | None,
    retries: int,
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        digest = sha256(destination)
        if expected is None or digest == expected:
            return "reuse"
        raise RuntimeError(f"existing checksum mismatch for {destination}: {digest} != {expected}")

    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(retries + 1):
        digest = hashlib.sha256()
        try:
            timeout = aiohttp.ClientTimeout(total=120, connect=30, sock_read=90)
            async with session.get(url, timeout=timeout) as response:
                if response.status >= 500 or response.status == 429:
                    raise aiohttp.ClientResponseError(response.request_info, response.history, status=response.status)
                response.raise_for_status()
                with temporary.open("wb") as out:
                    async for block in response.content.iter_chunked(1024 * 1024):
                        out.write(block)
                        digest.update(block)
            result = digest.hexdigest()
            if expected is not None and result != expected:
                raise RuntimeError(f"checksum mismatch for {destination}: {result} != {expected}")
            temporary.replace(destination)
            return "download"
        except Exception:
            if temporary.exists():
                temporary.unlink()
            if attempt >= retries:
                raise
            await asyncio.sleep(min(8.0, 0.5 * (2**attempt)))
    raise AssertionError("unreachable")


def read_records(path: pathlib.Path, limit: int | None) -> list[str]:
    # The published RECORDS file has a historical missing newline at one
    # section boundary.  Parse record paths by shape instead of relying on
    # physical line boundaries, otherwise one low-resolution record can be
    # silently concatenated with the following records500 entry.
    text = path.read_text(encoding="utf-8")
    records = sorted(set(re.findall(r"records100/[0-9]{5}/[0-9]{5}_lr", text)))
    if not records:
        raise ValueError(f"no records100 low-resolution paths found in {path}")
    return records if limit is None else records[:limit]


async def run(args: argparse.Namespace) -> int:
    args.root.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "12lead_fpga_20k/0.2 (research use; resumable async transfer)"}
    connector = aiohttp.TCPConnector(limit=args.workers, limit_per_host=args.workers, enable_cleanup_closed=True)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        for filename in METADATA:
            await fetch(session, BASE_URL + filename, args.root / filename, None, args.retries)
        hashes = expected_hashes(args.root / "SHA256SUMS.txt")
        for filename in METADATA[:-1]:
            expected = hashes.get(filename)
            if expected is None or sha256(args.root / filename) != expected:
                raise RuntimeError(f"metadata checksum failed for {filename}")

        records = read_records(args.root / "RECORDS", args.limit_records)
        print(f"[info] selected {len(records)} records100 low-resolution records; workers={args.workers}", flush=True)
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        for record in records:
            queue.put_nowait(record)
        failures: list[tuple[str, str]] = []
        completed = 0
        lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal completed
            while True:
                record = await queue.get()
                if record is None:
                    queue.task_done()
                    return
                error: str | None = None
                try:
                    for extension in (".hea", ".dat"):
                        key = record + extension
                        await fetch(session, BASE_URL + key, args.root / key, hashes.get(key), args.retries)
                except Exception as exc:  # keep other workers alive and log every failed record
                    error = f"{type(exc).__name__}: {exc}"
                async with lock:
                    completed += 1
                    if error:
                        failures.append((record, error))
                        print(f"[error] {record}: {error}", flush=True)
                    if completed % 250 == 0 or completed == len(records):
                        print(f"[progress] {completed}/{len(records)} records; failures={len(failures)}", flush=True)
                queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(args.workers)]
        await queue.join()
        for _ in workers:
            queue.put_nowait(None)
        await asyncio.gather(*workers)
        if failures:
            failure_log = args.root / "download_failures_async.txt"
            failure_log.write_text("\n".join(f"{record}\t{error}" for record, error in failures) + "\n", encoding="utf-8")
            print(f"[error] {len(failures)} records failed; retry with the same command. Details: {failure_log}", flush=True)
            return 2
    print("[ok] PTB-XL 100 Hz acquisition complete with published checksum verification", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--limit-records", type=int, default=None)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--retries", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.workers <= 64:
        raise ValueError("--workers must be between 1 and 64")
    if args.limit_records is not None and args.limit_records < 1:
        raise ValueError("--limit-records must be positive")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
