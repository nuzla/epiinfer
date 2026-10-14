"""Static checks on the Docker files (Docker itself runs in CI, not here)."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_run_all_script_is_valid_and_executable():
    script = ROOT / "docker" / "run_all.sh"
    assert os.access(script, os.X_OK), "docker/run_all.sh must be executable"
    bash = shutil.which("bash")
    assert bash and subprocess.run([bash, "-n", str(script)]).returncode == 0


def test_compose_matches_readme_mounts():
    yaml = pytest.importorskip("yaml")
    svc = yaml.safe_load((ROOT / "docker" / "docker-compose.yml").read_text())["services"]["epiinfer"]
    assert svc["build"]["dockerfile"] == "docker/Dockerfile"
    assert sorted(v.split(":")[1] for v in svc["volumes"]) == ["/data", "/work/results"]
    assert "LOCAL_USER" in svc["user"]


def test_readme_docker_commands_use_real_cli_commands():
    """Every `epi <command>` in the README's Docker section must be a real subcommand."""
    from epiinfer.cli import _build
    sub = next(a for a in _build()._actions if a.dest == "cmd")
    readme = (ROOT / "README.md").read_text()
    section = readme[readme.index("## Docker"):readme.index("## Methods")]
    used = set(re.findall(r"^epi (\w[\w-]*)", section, re.M))
    assert used and used <= set(sub.choices), used - set(sub.choices)
    assert "docker/run_all.sh" in section and "docker build -f docker/Dockerfile" in section


def test_dockerfile_uses_locked_install():
    text = (ROOT / "docker" / "Dockerfile").read_text()
    assert "uv sync --locked" in text and "USER epi" in text and 'ENTRYPOINT ["epiinfer"]' in text
