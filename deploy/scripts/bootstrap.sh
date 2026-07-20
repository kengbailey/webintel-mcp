#!/usr/bin/env bash
# Fetch WebIntel secrets from Secret Manager and (re)start the cloud stack.
# Idempotent and re-runnable. Run on the VM as root (or via `gcloud compute ssh`).
#
#   sudo /opt/webintel-mcp/deploy/scripts/bootstrap.sh
set -euo pipefail

APP_DIR="${1:-/opt/webintel-mcp}"
ENV_FILE="/opt/webintel.env"
META="http://metadata.google.internal/computeMetadata/v1"

PROJECT="$(curl -s -H "Metadata-Flavor: Google" "${META}/project/project-id)"
TOKEN="$(curl -s -H "Metadata-Flavor: Google" \
  "${META}/instance/service-accounts/default/token" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')"

get_secret() {
  local secret="$1"
  curl -s -H "Authorization: Bearer ${TOKEN}" \
    "https://secretmanager.googleapis.com/v1/projects/${PROJECT}/secrets/${secret}/versions/latest:access" \
    | python3 -c 'import sys,json,base64;d=json.load(sys.stdin);print(base64.b64decode(d["payload"]["data"]).decode())' 2>/dev/null || true
}

# env var name -> Secret Manager secret id
pairs=(
  "MCP_AUTHKIT_DOMAIN=webintel-mcp-authkit-domain"
  "MCP_BASE_URL=webintel-mcp-base-url"
  "MCP_RESOURCE_URL=webintel-mcp-resource-url"
  "MCP_MACHINE_SECRET=webintel-mcp-machine-secret"
  "MCP_MACHINE_ISSUER=webintel-mcp-machine-issuer"
  "MCP_REQUIRED_SCOPES=webintel-mcp-required-scopes"
  "REDDIT_CLIENT_ID=webintel-reddit-client-id"
  "REDDIT_CLIENT_SECRET=webintel-reddit-client-secret"
  "REDDIT_USER_AGENT=webintel-reddit-user-agent"
  "STT_ENDPOINT=webintel-stt-endpoint"
  "STT_MODEL=webintel-stt-model"
  "STT_API_KEY=webintel-stt-api-key"
  "CLOUDFLARE_TUNNEL_TOKEN=webintel-cloudflare-tunnel-token"
)

: > "$ENV_FILE"
for kv in "${pairs[@]}"; do
  var="${kv%%=*}"; secret="${kv#*=}"
  printf '%s=%s\n' "$var" "$(get_secret "$secret")" >> "$ENV_FILE"
done

cd "$APP_DIR"
docker compose -f docker-compose.cloud.yml --env-file "$ENV_FILE" up -d --build
