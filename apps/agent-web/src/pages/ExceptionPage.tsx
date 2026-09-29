import { type ChangeEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Check, FileUp, RotateCcw, ShieldAlert, X } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { EmptyInline, ErrorState, LoadingState, StandaloneFrame, StatusPill } from '../components/StandaloneFrame'
import { assignRework, decideException, listAudits, listVideos, readException, reviewRework, uploadReworkVideo, videoContentUrl, type ExceptionCase, type VideoAsset, type VideoAudit } from '../lib/api'
import { decisionLabels, exceptionStatusLabels, formatDate, statusTone } from '../lib/presentation'

const reviewerConfigured = Boolean(import.meta.env.VITE_AGENT_REVIEWER_ID?.trim())

async function fetchExceptionData(exceptionId: string): Promise<{ exception: ExceptionCase; videos: VideoAsset[]; latestAudit: VideoAudit | null }> {
  if (!exceptionId || exceptionId.startsWith('填写')) throw new Error('链接中缺少有效的异常 ID。')
  const next = await readException(exceptionId)
  const [nextVideos, audits] = await Promise.all([listVideos(next.workOrderId), listAudits(next.workOrderId)])
  const reworkVideoIds = new Set(nextVideos.filter((video) => video.reworkTaskId === next.reworkTask?.id).map((video) => video.id))
  const latest = audits
    .filter((audit) => reworkVideoIds.has(audit.videoId))
    .sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime())[0] ?? null
  return { exception: next, videos: nextVideos, latestAudit: latest }
}

export function ExceptionPage() {
  const { exceptionId = '' } = useParams()
  const [exception, setException] = useState<ExceptionCase | null>(null)
  const [videos, setVideos] = useState<VideoAsset[]>([])
  const [latestAudit, setLatestAudit] = useState<VideoAudit | null>(null)
  const [reason, setReason] = useState('')
  const [assignee, setAssignee] = useState('')
  const [instructions, setInstructions] = useState('补齐缺失步骤，并重新拍摄包含完整操作过程的视频。')
  const [reviewNotes, setReviewNotes] = useState('返工视频按原 SOP 复核。')
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const applyLoadedData = useCallback(async (next: ExceptionCase, nextVideos: VideoAsset[], nextLatestAudit: VideoAudit | null) => {
    setException(next)
    setVideos(nextVideos)
    setLatestAudit(nextLatestAudit ?? next.audit)
    setAssignee((current) => current || next.reworkTask?.assigneeId || '')
    setLoading(false)
  }, [])

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    async function refresh() {
      try {
        const { exception: next, videos: nextVideos, latestAudit: nextLatestAudit } = await fetchExceptionData(exceptionId)
        if (!active) return
        await applyLoadedData(next, nextVideos, nextLatestAudit)
        if (next.status === 'REWORK_REVIEW' || nextLatestAudit?.status === 'PROCESSING') timer = setTimeout(() => void refresh(), 4000)
      } catch (cause) {
        if (active) { setError(cause instanceof Error ? cause.message : '异常记录读取失败。'); setLoading(false) }
      }
    }
    void refresh()
    return () => { active = false; clearTimeout(timer) }
  }, [applyLoadedData, exceptionId])

  const reworkVideos = useMemo(() => videos.filter((video) => video.reworkTaskId === exception?.reworkTask?.id), [exception?.reworkTask?.id, videos])
  const submittedVideo = reworkVideos[0] ?? null
  const displayedAudit = latestAudit ?? exception?.audit ?? null

  async function mutate(action: () => Promise<ExceptionCase>) {
    setBusy(true); setError('')
    try { setException(await action()) } catch (cause) { setError(cause instanceof Error ? cause.message : '操作未完成。') } finally { setBusy(false) }
  }

  async function decide(action: 'confirm' | 'reject') {
    if (reason.trim().length < 2) return setError('请填写人工判断理由。')
    await mutate(() => decideException(exceptionId, action, reason.trim()))
  }

  async function createRework() {
    if (!assignee.trim() || !instructions.trim()) return setError('请填写返工负责人和要求。')
    await mutate(() => assignRework(exceptionId, assignee.trim(), instructions.trim()))
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null
    setFile(next)
    setError('')
  }

  async function submitVideo() {
    if (!exception?.reworkTask || !file) return setError('请选择返工视频。')
    setBusy(true); setError('')
    try {
      await uploadReworkVideo(exception.reworkTask.id, file)
      setFile(null)
      const refreshed = await fetchExceptionData(exceptionId)
      await applyLoadedData(refreshed.exception, refreshed.videos, refreshed.latestAudit)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '返工视频上传失败。') }
    finally { setBusy(false) }
  }

  async function runReview() {
    if (!exception?.reworkTask || !submittedVideo) return setError('找不到待复核的返工视频。')
    setBusy(true); setError('')
    try {
      const result = await reviewRework(exception.reworkTask.id, submittedVideo.id, reviewNotes.trim())
      setLatestAudit(result.audit)
      setFile(null)
      const refreshed = await fetchExceptionData(exceptionId)
      await applyLoadedData(refreshed.exception, refreshed.videos, refreshed.latestAudit ?? result.audit)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '返工复核失败。') }
    finally { setBusy(false) }
  }

  const status = exception?.status ?? 'PENDING'
  const originalVideo = exception && videos.find((video) => video.id === exception.audit.videoId)
  const canWrite = reviewerConfigured && !busy

  return <StandaloneFrame eyebrow="异常处置" title={exception ? exception.workOrderCode : '异常与返工复核'} description={exception ? '围绕同一个异常记录完成确认、返工和复核。' : '读取异常事实和返工复核状态。'} status={exception ? <StatusPill tone={statusTone(exception.status)}>{exceptionStatusLabels[exception.status]}</StatusPill> : undefined}>
    {error && !exception ? <ErrorState message={error} onRetry={() => { setError(''); setLoading(true); void fetchExceptionData(exceptionId).then(({ exception: next, videos: nextVideos, latestAudit: nextLatestAudit }) => void applyLoadedData(next, nextVideos, nextLatestAudit)).catch((cause) => { setError(cause instanceof Error ? cause.message : '异常记录读取失败。'); setLoading(false) }) }} /> : loading && !exception ? <LoadingState label="正在读取异常记录…" /> : exception && displayedAudit ? <div className="exception-view">
      <section className="exception-hero"><div className="exception-hero__mark"><ShieldAlert size={26} /></div><div><span className="section-label">原始审计 · {decisionLabels[exception.decision]}</span><h2>{exception.ruleCode}</h2><p>{exception.audit.summary}</p></div></section>
      {error && <p className="notice notice--error">{error}</p>}
      {!reviewerConfigured && <p className="notice notice--warning">当前展示环境未配置 `VITE_AGENT_REVIEWER_ID`，异常写操作已禁用。</p>}
      <div className="exception-grid"><section className="exception-facts"><div className="section-title"><span className="section-label">异常事实</span><strong>{exception.facts.length} 条</strong></div>{exception.facts.length === 0 ? <EmptyInline>接口没有返回异常事实，请回到审计结果核对证据。</EmptyInline> : <ul className="fact-list">{exception.facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>}<div className="exception-video"><div className="section-title"><span className="section-label">原始视频</span><small>{originalVideo?.filename ?? '视频文件'}</small></div>{originalVideo ? <video controls playsInline preload="metadata" src={videoContentUrl(exception.workOrderId, originalVideo.id)} /> : <p>原始视频记录不可用。</p>}</div></section>
        <section className="exception-actions"><span className="section-label">处置操作</span>{(status === 'PENDING' || status === 'MANUAL_REVIEW') && <div className="action-block"><label>判断理由<textarea disabled={!canWrite} onChange={(event) => setReason(event.target.value)} placeholder="依据视频事实填写" rows={4} value={reason} /></label><div className="action-row"><button className="button button--light" disabled={!canWrite || reason.trim().length < 2} onClick={() => void decide('reject')} type="button"><X size={16} />驳回异常</button><button className="button button--dark" disabled={!canWrite || reason.trim().length < 2} onClick={() => void decide('confirm')} type="button"><Check size={16} />确认异常</button></div></div>}{status === 'CONFIRMED' && <div className="action-block"><label>返工负责人<input disabled={!canWrite} onChange={(event) => setAssignee(event.target.value)} placeholder="例如 operator-07" value={assignee} /></label><label>返工要求<textarea disabled={!canWrite} onChange={(event) => setInstructions(event.target.value)} rows={4} value={instructions} /></label><button className="button button--dark" disabled={!canWrite} onClick={() => void createRework()} type="button"><RotateCcw size={16} />派发返工任务</button></div>}{status === 'REWORK_ASSIGNED' && exception.reworkTask && <div className="action-block"><div className="task-brief"><span>负责人</span><strong>{exception.reworkTask.assigneeId}</strong><p>{exception.reworkTask.instructions}</p></div><label className="file-control">返工视频<input accept=".mp4,.mov,.avi,.mkv,.webm" disabled={!canWrite} onChange={chooseFile} type="file" /><span><FileUp size={18} />{file?.name ?? '选择视频文件'}</span></label><button className="button button--dark" disabled={!canWrite || !file} onClick={() => void submitVideo()} type="button">提交返工视频</button></div>}{status === 'REWORK_SUBMITTED' && exception.reworkTask && <div className="action-block"><div className="task-brief"><span>待复核视频</span><strong>{submittedVideo?.filename ?? '正在读取…'}</strong></div><label>复核说明<textarea disabled={!canWrite} onChange={(event) => setReviewNotes(event.target.value)} rows={3} value={reviewNotes} /></label><button className="button button--dark" disabled={!canWrite || !submittedVideo} onClick={() => void runReview()} type="button">执行返工复核</button></div>}{status === 'REWORK_REVIEW' && <div className="status-block"><strong>返工复核处理中</strong><p>复核完成后刷新本页面即可查看最新结果。</p></div>}{status === 'RESOLVED' && <div className="status-block status-block--success"><strong>返工复核通过，工单已放行</strong><p>复核人：{exception.reworkTask?.reviewedBy ?? exception.reviewedBy ?? '已记录'}</p></div>}{status === 'REJECTED' && <div className="status-block"><strong>异常已驳回</strong><p>{exception.humanReason}</p></div>}
          <div className="rework-history"><div className="section-title"><span className="section-label">返工视频记录</span><strong>{reworkVideos.length} 个</strong></div>{reworkVideos.length === 0 ? <p>尚未提交返工视频。</p> : <ol>{reworkVideos.map((item) => <li key={item.id}><span>{item.filename}</span><small>{formatDate(item.createdAt)}</small><a href={videoContentUrl(exception.workOrderId, item.id)} rel="noreferrer" target="_blank">查看视频</a></li>)}</ol>}</div></section></div>
      {latestAudit && latestAudit.id !== exception.audit.id && <section className="latest-result"><div><span className="section-label">最近返工复核</span><h2>{latestAudit.status === 'PROCESSING' ? '返工复核处理中' : latestAudit.status === 'FAILED' ? '返工复核失败' : decisionLabels[latestAudit.decision]}</h2><p>{latestAudit.summary}</p><Link className="button button--light" to={`/audit/${exception.workOrderId}/${latestAudit.id}`}>查看返工复核结果</Link></div><StatusPill tone={latestAudit.status === 'COMPLETED' && latestAudit.decision === 'PASS' ? 'success' : 'warning'}>{latestAudit.status === 'COMPLETED' ? '复核完成' : latestAudit.status}</StatusPill></section>}
    </div> : <LoadingState />}
  </StandaloneFrame>
}
