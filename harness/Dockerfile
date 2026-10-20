FROM python:3.12-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl git sqlite3 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /harness
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

WORKDIR /workspace
CMD ["python", "-m", "longrun.cli", "--help"]
