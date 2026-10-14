# syntax=docker/dockerfile:1
# Build:  docker build -f docker/Dockerfile -t epiinfer .
# Run:    docker run --rm --user "$(id -u):$(id -g)" \
#           -v "$PWD/data:/data:ro" -v "$PWD/results:/work/results" \
#           epiinfer reproduce --table openabm --data /data/openabm
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir build==1.2.2 && python -m build --wheel --outdir /dist

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MPLBACKEND=Agg HOME=/work
COPY --from=build /dist/*.whl /tmp/
RUN pip install "$(ls /tmp/epiinfer-*.whl)[all]" && rm -f /tmp/*.whl \
    && useradd --create-home --uid 1000 epi \
    && mkdir -p /work/results && chmod -R a+rwX /work
USER epi
WORKDIR /work
# /data: datasets (mount read-only)   /work/results: outputs (default --out results)
VOLUME ["/work/results"]
ENTRYPOINT ["epiinfer"]
CMD ["--help"]
