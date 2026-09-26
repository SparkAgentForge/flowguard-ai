export type SourceReference = {
  fileId: string
  page: number | null
  paragraph: string | null
  quote: string
}

export type SopStep = {
  id: string
  code: string
  sequence: number
  name: string
  required: boolean
  preconditions: string[]
  evidenceRequirements: string[]
  onMissing: string
  sourceRefs: SourceReference[]
}

export type SopVersion = {
  id: string
  sopId: string
  code: string
  name: string
  productCode: string
  version: string
  status: 'DRAFT' | 'AI_EXTRACTED' | 'IN_REVIEW' | 'APPROVED' | 'PUBLISHED'
  sourceDocumentId: string | null
  publishedAt: string | null
  steps: SopStep[]
}

export type SopVersionSummary = Pick<SopVersion, 'id' | 'sopId' | 'code' | 'name' | 'productCode' | 'version' | 'status' | 'publishedAt'>

export type WorkOrder = {
  id: string
  code: string
  productCode: string
  sopVersionId: string
  status: string
  currentAssignee: string | null
  createdAt: string
  updatedAt: string
}

export type VideoAsset = {
  id: string
  workOrderId: string
  reworkTaskId: string | null
  filename: string
  contentType: string
  sha256: string
  createdAt: string
}

export type AuditFinding = {
  id: string
  sopStepId: string
  sequence: number
  stepName: string
  detected: boolean
  confidence: number
  evidenceStatus: 'CONFIRMED' | 'MISSING' | 'MISORDERED' | 'UNCERTAIN' | 'SKIPPED'
  evidenceScore: number
  occluded: boolean
  chunkIdx: number | null
  cvBoundaryScore: number | null
  startSeconds: number | null
  endSeconds: number | null
  evidence: string
  frameTimestamps: number[]
}

export type ReviewRequest = {
  id: string
  stepCode: string
  stepName: string
  startSeconds: number | null
  endSeconds: number | null
  question: string
  reason: string
  status: 'PENDING' | 'CONFIRMED' | 'REJECTED'
  resolvedBy?: string
  resolvedAt?: string
  note?: string | null
}

export type VideoAudit = {
  id: string
  workOrderId: string
  videoId: string
  status: 'COMPLETED' | 'FAILED'
  decision: 'PASS' | 'VIOLATION' | 'INSUFFICIENT_EVIDENCE'
  provider: string
  modelName: string
  overallPass: boolean
  summary: string
  createdAt: string
  completedAt: string
  executionTrace: {
    missingSteps: string[]
    misorderedSteps: string[]
    uncertainSteps: string[]
    trace: { expectedCode: string; observedCode: string | null; status: string; reason: string }[]
    graph: { nodes: unknown[]; edges: unknown[] }
  }
  reviewRequests: ReviewRequest[]
  findings: AuditFinding[]
}

export type ReworkTask = {
  id: string
  exceptionId: string
  workOrderId: string
  assigneeId: string
  instructions: string
  status: 'ASSIGNED' | 'SUBMITTED' | 'IN_REVIEW' | 'APPROVED'
  createdBy: string
  reviewedBy: string | null
  reviewNotes: string | null
  completedAt: string | null
}

export type ExceptionCase = {
  id: string
  workOrderId: string
  workOrderCode: string
  auditId: string
  status: 'PENDING' | 'MANUAL_REVIEW' | 'CONFIRMED' | 'REJECTED' | 'REWORK_ASSIGNED' | 'REWORK_SUBMITTED' | 'REWORK_REVIEW' | 'RESOLVED'
  decision: VideoAudit['decision']
  ruleCode: string
  facts: string[]
  humanReason: string | null
  reviewedBy: string | null
  audit: VideoAudit
  reworkTask: ReworkTask | null
}

export type Report = {
  id: string
  workOrderId: string
  workOrderCode: string
  version: number
  content: {
    schemaVersion: string
    outcome: string
    sop: { code: string | null; name: string | null; version: string | null; sourceDocumentSha256: string | null }
    videos: { id: string; filename: string; sha256: string; kind: string }[]
    audits: { id: string; decision: string; provider: string; model: string; promptVersion: string; summary: string; executionTrace?: VideoAudit['executionTrace']; frameAssetKeys?: string[]; findings: AuditFinding[] }[]
    humanDecision: { status: string; reason: string | null; reviewedBy: string | null } | null
    rework: { taskId: string; assigneeId: string; instructions: string; status: string; reviewedBy: string | null; reviewNotes: string | null } | null
  }
  pdfSha256: string
  archivedAt: string
  createdAt: string
}

export type ReportSummary = {
  id: string
  workOrderId: string
  workOrderCode: string
  productCode: string
  workOrderStatus: string
  version: number
  outcome: string
  archivedAt: string
}

type DocumentRecord = { id: string }

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status = 0,
    readonly code = 'REQUEST_FAILED',
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function defaultErrorMessage(status: number): string {
  if (status === 400) return '请求内容有误，请检查填写内容后重试。'
  if (status === 401 || status === 403) return '当前操作没有权限，请重新登录后重试。'
  if (status === 404) return '找不到对应记录，请刷新页面后重试。'
  if (status === 409) return '数据已发生变化，请刷新页面后重试。'
  if (status === 413) return '文件超过大小限制，请选择更小的文件。'
  if (status === 415) return '文件格式不受支持，请选择 PDF、DOCX 或支持的视频格式。'
  if (status === 422) return '提交内容无法处理，请检查后重试。'
  if (status === 503) return '服务或数据库暂时不可用，请稍后重试。'
  if (status >= 500) return '服务暂时无法完成请求，请稍后重试。'
  return '请求未完成，请稍后重试。'
}

function responseMessage(payload: unknown, status: number): { message: string; code: string } {
  if (payload && typeof payload === 'object') {
    const record = payload as { detail?: unknown; code?: unknown }
    if (typeof record.detail === 'string' && record.detail.trim()) {
      return { message: record.detail, code: typeof record.code === 'string' ? record.code : 'REQUEST_FAILED' }
    }
  }
  return { message: defaultErrorMessage(status), code: 'REQUEST_FAILED' }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/v1${path}`, init)
  } catch {
    throw new ApiError('无法连接后端服务，请确认 API 已启动后重试。', 0, 'NETWORK_ERROR')
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const failure = responseMessage(payload, response.status)
    throw new ApiError(failure.message, response.status, failure.code)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function uploadAndExtractSop(file: File, actorId: string): Promise<SopVersion> {
  const body = new FormData()
  body.append('file', file)
  const document = await request<DocumentRecord>('/documents', { method: 'POST', body })
  return request<SopVersion>(`/documents/${document.id}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actorId }),
  })
}

export function listSops(includeUnpublished = false): Promise<SopVersionSummary[]> {
  return request<SopVersionSummary[]>(`/sop-versions${includeUnpublished ? '?include_unpublished=true' : ''}`)
}

export function readSop(versionId: string): Promise<SopVersion> {
  return request<SopVersion>(`/sop-versions/${versionId}`)
}

export function listWorkOrders(): Promise<WorkOrder[]> {
  return request<WorkOrder[]>('/work-orders')
}

export function listAudits(workOrderId: string): Promise<VideoAudit[]> {
  return request<VideoAudit[]>(`/work-orders/${workOrderId}/audits`)
}

export function listVideos(workOrderId: string): Promise<VideoAsset[]> {
  return request<VideoAsset[]>(`/work-orders/${workOrderId}/videos`)
}

export function videoContentUrl(workOrderId: string, videoId: string): string {
  return `/api/v1/work-orders/${workOrderId}/videos/${videoId}/content`
}

export function createWorkOrder(payload: { code: string; productCode: string; sopVersionId: string }): Promise<WorkOrder> {
  return request<WorkOrder>('/work-orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteWorkOrder(workOrderId: string, actorId: string, confirmation: string): Promise<void> {
  return request<void>(`/work-orders/${workOrderId}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actorId, confirmation }),
  })
}

export async function uploadVideo(workOrderId: string, file: File): Promise<{ id: string; filename: string }> {
  const body = new FormData()
  body.append('file', file)
  return request<{ id: string; filename: string }>(`/work-orders/${workOrderId}/videos`, { method: 'POST', body })
}

export function inspectVideo(workOrderId: string, videoId: string, actorId: string): Promise<VideoAudit> {
  return request<VideoAudit>(`/work-orders/${workOrderId}/inspect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ videoId, actorId }),
  })
}

export function resolveReviewRequest(
  workOrderId: string,
  auditId: string,
  requestId: string,
  decision: 'CONFIRMED' | 'REJECTED',
  actorId: string,
  note?: string,
): Promise<ReviewRequest[]> {
  return request<ReviewRequest[]>(
    `/work-orders/${workOrderId}/audits/${auditId}/review-requests/${requestId}/resolve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, actorId, note }),
    },
  )
}

export function listExceptions(): Promise<ExceptionCase[]> {
  return request<ExceptionCase[]>('/exceptions')
}

export function decideException(exceptionId: string, action: 'confirm' | 'reject', actorId: string, reason: string): Promise<ExceptionCase> {
  return request<ExceptionCase>(`/exceptions/${exceptionId}/${action}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actorId, reason }),
  })
}

export function assignRework(exceptionId: string, actorId: string, assigneeId: string, instructions: string): Promise<ExceptionCase> {
  return request<ExceptionCase>(`/exceptions/${exceptionId}/rework-task`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actorId, assigneeId, instructions }),
  })
}

export async function uploadReworkVideo(taskId: string, file: File): Promise<{ id: string }> {
  const body = new FormData(); body.append('file', file)
  return request<{ id: string }>(`/rework-tasks/${taskId}/videos`, { method: 'POST', body })
}

export function reviewRework(taskId: string, actorId: string, videoId: string, notes: string): Promise<{ task: ReworkTask; audit: VideoAudit; workOrder: WorkOrder }> {
  return request(`/rework-tasks/${taskId}/review`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actorId, videoId, notes }),
  })
}

export function listReports(): Promise<ReportSummary[]> {
  return request<ReportSummary[]>('/reports')
}

export function createOrReadReport(workOrderId: string): Promise<Report> {
  return request<Report>(`/reports/${workOrderId}`)
}

export function updateSop(version: SopVersion, actorId: string): Promise<SopVersion> {
  return request<SopVersion>(`/sop-versions/${version.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      actorId,
      name: version.name,
      productCode: version.productCode,
      steps: version.steps.map((step) => ({
        code: step.code,
        sequence: step.sequence,
        name: step.name,
        required: step.required,
        preconditions: step.preconditions.map((item) => item.trim()).filter(Boolean),
        evidenceRequirements: step.evidenceRequirements.map((item) => item.trim()).filter(Boolean),
        onMissing: step.onMissing,
        sourceRefs: step.sourceRefs,
      })),
    }),
  })
}

export function runSopAction(
  versionId: string,
  action: 'submit-review' | 'approve' | 'publish',
  actorId: string,
): Promise<SopVersion> {
  return request<SopVersion>(`/sop-versions/${versionId}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actorId }),
  })
}
