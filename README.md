# FlowGuard AI

FlowGuard AI 是面向固定装配工位的质量审计系统：把已发布的 SOP 绑定到工作单，上传装配视频，保存逐步证据，发现漏装或证据不足后进入人工确认、返工、复核和报告归档。

## 当前能力

- SOP：上传 PDF/DOCX，模拟提取步骤，人工修改、审核和发布版本。
- 视频审计：上传本地视频，使用 Mock 或 StepFun 适配器生成步骤时间线、置信度和证据说明。
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
- PostgreSQL：`localhost:5432`
- MinIO 控制台：`http://localhost:9001`

API 容器启动时会自动执行 `alembic upgrade head`。默认使用 Mock 推理，不需要 GPU 或 StepFun 密钥。

## 本地开发

后端：

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
uvicorn flowguard_api.main:app --reload
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

完整演示路径：上传并发布 SOP → 创建工作单 → 上传视频 → 模拟检测 → 异常确认 → 派发返工 → 上传返工视频 → 复核放行 → 生成 PDF 报告。

## 配置重点

`.env.example` 包含数据库、上传目录、视频大小、抽帧频率、人工复核阈值和 StepFun 配置。将 `FLOWGUARD_INFERENCE_PROVIDER` 改为 `stepfun` 并设置 `FLOWGUARD_STEPFUN_API_KEY` 后，视频适配器会调用 StepFun 兼容的 Chat Completions 接口；未配置时请保持 `mock`。

## 项目结构

```text
apps/api/       FastAPI、SQLAlchemy、Alembic、推理和业务闭环
apps/web/       React + TypeScript 工业质量工作台
docs/           需求、检测场景和技术架构
compose.yaml    API、Web、PostgreSQL、MinIO 本地部署
scripts/        集成冒烟检查
```

## 约束

FlowGuard AI 用于质量辅助和流程审计，不替代最终安全认证；不控制 PLC 或生产线，不识别人脸或身份，不根据视频估算无法直接观察的物理参数。高风险异常必须经过人工决定。

项目采用 Apache License 2.0。
