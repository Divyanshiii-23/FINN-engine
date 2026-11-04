# FINN: research engine (Python) + web app (Next.js) in one image.
# The engine listens on 127.0.0.1 only; the web app is the public surface and proxies to it.

# ---- web build
FROM node:22-bookworm-slim AS web
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
RUN npx next build && npm prune --omit=dev

# ---- runtime
FROM node:22-bookworm-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NODE_ENV=production PORT=3000 FINN_PYTHON=/opt/venv/bin/python
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
WORKDIR /app
COPY engine ./engine
RUN /opt/venv/bin/pip install --no-cache-dir ./engine
COPY --from=web /app/apps/web ./apps/web
COPY deploy ./deploy
# Synthetic, labelled demo data (fixtures) is generated at build time; nothing is fetched.
RUN cd engine && /opt/venv/bin/python -m finn_engine fixtures && /opt/venv/bin/python -m finn_engine research-fixtures \
    && chmod +x /app/deploy/start.sh && useradd -r -u 10001 finn && chown -R finn /app
USER finn
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["/app/deploy/start.sh"]
