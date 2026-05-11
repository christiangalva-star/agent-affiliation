# ── Dockerfile — Agent Affiliation Amazon -> TikTok ──────────────────────────
FROM python:3.11-slim

# System dependencies (Playwright + moviepy + fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    fonts-dejavu-core fonts-liberation \
    ffmpeg \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgbm1 libasound2 libxrandr2 libxdamage1 \
    libpango-1.0-0 libcairo2 libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only)
RUN playwright install chromium

# Copy application
COPY agent_affiliation.py .

# Railway uses PORT env var — not needed here (no HTTP server)
# The agent runs as a one-shot job / cron

CMD ["python", "agent_affiliation.py"]
# rebuild mar.  5 mai 2026 18:51:56 CEST
# redeploy lun. 11 mai 2026 11:08:03 CEST
