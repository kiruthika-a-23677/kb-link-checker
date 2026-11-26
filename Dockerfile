# Slim image: Python + only the headless Chromium shell (no Firefox/WebKit).
# Catalyst unpacks the image in limited temp space, so size matters.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    KB_HEADLESS=1 \
    KB_ALLOWED_HOSTS=help.zoho.com

WORKDIR /app
COPY requirements.txt .

# Install deps, the browser and its system libraries in ONE layer, then clean
# apt caches so they don't stay in the image.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && pip install -r requirements.txt \
    && playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache

COPY . .

# EXPOSE is documentation only; AppSail sets X_ZOHO_CATALYST_LISTEN_PORT.
EXPOSE 9000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${X_ZOHO_CATALYST_LISTEN_PORT:-9000}"]
