import { type ChangeEvent, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, Play } from 'lucide-react'

import { StatusBadge } from '../components/StatusBadge'
import {
  createWorkOrder, deleteWorkOrder, inspectVideo, listAudits, listSops, listWorkOrders,
  resolveReviewRequest, type SopVersionSummary, type VideoAudit, type WorkOrder,
  uploadVideo, videoContentUrl,
} from '../lib/api'
import { auditDecisionLabels, auditStatusLabels, evidenceStatusLabels, workOrderStatusLabels } from '../lib/presentation'

const ACTOR_ID = 'quality-demo'
const MAX_VIDEO_BYTES = 500 * 1024 * 1024

function statusTone(status: string) {
  if (status === 'VERIFIED' || status === 'RELEASED' || status === 'ARCHIVED') return 'success' as const
  if (status === 'EXCEPTION_PENDING' || status === 'MANUAL_REVIEW') return 'danger' as const
  return 'warning' as const
}

function formatSeconds(value: number | null) {
  if (value === null) return '--:--'
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`
}

export function WorkOrdersPage() {
  const inputRef = useRef<HTMLInputElement>(null)
  const playerRef = useRef<HTMLVideoElement>(null)
  const pendingSeek = useRef<number | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const [sops, setSops] = useState<SopVersionSummary[]>([])
  const [orders, setOrders] = useState<WorkOrder[]>([])
  const [history, setHistory] = useState<{ orderId: string; audits: VideoAudit[] } | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [sopId, setSopId] = useState('')
  const [code, setCode] = useState('')
  const [filter, setFilter] = useState('')
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deleteConfirmation, setDeleteConfirmation] = useState('')

  useEffect(() => {
    Promise.all([listSops(), listWorkOrders()]).then(([published, existing]) => {
      setSops(published)
      setOrders(existing)
      setSopId(published[0]?.id ?? '')
    }).catch((cause) => setError(cause instanceof Error ? cause.message : '无法加载工单'))
      .finally(() => setLoading(false))
  }, [])

  const selectedOrderId = searchParams.get('id') ?? orders[0]?.id ?? ''
  const selectedOrder = orders.find((item) => item.id === selectedOrderId) ?? null
  const currentAudits = history?.orderId === selectedOrderId ? history.audits : []
  const selectedAudit = currentAudits.find((item) => item.id === searchParams.get('audit')) ?? currentAudits[0] ?? null
  const selectedSop = sops.find((item) => item.id === selectedOrder?.sopVersionId)
  const canInspect = selectedOrder?.status === 'CREATED' || selectedOrder?.status === 'INSPECTING'
  const visibleOrders = orders.filter((item) => `${item.code} ${item.productCode}`.toLowerCase().includes(filter.toLowerCase()))

  useEffect(() => {
    if (!selectedOrderId) return
    let active = true
    listAudits(selectedOrderId)
      .then((audits) => { if (active) setHistory({ orderId: selectedOrderId, audits }) })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '无法加载审计历史') })
    return () => { active = false }
  }, [selectedOrderId])

  function chooseOrder(id: string) {
    setSearchParams({ id })
    setFile(null)
    setError('')
    setDeleteConfirmation('')
  }

  async function removeSelectedOrder() {
    if (!selectedOrder) return
    if (deleteConfirmation.trim() !== selectedOrder.code) {
      setError('请输入完全一致的工单编号进行确认。')
      return
    }
    setBusy(true); setError('')
    try {
      await deleteWorkOrder(selectedOrder.id, ACTOR_ID, deleteConfirmation.trim())
      const remaining = orders.filter((item) => item.id !== selectedOrder.id)
      setOrders(remaining)
      setHistory(null)
      setFile(null)
      setDeleteConfirmation('')
      setSearchParams(remaining[0] ? { id: remaining[0].id } : {})
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '工单删除失败，请稍后重试。')
    } finally { setBusy(false) }
  }

  async function createOrder() {
    const sop = sops.find((item) => item.id === sopId)
    if (!sop || code.trim().length < 3) return setError('请选择已发布 SOP，并填写工作单编号。')
    setBusy(true); setError('')
    try {
      const order = await createWorkOrder({ code: code.trim(), productCode: sop.productCode, sopVersionId: sop.id })
      setOrders((current) => [order, ...current])
      setSearchParams({ id: order.id })
      setCode('')
      setFile(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '工单创建失败。')
    } finally { setBusy(false) }
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null
    if (next && next.size > MAX_VIDEO_BYTES) {
      setFile(null); setError('视频不能超过 500 MiB。'); return
    }
    setFile(next); setError('')
  }

  async function runInspection() {
    if (!selectedOrder || !file) return setError('请先选择工单和视频文件。')
    setBusy(true); setError('')
    try {
      const video = await uploadVideo(selectedOrder.id, file)
      const result = await inspectVideo(selectedOrder.id, video.id, ACTOR_ID)
      const nextStatus = result.decision === 'PASS' ? 'VERIFIED' : result.decision === 'INSUFFICIENT_EVIDENCE' ? 'MANUAL_REVIEW' : 'EXCEPTION_PENDING'
      setOrders((current) => current.map((item) => item.id === selectedOrder.id ? { ...item, status: nextStatus } : item))
      setHistory((current) => ({ orderId: selectedOrder.id, audits: [result, ...(current?.orderId === selectedOrder.id ? current.audits.filter((item) => item.id !== result.id) : [])] }))
      setSearchParams({ id: selectedOrder.id, audit: result.id })
      setFile(null)
    } catch (cause) {
      setOrders((current) => current.map((item) => item.id === selectedOrder.id ? { ...item, status: 'CREATED' } : item))
      void listAudits(selectedOrder.id).then((audits) => setHistory({ orderId: selectedOrder.id, audits })).catch(() => undefined)
      setError(cause instanceof Error ? cause.message : '视频检测失败。上传成功的视频可在当前工单中重新检测。')
    } finally { setBusy(false) }
  }

  function seekTo(seconds: number | null) {
    if (seconds === null) return
    const player = playerRef.current
    if (!player) return
    if (player.readyState < 1) {
      pendingSeek.current = seconds
      player.load()
      return
    }
    player.currentTime = seconds
    void player.play().catch(() => undefined)
    player.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  async function resolveReview(requestId: string, decision: 'CONFIRMED' | 'REJECTED') {
    if (!selectedOrder || !selectedAudit) return
    const note = reviewNotes[requestId]?.trim()
    if (!note) return setError('请先填写这条复核结论的依据。')
    setBusy(true); setError('')
    try {
      const requests = await resolveReviewRequest(selectedOrder.id, selectedAudit.id, requestId, decision, ACTOR_ID, note)
      setHistory((current) => current ? { ...current, audits: current.audits.map((item) => item.id === selectedAudit.id ? { ...item, reviewRequests: requests } : item) } : current)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '复核请求处理失败。')
    } finally { setBusy(false) }
  }

  return (
    <div className="work-orders-page">
      <header className="page-heading">
        <div><p className="eyebrow">视频证据 / 执行图</p><h1>工单中心</h1></div>
        {selectedOrder && <StatusBadge tone={statusTone(selectedOrder.status)}>{workOrderStatusLabels[selectedOrder.status] ?? selectedOrder.status}</StatusBadge>}
      </header>
      <div className="work-orders-layout">
        <section className="work-order-setup">
          <div className="section-heading"><div><span className="section-kicker">工作单</span><h2>选择或新建</h2></div><span>{orders.length} 条</span></div>
          <div className="create-order-form">
            <label>已发布 SOP<select value={sopId} onChange={(event) => setSopId(event.target.value)}><option value="">选择 SOP 版本</option>{sops.map((sop) => <option key={sop.id} value={sop.id}>{sop.code} / {sop.version} · {sop.name}</option>)}</select></label>
            <label>工作单编号<input value={code} onChange={(event) => setCode(event.target.value)} placeholder="例如 WO-2026-001" /></label>
            <button className="primary-action" disabled={busy || !sopId} onClick={createOrder} type="button">创建工单 <ArrowRight size={17} /></button>
          </div>
          <label>查找工单<input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="编号或产品" /></label>
          <div className="order-list" aria-label="工单列表">
            {visibleOrders.map((order) => <button className={`order-list__item${selectedOrder?.id === order.id ? ' is-selected' : ''}`} key={order.id} onClick={() => chooseOrder(order.id)} type="button"><strong>{order.code}</strong><StatusBadge tone={statusTone(order.status)}>{workOrderStatusLabels[order.status] ?? order.status}</StatusBadge></button>)}
            {!loading && visibleOrders.length === 0 && <p className="section-empty">没有匹配的工单。</p>}
          </div>
          {selectedOrder && <div className="delete-order-panel">
            <span className="section-kicker">清理测试数据</span>
            <p>删除将同时清理该工单的视频、审计、异常、返工、通知、报告及 Step 5 帧对象。已发布或已归档工单不能删除。</p>
            <label>输入工单编号确认<input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} placeholder={selectedOrder.code} /></label>
            <button className="danger-action" disabled={busy || deleteConfirmation.trim() !== selectedOrder.code} onClick={() => { if (window.confirm(`确定永久删除工单 ${selectedOrder.code} 及其全部关联数据吗？`)) void removeSelectedOrder() }} type="button">删除当前工单</button>
          </div>}
        </section>
        <section className="inspection-panel">
          <div className="section-heading"><div><span className="section-kicker">视频审计</span><h2>{selectedOrder ? selectedOrder.code : '选择工作单'}</h2></div>{selectedSop && <span>{selectedSop.code} / {selectedSop.version}</span>}</div>
          {selectedOrder && !canInspect ? <p className="status-note">当前工单处于“{workOrderStatusLabels[selectedOrder.status] ?? selectedOrder.status}”，不能重复提交初检。可在下方查看已有审计；返工请前往 <Link to="/exceptions">异常处置</Link>。</p> : <>
            <div className="video-dropzone"><div className="video-dropzone__mark" aria-hidden="true">＋</div><strong>{file?.name ?? '选择装配视频'}</strong><span>MP4 / MOV / AVI / MKV / WebM · 最大 500 MiB</span><input ref={inputRef} accept=".mp4,.mov,.avi,.mkv,.webm" className="visually-hidden" onChange={chooseFile} type="file" /><button className="secondary-action" disabled={!selectedOrder || busy} onClick={() => inputRef.current?.click()} type="button">{file ? '更换视频' : '选择视频'}</button></div>
            <button className="primary-action" disabled={busy || !selectedOrder || !file} onClick={runInspection} type="button">{busy ? '正在上传并审计…' : '开始视频审计'} <ArrowRight size={17} /></button>
          </>}
          {error && <p className="form-error" role="alert">{error}</p>}
        </section>
      </div>
      <section className="audit-result" aria-live="polite">
        <div className="section-heading"><div><span className="section-kicker">审计记录</span><h2>{selectedAudit ? (selectedAudit.status === 'FAILED' ? '检测失败' : '步骤证据') : '等待检测结果'}</h2></div>{selectedAudit && <StatusBadge tone={selectedAudit.status === 'FAILED' ? 'danger' : selectedAudit.decision === 'PASS' ? 'success' : selectedAudit.decision === 'VIOLATION' ? 'danger' : 'warning'}>{auditStatusLabels[selectedAudit.status] ?? auditDecisionLabels[selectedAudit.decision]}</StatusBadge>}</div>
        {currentAudits.length > 1 && <div className="audit-tabs" role="group" aria-label="选择审计记录">{currentAudits.map((item, index) => <button aria-pressed={selectedAudit?.id === item.id} className={selectedAudit?.id === item.id ? 'is-active' : ''} key={item.id} onClick={() => setSearchParams({ id: selectedOrderId, audit: item.id })} type="button">审计 {currentAudits.length - index} · {new Date(item.createdAt).toLocaleDateString('zh-CN')}</button>)}</div>}
        {selectedAudit?.status === 'FAILED' ? <div className="audit-empty"><span>!</span><p>{selectedAudit.summary}。请检查 Step 5 与 RustFS 的网络配置后重试。</p></div> : selectedAudit && selectedOrder ? <>
          <p className="audit-summary">{selectedAudit.summary}</p>
          <div className="evidence-workspace">
            <div className="video-player"><video controls key={selectedAudit.videoId} onLoadedMetadata={(event) => { if (pendingSeek.current !== null) { event.currentTarget.currentTime = pendingSeek.current; pendingSeek.current = null } }} playsInline preload="metadata" ref={playerRef} src={videoContentUrl(selectedOrder.id, selectedAudit.videoId)} /><div className="video-player__footer"><span>审计视频</span><span>{selectedAudit.provider} / {selectedAudit.modelName}</span></div></div>
            <div className="evidence-timeline">{selectedAudit.findings.map((finding) => {
              const uncertain = finding.evidenceStatus === 'UNCERTAIN'
              const missing = finding.evidenceStatus === 'MISSING' || finding.evidenceStatus === 'MISORDERED'
              return <article className={`timeline-item${uncertain ? ' is-uncertain' : missing ? ' is-missing' : ''}`} key={finding.id}><div className="timeline-item__rail"><span>{String(finding.sequence).padStart(2, '0')}</span><i /></div><div className="timeline-item__body"><div className="timeline-item__heading"><h3>{finding.stepName}</h3><strong>{evidenceStatusLabels[finding.evidenceStatus]}</strong></div><p>{finding.evidence}</p><div className="timeline-item__meta"><button className="time-link" disabled={finding.startSeconds === null} onClick={() => seekTo(finding.startSeconds)} type="button" title="跳转到视频时间点"><Play size={13} />{formatSeconds(finding.startSeconds)} – {formatSeconds(finding.endSeconds)}</button><span>模型证据评分 {finding.evidenceScore}%</span><span>关键帧 {finding.frameTimestamps.length} 张</span>{finding.occluded && <span>画面遮挡</span>}</div></div></article>
            })}</div>
          </div>
          {selectedAudit.reviewRequests.length > 0 && <div className="review-request-list"><div className="section-heading"><div><span className="section-kicker">人工复核</span><h2>待核对的步骤</h2></div><span>{selectedAudit.reviewRequests.filter((item) => item.status === 'PENDING').length} 待处理</span></div>{selectedAudit.reviewRequests.map((item) => <article className="review-request" key={item.id}><div><strong>{item.stepName}</strong><p>{item.question}</p><button className="time-link" onClick={() => seekTo(item.startSeconds)} type="button" title="跳转到待复核片段"><Play size={13} />{formatSeconds(item.startSeconds)} – {formatSeconds(item.endSeconds)}</button><small>{item.reason}</small></div>{item.status === 'PENDING' ? <div className="review-request__actions"><label>判断依据<textarea onChange={(event) => setReviewNotes((current) => ({ ...current, [item.id]: event.target.value }))} rows={2} value={reviewNotes[item.id] ?? ''} /></label><div><button className="secondary-action" disabled={busy || !reviewNotes[item.id]?.trim()} onClick={() => resolveReview(item.id, 'REJECTED')} type="button">证据不足</button><button className="primary-action" disabled={busy || !reviewNotes[item.id]?.trim()} onClick={() => resolveReview(item.id, 'CONFIRMED')} type="button">确认完成</button></div></div> : <StatusBadge tone={item.status === 'CONFIRMED' ? 'success' : 'danger'}>{item.status === 'CONFIRMED' ? '已确认' : '已驳回'}</StatusBadge>}</article>)}</div>}
          {selectedAudit.decision !== 'PASS' && <p className="status-note">人工复核记录不会自动改变原始模型结论；异常确认与返工决策请在 <Link to="/exceptions">异常处置</Link> 完成。</p>}
        </> : <div className="audit-empty"><span>03</span><p>{loading ? '正在加载…' : '选择工单并上传视频后，可在这里查看审计与视频证据。'}</p></div>}
      </section>
    </div>
  )
}
