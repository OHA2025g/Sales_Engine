FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 agrayian
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && python -c 'import tomllib,subprocess; deps=tomllib.load(open("pyproject.toml","rb"))["project"]["dependencies"]; subprocess.check_call(["pip","install",*deps])'
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-deps --no-cache-dir -e . \
    && chown -R agrayian:agrayian /app
USER agrayian
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
