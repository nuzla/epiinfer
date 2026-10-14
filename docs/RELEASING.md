# Releasing

## Publishing the Docker image (GitHub Container Registry)

The `publish` workflow builds a **linux/amd64 + linux/arm64** image, smoke-tests it, and
pushes it to `ghcr.io/<owner>/epiinfer`. The base images are pinned by digest in
`docker/Dockerfile`, and Dependabot proposes digest updates weekly.

1. **Dry run first (pushes nothing).** On GitHub: Actions → *publish* → *Run workflow*.
   It builds both architectures and runs the smoke test, so an arm64 build failure shows up
   before a release.
2. **Release.** Bump `version` in `pyproject.toml`, run `uv lock`, update `CHANGELOG.md`,
   commit, then:
   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   ```
   The workflow refuses a tag that does not match `pyproject.toml`. It pushes `0.1.0`, `0.1`
   and `latest` (a pre-release tag such as `v0.2.0-rc1` pushes only its own tag).
3. **Make the package public (first release only).** New packages start private. In the
   repository's *Packages* section open `epiinfer` → *Package settings* → *Change visibility*.
4. **Record the digest.** The workflow summary prints `ghcr.io/<owner>/epiinfer@sha256:…`.
   Quote it in the paper or release notes: tags can move, digests cannot.
5. **Test the pull** on a machine that is not logged in to GitHub:
   `docker pull ghcr.io/<owner>/epiinfer:0.1.0 && docker run --rm ghcr.io/<owner>/epiinfer:0.1.0 --version`

The Apptainer route needs no separate build: it converts the pushed image
(`apptainer pull docker://ghcr.io/<owner>/epiinfer:0.1.0`).

## A citable archive

Connect the repository to [Zenodo](https://zenodo.org) (Settings → GitHub), then publish a
GitHub release. Zenodo archives the code and issues a DOI that can go in `CITATION.cff`.
