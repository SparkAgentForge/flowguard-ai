import type { AuditFinding, VideoAudit } from './api'

export const workOrderStatusLabels: Record<string, string> = {
  CREATED: '待上传视频', INSPECTING: '检测中', VERIFIED: '检测通过',
  EXCEPTION_PENDING: '异常待确认', MANUAL_REVIEW: '人工复核中',
  EXCEPTION_CONFIRMED: '异常已确认', EXCEPTION_REJECTED: '异常已驳回',
  REWORK_ASSIGNED: '返工中', REWORK_SUBMITTED: '待复核', REWORK_REVIEW: '复核中',
  RELEASED: '已放行', ARCHIVED: '已归档',
}

export const auditDecisionLabels: Record<VideoAudit['decision'], string> = {
  PASS: '合规通过', VIOLATION: '发现违规', INSUFFICIENT_EVIDENCE: '证据不足',
}

export const auditStatusLabels: Record<VideoAudit['status'], string> = {
  COMPLETED: '检测完成', FAILED: '检测失败',
}

export const evidenceStatusLabels: Record<AuditFinding['evidenceStatus'], string> = {
  CONFIRMED: '证据充分', MISSING: '未观察到', MISORDERED: '顺序异常',
  UNCERTAIN: '证据不足', SKIPPED: '可选步骤',
}

export const exceptionRuleLabels: Record<string, string> = {
  INSUFFICIENT_VISUAL_EVIDENCE: '关键画面不足',
  REQUIRED_STEP_MISSING: '必需步骤缺失',
}

export const humanDecisionLabels: Record<string, string> = {
  CONFIRMED: '已确认', REJECTED: '已驳回',
}

export const videoKindLabels: Record<string, string> = {
  ORIGINAL: '初检视频', REWORK: '返工视频',
}
