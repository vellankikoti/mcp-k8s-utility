# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS builder
WORKDIR /build
COPY packages/server/pyproject.toml packages/server/pyproject.toml
COPY packages/server/src packages/server/src
COPY packages/server/README.md packages/server/README.md
RUN pip install --no-cache-dir build \
    && python -m build packages/server --wheel --outdir /wheels

FROM python:3.13-slim AS runtime
RUN groupadd -g 1000 utility \
    && useradd -m -u 1000 -g 1000 -s /bin/bash utility
WORKDIR /app
COPY --from=builder /wheels/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl \
    && rm -rf /tmp/*.whl \
    && pip cache purge
USER utility
EXPOSE 8080
ENV UTILITY_LLM_PROVIDER=disabled
ENTRYPOINT ["mcp-k8s-utility"]
CMD ["serve-mcp"]
