#!/usr/bin/env bash
set -euo pipefail

# 依赖 /etc/finance/backup.cnf：
# [client]
# user=backup
# password=...
# host=127.0.0.1
BACKUP_DIR="${BACKUP_DIR:-/var/backups/finance}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

install -d -m 700 "$BACKUP_DIR"
mysqldump --defaults-extra-file=/etc/finance/backup.cnf \
  --single-transaction --routines --triggers --events finance \
  | gzip -9 > "$BACKUP_DIR/finance-$STAMP.sql.gz"

find "$BACKUP_DIR" -type f -name 'finance-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "backup written: $BACKUP_DIR/finance-$STAMP.sql.gz"
