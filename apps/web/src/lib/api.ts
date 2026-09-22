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

export type AuditFinding = {
  id: string
  sopStepId: string
  sequence: number
  stepName: string
  detected: boolean
  confidence: number
  startSeconds: number | null
  endSeconds: number | null
  evidence: string
  frameTimestamps: number[]
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
    audits: { id: string; decision: string; provider: string; model: string; promptVersion: string; summary: string; findings: AuditFinding[] }[]
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, init)
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(payload?.detail || `请求失败（${response.status}）`)
  }
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

export function listPublishedSops(): Promise<SopVersionSummary[]> {
  return request<SopVersionSummary[]>('/sop-versions')
}

export function listWorkOrders(): Promise<WorkOrder[]> {
  return request<WorkOrder[]>('/work-orders')
}

export function createWorkOrder(payload: { code: string; productCode: string; sopVersionId: string }): Promise<WorkOrder> {
  return request<WorkOrder>('/work-orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
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
        preconditions: step.preconditions,
        evidenceRequirements: step.evidenceRequirements,
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
