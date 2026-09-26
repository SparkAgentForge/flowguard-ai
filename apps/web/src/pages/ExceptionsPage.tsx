import { type ChangeEvent, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

import { StatusBadge } from '../components/StatusBadge'
import {
  assignRework, decideException, listAudits, listExceptions, listVideos,
  reviewRework, type ExceptionCase, type VideoAsset, type VideoAudit,
  uploadReworkVideo, videoContentUrl,
} from '../lib/api'
import { auditDecisionLabels, evidenceStatusLabels, exceptionRuleLabels } from '../lib/presentation'

const LEADER_ID = 'leader-demo'
const QUALITY_ID = 'quality-demo'
const MAX_VIDEO_BYTES = 500 * 1024 * 1024

const statusLabel: Record<ExceptionCase['status'], string> = {
  PENDING: '待确认', MANUAL_REVIEW: '证据不足', CONFIRMED: '已确认', REJECTED: '已驳回',
  REWORK_ASSIGNED: '返工中', REWORK_SUBMITTED: '待复核', REWORK_REVIEW: '复核中', RESOLVED: '已放行',
}

function badgeTone(status: ExceptionCase['status']) {
  if (status === 'RESOLVED' || status === 'REJECTED') return 'success' as const
  if (status === 'PENDING' || status === 'CONFIRMED') return 'danger' as const
  return 'warning' as const
}

function formatVideoTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

export function ExceptionsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [items, setItems] = useState<ExceptionCase[]>([])
  const [videos, setVideos] = useState<{ exceptionId: string; items: VideoAsset[] } | null>(null)
  const [latestAudit, setLatestAudit] = useState<{ exceptionId: string; audit: VideoAudit | null } | null>(null)
  const [reason, setReason] = useState('')
  const [assignee, setAssignee] = useState('operator-07')
  const [instructions, setInstructions] = useState('补装缺失部件，并重新拍摄包含完整步骤的装配视频。')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    listExceptions().then(setItems)
      .catch((cause) => setError(cause instanceof Error ? cause.message : '无法加载异常队列。'))
      .finally(() => setLoading(false))
  }, [])

  const selected = items.find((item) => item.id === searchParams.get('id')) ?? items[0] ?? null
  const selectedId = selected?.id
  const selectedWorkOrderId = selected?.workOrderId

  useEffect(() => {
    if (!selectedId || !selectedWorkOrderId) return
    let active = true
    Promise.all([listVideos(selectedWorkOrderId), listAudits(selectedWorkOrderId)])
      .then(([nextVideos, audits]) => {
        if (!active) return
        setVideos({ exceptionId: selectedId, items: nextVideos })
        setLatestAudit({ exceptionId: selectedId, audit: audits.find((item) => item.status === 'COMPLETED') ?? null })
      })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '无法加载返工记录') })
    return () => { active = false }
  }, [selectedId, selectedWorkOrderId])

  function replace(next: ExceptionCase) {
    setItems((current) => current.map((item) => item.id === next.id ? next : item))
  }

  function selectItem(item: ExceptionCase) {
    setSearchParams({ id: item.id })
    setReason(item.humanReason ?? '')
    setFile(null)
    setError('')
  }

  async function decide(action: 'confirm' | 'reject') {
    if (!selected || reason.trim().length < 2) return setError('请填写人工判断理由。')
    setBusy(true); setError('')
    try { replace(await decideException(selected.id, action, LEADER_ID, reason.trim())) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '异常决定提交失败。') }
    finally { setBusy(false) }
  }

  async function createTask() {
    if (!selected || !assignee.trim() || !instructions.trim()) return setError('请填写返工负责人和要求。')
    setBusy(true); setError('')
    try { replace(await assignRework(selected.id, LEADER_ID, assignee.trim(), instructions.trim())) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '返工任务创建失败。') }
    finally { setBusy(false) }
  }

  function chooseVideo(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null
    if (next && next.size > MAX_VIDEO_BYTES) { setFile(null); setError('视频不能超过 500 MiB。'); return }
    setFile(next); setError('')
  }

  async function submitVideo() {
    if (!selected?.reworkTask || !file) return setError('请选择返工视频。')
    setBusy(true); setError('')
    try {
      const video = await uploadReworkVideo(selected.reworkTask.id, file)
      setVideos((current) => ({ exceptionId: selected.id, items: [{ id: video.id, workOrderId: selected.workOrderId, reworkTaskId: selected.reworkTask!.id, filename: file.name, contentType: file.type || 'video/mp4', sha256: '', createdAt: new Date().toISOString() }, ...(current?.exceptionId === selected.id ? current.items : [])] }))
      replace({ ...selected, status: 'REWORK_SUBMITTED', reworkTask: { ...selected.reworkTask, status: 'SUBMITTED' } })
      setFile(null)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '返工视频提交失败。') }
    finally { setBusy(false) }
  }

  const submittedVideo = selected?.reworkTask && videos?.exceptionId === selected.id
    ? videos.items.find((item) => item.reworkTaskId === selected.reworkTask?.id) : null
  const reworkVideos = selected?.reworkTask && videos?.exceptionId === selected.id
    ? videos.items.filter((item) => item.reworkTaskId === selected.reworkTask?.id) : []

  async function runReview() {
    if (!selected?.reworkTask || !submittedVideo) return setError('找不到已提交的返工视频。')
    setBusy(true); setError('')
    try {
      const result = await reviewRework(selected.reworkTask.id, QUALITY_ID, submittedVideo.id, '返工视频按原 SOP 复核')
      replace({ ...selected, status: result.task.status === 'APPROVED' ? 'RESOLVED' : 'REWORK_ASSIGNED', reworkTask: result.task })
      setLatestAudit({ exceptionId: selected.id, audit: result.audit })
      setFile(null)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '返工复核失败，已提交的视频可再次复核。') }
    finally { setBusy(false) }
  }

  const review = selected && latestAudit?.exceptionId === selected.id && latestAudit.audit?.id !== selected.audit.id
    ? latestAudit.audit : null
  const reviewVideo = review && videos?.exceptionId === selected?.id
    ? videos.items.find((item) => item.id === review.videoId) : null

  return (
    <div className="exceptions-page">
      <header className="page-heading"><div><p className="eyebrow">人工复核 / 返工</p><h1>异常处置</h1></div>{selected && <StatusBadge tone={badgeTone(selected.status)}>{statusLabel[selected.status]}</StatusBadge>}</header>
      {error && <p className="form-error" role="alert">{error}</p>}
      {!selected ? <section className="queue-empty"><strong>{loading ? '正在加载…' : '当前没有异常记录'}</strong></section> : <div className="exception-layout">
        <aside className="exception-queue"><span className="section-kicker">异常队列 · {items.length}</span>{items.map((item) => <button className={`exception-queue__item${selected.id === item.id ? ' is-selected' : ''}`} key={item.id} onClick={() => selectItem(item)} type="button"><strong>{item.workOrderCode}</strong><span>{exceptionRuleLabels[item.ruleCode] ?? item.ruleCode}</span><StatusBadge tone={badgeTone(item.status)}>{statusLabel[item.status]}</StatusBadge></button>)}</aside>
        <main className="exception-detail">
          <section className="exception-facts"><div className="section-heading"><div><span className="section-kicker">初始审计</span><h2>{selected.decision === 'INSUFFICIENT_EVIDENCE' ? '关键画面不足' : '流程偏差'}</h2></div><span>{selected.audit.modelName}</span></div><p className="audit-summary">{selected.audit.summary}</p>{selected.facts.map((fact, index) => <blockquote key={`${index}-${fact}`}>{fact}</blockquote>)}<div className="compact-findings">{selected.audit.findings.map((finding) => <div key={finding.id}><span>{String(finding.sequence).padStart(2, '0')}</span><strong>{finding.stepName}</strong><small>{evidenceStatusLabels[finding.evidenceStatus]} · {finding.confidence}%</small></div>)}</div><Link className="text-action" to={`/work-orders?id=${selected.workOrderId}&audit=${selected.audit.id}`}>查看视频与逐步证据 <ArrowRight size={17} /></Link>
            {review && <div className="latest-review"><span className="section-kicker">最近返工复核</span><strong>{auditDecisionLabels[review.decision]}</strong><p>{review.summary}</p><Link className="text-action" to={`/work-orders?id=${selected.workOrderId}&audit=${review.id}`}>查看返工证据 <ArrowRight size={17} /></Link></div>}
          </section>
          <section className="decision-panel"><span className="section-kicker">处置操作</span>
            {(selected.status === 'PENDING' || selected.status === 'MANUAL_REVIEW') && <><label>判断理由<textarea onChange={(event) => setReason(event.target.value)} placeholder="依据视频事实填写" rows={4} value={reason} /></label><div className="decision-actions"><button className="secondary-action" disabled={busy || reason.trim().length < 2} onClick={() => decide('reject')} type="button">驳回异常</button><button className="primary-action" disabled={busy || reason.trim().length < 2} onClick={() => decide('confirm')} type="button">确认异常 <ArrowRight size={17} /></button></div></>}
            {selected.status === 'CONFIRMED' && <><label>返工负责人<input onChange={(event) => setAssignee(event.target.value)} value={assignee} /></label><label>返工要求<textarea onChange={(event) => setInstructions(event.target.value)} rows={4} value={instructions} /></label><button className="primary-action" disabled={busy} onClick={createTask} type="button">派发返工任务 <ArrowRight size={17} /></button></>}
            {selected.status === 'REWORK_ASSIGNED' && selected.reworkTask && <><div className="rework-brief"><strong>负责人：{selected.reworkTask.assigneeId}</strong><p>{selected.reworkTask.instructions}</p></div><label className="rework-upload">返工视频<input accept=".mp4,.mov,.avi,.mkv,.webm" onChange={chooseVideo} type="file" /></label><button className="primary-action" disabled={busy || !file} onClick={submitVideo} type="button">{busy ? '正在提交…' : '提交返工视频'} <ArrowRight size={17} /></button></>}
            {selected.status === 'REWORK_SUBMITTED' && <><p className="status-note">{submittedVideo ? `待复核视频：${submittedVideo.filename}` : '正在读取已提交视频…'}</p><button className="primary-action" disabled={busy || !submittedVideo} onClick={runReview} type="button">{busy ? '正在复核…' : '执行返工复核'} <ArrowRight size={17} /></button></>}
            {selected.status === 'REWORK_REVIEW' && <p className="status-note">返工复核处理中。</p>}
            {selected.status === 'RESOLVED' && <div className="resolved-note"><strong>返工复核通过，工单已放行</strong><span>复核人：{selected.reworkTask?.reviewedBy}</span></div>}
            {selected.status === 'REJECTED' && <div className="resolved-note"><strong>异常已驳回</strong><span>{selected.humanReason}</span></div>}
            {review && <div className="rework-result-entry"><div><span className="section-kicker">最近返工复核</span><strong>{auditDecisionLabels[review.decision]}</strong><small>{reviewVideo?.filename ?? '返工视频'} · {review.summary}</small></div><Link className="primary-action" to={`/work-orders?id=${selected.workOrderId}&audit=${review.id}`}>查看复核结果 <ArrowRight size={17} /></Link></div>}
            {selected.reworkTask && <div className="rework-history"><div className="rework-history__heading"><span className="section-kicker">返工视频记录</span><strong>{reworkVideos.length} 个</strong></div>{reworkVideos.length === 0 ? <p className="rework-history__empty">尚未提交返工视频。</p> : <ol>{reworkVideos.map((video, index) => <li key={video.id}><div><strong>{video.filename}</strong><span>{index === 0 && selected.status === 'REWORK_SUBMITTED' ? '待复核' : '已保存'} · {formatVideoTime(video.createdAt)}</span></div><a href={videoContentUrl(selected.workOrderId, video.id)} rel="noreferrer" target="_blank">查看视频</a></li>)}</ol>}</div>}
          </section>
        </main>
      </div>}
    </div>
  )
}
