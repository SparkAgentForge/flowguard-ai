# FlowGuard AI API 文档

> API 版本：`0.1.0`
>
> 基础路径：`/api/v1`
>
> 文档依据：当前 FastAPI 路由、Pydantic Schema 与 OpenAPI，共 25 条路径、27 个 HTTP 操作。

## 1. 快速入口

本地开发默认地址：

```text
API Base URL  http://localhost:8000/api/v1
Swagger UI   http://localhost:8000/api/docs
OpenAPI JSON http://localhost:8000/api/openapi.json
```

本文示例使用环境变量表示服务地址：

```bash
BASE_URL=http://localhost:8000
```

PowerShell：

```powershell
$BASE_URL = "http://localhost:8000"
```

## 2. 通用约定

### 2.1 数据格式

- JSON 请求和响应使用 `application/json`。
- 文件上传使用 `multipart/form-data`，文件字段统一叫 `file`。
- JSON 字段统一使用 camelCase，例如 `actorId`、`productCode`、`sopVersionId`。
- 主键是 UUID 字符串，时间是带时区的 ISO 8601 字符串。
- 列表接口当前未实现分页。

### 2.2 认证现状

应用 API 当前没有登录、JWT 或角色权限系统。`actorId`、`assigneeId` 等字段用于记录演示中的操作身份，服务端尚未验证它们是否属于真实用户。

公网演示环境可以在 Nginx 层启用 HTTP Basic Auth。此时所有请求（包括 Swagger 和 API）都需要 Basic Auth：

```bash
curl -u '<用户名>:<密码>' "$BASE_URL/api/v1/health"
```

不要把公网地址、密码或 Token 提交到仓库。Basic Auth 只是比赛演示入口保护，不等于企业级鉴权；HTTP 环境下也不要传输真实敏感数据。

### 2.3 通用错误

业务错误采用 FastAPI 标准结构：

```json
{
  "detail": "当前状态不允许执行该操作"
}
```

| HTTP 状态 | 含义 |
| --- | --- |
| `400` | 空文件或请求内容不合法 |
| `401` | 公网网关要求 Basic Auth；本地应用本身不会返回此状态 |
| `404` | 资源不存在，或资源不属于指定父对象 |
| `409` | 状态冲突、重复编号或违反状态机 |
| `413` | 上传文件超过大小限制 |
| `415` | 文件扩展名不受支持 |
| `422` | JSON 字段校验失败，或视频推理无法完成 |

## 3. 状态与业务规则

### 3.1 SOP 状态

```text
DRAFT -> AI_EXTRACTED -> IN_REVIEW -> APPROVED -> PUBLISHED -> RETIRED
```

- 文档提取完成后接口直接返回 `AI_EXTRACTED`。
- SOP 只有在 `AI_EXTRACTED` 或 `IN_REVIEW` 时允许修改。
- 审核、批准和发布必须按顺序调用，非法跳转返回 `409`。
- `GET /sop-versions` 只返回 `PUBLISHED` 版本。

### 3.2 工单状态

```text
CREATED
  -> INSPECTING
      |-> VERIFIED -> ARCHIVED
      `-> EXCEPTION_PENDING
          |-> MANUAL_REVIEW
          |   |-> EXCEPTION_CONFIRMED
          |   `-> EXCEPTION_REJECTED -> VERIFIED
          |-> EXCEPTION_CONFIRMED
          |   -> REWORK_ASSIGNED
          |   -> REWORK_SUBMITTED
          |   -> REWORK_REVIEW
          |       |-> RELEASED -> ARCHIVED
          |       `-> REWORK_ASSIGNED
          `-> EXCEPTION_REJECTED -> VERIFIED
```

视频检测结论与工单状态：

| 检测结论 | 工单结果 |
| --- | --- |
| `PASS` | `VERIFIED` |
| `VIOLATION` | `EXCEPTION_PENDING` |
| `INSUFFICIENT_EVIDENCE` | `MANUAL_REVIEW` |

报告只能为 `VERIFIED`、`RELEASED` 或 `ARCHIVED` 工单生成。

## 4. 接口总览

### 健康检查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/health` | 检查 API、环境和推理提供方 |

### 文档与 SOP

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/documents` | 上传 PDF/DOCX |
| POST | `/api/v1/documents/{document_id}/extract` | 从文档提取候选 SOP |
| GET | `/api/v1/sop-versions` | 查询已发布 SOP |
| GET | `/api/v1/sop-versions/{version_id}` | 查询 SOP 版本详情 |
| PUT | `/api/v1/sop-versions/{version_id}` | 修改候选 SOP |
| POST | `/api/v1/sop-versions/{version_id}/submit-review` | 提交审核 |
| POST | `/api/v1/sop-versions/{version_id}/approve` | 批准 SOP |
| POST | `/api/v1/sop-versions/{version_id}/publish` | 发布 SOP |

### 工单与视频审计

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/work-orders` | 查询工单列表 |
| POST | `/api/v1/work-orders` | 创建工单 |
| GET | `/api/v1/work-orders/{work_order_id}` | 查询工单和状态事件 |
| POST | `/api/v1/work-orders/{work_order_id}/transitions` | 执行允许的状态转换 |
| POST | `/api/v1/work-orders/{work_order_id}/videos` | 上传原始装配视频 |
| POST | `/api/v1/work-orders/{work_order_id}/inspect` | 检测指定视频 |
| GET | `/api/v1/work-orders/{work_order_id}/audits/{audit_id}` | 查询视频审计结果 |
| GET | `/api/v1/work-orders/{work_order_id}/audits/{audit_id}/review-requests` | 查询主动复核请求 |
| POST | `/api/v1/work-orders/{work_order_id}/audits/{audit_id}/review-requests/{request_id}/resolve` | 确认或驳回复核请求 |

### 异常、返工与通知

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/exceptions` | 查询异常列表 |
| GET | `/api/v1/exceptions/{exception_id}` | 查询异常详情和证据 |
| POST | `/api/v1/exceptions/{exception_id}/confirm` | 人工确认异常 |
| POST | `/api/v1/exceptions/{exception_id}/reject` | 人工驳回异常 |
| POST | `/api/v1/exceptions/{exception_id}/rework-task` | 派发返工任务 |
| POST | `/api/v1/rework-tasks/{task_id}/videos` | 上传返工视频 |
| POST | `/api/v1/rework-tasks/{task_id}/review` | 检测并复核返工视频 |
| GET | `/api/v1/notifications?recipient_id={recipient_id}` | 查询站内通知 |

### 报告归档

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/reports` | 查询归档报告列表 |
| GET | `/api/v1/reports/{work_order_id}` | 获取或首次生成 JSON 报告 |
| GET | `/api/v1/reports/{work_order_id}/pdf` | 获取或首次生成 PDF 报告 |

## 5. 健康检查

### `GET /api/v1/health`

成功响应 `200`：

```json
{
  "status": "ok",
  "service": "flowguard-api",
  "environment": "production",
  "inference_provider": "mock"
}
```

注意：健康检查模型没有使用公共 camelCase 基类，因此这里保留字段名 `inference_provider`。

## 6. 文档与 SOP

### 6.1 上传 SOP 文档

`POST /api/v1/documents`

```bash
curl -X POST "$BASE_URL/api/v1/documents" \
  -F 'file=@./泵体端盖装配.pdf;type=application/pdf'
```

限制：

- 支持 `.pdf`、`.docx`。
- 默认最大 20 MiB。
- 相同 SHA256 的文档重复上传会返回已有记录。

成功响应 `201`：

```json
{
  "id": "document-uuid",
  "filename": "泵体端盖装配.pdf",
  "contentType": "application/pdf",
  "sha256": "64位十六进制摘要",
  "createdAt": "2026-09-23T06:00:00Z"
}
```

### 6.2 提取候选 SOP

`POST /api/v1/documents/{document_id}/extract`

```json
{
  "actorId": "engineer-01"
}
```

成功响应为 `SopVersionDetail`，初始状态是 `AI_EXTRACTED`。设置 `FLOWGUARD_SOP_EXTRACTOR_PROVIDER=stepfun` 后，PDF 会逐页渲染成 PNG，页面图片写入 RustFS，再把带时效的 presigned URL 作为 `image_url` 发送给 Step 5；每个候选步骤必须包含有效页码和原文引用。DOCX 仍用本地规则解析。`rule_based` 模式只支持 DOCX；PDF 不读取文本层，也不会回退到文本解析。候选结果必须人工审核后才能发布。Step 5 模式需要配置 API Key 和 Step 5 可访问的 `FLOWGUARD_OBJECT_STORAGE_PUBLIC_ENDPOINT`。

### 6.3 查询已发布 SOP

`GET /api/v1/sop-versions`

只返回 `PUBLISHED` 版本，按创建时间倒序排列。

### 6.4 查询 SOP 详情

`GET /api/v1/sop-versions/{version_id}`

响应包含按 `sequence` 排序的 `steps` 和完整 `events`。

```json
{
  "id": "version-uuid",
  "sopId": "sop-uuid",
  "code": "PUMP-COVER-ASSEMBLY",
  "name": "泵体端盖装配",
  "productCode": "PUMP-A01",
  "version": "1.0-draft",
  "status": "AI_EXTRACTED",
  "sourceDocumentId": "document-uuid",
  "publishedAt": null,
  "steps": [
    {
      "id": "step-uuid",
      "code": "install_seal",
      "sequence": 2,
      "name": "安装绿色密封圈",
      "required": true,
      "preconditions": ["scan_part"],
      "evidenceRequirements": ["密封圈完全进入槽位"],
      "onMissing": "BLOCK",
      "sourceRefs": [
        {
          "fileId": "document-uuid",
          "page": 1,
          "paragraph": null,
          "quote": "安装绿色密封圈"
        }
      ]
    }
  ],
  "events": []
}
```

### 6.5 修改候选 SOP

`PUT /api/v1/sop-versions/{version_id}`

仅允许 `AI_EXTRACTED`、`IN_REVIEW` 状态。请求会整体替换步骤列表：

```json
{
  "actorId": "engineer-01",
  "name": "泵体端盖装配",
  "productCode": "PUMP-A01",
  "steps": [
    {
      "code": "scan_part",
      "sequence": 1,
      "name": "扫描泵体二维码",
      "required": true,
      "preconditions": [],
      "evidenceRequirements": ["画面中出现扫码动作"],
      "onMissing": "BLOCK",
      "sourceRefs": [
        {
          "fileId": "document-uuid",
          "page": 1,
          "paragraph": null,
          "quote": "扫描泵体二维码"
        }
      ]
    }
  ]
}
```

### 6.6 审核与发布动作

三个接口使用相同请求体：

```json
{
  "actorId": "reviewer-01"
}
```

| 当前状态 | 接口 | 目标状态 |
| --- | --- | --- |
| `AI_EXTRACTED` | `POST /sop-versions/{version_id}/submit-review` | `IN_REVIEW` |
| `IN_REVIEW` | `POST /sop-versions/{version_id}/approve` | `APPROVED` |
| `APPROVED` | `POST /sop-versions/{version_id}/publish` | `PUBLISHED` |

## 7. 工单与视频审计

### 7.1 创建工单

`POST /api/v1/work-orders`

```json
{
  "code": "WO-2026-001",
  "productCode": "PUMP-A01",
  "sopVersionId": "published-version-uuid",
  "currentAssignee": "operator-01"
}
```

成功响应 `201`，初始状态为 `CREATED`。

调用方应传入已发布 SOP 的 ID。当前实现只在数据库层验证 SOP 版本存在，尚未在创建接口中强制检查其状态为 `PUBLISHED`；正式集成不能依赖前端下拉框作为安全门禁。

### 7.2 查询工单

- `GET /api/v1/work-orders`：返回全部工单，按创建时间倒序。
- `GET /api/v1/work-orders/{work_order_id}`：返回工单和状态变更事件 `events`。

### 7.3 通用状态转换

`POST /api/v1/work-orders/{work_order_id}/transitions`

```json
{
  "targetStatus": "INSPECTING",
  "actorId": "operator-01",
  "reason": "开始检测"
}
```

后端会校验状态机，非法跳转返回 `409`。正常业务应优先调用检测、异常和返工接口，让它们自动推动状态；该接口主要用于内部联调或受控管理操作。

### 7.4 上传原始视频

`POST /api/v1/work-orders/{work_order_id}/videos`

```bash
curl -X POST "$BASE_URL/api/v1/work-orders/$WORK_ORDER_ID/videos" \
  -F 'file=@./normal.mp4;type=video/mp4'
```

限制：

- 支持 `.mp4`、`.mov`、`.avi`、`.mkv`、`.webm`。
- 默认最大 500 MiB。
- 同一工单内相同 SHA256 的视频重复上传会返回已有视频。

### 7.5 发起视频检测

`POST /api/v1/work-orders/{work_order_id}/inspect`

```json
{
  "videoId": "video-uuid",
  "actorId": "operator-01"
}
```

前置条件：视频属于该工单，工单为 `CREATED` 或 `INSPECTING`。重复检测同一个已经完成的视频会直接返回已有审计结果。

当 `FLOWGUARD_INFERENCE_PROVIDER=stepfun` 时，API 先用 FFmpeg 抽取关键帧，将 JPEG 写入 RustFS，再把带时效的 presigned URL 作为 `image_url` 发送给 Step 5。RustFS 的内部 endpoint 供 API 写入，`FLOWGUARD_OBJECT_STORAGE_PUBLIC_ENDPOINT` 必须是 Step 5 能访问的地址。

响应示例：

```json
{
  "id": "audit-uuid",
  "workOrderId": "work-order-uuid",
  "videoId": "video-uuid",
  "status": "COMPLETED",
  "decision": "VIOLATION",
  "provider": "mock",
  "modelName": "deterministic-demo",
  "overallPass": false,
  "summary": "检测到必需步骤缺失",
  "createdAt": "2026-09-23T06:00:00Z",
  "completedAt": "2026-09-23T06:00:00Z",
  "findings": [
    {
      "id": "finding-uuid",
      "sopStepId": "step-uuid",
      "sequence": 2,
      "stepName": "安装绿色密封圈",
      "detected": false,
      "confidence": 92,
      "evidenceStatus": "MISSING",
      "evidenceScore": 92,
      "occluded": false,
      "chunkIdx": null,
      "cvBoundaryScore": null,
      "startSeconds": null,
      "endSeconds": null,
      "evidence": "在预期时间窗口内未观察到该步骤",
      "frameTimestamps": []
    }
  ],
  "executionTrace": {
    "missingSteps": ["install_seal"],
    "misorderedSteps": [],
    "uncertainSteps": [],
    "trace": []
  },
  "reviewRequests": []
}
```

### 7.6 查询审计结果

`GET /api/v1/work-orders/{work_order_id}/audits/{audit_id}`

只有审计记录确实属于指定工单时才返回结果，否则返回 `404`。

### 7.7 Mock 文件名约定

默认推理提供方为 `mock`：

| 文件名 | 结果 |
| --- | --- |
| `normal.mp4` | 所有步骤通过，工单进入 `VERIFIED` |
| `missing-step.mp4` | 第 3 步（绿色密封圈）缺失，工单进入 `EXCEPTION_PENDING` |
| `occluded.mp4` | 低置信度，工单进入 `MANUAL_REVIEW` |
| `rework-normal.mp4` | 返工检测通过，工单进入 `RELEASED` |

## 8. 异常、返工与通知

### 8.1 查询异常

- `GET /api/v1/exceptions`：返回全部异常，按创建时间倒序。
- `GET /api/v1/exceptions/{exception_id}`：返回异常、检测决定、逐步证据和返工任务。

`ExceptionRead` 的关键字段：

```json
{
  "id": "exception-uuid",
  "workOrderId": "work-order-uuid",
  "workOrderCode": "WO-2026-001",
  "auditId": "audit-uuid",
  "status": "PENDING",
  "decision": "VIOLATION",
  "ruleCode": "REQUIRED_STEP_MISSING",
  "facts": ["在预期时间窗口内未观察到安装密封圈"],
  "humanReason": null,
  "reviewedBy": null,
  "reviewedAt": null,
  "audit": {},
  "reworkTask": null
}
```

### 8.2 确认或驳回异常

确认：`POST /api/v1/exceptions/{exception_id}/confirm`

驳回：`POST /api/v1/exceptions/{exception_id}/reject`

请求体相同：

```json
{
  "actorId": "leader-01",
  "reason": "已核对视频证据和 SOP 条款"
}
```

仅 `PENDING`、`MANUAL_REVIEW` 异常允许处理：

- 确认后，异常为 `CONFIRMED`，工单为 `EXCEPTION_CONFIRMED`。
- 驳回后，异常为 `REJECTED`，工单最终回到 `VERIFIED`。

### 8.3 派发返工

`POST /api/v1/exceptions/{exception_id}/rework-task`

仅已确认异常允许派发，且每个异常只能有一个返工任务。

```json
{
  "actorId": "leader-01",
  "assigneeId": "operator-07",
  "instructions": "补装密封圈并重新拍摄完整装配视频"
}
```

成功响应 `201`，同时创建一条 `REWORK_ASSIGNED` 站内通知。

### 8.4 查询通知

`GET /api/v1/notifications?recipient_id=operator-07`

`recipient_id` 是必填查询参数。通知按创建时间倒序返回。

### 8.5 上传返工视频

`POST /api/v1/rework-tasks/{task_id}/videos`

仅 `ASSIGNED` 返工任务允许上传。文件格式和大小限制与原始视频相同。上传成功后：

- 返工任务进入 `SUBMITTED`。
- 异常进入 `REWORK_SUBMITTED`。
- 工单进入 `REWORK_SUBMITTED`。

### 8.6 返工复核

`POST /api/v1/rework-tasks/{task_id}/review`

```json
{
  "actorId": "quality-01",
  "videoId": "rework-video-uuid",
  "notes": "返工视频步骤完整"
}
```

接口会立即执行一次视频检测：

- `PASS`：任务为 `APPROVED`、异常为 `RESOLVED`、工单为 `RELEASED`。
- 非 `PASS`：任务和工单回到 `REWORK_ASSIGNED`，并生成 `REWORK_REJECTED` 通知。

响应包含 `task`、`audit` 和 `workOrder` 三部分。

## 9. 报告归档

### 9.1 查询报告列表

`GET /api/v1/reports`

返回已生成的报告摘要，包括工单编号、产品、工单状态、报告版本、最终结果和归档时间。

### 9.2 获取或生成 JSON 报告

`GET /api/v1/reports/{work_order_id}`

这个 GET 接口在报告不存在时会创建 v1 报告并写入归档；之后重复请求返回同一记录。未完成检测或返工复核的工单返回 `409`。

报告 `content` 包含：

- `schemaVersion`
- `workOrder`
- `sop` 及原始文档 SHA256
- 原始与返工 `videos` 及 SHA256
- `audits`、模型、Prompt 版本和逐步证据
- `humanDecision`
- `rework`
- `outcome`：`VERIFIED` 或 `RELEASED_AFTER_REWORK`

### 9.3 下载 PDF

`GET /api/v1/reports/{work_order_id}/pdf`

响应：

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="flowguard-{工单编号}-v1.pdf"
ETag: {PDF SHA256}
```

PDF 不存在时会先生成报告。PDF 内容来自数据库事实，包括 SOP、视频哈希、检测结果、人工决定和返工记录。

## 10. 完整调用顺序

### 10.1 正常通过

```text
上传文档
  -> 提取 SOP
  -> 修改 SOP（可选）
  -> 提交审核
  -> 批准
  -> 发布
  -> 创建工单
  -> 上传 normal.mp4
  -> 发起检测（PASS / VERIFIED）
  -> 获取 JSON 报告
  -> 下载 PDF
```

### 10.2 漏步、返工和放行

```text
创建工单
  -> 上传 missing-step.mp4
  -> 发起检测（VIOLATION / EXCEPTION_PENDING）
  -> 查询异常
  -> 人工确认
  -> 派发返工
  -> 查询通知
  -> 上传 rework-normal.mp4
  -> 返工复核（PASS / RELEASED）
  -> 获取 JSON 报告
  -> 下载 PDF
```

### 10.3 遮挡处理

```text
上传 occluded.mp4
  -> 发起检测
  -> INSUFFICIENT_EVIDENCE
  -> 工单和异常进入 MANUAL_REVIEW
  -> 人工确认或驳回
```

## 11. 当前限制

- 没有应用级登录、权限或真实用户系统。
- 文档提取使用本地规则解析 PDF/DOCX 的带序号操作条目；复杂版式、扫描件 OCR 和隐含步骤仍需要后续增强或接入 LLM 提取器。
- 视频检测默认是 Mock；Step 5 模式需要 API Key、FFmpeg 和可被 Step 5 访问的 RustFS presigned URL。
- 上传和检测在请求内同步执行，没有后台任务进度接口。
- 列表接口没有分页、筛选或排序参数。
- 创建工单接口尚未强制验证 SOP 状态为 `PUBLISHED`。
- 通用工单转换接口尚未限制为管理员使用。
- 首次读取报告会产生写入副作用。
- 报告数据结构目前用自由字典承载，OpenAPI 不会展开全部内部字段。
- 公网 Basic Auth 由 Nginx 提供，不属于 FastAPI OpenAPI 安全模型。

## 12. 联调建议

1. 优先打开 `/api/docs` 查看当前运行实例的交互式 Schema。
2. 保存每一步响应中的真实 UUID，不要把示例占位符直接用于请求。
3. 严格按状态机调用，收到 `409` 时先查询资源当前状态。
4. Mock 联调使用约定文件名，文件必须非空且扩展名合法。
5. 自动化验收可执行：

```bash
python scripts/integration_smoke.py
```

受 Basic Auth 保护的环境：

```bash
FLOWGUARD_SMOKE_BASE_URL="$BASE_URL" \
FLOWGUARD_SMOKE_USERNAME='<用户名>' \
FLOWGUARD_SMOKE_PASSWORD='<密码>' \
python scripts/integration_smoke.py
```
