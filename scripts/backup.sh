#!/usr/bin/env bash
# ==============================================================================
# Automated Database & State Backup for Academic LLM Chat Assistant
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/chat-assistant/backups}"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

echo "==> [1/3] Dumping PostgreSQL database..."
if docker ps --format '{{.Names}}' | grep -q "^chat-postgres$"; then
    docker exec chat-postgres pg_dump -U "${POSTGRES_USER:-webui_user}" "${POSTGRES_DB:-openwebui}" | gzip > "${BACKUP_DIR}/db_${TIMESTAMP}.sql.gz"
    echo "✓ Database dump created at: ${BACKUP_DIR}/db_${TIMESTAMP}.sql.gz"
else
    echo "⚠️ Warning: chat-postgres container is not running, skipping database dump."
fi

echo "==> [2/3] Archiving WebUI documents and vectors..."
if docker volume inspect llm_chat_ui_webui_data &> /dev/null || docker volume inspect chat-assistant_webui_data &> /dev/null; then
    docker run --rm -v "${PWD}_webui_data:/data:ro" -v "${BACKUP_DIR}:/backup" alpine tar -czf "/backup/data_${TIMESTAMP}.tar.gz" -C /data .
    echo "✓ Data archive created at: ${BACKUP_DIR}/data_${TIMESTAMP}.tar.gz"
fi

echo "==> [3/3] Pruning backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -type f -name "*.tar.gz" -mtime +"${RETENTION_DAYS}" -delete || true
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete || true

echo "✓ Backup routine completed successfully."
