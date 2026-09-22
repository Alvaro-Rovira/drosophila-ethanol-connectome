#!/usr/bin/env bash
# Local server for development and captures (test token in tmp/local-secrets).
#   MOSCA_DEBUG=1 ./scripts/serve_local.sh   -> enables ?debug_a=&debug_r=&seed=&debug_puddles=1
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
if [ ! -f tmp/local-secrets/tokens.yaml ]; then
  mkdir -p tmp/local-secrets && chmod 700 tmp/local-secrets
  uv run python -c "import secrets; open('tmp/local-secrets/tokens.yaml','w').write('prueba: %s\n' % secrets.token_urlsafe(24)); open('tmp/local-secrets/hmac.key','w').write(secrets.token_urlsafe(32))"
  chmod 600 tmp/local-secrets/*
fi
export MOSCA_TOKENS=tmp/local-secrets/tokens.yaml
export MOSCA_HMAC_KEY_FILE=tmp/local-secrets/hmac.key
export MOSCA_HOST=127.0.0.1 MOSCA_PORT="${MOSCA_PORT:-8765}"
echo "Abre: http://127.0.0.1:$MOSCA_PORT/?k=$(cut -d' ' -f2 tmp/local-secrets/tokens.yaml | head -1)"
export PYTHONPATH="$PWD/src"
exec uv run python -m mosca.server
