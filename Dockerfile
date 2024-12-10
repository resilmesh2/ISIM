FROM python:3.12-bookworm AS build

WORKDIR /app

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    python -m venv /venv

COPY . .
COPY pyproject.toml poetry.lock ./
RUN . /venv/bin/activate && ~/.local/bin/poetry install --no-root --only main

FROM python:3.12-slim-bookworm AS runtime
ENV VIRTUAL_ENV=/venv \
	PATH=/venv/bin:$PATH \
	PYTHONFAULTHANDLER=1 \
    PYTHONBUFFERED=1 \
    PYTHONPATH=/app

ENV WORKER_COUNT=3

WORKDIR /app

RUN groupadd -g 1001 app && \
    useradd -u 1001 -g app -s /bin/sh -d /app app

COPY --chown=1001:1001 --from=build /app /app
COPY --chown=1001:1001 --from=build /venv /venv

USER 1001:1001
EXPOSE 8000

CMD python /app/isim_rest/manage.py makemigrations && \
    python /app/isim_rest/manage.py migrate && \
    gunicorn --preload --workers=${WORKER_COUNT} --timeout 1200 --chdir /app/isim_rest --bind 0.0.0.0:8000 'neo4j_rest.wsgi:application'
