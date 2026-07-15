# 人事考核系统

FastAPI API + React + TypeScript + Ant Design 的单位内部人事考核系统。数据库支持 SQLite、MySQL 和 PostgreSQL，后端只提供 `/api` JSON 接口，前端位于 `frontend/`。

## 运行要求

- Python 3.11 或 3.12。
- Node.js 20 或 22，npm 10+。
- SQLite 3、MySQL 8.0+ 或 PostgreSQL 13+。
- Docker 部署需要 Docker Engine 24+ 和 Docker Compose v2。

## 后端启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/init_database.py --admin-password 'replace-with-a-strong-password'
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：`/health/live` 检查进程存活，`/health/ready` 检查数据库就绪；`/health` 保留为兼容入口。

## 数据库配置

在项目根目录的 `.env` 中设置 `DATABASE_URL`。只启用下面一种配置：

```dotenv
# SQLite（默认）
DATABASE_URL=sqlite:///data/personnel_eval.db

# MySQL 8.0+
DATABASE_URL=mysql+pymysql://personnel_user:password@127.0.0.1:3306/personnel_eval?charset=utf8mb4

# PostgreSQL 13+
DATABASE_URL=postgresql+psycopg://personnel_user:password@127.0.0.1:5432/personnel_eval
```

数据库名需要先在 MySQL/PostgreSQL 中创建，表结构由 Alembic 版本迁移管理。密码包含 `@`、`:`、`/` 等特殊字符时，必须先进行 URL 编码。

```bash
# 验证连接，不创建表
python scripts/init_database.py --check-only

# 创建表并创建/更新管理员
python scripts/init_database.py \
  --admin-username admin \
  --admin-name 系统管理员 \
  --admin-password 'replace-with-a-strong-password'

# 只创建表
python scripts/init_database.py --skip-admin
```

脚本可重复执行，不会清空已有数据。应用启动时也会确保表存在，但生产环境建议先显式执行初始化脚本。

### Alembic 结构迁移

应用和初始化脚本会自动执行 `alembic upgrade head`。生产发布前仍建议独立执行并确认迁移成功：

```bash
alembic current
alembic history
alembic upgrade head
# 回滚前必须先备份
alembic downgrade -1
```

新增或修改字段时应提交新的迁移文件。`create_all()` 仅用于空数据库初始化兼容，不能替代已有数据库的版本升级。

### 升级已有部署

升级前必须先备份数据库，再更新依赖、迁移结构并构建前端：

```bash
python3 scripts/database_transfer.py backup
pip install -r requirements.txt
alembic upgrade head
cd frontend && npm ci && npm run build && cd ..
# 最后重启 uvicorn、systemd 或 Docker 服务
```

若迁移失败，不要继续启动新版本；应保留错误日志，并使用升级前备份恢复。生产数据库执行 `alembic downgrade` 前也必须验证该迁移确实支持安全回滚。

## 会话与敏感密码

登录使用服务端随机会话令牌，数据库只保存令牌的 SHA-256 摘要。默认会话有效期为 8 小时：

```dotenv
SESSION_COOKIE_NAME=personnel_session
SESSION_MAX_AGE=28800
# 使用 HTTPS 部署时必须设为 true
SESSION_COOKIE_SECURE=false
```

评分详情查看密码使用带随机盐的 PBKDF2 摘要。交互式生成新摘要：

```bash
python3 scripts/hash_password.py
```

将输出结果写入 `.env` 的 `SCORE_DETAIL_PASSWORD_HASH`，然后重启服务。不再支持 `SCORE_DETAIL_PASSWORD_MD5`。

新建人员默认密码为 `password!`，首次登录必须修改。管理员重置密码会撤销该人员现有会话，并要求下次登录先修改密码。生产环境初始化管理员时仍应设置独立强密码。

## 日志与请求追踪

后端默认输出 JSON 结构化日志，记录请求方法、路径、状态码、耗时、客户端地址和请求 ID。响应携带 `X-Request-ID`，调用方也可以传入该请求头用于链路追踪。日志不会记录请求体、密码或 Cookie。

```dotenv
LOG_LEVEL=INFO
LOG_JSON=true
```

本地阅读日志时可设置 `LOG_JSON=false` 使用文本格式。

```bash
# 直接运行时，日志输出在当前终端
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Docker 部署
docker compose logs -f --tail=200 app

# systemd 部署
journalctl -u personnel-evaluation -f -n 200
```

项目不直接写入 `logs/*.log`，而是输出到标准输出和标准错误，由 Docker、systemd、Loki 或 ELK 负责持久化与轮转。排查接口错误时，可使用响应头中的 `X-Request-ID` 检索同一次请求。

## 备份、恢复与数据库迁移

数据工具使用带 SHA-256 完整性校验的 gzip 逻辑备份，可跨 SQLite、MySQL 和 PostgreSQL 恢复。活动登录会话不会写入备份。

```bash
# 备份当前 DATABASE_URL，默认输出到 backups/
python3 scripts/database_transfer.py backup

# 恢复到空数据库
python3 scripts/database_transfer.py restore backups/personnel-evaluation-20260714-120000.json.gz

# 覆盖非空目标数据库，必须显式确认
python3 scripts/database_transfer.py restore backup.json.gz --clear-existing
```

跨数据库直接迁移建议通过环境变量传递连接串，避免密码留在 Shell 历史中：

```bash
export SOURCE_DATABASE_URL='sqlite:///data/personnel_eval.db'
export TARGET_DATABASE_URL='postgresql+psycopg://user:password@127.0.0.1:5432/personnel_eval'
python3 scripts/database_transfer.py migrate
```

目标数据库默认必须为空；只有明确使用 `--clear-target` 才会覆盖它。备份包含人员信息和密码摘要，工具会以 `0600` 权限创建文件，仍应将其保存在受控位置。

## 前端启动

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

访问 `http://127.0.0.1:5173`。开发环境下 Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

前端已接入：

- 登录、退出、当前用户。
- 管理端首页。
- 部门、职位、人员、评分选项管理。
- 考核创建、规则配置、任务生成、开放/关闭、提交管理、实时统计、归档与详情。
- 普通用户评分页和提交评分。

## 生产构建

```bash
cd frontend
npm run build
cd ..
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`app.main` 会在 `frontend/dist` 存在时挂载前端构建产物；否则根路径返回 API 启动说明。

因此生产环境只启动 Uvicorn 即可访问前后端；`npm run dev` 仅用于前端开发和热更新，不应作为生产服务运行。

## Docker 部署

Docker 镜像使用多阶段构建：第一阶段构建 React 前端，第二阶段运行 FastAPI 并直接提供前端静态资源。同一镜像支持 SQLite、MySQL 和 PostgreSQL。

首次部署先准备环境变量，必须修改初始管理员密码：

```bash
cp .env.docker.example .env.docker
```

### SQLite（默认）

```bash
docker compose --env-file .env.docker up -d --build
```

SQLite 数据通过 `./data:/app/data` 挂载保存在项目的 `data/` 目录，备份和迁移前应确认该目录所在磁盘有足够空间。

### MySQL 8

在 `.env.docker` 中取消 MySQL `DOCKER_DATABASE_URL` 的注释，并使 URL 中的用户名、密码、数据库名与 `MYSQL_*` 配置一致，然后运行：

```bash
docker compose --env-file .env.docker \
  -f compose.yml -f compose.mysql.yml \
  up -d --build
```

### PostgreSQL 16

在 `.env.docker` 中取消 PostgreSQL `DOCKER_DATABASE_URL` 的注释，并使 URL 中的配置与 `POSTGRES_*` 一致，然后运行：

```bash
docker compose --env-file .env.docker \
  -f compose.yml -f compose.postgres.yml \
  up -d --build
```

容器启动时会等待数据库就绪、执行 Alembic 迁移并初始化空库。`INITIAL_ADMIN_PASSWORD` 只用于管理员不存在时创建账号，容器重启不会重置已有管理员密码。

```bash
# 查看运行状态和日志
docker compose ps
docker compose logs -f app

# 停止服务，保留数据卷
docker compose down
```

访问 `http://127.0.0.1:8000`。MySQL/PostgreSQL 部署不要在需要保留数据时执行 `docker compose down -v`，该命令会删除数据库命名卷；默认 SQLite 使用 `./data` 目录挂载，不由 `-v` 删除，但仍应单独备份。数据库密码包含特殊字符时，连接 URL 中的密码必须进行 URL 编码。

## 生产安全清单

- 修改 `INITIAL_ADMIN_PASSWORD`，不要在生产环境继续使用 `password!`。
- 使用 `scripts/hash_password.py` 生成独立的 `SCORE_DETAIL_PASSWORD_HASH`。
- 通过 HTTPS 提供服务，并设置 `SESSION_COOKIE_SECURE=true`。
- 限制数据库端口只允许应用服务器访问，不要暴露 SQLite 文件或备份目录。
- 将 `.env`、`.env.docker`、数据库备份和日志平台权限限定给运维人员。
- 发布前执行数据库备份、`alembic upgrade head`、后端测试和前端生产构建。
- 定期验证 `/health/ready`、磁盘空间、备份可恢复性和异常日志告警。

## SQLite 数据查看

```bash
sqlite_web data/personnel_eval.db
```

`sqlite-web` 仅用于 SQLite，MySQL/PostgreSQL 请使用各自的管理工具。

## 测试

```bash
python3 -m pytest -q
cd frontend
npm run build
```
