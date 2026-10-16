FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Playwright's Chromium needs these; keep them in the image so the scraper can run
# in the worker container without a second build stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --upgrade pip && pip install -e ".[dev]"

# Chromium is only needed by the fuel-card portal scraper. If it cannot be
# installed the build still succeeds; the scraper then reports needs_login
# instead of taking the whole API down with it.
RUN playwright install --with-deps chromium || \
    echo "playwright browser install skipped (portal scraper unavailable)"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
