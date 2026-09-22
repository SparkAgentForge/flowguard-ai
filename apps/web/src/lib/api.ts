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
