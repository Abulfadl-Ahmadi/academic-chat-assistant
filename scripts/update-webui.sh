#!/usr/bin/env bash
# Rebuild the G-CAT Open WebUI image from the latest upstream tag.
#
#   ./scripts/update-webui.sh
#
# Pulls ghcr.io/open-webui/open-webui:main, rebuilds the derived image with
# the branding baked in, and recreates the container. The build fails loudly
# if upstream restructures anything the customisations depend on, so a broken
# result cannot be deployed silently.
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE="gcat/open-webui:custom"
BUILD="$(date +%Y%m%d-%H%M%S)"

echo "==> Pulling upstream open-webui:main"
docker pull ghcr.io/open-webui/open-webui:main

echo "==> Building $IMAGE (build $BUILD)"
docker build -f Dockerfile.webui \
    --build-arg CUSTOM_BUILD="$BUILD" \
    -t "$IMAGE" .

echo "==> Recreating open-webui"
docker compose up -d --force-recreate --no-deps open-webui

echo "==> Verifying branding took effect"
docker compose exec -T open-webui sh -c '
  set -e
  grep -q "WEBUI_NAME = os.getenv(.WEBUI_NAME., .G-CAT.)" \
      /app/backend/open_webui/env.py \
    || { echo "FAIL: WEBUI_NAME is not G-CAT"; exit 1; }
  grep -rqs "auth.gcat.ir" /app/build/_app/immutable/chunks/*.js \
    || { echo "FAIL: logout chunk does not point at auth.gcat.ir"; exit 1; }
  echo "OK: branding and logout patch present"
'

echo
echo "Done. Check the site, then commit any upstream-facing changes."
