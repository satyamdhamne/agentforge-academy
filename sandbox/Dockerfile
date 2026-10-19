# Isolated code runner. Run it with the restrictions in docker-compose.yml:
# internal-only network, read-only root fs, tmpfs /tmp, cap_drop ALL, no-new-privileges, pids/memory/CPU limits.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin runner

WORKDIR /srv
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.7"
COPY runner ./runner

USER runner
ENV PYTHONUNBUFFERED=1 TMPDIR=/tmp SANDBOX_PYTHON=/usr/local/bin/python3 SANDBOX_NODE=/usr/bin/node
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uvicorn", "runner.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
