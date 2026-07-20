#!/usr/bin/env bash
# Seed Secret Manager secrets from a local env file (KEY=VALUE per line).
# Run from a machine with gcloud authed (the Mac). Creates a new secret
# version for each known key; secret containers must already exist
# (created by `terraform apply`).
#
#   PROJECT=homelab-424902 ./deploy/scripts/seed-secrets.sh .env.cloud
set -euo pipefail
PROJECT="${PROJECT:-homelab-424902}"
ENV_FILE="${1:?usage: seed-secrets.sh <env-file>}"

declare -A MAP=(
  [MCP_AUTHKIT_DOMAIN]=webintel-mcp-authkit-domain
  [MCP_BASE_URL]=webintel-mcp-base-url
  [MCP_RESOURCE_URL]=webintel-mcp-resource-url
  [MCP_MACHINE_SECRET]=webintel-mcp-machine-secret
  [MCP_MACHINE_ISSUER]=webintel-mcp-machine-issuer
  [MCP_REQUIRED_SCOPES]=webintel-mcp-required-scopes
  [REDDIT_CLIENT_ID]=webintel-reddit-client-id
  [REDDIT_CLIENT_SECRET]=webintel-reddit-client-secret
  [REDDIT_USER_AGENT]=webintel-reddit-user-agent
  [STT_ENDPOINT]=webintel-stt-endpoint
  [STT_MODEL]=webintel-stt-model
  [STT_API_KEY]=webintel-stt-api-key
  [CLOUDFLARE_TUNNEL_TOKEN]=webintel-cloudflare-tunnel-token
)

gcloud services enable secretmanager.googleapis.com --project "$PROJECT" >/dev/null 2>&1 || true

while IFS='=' read -r key val; do
  [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
  secret="${MAP[$key]:-}"
  [ -z "$secret" ] && continue
  printf '%s' "$val" | gcloud secrets versions add "$secret" --data-file - --project "$PROJECT"
  echo "seeded $key -> $secret"
done < "$ENV_FILE"

echo "done."
