import { type ChangeEvent, useEffect, useRef, useState } from 'react'

import { Icon } from '../components/Icons'
import { StatusBadge } from '../components/StatusBadge'
import {
  createWorkOrder,
  inspectVideo,
  listPublishedSops,
  listWorkOrders,
  type SopVersionSummary,
  type VideoAudit,
  type WorkOrder,
  uploadVideo,
} from '../lib/api'

const ACTOR_ID = 'quality-demo'
const statusCopy: Record<string, string> = {
  CREATED: '待上传视频', INSPECTING: '检测中', VERIFIED: '检测通过',
  EXCEPTION_PENDING: '待确认异常', MANUAL_REVIEW: '人工复核中',
}

function statusTone(status: string) {
  if (status === 'VERIFIED') return 'success' as const
  if (status === 'EXCEPTION_PENDING' || status === 'MANUAL_REVIEW') return 'danger' as const
  return 'warning' as const
}

function formatSeconds(value: number | null) {
  if (value === null) return '--:--'
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`
}

export function WorkOrdersPage() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [sops, setSops] = useState<SopVersionSummary[]>([])
  const [orders, setOrders] = useState<WorkOrder[]>([])
  const [selectedOrder, setSelectedOrder] = useState<WorkOrder | null>(null)
  const [audit, setAudit] = useState<VideoAudit | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [sopId, setSopId] = useState('')
  const [code, setCode] = useState('WO-2026-')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([listPublishedSops(), listWorkOrders()]).then(([published, existing]) => {
      setSops(published); setOrders(existing); setSopId(published[0]?.id ?? '')
    }).catch(() => setError('无法加载工作单和已发布 SOP，请检查后端服务。'))
  }, [])

  async function createOrder() {
    const sop = sops.find((item) => item.id === sopId)
    if (!sop || code.trim().length < 3) return setError('请选择已发布 SOP，并填写工作单编号。')
    setBusy(true); setError('')
    try {
      const order = await createWorkOrder({ code: code.trim(), productCode: sop.productCode, sopVersionId: sop.id })
      setOrders((current) => [order, ...current]); setSelectedOrder(order); setAudit(null); setCode('WO-2026-')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '工作单创建失败。')
    } finally { setBusy(false) }
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null); setError('')
  }

  async function runInspection() {
    if (!selectedOrder || !file) return setError('请先选择工作单和视频文件。')
    setBusy(true); setError('')
    try {
      const video = await uploadVideo(selectedOrder.id, file)
      const result = await inspectVideo(selectedOrder.id, video.id, ACTOR_ID)
      const nextStatus = result.overallPass ? 'VERIFIED' : 'EXCEPTION_PENDING'
      setAudit(result); setSelectedOrder((current) => current ? { ...current, status: nextStatus } : current)
      setOrders((current) => current.map((item) => item.id === selectedOrder.id ? { ...item, status: nextStatus } : item))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '视频检测失败，请稍后重试。')
    } finally { setBusy(false) }
  }

  const selectedSop = sops.find((item) => item.id === selectedOrder?.sopVersionId)

  return (
    <div className="work-orders-page">
      <header className="page-heading">
        <div><p className="eyebrow">视频证据 / 模拟检测</p><h1>工单中心</h1><p>选择已发布 SOP，上传固定工位视频，按步骤查看模型观察到的证据和时间线。</p></div>
        {selectedOrder && <StatusBadge tone={statusTone(selectedOrder.status)}>{statusCopy[selectedOrder.status] ?? selectedOrder.status}</StatusBadge>}
      </header>
      <div className="work-orders-layout">
        <section className="work-order-setup">
          <div className="section-heading"><div><span className="section-kicker">01 / 建立检测上下文</span><h2>先绑定工单和 SOP</h2></div><span>{orders.length} 个工单</span></div>
          <label>已发布 SOP<select value={sopId} onChange={(event) => setSopId(event.target.value)}><option value="">选择 SOP 版本</option>{sops.map((sop) => <option key={sop.id} value={sop.id}>{sop.code} / {sop.version} · {sop.name}</option>)}</select></label>
          <label>工作单编号<input value={code} onChange={(event) => setCode(event.target.value)} /></label>
          <button className="primary-action" disabled={busy || !sopId} onClick={createOrder} type="button">创建检测工单 <Icon name="arrow" /></button>
          {orders.length > 0 && <div className="order-list"><span className="section-kicker">已有工作单</span>{orders.slice(0, 5).map((order) => <button className={`order-list__item${selectedOrder?.id === order.id ? ' is-selected' : ''}`} key={order.id} onClick={() => { setSelectedOrder(order); setAudit(null); setFile(null) }} type="button"><strong>{order.code}</strong><StatusBadge tone={statusTone(order.status)}>{statusCopy[order.status] ?? order.status}</StatusBadge></button>)}</div>}
        </section>
        <section className="inspection-panel">
          <div className="section-heading"><div><span className="section-kicker">02 / 送入视频</span><h2>{selectedOrder ? selectedOrder.code : '等待选择工作单'}</h2></div>{selectedSop && <span>{selectedSop.code} / {selectedSop.version}</span>}</div>
          <div className="video-dropzone"><div className="video-dropzone__mark" aria-hidden="true">＋</div><strong>{file?.name ?? '选择装配视频'}</strong><span>MP4 / MOV / WebM，最大 500 MiB</span><input ref={inputRef} accept="video/mp4,video/quicktime,video/webm,video/x-matroska" className="visually-hidden" onChange={chooseFile} type="file" /><button className="secondary-action" onClick={() => inputRef.current?.click()} type="button">{file ? '更换视频' : '选择视频'}</button></div>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-action" disabled={busy || !selectedOrder || !file} onClick={runInspection} type="button">{busy ? '正在上传并检测…' : '开始模拟检测'} <Icon name="arrow" /></button>
        </section>
      </div>
      <section className="audit-result" aria-live="polite">
        <div className="section-heading"><div><span className="section-kicker">03 / 证据时间线</span><h2>{audit ? (audit.overallPass ? '全部步骤已观察到' : '发现需要人工确认的步骤') : '检测结果将在这里出现'}</h2></div>{audit && <StatusBadge tone={audit.overallPass ? 'success' : 'danger'}>{audit.overallPass ? 'VERIFIED' : 'EXCEPTION_PENDING'}</StatusBadge>}</div>
        {audit ? <><p className="audit-summary">{audit.summary}</p><div className="evidence-timeline">{audit.findings.map((finding) => <article className={`timeline-item${finding.detected ? '' : ' is-missing'}`} key={finding.id}><div className="timeline-item__rail"><span>{String(finding.sequence).padStart(2, '0')}</span><i /></div><div className="timeline-item__body"><div className="timeline-item__heading"><h3>{finding.stepName}</h3><strong>{finding.detected ? '已观察' : '未观察到'}</strong></div><p>{finding.evidence}</p><div className="timeline-item__meta"><span>{formatSeconds(finding.startSeconds)} – {formatSeconds(finding.endSeconds)}</span><span>置信度 {finding.confidence}%</span><span>关键帧 {finding.frameTimestamps.length} 张</span></div></div></article>)}</div></> : <div className="audit-empty"><span>03</span><p>上传视频并开始检测后，这里会按 SOP 顺序展示每一步的时间范围、置信度和证据说明。</p></div>}
      </section>
    </div>
  )
}
