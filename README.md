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

- Web 工作台：`http://localhost:5173`
- API：`http://localhost:8000`
- OpenAPI：`http://localhost:8000/api/docs`
- 接口文档：[API.md](API.md)
- PostgreSQL：`localhost:5432`
- RustFS S3 API：`http://localhost:9000`
- RustFS 控制台：`http://localhost:9001`（仅本机或 SSH 隧道）

API 容器启动时会自动执行 `alembic upgrade head`。默认使用 Mock 推理，不需要 GPU 或 StepFun 密钥。

## 本地开发

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

## 验收命令

```bash
cd apps/api
python -m pytest -q
python -m ruff check src tests

cd ../web
npm run build
npm run lint

cd ../..
python scripts/integration_smoke.py
```

完整演示路径：上传并发布 SOP → 创建工作单 → 上传视频 → 开始视频审计 → 查看执行轨迹和复核请求 → 异常确认 → 派发返工 → 上传返工视频 → 复核放行 → 生成 PDF 报告。

## 配置重点

`.env.example` 包含数据库、RustFS、上传目录、视频大小、抽帧频率、人工复核阈值、API 监听地址、Step 5 和 DeepStream 配置。`FLOWGUARD_API_HOST` 与 `FLOWGUARD_API_PORT` 会同时作用于直接启动和 Docker Compose 启动；默认 API 地址仍为 `http://localhost:8000`。默认 `FLOWGUARD_SOP_EXTRACTOR_PROVIDER=stepfun` 会把 PDF 手册逐页转 PNG、写入 RustFS，再以 presigned `image_url` 发给 Step 5 视觉解析；DOCX 仍由本地规则解析。`rule_based` 只支持 DOCX，不对 PDF 做文本层抽取。将 `FLOWGUARD_INFERENCE_PROVIDER` 改为 `stepfun` 并设置 `FLOWGUARD_STEPFUN_API_KEY` 后，视频适配器会把抽出的 JPEG 帧写入 RustFS，再把带时效的 presigned URL 作为 `image_url` 发送给 Step 5；改为 `deepstream` 时只调用官方 `sop-inference-bp` 的 `/v1/files` 和 `/v1/chat/completions`，执行图仍由 FlowGuard 判定。无 GPU、RustFS 或 API Key 的本地演示请保持视频推理的 `mock`。

## 项目结构

```text
apps/api/       FastAPI、SQLAlchemy、Alembic、推理和业务闭环
apps/web/       React + TypeScript 工业质量工作台
docs/           需求、检测场景和技术架构
compose.yaml    API、Web、PostgreSQL、RustFS 本地部署
scripts/        集成冒烟检查
```

API 内部按依赖方向分层：`application.py` 负责应用装配，`core/` 定义 AI 与对象存储契约，`infrastructure/` 提供数据库、RustFS、Step 5、DeepStream 和 Mock 的具体适配器，`services/` 只编排业务规则，`routes/` 只负责 HTTP 接口。

## 约束

FlowGuard AI 用于质量辅助和流程审计，不替代最终安全认证；不控制 PLC 或生产线，不识别人脸或身份，不根据视频估算无法直接观察的物理参数。高风险异常必须经过人工决定。

项目采用 Apache License 2.0。

## DGX Spark 公网访问

Spark 云节点只将节点内的 `9000` 端口映射到公网业务端口，节点编号为 `NN` 时公网端口为 `90NN`。RustFS 的 S3 API 监听 `0.0.0.0:9000`，因此外部文件访问地址为：

```text
http://<组委会提供的公网 IP>:90NN
```

RustFS 控制台 `9001` 没有公网映射，配置为节点本机回环地址；需要管理控制台时通过 SSH 隧道访问：

```bash
ssh -p <SSH端口> -L 9001:localhost:9001 Developer@<公网 IP>
```

公网 S3 API 必须使用非默认的 `RUSTFS_ACCESS_KEY` 和 `RUSTFS_SECRET_KEY`，不要把控制台或无鉴权的文件管理器直接暴露到公网。

Step 5 若运行在容器或远程节点，`FLOWGUARD_OBJECT_STORAGE_PUBLIC_ENDPOINT` 必须填写 Step 5 实际能访问的 RustFS 地址；它与 API 容器内部使用的 `FLOWGUARD_OBJECT_STORAGE_ENDPOINT` 可以不同。
