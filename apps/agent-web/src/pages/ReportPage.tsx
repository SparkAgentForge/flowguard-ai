import { Download, Fingerprint, FileCheck2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { EmptyInline, ErrorState, LoadingState, StandaloneFrame, StatusPill } from '../components/StandaloneFrame'
import { readReport, reportPdfUrl, type Report } from '../lib/api'
import { decisionLabels, formatDate } from '../lib/presentation'

export function ReportPage() {
  const { workOrderId = '' } = useParams()
  const invalidLink = !workOrderId || workOrderId.startsWith('填写')
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (invalidLink) return
    readReport(workOrderId).then(setReport).catch((cause) => setError(cause instanceof Error ? cause.message : '报告读取失败。'))
  }, [invalidLink, workOrderId])

  const displayError = error || (invalidLink ? '链接中缺少有效的工单 ID。' : '')

  return <StandaloneFrame eyebrow="证据归档" title={report?.workOrderCode ?? '归档报告'} description={report ? `报告 V${report.version} · 归档于 ${formatDate(report.archivedAt)}` : '读取本次工单的固定报告和追溯信息。'} status={report ? <StatusPill tone="success">已归档 V{report.version}</StatusPill> : undefined}>
    {displayError ? <ErrorState message={displayError} onRetry={() => window.location.reload()} /> : !report ? <LoadingState label="正在读取归档报告…" /> : <div className="report-view">
      <section className="report-hero"><div className="report-hero__icon"><FileCheck2 size={28} /></div><div><span className="section-label">最终结论</span><h2>{decisionLabels[report.content.outcome as keyof typeof decisionLabels] ?? report.content.outcome}</h2><p>{report.content.sop.name} · {report.content.sop.version}</p></div><a className="button button--dark" href={reportPdfUrl(report.workOrderId)}><Download size={16} />下载 PDF</a></section>
      <div className="report-grid"><section><div className="section-title"><span className="section-label">审计记录</span><strong>{report.content.audits.length} 次</strong></div>{report.content.audits.length === 0 ? <EmptyInline>报告尚未包含审计记录。</EmptyInline> : <div className="report-list">{report.content.audits.map((audit, index) => <article key={audit.id}><div className="report-list__heading"><strong>审计 {index + 1}</strong><StatusPill tone={audit.decision === 'PASS' ? 'success' : audit.decision === 'VIOLATION' ? 'danger' : 'warning'}>{decisionLabels[audit.decision as keyof typeof decisionLabels] ?? audit.decision}</StatusPill></div><p>{audit.summary}</p><small>{audit.provider} · {audit.model} · {audit.promptVersion}</small></article>)}</div>}</section><section><div className="section-title"><span className="section-label">文件追溯</span><strong>{report.content.videos.length} 个视频</strong></div>{report.content.videos.length === 0 ? <EmptyInline>报告尚未归档视频文件。</EmptyInline> : <div className="hash-list">{report.content.videos.map((video) => <article key={video.id}><strong>{video.filename}</strong><span>{video.kind}</span><code>{video.sha256}</code></article>)}</div>}<div className="hash-seal"><Fingerprint size={20} /><div><span>PDF SHA256</span><code>{report.pdfSha256}</code></div></div></section></div>
      {report.content.humanDecision && <section className="report-section"><span className="section-label">人工决定</span><h2>{report.content.humanDecision.status}</h2><p>{report.content.humanDecision.reason ?? '已记录人工决定。'} · {report.content.humanDecision.reviewedBy ?? '未填写复核人'}</p></section>}
      {report.content.rework && <section className="report-section"><span className="section-label">返工记录</span><h2>{report.content.rework.status}</h2><p>{report.content.rework.instructions}</p><small>负责人：{report.content.rework.assigneeId} · 复核人：{report.content.rework.reviewedBy ?? '未填写'}</small></section>}
    </div>}
  </StandaloneFrame>
}
