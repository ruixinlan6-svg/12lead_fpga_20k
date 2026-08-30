"""Official LUDB 1.0.1 downloader and integrity verification tool."""

from __future__ import annotations

import io
import os
import sys
import zipfile
import urllib.request
from pathlib import Path

# Add project root and train/ec57 to path
ROOT_DIR = Path(__file__).resolve().parents[2]
TRAIN_EC57_DIR = ROOT_DIR / "train" / "ec57"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(TRAIN_EC57_DIR) not in sys.path:
    sys.path.insert(0, str(TRAIN_EC57_DIR))

from ludb_io import (
    LUDB_VERSION,
    LUDB_SOURCE_URL,
    discover_ludb_records,
    build_sha256_inventory,
    verify_published_sha256s
)

ZIP_URL = "https://physionet.org/static/published-projects/ludb/lobachevsky-university-electrocardiography-database-1.0.1.zip"


def download_and_extract_ludb(target_dir: str | Path) -> None:
    target_path = Path(target_dir).resolve()
    target_path.mkdir(parents=True, exist_ok=True)

    print(f"Downloading official LUDB {LUDB_VERSION} from {ZIP_URL}...")
    req = urllib.request.Request(
        ZIP_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    
    with urllib.request.urlopen(req, timeout=120) as response:
        total_size = response.length or 0
        print(f"Archive size: {total_size / (1024*1024):.2f} MB")
        data = io.BytesIO(response.read())

    print("Extracting archive into target directory...")
    with zipfile.ZipFile(data) as zf:
        members = zf.infolist()
        prefix = ""
        for member in members:
            if "RECORDS" in member.filename:
                idx = member.filename.find("RECORDS")
                prefix = member.filename[:idx]
                break

        for member in members:
            if member.is_dir():
                continue
            rel_name = member.filename
            if prefix and rel_name.startswith(prefix):
                rel_name = rel_name[len(prefix):]
            
            dest_file = target_path / rel_name
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(dest_file, "wb") as dst:
                dst.write(src.read())

    print("Extract complete. Verifying published SHA-256 checksums...")
    result = verify_published_sha256s(target_path)
    print(f"Successfully verified {result['verified_file_count']} files against official SHA256SUMS.txt!")
    
    records = discover_ludb_records(target_path)
    print(f"Successfully discovered all {len(records)} LUDB records.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download and verify official PhysioNet LUDB 1.0.1 dataset")
    parser.add_argument("--target-dir", default="data/ludb/1.0.1", help="Target destination directory")
    args = parser.parse_args()

    download_and_extract_ludb(args.target_dir)
