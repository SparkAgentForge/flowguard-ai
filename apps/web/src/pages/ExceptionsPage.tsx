import { type ChangeEvent, useEffect, useState } from 'react'

import { Icon } from '../components/Icons'
import { StatusBadge } from '../components/StatusBadge'
import {
  assignRework,
  decideException,
  type ExceptionCase,
  listExceptions,
  reviewRework,
  uploadReworkVideo,
} from '../lib/api'

const LEADER_ID = 'leader-demo'
const QUALITY_ID = 'quality-demo'

const statusLabel: Record<ExceptionCase['status'], string> = {
  PENDING: '待确认', MANUAL_REVIEW: '证据不足', CONFIRMED: '已确认', REJECTED: '已驳回',
  REWORK_ASSIGNED: '返工中', REWORK_SUBMITTED: '待复核', REWORK_REVIEW: '复核中', RESOLVED: '已放行',
}

function badgeTone(status: ExceptionCase['status']) {
  if (status === 'RESOLVED' || status === 'REJECTED') return 'success' as const
  if (status === 'PENDING' || status === 'CONFIRMED') return 'danger' as const
  return 'warning' as const
}

export function ExceptionsPage() {
  const [items, setItems] = useState<ExceptionCase[]>([])
  const [selected, setSelected] = useState<ExceptionCase | null>(null)
  const [reason, setReason] = useState('')
  const [assignee, setAssignee] = useState('operator-07')
  const [instructions, setInstructions] = useState('补装缺失部件，并重新拍摄包含完整步骤的装配视频。')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { listExceptions().then((data) => { setItems(data); setSelected(data[0] ?? null) }).catch(() => setError('无法加载异常队列。')) }, [])

  function replace(next: ExceptionCase) {
    setSelected(next); setItems((current) => current.map((item) => item.id === next.id ? next : item))
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

  function chooseVideo(event: ChangeEvent<HTMLInputElement>) { setFile(event.target.files?.[0] ?? null); setError('') }

  async function submitAndReview() {
    if (!selected?.reworkTask || !file) return setError('请选择返工视频。')
    setBusy(true); setError('')
    try {
      const video = await uploadReworkVideo(selected.reworkTask.id, file)
      const result = await reviewRework(selected.reworkTask.id, QUALITY_ID, video.id, '返工视频已按原 SOP 复核')
      replace({ ...selected, status: result.task.status === 'APPROVED' ? 'RESOLVED' : 'REWORK_ASSIGNED', reworkTask: result.task })
    } catch (cause) { setError(cause instanceof Error ? cause.message : '返工复核失败。') }
    finally { setBusy(false) }
  }

  return (
    <div className="exceptions-page">
      <header className="page-heading"><div><p className="eyebrow">事实 / 规则 / 人工决定</p><h1>异常处置</h1><p>先查看模型观察与 SOP 证据，再确认是否成立。证据不足不会自动归责，必须由人复核。</p></div>{selected && <StatusBadge tone={badgeTone(selected.status)}>{statusLabel[selected.status]}</StatusBadge>}</header>
      {items.length === 0 ? <section className="queue-empty"><strong>当前没有待处理异常</strong><p>视频检测产生的漏步骤或证据不足记录会自动进入这里。</p></section> : <div className="exception-layout">
        <aside className="exception-queue"><span className="section-kicker">异常队列 · {items.length}</span>{items.map((item) => <button className={`exception-queue__item${selected?.id === item.id ? ' is-selected' : ''}`} key={item.id} onClick={() => { setSelected(item); setReason(item.humanReason ?? ''); setFile(null) }} type="button"><strong>{item.workOrderCode}</strong><span>{item.ruleCode}</span><StatusBadge tone={badgeTone(item.status)}>{statusLabel[item.status]}</StatusBadge></button>)}</aside>
        {selected && <main className="exception-detail">
          <section className="exception-facts"><div className="section-heading"><div><span className="section-kicker">01 / 已观察事实</span><h2>{selected.decision === 'INSUFFICIENT_EVIDENCE' ? '关键画面不足' : '必需步骤未观察到'}</h2></div><span>{selected.audit.modelName}</span></div><p className="audit-summary">{selected.audit.summary}</p>{selected.facts.map((fact) => <blockquote key={fact}>{fact}</blockquote>)}<div className="compact-findings">{selected.audit.findings.map((finding) => <div key={finding.id}><span>{String(finding.sequence).padStart(2, '0')}</span><strong>{finding.stepName}</strong><small>{finding.detected ? '已观察' : '未观察'} · {finding.confidence}%</small></div>)}</div></section>
          <section className="decision-panel"><span className="section-kicker">02 / 人工决定</span>{(selected.status === 'PENDING' || selected.status === 'MANUAL_REVIEW') && <><label>判断理由<textarea rows={4} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="写明你依据哪些视频事实作出决定" /></label><div className="decision-actions"><button className="secondary-action" disabled={busy} onClick={() => decide('reject')} type="button">驳回异常</button><button className="primary-action" disabled={busy} onClick={() => decide('confirm')} type="button">确认异常 <Icon name="arrow" /></button></div></>}
            {selected.status === 'CONFIRMED' && <><label>返工负责人<input value={assignee} onChange={(event) => setAssignee(event.target.value)} /></label><label>返工要求<textarea rows={4} value={instructions} onChange={(event) => setInstructions(event.target.value)} /></label><button className="primary-action" disabled={busy} onClick={createTask} type="button">派发返工任务 <Icon name="arrow" /></button></>}
            {selected.status === 'REWORK_ASSIGNED' && selected.reworkTask && <><div className="rework-brief"><strong>已派给 {selected.reworkTask.assigneeId}</strong><p>{selected.reworkTask.instructions}</p></div><label className="rework-upload">返工视频<input accept="video/*" onChange={chooseVideo} type="file" /></label><button className="primary-action" disabled={busy || !file} onClick={submitAndReview} type="button">提交并复核 <Icon name="arrow" /></button></>}
            {selected.status === 'RESOLVED' && <div className="resolved-note"><strong>返工复核通过，工单已放行</strong><span>复核人：{selected.reworkTask?.reviewedBy}</span></div>}{error && <p className="form-error" role="alert">{error}</p>}
          </section>
        </main>}
      </div>}
    </div>
  )
}
