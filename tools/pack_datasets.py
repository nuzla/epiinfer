"""Pack dataset folders into release zips + a checksum manifest.

    uv run python tools/pack_datasets.py OUT_DIR NAME=FOLDER [NAME=FOLDER ...]
    uv run python tools/pack_datasets.py dist-data age_structured=PATH/dataset openabm=PATH/new_data_set

The zips are deterministic (fixed timestamps, permissions and member order), so packing the
same data again gives the same SHA-256. Copy the printed lines into
``src/epiinfer/checksums.txt`` so ``epiinfer fetch-data`` verifies downloads by default.
"""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from epiinfer.fetch import sha256  # noqa: E402

FILES = ["age_group_population.csv", "daily_group_avg_contacts.csv", "daily_group_infected.csv",
         "individual_age_group.csv", "individual_day_state.csv", "states_total.csv",
         "timed_edges.csv"]
EPOCH = (1980, 1, 1, 0, 0, 0)


def pack(name: str, folder: str | Path, out_dir: Path) -> Path:
    archive = out_dir / f"epiinfer-data-{name}.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for f in FILES:                                    # fixed order
            p = Path(folder) / f
            if not p.exists():
                continue
            info = zipfile.ZipInfo(f"{name}/{f}", date_time=EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3                         # unix, regardless of host
            z.writestr(info, p.read_bytes(), compresslevel=9)
    return archive


def main(out: str, *specs: str) -> None:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for spec in specs:
        name, folder = spec.split("=", 1)
        archive = pack(name, folder, out_dir)
        lines.append(f"{sha256(archive)}  {archive.name}")
        print(lines[-1])
    (out_dir / "checksums.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
