"""Download and verify dataset archives (the paper's exact datasets, hosted as release assets).

The hosting location is not baked in: pass ``--url`` or set ``EPIINFER_DATA_URL``. Every
download is verified against a SHA-256 you supply or against ``data/checksums.txt``.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
import zipfile
from pathlib import Path


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str | None, dest: str | Path, expected_sha256: str | None = None) -> Path:
    """Download ``url`` to ``dest`` and unzip it; refuse to unpack on a checksum mismatch."""
    url = url or os.environ.get("EPIINFER_DATA_URL")
    if not url:
        raise SystemExit("no data URL: pass --url or set EPIINFER_DATA_URL "
                         "(see docs/REPRODUCING.md), or generate data with `epiinfer simulate`")
    if not url.lower().startswith(("https://", "http://localhost")):
        raise SystemExit("refusing non-HTTPS data URL")
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / Path(url).name
    urllib.request.urlretrieve(url, archive)  # noqa: S310 - scheme checked above
    got = sha256(archive)
    if expected_sha256 and got.lower() != expected_sha256.lower():
        archive.unlink()
        raise SystemExit(f"checksum mismatch for {archive.name}: expected {expected_sha256}, got {got}")
    if not expected_sha256:
        print(f"WARNING: no checksum supplied; archive sha256 = {got}")
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            target = (dest / member).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise SystemExit(f"unsafe path in archive: {member}")
        z.extractall(dest)
    return dest
