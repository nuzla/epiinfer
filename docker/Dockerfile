# syntax=docker/dockerfile:1
# Installs the exact versions in uv.lock, so every image runs the same numerical stack.
# Build:  docker build -f docker/Dockerfile -t epiinfer .
# Run:    docker run --rm --user "$(id -u):$(id -g)" \
#           -v "$PWD/data:/data:ro" -v "$PWD/results:/work/results" \
#           epiinfer reproduce --table openabm --data /data/openabm
ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE} AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
# dependencies first (cached layer), then the project itself
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-dev --all-extras --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --all-extras --no-editable

FROM ${PYTHON_IMAGE}
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 MPLBACKEND=Agg HOME=/work
COPY --from=build /opt/venv /opt/venv
RUN useradd --create-home --uid 1000 epi && mkdir -p /work/results && chmod -R a+rwX /work
USER epi
WORKDIR /work
# /data: datasets (mount read-only)   /work/results: outputs (default --out results)
VOLUME ["/work/results"]
ENTRYPOINT ["epiinfer"]
CMD ["--help"]
