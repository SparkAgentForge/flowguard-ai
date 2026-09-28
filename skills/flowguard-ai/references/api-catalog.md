# FlowGuard 接口手册

这份目录是 Skill 的操作手册。需要执行用户请求时，先按“入口”和“调用时机”
选择接口，再读取项目 OpenAPI 获取当前请求体和响应字段。不要把 provider 的
接口当成 FlowGuard 的业务接口，也不要跳过状态机直接调用后续接口。

## 基础信息

FlowGuard API 默认基地址：

```text
http://localhost:8000/api/v1
```

OpenAPI：

```text
GET /api/openapi.json
```

当前业务 API：

- 30 个不同 URL 路径；
- 34 个 HTTP 方法操作；
- 所有路径都在 `/api/v1` 下，除 OpenAPI、Swagger 和 Web 页面外。

## Skill 入口

| 入口 | 类型 | 触发方式 | 作用 |
| --- | --- | --- | --- |
| 自然语言 + 视频附件 | Skill 入口 | “检测这个视频是否符合操作规范” | 自动发现或准备 FlowGuard，执行完整审计 |
| `$flowguard-ai` | 显式入口 | 用户明确指定 Skill | 执行同一套视频审计或维护流程 |
| `FLOWGUARD_BASE_URL` | 环境入口 | 已有服务地址 | 优先连接指定 FlowGuard API |
| 项目目录 / Docker Compose | 本地入口 | 在当前目录或父目录发现项目 | 检查并启动项目服务 |

Skill 不是 HTTP 服务，不监听端口。它通过下面的 FlowGuard API 编排业务。

## 最小视频审计链路

| 顺序 | 方法 | 路径 | 调用时机 | 前置条件 |
| ---: | --- | --- | --- | --- |
| 1 | GET | `/health` | 任何业务操作前 | API 地址已知 |
| 2 | GET | `/sop-versions` | 选择操作规范 | 至少一个 `PUBLISHED` SOP |
| 3 | POST | `/work-orders` | 建立本次审计上下文 | 已选择发布版 SOP |
| 4 | POST | `/work-orders/{work_order_id}/videos` | 保存用户视频 | 工单状态允许上传 |
| 5 | POST | `/work-orders/{work_order_id}/inspect` | 启动视频审计 | 视频已上传，工单可检测 |
| 6 | GET | `/work-orders/{work_order_id}/audits` | 请求超时或需要恢复状态 | 已有工单 ID |
| 7 | GET | `/work-orders/{work_order_id}/audits/{audit_id}` | 读取最终详情和证据 | 已有审计 ID |

`inspect` 返回或客户端超时后，如果审计是 `PROCESSING`，只轮询第 6、7 步，
不要重复提交同一个视频。

## 健康检查：1 个操作

| 方法 | 路径 | 用途 | 关键结果 |
| --- | --- | --- | --- |
| GET | `/health` | 检查 API 和推理 provider | `status=ok`，记录 `inference_provider` |

健康接口通过后，还要检查 Docker Compose、PostgreSQL、RustFS 和 Web；健康接口
本身不代表模型凭据或完整视频推理链路一定可用。

## SOP：8 个操作

| 方法 | 路径 | 用途 | 调用条件 |
| --- | --- | --- | --- |
| POST | `/documents` | 上传 PDF/DOCX 操作手册 | 没有可用文档时 |
| POST | `/documents/{document_id}/extract` | 解析手册并生成候选 SOP | 文档上传成功 |
| GET | `/sop-versions` | 查询 SOP | 选择审计规范 |
| GET | `/sop-versions/{version_id}` | 查看 SOP 和步骤 | 已有版本 ID |
| PUT | `/sop-versions/{version_id}` | 修改候选步骤 | 版本尚未发布 |
| POST | `/sop-versions/{version_id}/submit-review` | 提交人工审核 | 候选内容已确认 |
| POST | `/sop-versions/{version_id}/approve` | 审核通过 | 版本处于审核状态 |
| POST | `/sop-versions/{version_id}/publish` | 发布不可变 SOP | 版本已批准 |

SOP 状态顺序：

```text
DRAFT -> AI_EXTRACTED -> IN_REVIEW -> APPROVED -> PUBLISHED
```

没有 `PUBLISHED` SOP 时，不能直接审计视频，也不能从视频内容猜测 SOP。

## 工单：5 个操作

| 方法 | 路径 | 用途 | 调用条件 |
| --- | --- | --- | --- |
| GET | `/work-orders` | 查询工单列表 | 页面初始化或恢复任务 |
| POST | `/work-orders` | 创建工单并绑定 SOP | 已有发布版 SOP |
| GET | `/work-orders/{work_order_id}` | 查看工单和状态事件 | 已有工单 ID |
| DELETE | `/work-orders/{work_order_id}` | 删除工单及关联对象 | 用户明确确认，且工单可删除 |
| POST | `/work-orders/{work_order_id}/transitions` | 执行允许的状态转换 | 需要人工推进状态 |

删除工单会清理该工单关联的视频、审计、证据片段、返工记录和 Step 5 帧对象；
不会删除 PostgreSQL 或 RustFS 数据卷。

## 视频审计：9 个操作

| 方法 | 路径 | 用途 | 调用条件 |
| --- | --- | --- | --- |
| GET | `/work-orders/{work_order_id}/audits` | 查询审计历史 | 已有工单 ID |
| GET | `/work-orders/{work_order_id}/videos` | 查询已上传视频 | 已有工单 ID |
| GET | `/work-orders/{work_order_id}/videos/{video_id}/content` | 播放或下载视频 | 视频属于该工单 |
| POST | `/work-orders/{work_order_id}/videos` | 上传装配视频 | 文件格式和大小符合限制 |
| POST | `/work-orders/{work_order_id}/inspect` | 执行视频审计 | 视频已上传，工单可检测 |
| GET | `/work-orders/{work_order_id}/audits/{audit_id}` | 查询审计详情 | 已有审计 ID |
| GET | `/work-orders/{work_order_id}/audits/{audit_id}/findings/{step_ref}/clip` | 获取确认或候选证据片段 | finding 存在，可选 `kind=confirmed|candidate` |
| GET | `/work-orders/{work_order_id}/audits/{audit_id}/review-requests` | 查询人工复核请求 | 审计已生成复核请求 |
| POST | `/work-orders/{work_order_id}/audits/{audit_id}/review-requests/{request_id}/resolve` | 确认或驳回复核请求 | 请求仍为 `PENDING` |

审计终态：

```text
PROCESSING -> COMPLETED
PROCESSING -> FAILED
```

完成后的业务决策：

| 决策 | 含义 | Skill 后续动作 |
| --- | --- | --- |
| `PASS` | 必需步骤按顺序且有时间证据 | 返回通过结果；按业务需要生成报告 |
| `VIOLATION` | 必需步骤缺失或错序 | 展示异常，等待确认或创建返工 |
| `INSUFFICIENT_EVIDENCE` | 遮挡、低置信度或时间证据不足 | 提供候选片段并请求人工复核 |

## 异常与返工：8 个操作

| 方法 | 路径 | 用途 | 调用条件 |
| --- | --- | --- | --- |
| GET | `/exceptions` | 查询异常列表 | 异常中心初始化 |
| GET | `/exceptions/{exception_id}` | 查看异常详情 | 已有异常 ID |
| POST | `/exceptions/{exception_id}/confirm` | 人工确认异常 | 异常处于待确认状态 |
| POST | `/exceptions/{exception_id}/reject` | 驳回异常 | 人工判断异常不成立 |
| POST | `/exceptions/{exception_id}/rework-task` | 创建返工任务 | 异常已确认 |
| POST | `/rework-tasks/{task_id}/videos` | 上传返工视频 | 返工任务允许提交 |
| POST | `/rework-tasks/{task_id}/review` | 执行返工复核 | 返工视频已提交 |
| GET | `/notifications` | 查询返工通知 | 提供 `recipient_id` |

上传返工视频不等于复核通过。必须调用返工复核接口并读取新的审计结果。

## 报告：3 个操作

| 方法 | 路径 | 用途 | 调用条件 |
| --- | --- | --- | --- |
| GET | `/reports` | 查询归档报告 | 报告中心初始化 |
| GET | `/reports/{work_order_id}` | 获取或生成 JSON 报告 | 工单达到可报告状态 |
| GET | `/reports/{work_order_id}/pdf` | 获取 PDF 报告 | 工单达到可报告状态 |

## 内部推理服务接口

这些不是 Skill 的用户入口，而是 FlowGuard 后端根据 provider 配置调用的服务。

### Step 5

```text
POST {FLOWGUARD_STEPFUN_BASE_URL}/chat/completions
```

FlowGuard 先将页面或视频帧写入 RustFS，再将图片作为 Base64 data URL 发送给
Step 5。Step 5 返回视觉观察，最终决策仍由 FlowGuard 执行图完成。

### 官方 DeepStream SOP

仅当设置：

```text
FLOWGUARD_INFERENCE_PROVIDER=deepstream
```

才使用：

```text
POST /v1/files
POST /v1/chat/completions
```

DeepStream 负责文件接收、GEBD/DDM 分段和 chunk 观察；FlowGuard 负责 SOP 对齐、
缺失/错序判定、人工复核、返工和报告。

## 常见错误处理

| 状态码 | 含义 | Skill 处理 |
| ---: | --- | --- |
| 400 | 空文件或请求非法 | 修正输入后再提交 |
| 404 | 资源不存在或不属于父对象 | 重新查询上级资源，不猜 ID |
| 409 | 状态机不允许操作或已有处理中审计 | 查询当前状态，不重复提交 |
| 413 | 文件太大 | 告知大小限制 |
| 415 | 视频/文档格式不支持 | 告知支持格式 |
| 422 | 推理、媒体或字段校验失败 | 返回脱敏错误并检查服务配置 |
| 500 | 服务内部错误 | 保留审计 ID，检查日志和健康状态 |

完整请求体和响应字段以运行中的 `/api/openapi.json` 为准。
