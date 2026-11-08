FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
LABEL org.opencontainers.image.licenses="Apache-2.0"
WORKDIR /app
COPY energy /app/energy
COPY LICENSE NOTICE /usr/share/licenses/eos-energiezentrale/
CMD ["python", "-m", "energy.server"]
