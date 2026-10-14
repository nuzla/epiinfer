"""Pack dataset folders into zips + a checksum manifest for a GitHub Release.

    python tools/pack_datasets.py OUT_DIR NAME=FOLDER [NAME=FOLDER ...]
    python tools/pack_datasets.py dist-data age_structured=PATH/dataset openabm=PATH/new_data_set
"""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from epiinfer.fetch import sha256  # noqa: E402

FILES = ["individual_day_state.csv", "timed_edges.csv", "states_total.csv",
         "age_group_population.csv", "individual_age_group.csv",
         "daily_group_infected.csv", "daily_group_avg_contacts.csv"]


def main(out: str, *specs: str) -> None:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for spec in specs:
        name, folder = spec.split("=", 1)
        archive = out_dir / f"epiinfer-data-{name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for f in FILES:
                p = Path(folder) / f
                if p.exists():
                    z.write(p, f"{name}/{f}")
        lines.append(f"{sha256(archive)}  {archive.name}")
        print(lines[-1])
    (out_dir / "checksums.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
