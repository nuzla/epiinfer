# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MPLBACKEND=Agg
RUN useradd --create-home --uid 1000 epi
COPY --from=build /dist/*.whl /tmp/
RUN pip install "$(ls /tmp/epiinfer-*.whl)[all]" && rm -f /tmp/*.whl
USER epi
WORKDIR /work
# /data: datasets (read-only is fine)   /work/results: outputs
VOLUME ["/data", "/work/results"]
ENTRYPOINT ["epiinfer"]
CMD ["--help"]
