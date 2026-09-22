import { useEffect, useState } from 'react'

import { Icon } from '../components/Icons'
import { StatusBadge } from '../components/StatusBadge'
import {
  createOrReadReport,
  listReports,
  listWorkOrders,
  type Report,
  type ReportSummary,
  type WorkOrder,
} from '../lib/api'

const FINAL_STATUSES = new Set(['VERIFIED', 'RELEASED', 'ARCHIVED'])

export function ReportsPage() {
  const [orders, setOrders] = useState<WorkOrder[]>([])
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [selected, setSelected] = useState<Report | null>(null)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([listWorkOrders(), listReports()]).then(([allOrders, archived]) => {
      setOrders(allOrders.filter((order) => FINAL_STATUSES.has(order.status)))
      setReports(archived)
    }).catch(() => setError('无法加载可归档工作单。'))
  }, [])

  async function openReport(order: WorkOrder) {
    setBusyId(order.id); setError('')
    try {
      const report = await createOrReadReport(order.id)
      setSelected(report)
      setReports((current) => current.some((item) => item.id === report.id) ? current : [{
        id: report.id, workOrderId: report.workOrderId, workOrderCode: report.workOrderCode,
        productCode: order.productCode, workOrderStatus: order.status, version: report.version,
        outcome: report.content.outcome, archivedAt: report.archivedAt,
      }, ...current])
    } catch (cause) { setError(cause instanceof Error ? cause.message : '报告生成失败。') }
    finally { setBusyId('') }
  }

  return (
    <div className="reports-page">
      <header className="page-heading"><div><p className="eyebrow">不可覆盖 / 可追溯</p><h1>证据归档</h1><p>报告只从数据库事实生成，固定记录 SOP、视频哈希、模型版本、人工决定和返工结果。</p></div>{selected && <StatusBadge tone="success">已归档 V{selected.version}</StatusBadge>}</header>
      <div className="reports-layout">
        <section className="archive-list"><div className="section-heading"><div><span className="section-kicker">可归档工作单</span><h2>{orders.length} 条完成记录</h2></div></div>{orders.length === 0 ? <p className="archive-empty">完成检测或返工放行后，工作单会出现在这里。</p> : orders.map((order) => { const archived = reports.find((report) => report.workOrderId === order.id); return <article className="archive-row" key={order.id}><div><strong>{order.code}</strong><span>{order.productCode} · {order.status}</span></div>{archived ? <button className="text-action" onClick={() => openReport(order)} type="button">查看 V{archived.version}</button> : <button className="secondary-action" disabled={busyId === order.id} onClick={() => openReport(order)} type="button">{busyId === order.id ? '生成中…' : '生成归档'}</button>}</article> })}{error && <p className="form-error" role="alert">{error}</p>}</section>
        <section className="report-preview">
          <div className="section-heading"><div><span className="section-kicker">归档报告</span><h2>{selected?.workOrderCode ?? '选择一条完成记录'}</h2></div>{selected && <a className="primary-action" href={`/api/v1/reports/${selected.workOrderId}/pdf`}>下载 PDF <Icon name="arrow" /></a>}</div>
          {selected ? <><div className="report-ledger"><div><span>最终结论</span><strong>{selected.content.outcome}</strong></div><div><span>SOP 版本</span><strong>{selected.content.sop.code} / {selected.content.sop.version}</strong></div><div><span>视频文件</span><strong>{selected.content.videos.length}</strong></div><div><span>审计次数</span><strong>{selected.content.audits.length}</strong></div></div><section className="report-section"><span className="section-kicker">模型与证据</span>{selected.content.audits.map((audit, index) => <article key={audit.id}><strong>审计 {index + 1} · {audit.decision}</strong><p>{audit.summary}</p><small>{audit.provider} / {audit.model} / {audit.promptVersion}</small></article>)}</section><section className="report-section"><span className="section-kicker">哈希追溯</span>{selected.content.videos.map((video) => <article className="hash-row" key={video.id}><strong>{video.kind} · {video.filename}</strong><code>{video.sha256}</code></article>)}</section>{selected.content.humanDecision && <section className="report-section"><span className="section-kicker">人工决定</span><p>{selected.content.humanDecision.reason}</p><small>{selected.content.humanDecision.reviewedBy} · {selected.content.humanDecision.status}</small></section>}<div className="report-seal"><span>PDF SHA256</span><code>{selected.pdfSha256}</code></div></> : <div className="report-empty"><span>ARC</span><p>选择左侧完成工单生成归档。第一次生成后，JSON 与 PDF 哈希固定，不会被后续请求覆盖。</p></div>}
        </section>
      </div>
    </div>
  )
}
