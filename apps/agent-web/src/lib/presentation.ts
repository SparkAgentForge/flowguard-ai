import type { AuditFinding, ExceptionCase, VideoAudit } from './api'

export const decisionLabels: Record<VideoAudit['decision'], string> = {
  PASS: '合规通过',
  VIOLATION: '发现违规',
  INSUFFICIENT_EVIDENCE: '证据不足',
}

export const decisionTone: Record<VideoAudit['decision'], 'success' | 'danger' | 'warning'> = {
  PASS: 'success',
  VIOLATION: 'danger',
  INSUFFICIENT_EVIDENCE: 'warning',
}

export const statusLabels: Record<VideoAudit['status'], string> = {
  PROCESSING: '分析中',
  COMPLETED: '分析完成',
  FAILED: '分析失败',
}

export const evidenceLabels: Record<AuditFinding['evidenceStatus'], string> = {
  CONFIRMED: '证据充分',
  MISSING: '未观察到',
  MISORDERED: '顺序异常',
  UNCERTAIN: '证据不足',
  SKIPPED: '可选步骤',
}

export const exceptionStatusLabels: Record<ExceptionCase['status'], string> = {
  PENDING: '待确认',
  MANUAL_REVIEW: '人工复核',
  CONFIRMED: '异常已确认',
  REJECTED: '异常已驳回',
  REWORK_ASSIGNED: '返工中',
  REWORK_SUBMITTED: '待复核',
  REWORK_REVIEW: '复核中',
  RESOLVED: '已放行',
}

export function formatSeconds(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '--:--'
  const value = Math.max(0, Math.round(seconds))
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`
}

export function formatDate(value: string | null): string {
  if (!value) return '尚未完成'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

export function statusTone(status: ExceptionCase['status']): 'success' | 'danger' | 'warning' | 'neutral' {
  if (status === 'RESOLVED' || status === 'REJECTED') return 'success'
  if (status === 'PENDING' || status === 'CONFIRMED') return 'danger'
  if (status === 'MANUAL_REVIEW' || status === 'REWORK_REVIEW' || status === 'REWORK_SUBMITTED') return 'warning'
  return 'neutral'
}
