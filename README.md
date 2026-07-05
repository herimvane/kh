# 毕节金融监管分局人事考核系统

FastAPI + Jinja2 + SQLite 的单位内部人事考核系统。界面使用本地 clean 样式和本地 SVG 图标，不依赖 CDN，适合离线内网环境运行。

## 启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/create_admin.py --username admin --password admin123 --name 系统管理员
uvicorn app.main:app --reload
```

访问 `http://127.0.0.1:8000`，管理员账号默认示例为 `admin / admin123`。

## sqlite-web

```bash
sqlite_web data/personnel_eval.db
```

## 离线说明

系统页面只引用 `/static/app.css` 和 `/static/app.js`，图标位于 `templates/icons/`，不需要访问外部 Tailwind、DaisyUI、HTMX 或 Alpine.js CDN。

## 测试

```bash
pytest
```
