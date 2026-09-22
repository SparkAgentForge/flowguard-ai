# FlowGuard AI

FlowGuard AI 是一个面向固定装配工位的 AI 质量闭环项目，方案工作名为 **SparkSOP**。它根据标准作业程序（SOP）分析装配视频，检查关键步骤是否完整、顺序是否正确，并为异常处理、返工和复核保留可追溯证据。

> 项目当前处于 MVP 开发阶段，已提供前后端基础工程和本地依赖环境。

## 目标场景

项目聚焦于“明确产品、明确 SOP、固定摄像头”的人工装配场景。例如，在泵体端盖装配过程中检查扫码、安装密封圈、安装端盖并锁紧、粘贴质检标签等步骤，及时发现漏装或顺序错误。

## 核心能力

- 将自然语言 SOP 转换为可执行的工序规则
- 从装配视频中提取步骤时间线和关键证据
- 检查步骤完整性、执行顺序和阻断条件
- 对低置信度结果发起人工复核
- 生成异常工单，并跟踪返工和最终放行

## 典型流程

1. 工艺工程师上传并确认 SOP 规则。
2. 操作员提交装配视频。
3. 系统识别操作步骤并校验规则。
4. 正常工单生成完成记录，异常工单进入返工流程。
5. 质检人员复核证据并决定是否放行。

## 项目状态

当前已完成 React 前端、FastAPI 后端健康检查和 PostgreSQL/MinIO 本地依赖编排。业务模块将按可独立验收的提交逐步实现。

## 项目结构

```text
apps/
  api/       FastAPI 后端
  web/       React + TypeScript 前端
docs/        产品需求、检测场景和技术架构
compose.yaml PostgreSQL 与 MinIO 本地环境
```

## 本地开发

启动基础依赖：

```bash
docker compose up -d
```

启动后端：

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell 使用 .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn flowguard_api.main:app --reload
```

启动前端：

```bash
cd apps/web
npm install
npm run dev
```

默认访问地址：

- 前端：`http://localhost:5173`
- 后端健康检查：`http://localhost:8000/api/v1/health`
- 后端接口文档：`http://localhost:8000/api/docs`

## 许可证

本项目采用 [Apache License 2.0](LICENSE) 许可证。
