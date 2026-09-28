export type SopStep = {
  id: string
  code: string
  sequence: number
  name: string
  required: boolean
  preconditions: string[]
  evidenceRequirements: string[]
  onMissing: string
  sourceRefs: { fileId: string; page: number | null; paragraph: string | null; quote: string }[]
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
  startSeconds: number | null
  endSeconds: number | null
  candidateStartSeconds: number | null
  candidateEndSeconds: number | null
  evidence: string
  frameTimestamps: number[]
  candidateFrameTimestamps: number[]
  hasConfirmedClip: boolean
  hasCandidateClip: boolean
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
  resolvedBy?: string | null
  resolvedAt?: string | null
  note?: string | null
}

export type VideoAudit = {
  id: string
  workOrderId: string
  videoId: string
  status: 'PROCESSING' | 'COMPLETED' | 'FAILED'
  decision: 'PASS' | 'VIOLATION' | 'INSUFFICIENT_EVIDENCE'
  provider: string
  modelName: string
  overallPass: boolean
  summary: string
  createdAt: string
  completedAt: string | null
  executionTrace: {
    missingSteps: string[]
    misorderedSteps: string[]
    uncertainSteps: string[]
    trace: { expectedCode: string; observedCode: string | null; status: string; reason: string }[]
  }
  reviewRequests: ReviewRequest[]
  findings: AuditFinding[]
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
  pdfSha256: string
  archivedAt: string
  createdAt: string
  content: {
    outcome: string
    sop: { code: string | null; name: string | null; version: string | null; sourceDocumentSha256: string | null }
    videos: { id: string; filename: string; sha256: string; kind: string }[]
    audits: { id: string; decision: string; provider: string; model: string; promptVersion: string; summary: string; findings: AuditFinding[] }[]
    humanDecision: { status: string; reason: string | null; reviewedBy: string | null } | null
    rework: { taskId: string; assigneeId: string; instructions: string; status: string; reviewedBy: string | null; reviewNotes: string | null } | null
  }
}

export class ApiError extends Error {
  constructor(message: string, readonly status = 0) {
    super(message)
    this.name = 'ApiError'
  }
}

const apiBase = (import.meta.env.VITE_AGENT_API_BASE_URL || '/api/v1').replace(/\/$/, '')
const reviewerId = import.meta.env.VITE_AGENT_REVIEWER_ID || ''

function errorMessage(status: number): string {
  if (status === 404) return '找不到这条记录，链接可能已失效或参数不完整。'
  if (status === 409) return '当前状态不允许这个操作，请刷新页面后再试。'
  if (status === 413) return '视频超过大小限制，请选择更小的文件。'
  if (status === 415) return '文件格式不受支持，请选择常见视频格式。'
  if (status >= 500) return '服务暂时无法完成请求，请稍后重试。'
  return '请求未完成，请检查内容后重试。'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${apiBase}${path}`, init)
  } catch {
    throw new ApiError('无法连接 FlowGuard 服务，请确认服务正在运行。')
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null
    const detail = typeof payload?.detail === 'string' ? payload.detail : errorMessage(response.status)
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function readSop(versionId: string): Promise<SopVersion> {
  return request<SopVersion>(`/sop-versions/${encodeURIComponent(versionId)}`)
}

export function readAudit(workOrderId: string, auditId: string): Promise<VideoAudit> {
  return request<VideoAudit>(`/work-orders/${encodeURIComponent(workOrderId)}/audits/${encodeURIComponent(auditId)}`)
}

export function listAudits(workOrderId: string): Promise<VideoAudit[]> {
  return request<VideoAudit[]>(`/work-orders/${encodeURIComponent(workOrderId)}/audits`)
}

export function listVideos(workOrderId: string): Promise<VideoAsset[]> {
  return request<VideoAsset[]>(`/work-orders/${encodeURIComponent(workOrderId)}/videos`)
}

export function readException(exceptionId: string): Promise<ExceptionCase> {
  return request<ExceptionCase>(`/exceptions/${encodeURIComponent(exceptionId)}`)
}

export function videoContentUrl(workOrderId: string, videoId: string): string {
  return `${apiBase}/work-orders/${encodeURIComponent(workOrderId)}/videos/${encodeURIComponent(videoId)}/content`
}

export function evidenceClipUrl(workOrderId: string, auditId: string, stepCode: string, kind: 'confirmed' | 'candidate'): string {
  return `${apiBase}/work-orders/${encodeURIComponent(workOrderId)}/audits/${encodeURIComponent(auditId)}/findings/${encodeURIComponent(stepCode)}/clip?kind=${kind}`
}

export function reportPdfUrl(workOrderId: string): string {
  return `${apiBase}/reports/${encodeURIComponent(workOrderId)}/pdf`
}

export function readReport(workOrderId: string): Promise<Report> {
  return request<Report>(`/reports/${encodeURIComponent(workOrderId)}`)
}

function requireReviewer(): string {
  if (!reviewerId.trim()) throw new ApiError('当前展示环境没有配置复核人，写操作暂不可用。')
  return reviewerId.trim()
}

export function decideException(exceptionId: string, action: 'confirm' | 'reject', reason: string): Promise<ExceptionCase> {
  return request<ExceptionCase>(`/exceptions/${encodeURIComponent(exceptionId)}/${action}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actorId: requireReviewer(), reason }),
  })
}

export function assignRework(exceptionId: string, assigneeId: string, instructions: string): Promise<ExceptionCase> {
  return request<ExceptionCase>(`/exceptions/${encodeURIComponent(exceptionId)}/rework-task`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actorId: requireReviewer(), assigneeId, instructions }),
  })
}

export async function uploadReworkVideo(taskId: string, file: File): Promise<VideoAsset> {
  const body = new FormData()
  body.append('file', file)
  return request<VideoAsset>(`/rework-tasks/${encodeURIComponent(taskId)}/videos`, { method: 'POST', body })
}

export function reviewRework(taskId: string, videoId: string, notes: string): Promise<{ task: ReworkTask; audit: VideoAudit; workOrder: WorkOrder }> {
  return request(`/rework-tasks/${encodeURIComponent(taskId)}/review`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actorId: requireReviewer(), videoId, notes }),
  })
}
