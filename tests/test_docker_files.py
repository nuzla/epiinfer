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


def test_dockerfile_base_images_pinned_by_digest():
    text = (ROOT / "docker" / "Dockerfile").read_text()
    froms = re.findall(r"^FROM (\S+)", text, re.M)
    assert len(froms) == 2 and all(re.search(r"@sha256:[0-9a-f]{64}$", f) for f in froms), froms
    assert re.search(r"--from=ghcr\.io/astral-sh/uv:[\d.]+@sha256:[0-9a-f]{64} ", text)
    assert "LICENSE" in text        # pyproject's license-files needs it at build time


def test_publish_workflow_is_tag_triggered_and_safe():
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "publish.yml").read_text())
    triggers = wf.get("on", wf.get(True))
    assert triggers["push"]["tags"] == ["v*"] and "workflow_dispatch" in triggers
    assert wf["permissions"] == {"contents": "read", "packages": "write"}
    text = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
    # branch pushes and manual runs must never push an image
    assert "startsWith(github.ref, 'refs/tags/v')" in text
    assert "linux/amd64,linux/arm64" in text and "GITHUB_TOKEN" in text
    step_names = [s.get("name", "") for s in wf["jobs"]["image"]["steps"]]
    assert any("match the package version" in n for n in step_names)


def test_dependabot_covers_docker_and_actions():
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())
    assert {u["package-ecosystem"] for u in cfg["updates"]} == {"docker", "github-actions"}


def test_readme_documents_ghcr_and_apptainer():
    readme = (ROOT / "README.md").read_text()
    for needle in ("docker pull ghcr.io/nuzla/epiinfer", "apptainer pull epiinfer.sif docker://",
                   "### Apptainer / Singularity", "not been tested", "@sha256"):
        assert needle in readme, needle
    assert (ROOT / "docs" / "RELEASING.md").exists()
