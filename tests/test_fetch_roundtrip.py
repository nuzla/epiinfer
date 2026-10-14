"""End to end: pack a dataset, serve it over HTTP, fetch-data it, load it."""

import functools
import http.server
import importlib.util
import threading
from pathlib import Path

import pytest

import epiinfer.fetch as fetch_mod
from epiinfer import load_dataset

ROOT = Path(__file__).resolve().parents[1]


def _pack_module():
    spec = importlib.util.spec_from_file_location("pack_datasets", ROOT / "tools" / "pack_datasets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture()
def served(tmp_path, demo_path):
    """Serve a packed copy of the demo data on 127.0.0.1; yields (base_url, folder, sha)."""
    pack = _pack_module()
    rel = tmp_path / "release"
    rel.mkdir()
    archive = pack.pack("demo", demo_path, rel)
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(rel)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", rel, fetch_mod.sha256(archive)
    finally:
        srv.shutdown()


def test_pack_is_deterministic(tmp_path, demo_path):
    """Same data, different file timestamps (e.g. a fresh checkout) -> same archive hash."""
    import os
    import shutil
    pack = _pack_module()
    src = tmp_path / "src"
    shutil.copytree(demo_path, src)
    hashes = []
    for stamp in (1_000_000_000, 1_700_000_000):
        for f in src.iterdir():
            os.utime(f, (stamp, stamp))
        out = tmp_path / str(stamp)
        out.mkdir()
        hashes.append(fetch_mod.sha256(pack.pack("demo", src, out)))
    assert hashes[0] == hashes[1]


def test_fetch_verifies_against_packaged_checksums(served, tmp_path, monkeypatch):
    url, rel, sha = served
    monkeypatch.setattr(fetch_mod, "known_checksums", lambda: {"epiinfer-data-demo.zip": sha})
    out = fetch_mod.fetch(f"{url}/epiinfer-data-demo.zip", tmp_path / "data")
    assert load_dataset(out / "demo").population_total == 600

    archive = rel / "epiinfer-data-demo.zip"                # tamper with the served file
    archive.write_bytes(archive.read_bytes()[:-8] + b"tampered")
    with pytest.raises(SystemExit, match="checksum mismatch"):
        fetch_mod.fetch(f"{url}/epiinfer-data-demo.zip", tmp_path / "data2")
    assert not (tmp_path / "data2" / "demo").exists()


def test_packaged_checksum_list_is_well_formed():
    known = fetch_mod.known_checksums()
    assert set(known) == {"epiinfer-data-age_structured.zip", "epiinfer-data-openabm.zip"}
    assert all(len(v) == 64 and int(v, 16) >= 0 for v in known.values())
