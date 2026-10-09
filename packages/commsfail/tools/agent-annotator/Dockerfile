# The annotator agents' image: Codex CLI 0.160.1 (the version the runs used), with tools to read a bundle.
FROM node:22.18.0-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ripgrep jq ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @openai/codex@0.160.1 && npm cache clean --force
WORKDIR /bundle
