# syntax=docker/dockerfile:1.7

# ============================================================
# Stage 1: CSS builder - compile Tailwind + daisyUI to style.css
# ============================================================
FROM node:lts-alpine AS css-builder

WORKDIR /build

# Install npm deps first so this layer caches unless package.json changes
COPY package.json package-lock.json ./
RUN npm ci

# Tailwind v4 scans @source globs in input.css plus auto-detects sources.
# Copy the entire vweb tree so every .jinja template is visible to the scanner.
COPY src/ ./src/

RUN npx @tailwindcss/cli \
    -i src/vweb/static/css/input.css \
    -o src/vweb/static/css/style.css \
    --minify

# ============================================================
# Stage 2: Python builder - install dependencies and project
# ============================================================
FROM ghcr.io/astral-sh/uv:0.11.3-python3.13-trixie-slim AS python-builder

# Build-time system deps for any native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libc6-dev \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

# Cache dependency install separately from project install
COPY uv.lock pyproject.toml README.md ./
RUN uv sync --locked --no-dev --no-cache --no-install-project

# Install the project itself
COPY src/ ./src/
RUN uv sync --locked --no-dev --no-cache

# ============================================================
# Stage 3: Runtime - lean production image
# ============================================================
FROM python:3.13-slim-trixie

# Runtime-only system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini tzdata gosu \
    && rm -rf /var/lib/apt/lists/*

# Timezone
ENV TZ=Etc/UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ >/etc/timezone

# Create default app user
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# PUID/PGID defaults (overridden at runtime via env vars)
ENV PUID=1000
ENV PGID=1000

WORKDIR /app

# Copy the built venv from the python builder
COPY --from=python-builder /app/.venv .venv

# Copy application source
COPY src/ ./src/

# Copy the compiled stylesheet from the css builder, overwriting any
# leftover file from the source tree
COPY --from=css-builder /build/src/vweb/static/css/style.css ./src/vweb/static/css/style.css

# Copy entrypoint
COPY scripts/docker_entry.sh ./scripts/docker_entry.sh
RUN chmod +x scripts/docker_entry.sh

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8089

# OCI labels (placed after stable layers to avoid cache busting)
LABEL org.opencontainers.image.source=https://github.com/natelandau/valentina-web
LABEL org.opencontainers.image.description="Valentina Web"
LABEL org.opencontainers.image.url=https://github.com/natelandau/valentina-web
LABEL org.opencontainers.image.title="Valentina Web"

ENTRYPOINT ["tini", "--"]
CMD ["scripts/docker_entry.sh"]
