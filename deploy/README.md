# 生产部署指南

## 1. 拓扑

```
用户浏览器
   │ HTTPS 443
   ▼
前端服务器（AnolisOS 8.4）Nginx
   ├── /            -> Vue 静态文件 /usr/share/nginx/finance-web
   └── /api/        -> 后端服务器私网 IP:80（Nginx）
                         │
                         ▼
                    后端服务器（Ubuntu 24.04）
                    Nginx 80 -> Gunicorn 127.0.0.1:8000
                    ├── Django/DRF
                    ├── MySQL 8（127.0.0.1:3306）
                    └── APScheduler（systemd 独立进程）
```

- 浏览器只访问前端域名，`/api/` 由前端 Nginx 反代，**不产生跨域**，JWT 不需要 CORS。
- 后端只开放 HTTP 80 给前端服务器私网 IP；MySQL 只监听 `127.0.0.1`。
- 如果前端 Nginx 无法代理、必须直连后端公网 API，则需要配置 `CORS_ALLOWED_ORIGINS`、`CSRF_TRUSTED_ORIGINS` 和 HTTPS。

## 2. 后端服务器（Ubuntu 24.04）

### 2.1 系统依赖

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip \
  mysql-server nginx build-essential libffi-dev libssl-dev \
  curl git rsync
sudo systemctl enable --now mysql nginx
```

### 2.2 MySQL 8

```bash
sudo mysql < deploy/backend/create_mysql.sql
# 或手动执行 create_mysql.sql，先替换 CHANGE_ME
```

建议额外创建只读备份账号，并配置 `/etc/finance/backup.cnf`（权限 600）。MySQL 只监听 `127.0.0.1`，不要暴露公网。

### 2.3 代码与虚拟环境

```bash
sudo useradd --system --create-home --shell /bin/bash finance
sudo mkdir -p /opt/finance
sudo chown -R finance:finance /opt/finance

# 将仓库放到 /opt/finance（git clone 或 rsync）
sudo -u finance -H bash
cd /opt/finance
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 2.4 环境变量

```bash
cp deploy/backend/.env.production.example backend/.env
chmod 600 backend/.env
# 编辑 backend/.env：
#  - SECRET_KEY: python -c "import secrets; print(secrets.token_urlsafe(50))"
#  - DB_PASSWORD: 与 create_mysql.sql 一致
#  - AI_ENCRYPTION_KEY: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#  - ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS / CORS_ALLOWED_ORIGINS 替换真实域名
```

### 2.5 初始化

```bash
cd /opt/finance/backend
source ../venv/bin/activate
python manage.py migrate
python manage.py seed_system_data
python manage.py seed_demo          # 可选，仅演示环境
python manage.py collectstatic --noinput
python manage.py check --deploy
```

生产环境不要保留演示账号密码，登录后立即修改；如需干净环境，跳过 `seed_demo` 并只创建管理员：

```bash
python manage.py createsuperuser
```

### 2.6 Gunicorn 与 systemd

```bash
sudo cp deploy/backend/finance-api.service /etc/systemd/system/
sudo cp deploy/backend/finance-scheduler.service /etc/systemd/system/
# 如果代码不在 /opt/finance/backend，请同步修改两个 service 文件中的路径
sudo systemctl daemon-reload
sudo systemctl enable --now finance-api finance-scheduler
sudo systemctl status finance-api --no-pager
curl -s http://127.0.0.1:8000/api/v1/health
```

- Gunicorn 使用 `gthread`，超时 300 秒，适配 AI 限流重试。
- 调度器必须只运行一个实例（`finance-scheduler`），不要同时手动运行 `run_scheduler`。
- 查看日志：`journalctl -u finance-api -f`、`journalctl -u finance-scheduler -f`。

### 2.7 后端 Nginx

```bash
sudo cp deploy/backend/nginx-api.conf /etc/nginx/sites-available/finance-api
sudo ln -s /etc/nginx/sites-available/finance-api /etc/nginx/sites-enabled/finance-api
sudo nginx -t && sudo systemctl reload nginx
```

把 `server_name api.example.com` 改成真实 API 域名；把前端服务器私网 IP 加入安全组/防火墙，仅允许它访问 80。

前端 Nginx 会把 `X-Forwarded-Proto: https` 传给后端，因此后端可以开启 `SECURE_SSL_REDIRECT=1` 和 HSTS，不会产生循环重定向。后端 Nginx 的 `/health` 探测已固定带上该请求头。如果后端也要直接对公网提供 HTTPS，可在后端 Nginx 上再叠加证书；本项目推荐由前端统一终止 TLS。

## 3. 前端服务器（AnolisOS 8.4）

AnolisOS 8.4 与 RHEL 8 兼容，使用 `dnf`。

### 3.1 安装 Nginx 与 Node.js

```bash
sudo dnf install -y nginx
sudo systemctl enable --now nginx

# Node.js 22（二选一）
# A. 在构建机/本机构建后只上传 dist（推荐，前端服务器无需 Node）
# B. 在前端服务器构建：
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo dnf install -y nodejs
sudo corepack enable
node -v && pnpm -v
```

### 3.2 构建

```bash
cd /opt/finance/frontend
cp .env.production.example .env.production
# 默认 VITE_API_BASE_URL=/api/v1，由 Nginx 反代；如直连后端改为完整 URL
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build
```

### 3.3 部署静态文件

```bash
sudo mkdir -p /usr/share/nginx/finance-web
sudo rsync -a --delete dist/ /usr/share/nginx/finance-web/
sudo chown -R nginx:nginx /usr/share/nginx/finance-web
```

### 3.4 Nginx 站点

```bash
sudo cp deploy/frontend/nginx-web.conf /etc/nginx/conf.d/finance-web.conf
# 修改 server_name、root、BACKEND_PRIVATE_IP、api.example.com
sudo nginx -t && sudo systemctl reload nginx
```

SELinux（AnolisOS 默认启用）需要允许 Nginx 反代和读取站点目录：

```bash
sudo setsebool -P httpd_can_network_connect 1
sudo semanage fcontext -a -t httpd_sys_content_t "/usr/share/nginx/finance-web(/.*)?"
sudo restorecon -Rv /usr/share/nginx/finance-web
```

防火墙：

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 3.5 HTTPS

在前端服务器用 certbot 或云厂商证书：

```bash
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d finance.example.com
```

证书生效后，浏览器访问 `https://finance.example.com`；`/api/` 仍由 Nginx 反代到后端私网 HTTP，`X-Forwarded-Proto: https` 会传给 Django。

## 4. 更新发布

### 后端

```bash
cd /opt/finance
git pull
source venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart finance-api finance-scheduler
curl -fsS http://127.0.0.1:8000/api/v1/health
```

### 前端

```bash
cd /opt/finance/frontend
pnpm install --frozen-lockfile
pnpm build
sudo rsync -a --delete dist/ /usr/share/nginx/finance-web/
sudo chown -R nginx:nginx /usr/share/nginx/finance-web
sudo nginx -t && sudo systemctl reload nginx
```

## 5. 备份与监控

- MySQL 备份：`deploy/backend/backup.sh`，建议 cron 每天执行并同步到异地。
- 健康检查：`GET /api/v1/health` 应返回 `{"status":"ok","database":"ok"}`。
- 日志：`journalctl -u finance-api`、`journalctl -u finance-scheduler`、Nginx access/error log。
- 监控建议：HTTP 5xx、Gunicorn worker 数、MySQL 连接数、磁盘、AI 429 次数。
- 安全：`.env` 权限 600；数据库不对公网开放；后端 80 只允许前端私网 IP；定期 `pip list --outdated` 和系统更新。

## 6. AI（DeepSeek V4.1 Flash / SenseNova）

- Base URL：`https://token.sensenova.cn/v1`
- 模型：`deepseek-flash`
- 建议额外请求体：`{"thinking":{"type":"disabled"}}`
- 该模型默认开启思考模式，思考内容会占用输出 token；关闭 thinking 可减少 TPM 消耗并获得直接回答。
- 服务商 429（RPM/TPM 限流）时，后端会按 `retry_wait_seconds` 自动重试；如果仍失败，请等待配额恢复、在服务商控制台提升配额，或更换一个配额充足的 API Key。
- `max_tokens` 建议 2048；如果只返回 `reasoning_content` 没有 `content`，说明输出预算被思考耗尽，应增大 `max_tokens` 或设置 `thinking=disabled`。
- AI Key 使用 Fernet 加密存储，生产环境务必单独生成 `AI_ENCRYPTION_KEY`，不要与开发环境共用。

## 7. 常见问题

- **前端刷新 404**：Nginx 缺少 `try_files $uri $uri/ /index.html`。
- **登录后接口 401/跨域**：确认 `/api/` 反代目标、`ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS`；同源反代通常不需要 CORS。
- **静态资源 404**：确认 `collectstatic` 已执行，后端 Nginx `alias /opt/finance/backend/staticfiles/` 路径正确。
- **AI 超时**：Gunicorn/Nginx `proxy_read_timeout` 需 ≥ 300s；AI 分析可能因 429 重试等待。
- **SELinux 阻止反代**：执行 `setsebool -P httpd_can_network_connect 1` 并检查审计日志。
