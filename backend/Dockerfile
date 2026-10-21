# Build from the repository root:  docker build -f backend/Dockerfile .
# (the backend imports the reference agents package from ./agents)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app
WORKDIR /srv

# Dependencies first for better layer caching
COPY agents/pyproject.toml agents/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
COPY agents/agentforge_agents agents/agentforge_agents
COPY agents/tests agents/tests
COPY backend/app backend/app
COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/alembic.ini
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# Editable install keeps agent sources (and their tests) on disk: the agent detail pages show them.
# Strip Windows line endings (CRLF checkouts) so the shell script always runs.
RUN pip install -e ./agents -e ./backend \
 && sed -i "s/\r$//" /usr/local/bin/docker-entrypoint.sh \
 && chmod +x /usr/local/bin/docker-entrypoint.sh

USER app
WORKDIR /srv/backend
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
