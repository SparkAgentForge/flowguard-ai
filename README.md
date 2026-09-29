# FlowGuard AI

FlowGuard AI 是面向固定装配工位的质量审计系统：把已发布的 SOP 绑定到工作单，上传装配视频，保存逐步证据，发现漏装或证据不足后进入人工确认、返工、复核和报告归档。

## 当前能力

- SOP：上传 PDF/DOCX，解析操作手册生成候选步骤和原文引用，人工修改、审核和发布版本。
- 视频审计：上传本地视频，使用 Mock、Step 5 或 DeepStream 适配器生成步骤时间线、证据状态和 chunk 追踪。
- 执行图判定：把模型观察对齐到已发布 SOP，区分通过、流程违规和证据不足，并为遮挡片段生成定向复核请求。
- 异常闭环：确认/驳回异常，派发返工任务，上传返工视频，按同一 SOP 复核并放行。
- 证据归档：从数据库事实生成结构化 JSON 和 PDF，固定报告版本与 PDF SHA256。

系统只在已发布 SOP 上执行检测；低置信度或遮挡画面进入人工复核，不自动认定操作员责任。

## 快速启动

复制配置并启动完整容器环境：

```bash
cp .env.example .env
docker compose up --build
```

访问：

- Web 工作台：`http://localhost:8888`
- AI 结果展示页：`http://localhost:9000`
- API：`http://localhost:8000`
- OpenAPI：`http://localhost:8000/api/docs`
- 接口文档：[API.md](docs/API.md)
- PostgreSQL：`localhost:15432`（仅本机或 SSH 隧道）
- RustFS S3 API：`http://localhost:19000`（仅本机或 SSH 隧道）
- RustFS 控制台：`http://localhost:19001`（仅本机或 SSH 隧道）

上述地址使用宿主机端口。容器内 PostgreSQL 仍为 `postgres:5432`，RustFS
仍为 `rustfs:9000`，两个前端容器仍监听 `80`。云节点公网端口与这些端口的
对应关系见文末。Vite 开发和预览默认使用 `8888` / `9000`，与 Compose 前端
不能同时占用相同端口；端口冲突时明确报错，不自动切换端口。

API 容器启动时会自动执行 `alembic upgrade head`。默认使用 Mock 推理，不需要 GPU 或 StepFun 密钥。

## 本地开发

使用 `stepfun` 或 `deepstream` 视频推理前，本机必须安装完整的 FFmpeg（同时包含
`ffmpeg` 和 `ffprobe`）。当前 Python 环境缺少或无法加载这两个工具时，页面会提示
“FFmpeg/ffprobe 安装不完整”。请由环境维护者按本机方式安装，例如 macOS 可执行
`brew install ffmpeg`，Conda 环境可执行 `conda install -n flowguard-ai -c conda-forge ffmpeg`。
安装到非默认位置时，在 `.env` 中设置 `FLOWGUARD_FFMPEG_BINARY` 和
`FLOWGUARD_FFPROBE_BINARY` 的绝对路径。Mock 推理不需要 FFmpeg。

后端：

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
uvicorn flowguard_api.application:app --reload
# 或直接执行启动类
python -m flowguard_api.application
```

前端：

```bash
cd apps/web
npm ci
npm run dev
```

展示型 Agent UI：

```bash
cd apps/agent-web
npm ci
npm run dev
```

展示页使用独立 URL，不带管理工作台导航。AI 根据审计结果返回
`FLOWGUARD_AGENT_WEB_URL/audit/{work_order_id}/{audit_id}`、
`/exception/{exception_id}`、`/sop/{version_id}` 或
`/report/{work_order_id}`。默认不启用鉴权；如需在异常页执行确认和返工操作，
构建展示前端时设置 `VITE_AGENT_REVIEWER_ID`。

## 验收命令

```bash
cd apps/api
export FLOWGUARD_TEST_DATABASE_URL=postgresql+pg8000://flowguard:flowguard@localhost:15432/flowguard_test
python -m pytest -q
python -m ruff check src tests

cd ../web
npm run build
npm run lint

cd ../..
python scripts/integration_smoke.py
```

完整演示路径：上传并发布 SOP → 创建工作单 → 上传视频 → 开始视频审计 → 查看执行轨迹和复核请求 → 异常确认 → 派发返工 → 上传返工视频 → 复核放行 → 生成 PDF 报告。

删除未放行工单时，`DELETE /api/v1/work-orders/{work_order_id}` 会同时清理其原始及返工视频、浏览器预览、Step 5 帧和 PDF 报告对象；未写入审计记录但位于工单专属前缀下的中间文件也会清理。可能由其他工单复用的 SOP 与来源手册保留。已放行或归档的工单不能删除。

## 配置重点

`FLOWGUARD_DATABASE_URL` 为必填 PostgreSQL 配置，缺失或为空时启动会报错。自动化测试也使用独立的 PostgreSQL 测试库 `flowguard_test`，运行前创建该库并设置 `FLOWGUARD_TEST_DATABASE_URL`；测试会重置该库的 `public` schema，绝不能指向业务数据库。缺少测试库时 pytest 会直接拒绝运行。

`.env.example` 包含数据库、RustFS、上传目录、视频大小、抽帧频率、人工复核阈值、API 监听地址、Step 5 和 DeepStream 配置。`FLOWGUARD_API_HOST` 与 `FLOWGUARD_API_PORT` 会同时作用于直接启动和 Docker Compose 启动；默认 API 地址仍为 `http://localhost:8000`。Step 5 视频默认使用独立的 `FLOWGUARD_STEPFUN_FRAME_INTERVAL_SECONDS=1` 与 `FLOWGUARD_STEPFUN_MAX_VIDEO_FRAMES=20`，避免长视频一次请求发送过多图片触发上游限制。默认 `FLOWGUARD_SOP_EXTRACTOR_PROVIDER=stepfun` 会把 PDF 手册逐页转 PNG、写入 RustFS，再以 Base64 data URL 发给 Step 5 视觉解析；DOCX 仍由本地规则解析。`rule_based` 只支持 DOCX，不对 PDF 做文本层抽取。将 `FLOWGUARD_INFERENCE_PROVIDER` 改为 `stepfun` 并设置 `FLOWGUARD_STEPFUN_API_KEY` 后，视频适配器会把抽出的 JPEG 帧写入 RustFS，再以 Base64 data URL 作为 `image_url` 发送给 Step 5；改为 `deepstream` 时只调用官方 `sop-inference-bp` 的 `/v1/files` 和 `/v1/chat/completions`，执行图仍由 FlowGuard 判定。无 GPU、RustFS 或 API Key 的本地演示请保持视频推理的 `mock`。

## 项目结构

```text
apps/api/       FastAPI、SQLAlchemy、Alembic、推理和业务闭环
apps/web/       React + TypeScript 工业质量工作台
apps/agent-web/ React + TypeScript 独立结果展示前端
docs/           需求、检测场景和技术架构
compose.yaml    API、Web、PostgreSQL、RustFS 本地部署
scripts/        集成冒烟检查
```

API 内部按依赖方向分层：`application.py` 负责应用装配，`core/` 定义 AI 与对象存储契约，`infrastructure/` 提供数据库、RustFS、Step 5、DeepStream 和 Mock 的具体适配器，`services/` 只编排业务规则，`routes/` 只负责 HTTP 接口。

## 约束

FlowGuard AI 用于质量辅助和流程审计，不替代最终安全认证；不控制 PLC 或生产线，不识别人脸或身份，不根据视频估算无法直接观察的物理参数。高风险异常必须经过人工决定。

项目采用 Apache License 2.0。

## 云节点端口与公网访问

云节点网关把两个公网业务端口分别转发到节点的 `8888` 和 `9000`。
以分配的公网端口 `8021` / `9021` 为例：

| 服务 | 浏览器公网入口 | 节点宿主机监听 | 容器内端口 |
| --- | --- | --- | --- |
| 管理工作台 | `http://<公网IP>:8021` | `0.0.0.0:8888` | `web:80` |
| AI 结果展示页 | `http://<公网IP>:9021` | `0.0.0.0:9000` | `agent-web:80` |
| PostgreSQL | 无，使用 SSH 隧道 | `127.0.0.1:15432` | `postgres:5432` |
| RustFS S3 API | 无，使用 SSH 隧道 | `127.0.0.1:19000` | `rustfs:9000` |
| RustFS 控制台 | 无，使用 SSH 隧道 | `127.0.0.1:19001` | `rustfs:9001` |

`8021` 和 `9021` 是网关端口，不是 Compose 应绑定的宿主机端口。
`FLOWGUARD_WEB_PORT=8888`、`FLOWGUARD_AGENT_WEB_PORT=9000` 控制 Compose
的宿主机绑定；两个前端通过同源 `/api` 代理访问 `api:8000`，浏览器无需访问
后端的独立端口。

本地 `.env.example` 中的结果地址为 `http://localhost:9000`。远程部署时将
`FLOWGUARD_AGENT_WEB_URL` 改为 `http://<实际公网IP>:9021`，供 Skill 返回可访问的
结果链接；该变量不改变服务监听端口。其他节点使用其实际分配的公网端口。

需要从本机连接数据库或管理对象存储时，建立 SSH 隧道：

```bash
ssh -p <SSH端口> \
  -L 15432:127.0.0.1:15432 \
  -L 19000:127.0.0.1:19000 \
  -L 19001:127.0.0.1:19001 <用户名>@<公网IP>
```

Step 5 图片使用 Base64 data URL，网页视频和证据由 API 同源流式返回，均无需
RustFS 公网入口。直接运行后端时，对象存储地址使用 `http://localhost:19000`；
Compose 自动使用内部地址 `http://rustfs:9000`。`FLOWGUARD_OBJECT_STORAGE_PUBLIC_ENDPOINT`
仅用于显式请求预签名链接的调用方，不能填成展示页占用的公网 `9021` 地址。

端口映射不提供鉴权；当前展示前端未实现登录，公网部署须按所在环境要求配置访问控制。
