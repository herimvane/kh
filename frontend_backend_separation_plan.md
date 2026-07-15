# 前后端分离改造方案

## 目标

在不改变现有业务功能、数据模型和测试行为的前提下，把当前 FastAPI + Jinja2 整页刷新项目改造为“后端 API 服务 + 独立前端应用”的结构。

核心原则：

- 业务逻辑继续复用 `app/services.py`，避免把评分、任务生成、归档等规则重写到前端。
- 数据库模型继续复用 `app/models.py`，SQLite 默认路径和现有数据兼容逻辑保留。
- 先新增 API，不急于删除 Jinja 页面；改造期间原页面可作为回退入口。
- 每迁移一个页面，都用现有 Web flow 测试和新增 API 测试兜底。

## 当前项目判断

当前项目是传统服务端渲染应用：

- 路由、权限、表单处理、页面渲染主要集中在 `app/main.py`。
- 模板在 `templates/`，静态资源在 `static/`。
- 普通用户评分、后台管理、考核规则、实时统计、归档详情等页面都由 Jinja 渲染。
- 大多数操作通过 `POST form` 后跳转，只有“按职位加载指定评价人”已经返回 JSON。
- 核心业务逻辑已经在 `app/services.py` 中沉淀，适合抽 API 后继续复用。

因此推荐采用渐进式前后端分离，而不是一次性推倒重写。

## 目标架构

建议目录结构：

```text
.
├── app/
│   ├── main.py                 # 应用装配、兼容旧页面、挂载路由
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py             # 当前用户、管理员、数据库依赖
│   │   ├── schemas.py          # Pydantic 请求/响应模型
│   │   ├── auth.py             # 登录、登出、当前用户
│   │   ├── departments.py
│   │   ├── positions.py
│   │   ├── users.py
│   │   ├── score_options.py
│   │   ├── evaluations.py
│   │   └── app_evaluation.py   # 普通用户评分 API
│   ├── models.py
│   ├── services.py
│   ├── database.py
│   └── security.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── api/
│       ├── routes/
│       ├── components/
│       └── main.tsx
├── templates/                  # 过渡期保留，全部迁完后再删除或仅保留兜底页
├── static/                     # 过渡期保留
└── tests/
```

后端仍由 FastAPI 提供：

- `/api/*`：新前端使用的 JSON API。
- `/admin/*`、`/app/*`、`/login`：过渡期保留的旧 Jinja 页面。
- 生产部署时前端可单独由 Nginx/静态服务托管，也可由 FastAPI 挂载前端构建产物。

## 认证与权限方案

项目使用服务端随机会话令牌；浏览器只保存 HttpOnly Cookie，数据库仅保存令牌的 SHA-256 摘要和过期时间。

当前 Cookie 会话接口：

- `POST /api/auth/login`：校验用户名密码，生成高熵随机会话令牌，返回用户信息和默认跳转角色。
- `POST /api/auth/logout`：清除 cookie。
- `GET /api/auth/me`：返回当前登录用户。
- API 统一使用 `require_user_api`、`require_admin_api` 依赖。

为了兼容前端跨域开发：

- 开发环境允许 `http://127.0.0.1:5173` 携带 cookie。
- FastAPI 增加 CORS 配置，`allow_credentials=True`。
- 前端请求统一设置 `credentials: "include"`。

暂不建议一开始改 JWT。当前系统是内网考核系统，cookie 更贴近原有逻辑，迁移风险更低。

## API 设计

### 通用响应

分页接口建议统一返回：

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "total_pages": 1,
    "total": 0,
    "page_size": 10
  }
}
```

操作失败统一返回：

```json
{
  "detail": "错误提示"
}
```

### 基础数据

部门：

- `GET /api/departments`
- `POST /api/departments`
- `PUT /api/departments/{id}`
- `DELETE /api/departments/{id}`
- `GET /api/departments/choices`

职位：

- `GET /api/positions`
- `POST /api/positions`
- `PUT /api/positions/{id}`
- `DELETE /api/positions/{id}`
- `GET /api/positions/{id}/reviewer-users`

人员：

- `GET /api/users?q=&page=`
- `POST /api/users`
- `PUT /api/users/{id}`
- `DELETE /api/users/{id}`

评分选项：

- `GET /api/score-options`
- `POST /api/score-options`
- `PUT /api/score-options/{id}`
- `DELETE /api/score-options/{id}`

这些接口应直接复用当前删除引用检查、排序归一化、密码哈希等逻辑。

### 考核管理

考核列表和基础操作：

- `GET /api/evaluations`
- `POST /api/evaluations`
- `POST /api/evaluations/{id}/copy`
- `DELETE /api/evaluations/{id}`
- `POST /api/evaluations/{id}/generate-tasks`
- `POST /api/evaluations/{id}/toggle-open`
- `POST /api/evaluations/{id}/archive`

考核设置：

- `GET /api/evaluations/{id}/settings`
- `PUT /api/evaluations/{id}/person-options`
- `PUT /api/evaluations/{id}/department-options`
- `GET /api/evaluations/{id}/person-limits`
- `POST /api/evaluations/{id}/person-limits`
- `PUT /api/evaluations/{id}/person-limits/{limit_id}`
- `DELETE /api/evaluations/{id}/person-limits/{limit_id}`
- `GET /api/evaluations/{id}/department-limits`
- `POST /api/evaluations/{id}/department-limits`
- `PUT /api/evaluations/{id}/department-limits/{limit_id}`
- `DELETE /api/evaluations/{id}/department-limits/{limit_id}`

考核规则：

- `GET /api/evaluations/{id}/person-rules`
- `POST /api/evaluations/{id}/person-rules`
- `PUT /api/evaluations/{id}/person-rules/{rule_id}`
- `DELETE /api/evaluations/{id}/person-rules/{rule_id}`
- `GET /api/evaluations/{id}/department-rules`
- `POST /api/evaluations/{id}/department-rules`
- `PUT /api/evaluations/{id}/department-rules/{rule_id}`
- `DELETE /api/evaluations/{id}/department-rules/{rule_id}`
- `GET /api/evaluations/{id}/department-share-rules`
- `POST /api/evaluations/{id}/department-share-rules`
- `PUT /api/evaluations/{id}/department-share-rules/{rule_id}`
- `DELETE /api/evaluations/{id}/department-share-rules/{rule_id}`
- `GET /api/evaluations/{id}/manual-department-scores`
- `POST /api/evaluations/{id}/manual-department-scores`
- `PUT /api/evaluations/{id}/manual-department-scores/{score_id}`
- `DELETE /api/evaluations/{id}/manual-department-scores/{score_id}`

统计、详情、审计：

- `GET /api/evaluations/{id}/live-stats?person_page=&vote_page=`
- `GET /api/evaluations/{id}/review-submissions?q=&page=`
- `POST /api/evaluations/{id}/review-submissions/{reviewer_id}/reopen`
- `POST /api/evaluations/{id}/review-submissions/{reviewer_id}/cancel`
- `GET /api/evaluations/{id}/details?person_page=&vote_page=`
- `GET /api/evaluations/audit?q=&page=`

### 普通用户评分

- `GET /api/app/evaluation`：返回当前开放考核、任务分组、选项、限制、已选评分、是否可提交。
- `POST /api/app/evaluation/submit`：提交评分，复用 `validate_vote_payload` 和 `submit_votes`。
- `POST /api/app/password`：修改密码。

前端评分页仍保持现有行为：

- 未开放不允许提交。
- 已提交且未允许修改时不允许重复提交。
- 提交前必须完成所有任务。
- 前端只显示评分选项名称，不显示分值。
- 一键选择和超限标红在前端做体验增强，最终以后端校验为准。

## 后端改造步骤

### 第 1 阶段：拆出 API 基础设施

1. 新建 `app/api/deps.py`，把 `current_user`、`require_user`、`require_admin` 抽成 API 可复用依赖。
2. 新建 `app/api/schemas.py`，定义 Pydantic 输入输出模型。
3. 新建 `app/api/auth.py`，提供登录、登出、当前用户接口。
4. 在 `app/main.py` 中注册 `api_router`，旧页面路由暂不移动。
5. 增加 API 测试：登录、未登录 401、普通用户访问管理员 API 403。

验收标准：

- 原有 `PYTHONPATH=. pytest -q` 继续通过。
- 旧页面仍可正常登录和操作。
- `/api/auth/me` 能返回当前用户。

### 第 2 阶段：抽基础数据 API

迁移部门、职位、人员、评分选项接口。

注意点：

- 删除接口必须复用当前“已引用不可删除”的规则。
- 排序逻辑继续复用 `normalize_sort_orders`、`reserve_sort_order`、`apply_sort_order`。
- 人员接口保留分页每页 10 人。
- 人员密码为空时不修改密码，新增人员默认密码规则保持一致。

验收标准：

- 基础数据 API 覆盖增删改查和引用删除失败。
- 旧 Jinja 页面继续可用。

### 第 3 阶段：抽考核配置 API

迁移考核、评分选项绑定、人员限制、部门限制、人员规则、部门规则、部门得分占比、手动部门得分。

注意点：

- 已归档考核的修改阻断逻辑要从 middleware 提炼成 API 依赖/函数，例如 `ensure_evaluation_editable`。
- 指定评价人的校验继续复用 `selected_reviewer_user_id` 逻辑。
- 部门规则多选拆分、多部门树选择摘要等页面展示逻辑可转为前端处理，后端只返回结构化数据。
- 复制考核只复制配置，不复制任务、评分、归档结果。

验收标准：

- 能通过 API 完整创建一个考核配置。
- 生成任务数量与旧页面逻辑一致。
- 现有服务层测试继续通过。

### 第 4 阶段：抽评分和统计 API

迁移普通用户评分、实时统计、提交管理、归档详情、审计。

注意点：

- `GET /api/app/evaluation` 要返回接近当前 `task_groups` 的结构，减少前端重新理解业务。
- 评分提交 payload 建议使用 `{ "choices": { "task_id": "option_id" } }`。
- 实时统计和归档详情继续复用 `calculate_evaluation_scores`、`archive_evaluation`。
- 提交管理的 reopen/cancel 操作后不再依赖 URL 跳回分页，而由前端保留列表筛选状态。

验收标准：

- API 测试覆盖管理员配置到用户提交再归档的主流程。
- API 统计结果与旧页面归档结果一致。

### 第 5 阶段：建立独立前端

推荐技术栈：

- Vite + React + TypeScript。
- UI 自建轻量组件，继续满足内网离线要求。
- 图标可使用本地 SVG 或打包进前端，不依赖 CDN。

页面迁移顺序：

1. 登录页和布局框架。
2. 普通用户评分页。
3. 人员管理、部门管理、职位管理、评分选项。
4. 考核列表和考核设置。
5. 实时统计、评分提交管理、考核详情、操作审计。

优先迁普通用户评分页，是因为它业务闭环最关键，且前端交互已经集中在 `static/app.js`，便于对照还原。

### 第 6 阶段：切换入口并清理旧页面

所有前端页面完成后：

1. `/` 改为返回前端应用入口或跳转前端地址。
2. 保留 `/api/*` 为唯一业务接口。
3. `templates/` 和 `static/app.js` 进入冻结期。
4. 稳定运行后再删除旧 Jinja 页面。

如果系统部署在内网单机，可以让 FastAPI 挂载 `frontend/dist`：

```python
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend" / "dist", html=True), name="frontend")
```

注意要避免覆盖 `/api/*`、`/static/*` 等后端路径。

## 前端状态设计

建议前端按业务域拆分：

- `authStore`：当前用户、登录状态。
- `admin/evaluations`：考核列表、配置详情、规则表单状态。
- `admin/masterData`：部门、职位、人员、评分选项。
- `app/evaluation`：当前任务、评分选择、完成度、限制统计。

前端不保存业务计算结果，只保存展示和表单状态。分数计算、归档、提交校验全部以后端为准。

## 兼容与风险控制

主要风险：

- `app/main.py` 中页面路由和业务处理混在一起，直接迁移容易漏逻辑。
- Jinja 模板里有不少展示派生字段，API 需要显式返回。
- 表单 POST 依赖 redirect + flash，API 需要改成状态码和 JSON 错误。
- 归档考核禁止修改的逻辑目前在 middleware 中按 URL 判断，API 化后需要结构化权限检查。

控制方式：

- 每抽一个模块，先补 API 测试，再接前端。
- 旧页面和新 API 并行一段时间。
- 服务层函数只做小幅封装，不重写业务规则。
- 复杂页面先让 API 返回“前端直接可渲染”的聚合数据，后续再细化。

## 测试方案

后端测试：

- 保留现有 `tests/test_services.py` 和 `tests/test_web_flow.py`。
- 新增 `tests/test_api_auth.py`。
- 新增 `tests/test_api_master_data.py`。
- 新增 `tests/test_api_evaluation_flow.py`，覆盖管理员配置、生成任务、开放、用户提交、重新修改、统计、归档。

前端测试：

- 对普通用户评分页做浏览器测试：未完成禁用提交、一键选择、超限标红、提交成功。
- 对管理员主流程做浏览器测试：创建基础数据、配置考核、生成任务、开放、归档。

每阶段验收命令：

```bash
PYTHONPATH=. pytest -q
```

前端完成后增加：

```bash
cd frontend
npm run build
npm run test
```

## 推荐实施顺序

1. 保留旧页面，新增 `/api/auth/*` 和 API 依赖。
2. 抽基础数据 API。
3. 抽考核配置 API。
4. 抽普通用户评分 API。
5. 抽统计、提交管理、详情、审计 API。
6. 创建 `frontend/`，先实现登录和普通用户评分页。
7. 迁移管理员基础数据页。
8. 迁移考核管理全流程。
9. 切换默认入口到前端应用。
10. 观察稳定后删除或归档旧 Jinja 模板。

## 不建议的做法

- 不建议直接删除 `templates/` 后重写前端，风险太高。
- 不建议把分数计算、限制校验搬到前端，容易产生口径不一致。
- 不建议第一步就换 JWT 或复杂权限系统，会扩大改造范围。
- 不建议同步引入 Alembic、PostgreSQL、权限模型重构等额外目标；这些应作为前后端分离完成后的独立演进。
