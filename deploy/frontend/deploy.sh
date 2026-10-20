#!/usr/bin/env bash
set -euo pipefail

# 在前端服务器仓库目录执行（AnolisOS 8.4 / RHEL 8 兼容）
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB_ROOT="${WEB_ROOT:-/usr/share/nginx/finance-web}"

cd "$ROOT/frontend"
corepack enable
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build

install -d -m 755 "$WEB_ROOT"
rsync -a --delete "$ROOT/frontend/dist/" "$WEB_ROOT/"
chown -R nginx:nginx "$WEB_ROOT" 2>/dev/null || true

sudo nginx -t
sudo systemctl reload nginx
echo "frontend deployed to $WEB_ROOT"
