# ---------- build ----------
FROM python:3.12-bookworm AS build

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /venv && \
    /venv/bin/pip install \
        neo4j \
        flask \
        flask-cors \
        pyyaml \
        dacite \
        structlog \
        python-dotenv \
        opensearch-py \
        temporalio

COPY neo4j_adapter/ /app/
COPY isim_common/ /app/isim_common/

RUN sed -i 's/\r$//' /app/crontab /app/start.sh /app/*.py && \
    chmod +x /app/start.sh

# ---------- runtime ----------
FROM python:3.12-slim-bookworm AS runtime

ENV VIRTUAL_ENV=/venv \
    PATH=/venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONFAULTHANDLER=1 \
    PYTHONBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends cron && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 app && \
    useradd -u 1001 -g app -s /bin/sh -d /app app

RUN mkdir -p /app/logs && chmod 777 /app/logs

COPY --from=build /venv /venv
COPY --from=build /app /app

USER 1001:1001

EXPOSE 5000

CMD ["/bin/bash", "/app/start.sh"]
