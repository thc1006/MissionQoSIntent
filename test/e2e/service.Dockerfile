# L2/L3 admission service image for the Stage-9 E2E harness. Build from the repo ROOT:
#   podman build -f test/e2e/service.Dockerfile -t localhost/mqi-admission:e2e .
# Runtime config via env (see mqi.serve.__main__): MQI_IR_PATH (required), MQI_LISTEN, MQI_MAX_QUEUE,
# MQI_BURST_SECONDS. The compiled ir.json is mounted into the pod (ConfigMap) at MQI_IR_PATH.
FROM python:3.12-slim AS build
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
# Copy only the installed package + deps from the build stage (no build tooling in the final image).
COPY --from=build /install /usr/local
RUN useradd --create-home --uid 10001 mqi
USER mqi
ENV MQI_LISTEN=0.0.0.0:8080 PYTHONUNBUFFERED=1
EXPOSE 8080
ENTRYPOINT ["python", "-m", "mqi.serve"]
