# ── MindBridge Docker Image ──────────────────────────────────────────────────
# Minimal Python image — no extra dependencies needed (stdlib only)
FROM python:3.11-slim

# Metadata
LABEL maintainer="Ramis63"
LABEL description="MindBridge Student Mental Wellness Tracker"
LABEL version="1.0"

# Set working directory inside the container
WORKDIR /app

# Copy all project files into the container
COPY . .

# Create a dedicated volume directory for the SQLite database
# This ensures data persists when the container restarts
RUN mkdir -p /data

# Add the default Codespaces user and own app/data directories
RUN useradd --create-home --shell /bin/bash vscode \
    && chown -R vscode:vscode /app /data

# Run as the same user VS Code/Codespaces uses for terminals and tasks,
# so files created by the auto-started server (e.g. the SQLite DB) stay
# writable if the server is later restarted manually from a Codespaces terminal
USER vscode

# Expose the app port
EXPOSE 8000

# Health check — Docker will mark the container as healthy once the server responds
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Override the DB path to use the persistent /data volume
ENV DB_PATH=/data/mindbridge.db

# Start the server
CMD ["python", "-u", "run.py"]
