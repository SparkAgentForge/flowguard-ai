import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, Clock3, ExternalLink, PauseCircle, Play, ShieldAlert } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { EmptyInline, ErrorState, LoadingState, StandaloneFrame, StatusPill } from '../components/StandaloneFrame'
import { evidenceClipUrl, listVideos, readAudit, type AuditFinding, type VideoAsset, type VideoAudit, videoContentUrl } from '../lib/api'
import { decisionLabels, decisionTone, evidenceLabels, formatDate, formatSeconds, statusLabels } from '../lib/presentation'

function findingTone(status: AuditFinding['evidenceStatus']): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'CONFIRMED' || status === 'SKIPPED') return 'success'
  if (status === 'UNCERTAIN') return 'warning'
  return 'danger'
}

export function AuditPage() {
  const { workOrderId = '', auditId = '' } = useParams()
  const invalidLink = !workOrderId || !auditId || workOrderId.startsWith('填写') || auditId.startsWith('填写')
  const [audit, setAudit] = useState<VideoAudit | null>(null)
  const [video, setVideo] = useState<VideoAsset | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const playerRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    if (invalidLink) return
    let active = true
    let timer: number | undefined
    const load = async () => {
      try {
        const [nextAudit, videos] = await Promise.all([readAudit(workOrderId, auditId), listVideos(workOrderId)])
        if (!active) return
        setAudit(nextAudit)
        setVideo(videos.find((item) => item.id === nextAudit.videoId) ?? null)
        setLoading(false)
        if (nextAudit.status === 'PROCESSING') timer = window.setTimeout(load, 2500)
      } catch (cause) {
        if (!active) return
        setError(cause instanceof Error ? cause.message : '审计结果读取失败。')
        setLoading(false)
      }
    }
    void load()
    return () => { active = false; if (timer !== undefined) window.clearTimeout(timer) }
  }, [auditId, invalidLink, workOrderId])

  function seek(seconds: number | null) {
    if (seconds === null || !playerRef.current) return
    playerRef.current.currentTime = seconds
    void playerRef.current.play()
  }

  const currentDecision = audit?.decision ?? 'INSUFFICIENT_EVIDENCE'
  const pageTitle = audit?.status === 'PROCESSING' ? '视频分析进行中' : audit?.status === 'FAILED' ? '视频分析失败' : audit ? decisionLabels[audit.decision] : '视频审计结果'
  const statusTone = audit?.status === 'FAILED' ? 'danger' : audit?.status === 'PROCESSING' ? 'warning' : decisionTone[currentDecision]

  return <StandaloneFrame eyebrow="视频审计" title={pageTitle} description={audit ? audit.summary : '读取本次视频分析和逐步证据。'} status={audit ? <StatusPill tone={statusTone}>{audit.status === 'COMPLETED' ? decisionLabels[audit.decision] : statusLabels[audit.status]}</StatusPill> : undefined}>
    {error || invalidLink ? <ErrorState message={error || '链接中缺少有效的工单 ID 或审计 ID。'} onRetry={() => window.location.reload()} /> : loading && !audit ? <LoadingState label="正在读取审计结果…" /> : audit?.status === 'FAILED' ? <ErrorState message={audit.summary} /> : audit ? <div className="audit-view">
      <section className={`decision-hero decision-hero--${statusTone}`}><div className="decision-hero__icon">{audit.status === 'PROCESSING' ? <Clock3 size={28} /> : audit.decision === 'PASS' ? <Check size={30} /> : audit.decision === 'VIOLATION' ? <ShieldAlert size={30} /> : <AlertTriangle size={30} />}</div><div><span className="section-label">{audit.status === 'PROCESSING' ? '正在分析' : '最终判断'}</span><h2>{audit.status === 'PROCESSING' ? '视频分析进行中' : decisionLabels[audit.decision]}</h2><p>{audit.summary}</p></div><span className="decision-hero__meta">{audit.provider} · {audit.modelName}</span></section>
      <section className="audit-evidence-grid">
        <div className="video-panel"><div className="section-title"><span className="section-label">原始视频</span><small>{video?.filename ?? '视频文件'}</small></div><div className="video-frame">{video ? <video controls playsInline preload="metadata" ref={playerRef} src={videoContentUrl(workOrderId, video.id)} /> : <div className="video-placeholder"><PauseCircle size={30} /><span>视频记录不可用</span></div>}</div><div className="video-meta"><span>{formatDate(audit.createdAt)}</span><span>{audit.findings.length} 个步骤证据</span></div></div>
        <div className="timeline-panel"><div className="section-title"><span className="section-label">步骤证据</span><strong>{audit.findings.length} 项</strong></div>{audit.findings.length === 0 ? <EmptyInline>{audit.status === 'PROCESSING' ? '分析完成后会在这里显示步骤证据。' : '本次审计没有返回可展示的步骤证据。'}</EmptyInline> : <ol className="audit-timeline">{audit.findings.map((finding) => { const candidate = finding.evidenceStatus === 'UNCERTAIN' || finding.evidenceStatus === 'MISSING' || finding.evidenceStatus === 'MISORDERED'; const start = candidate ? finding.candidateStartSeconds : finding.startSeconds; const end = candidate ? finding.candidateEndSeconds : finding.endSeconds; const kind = candidate ? 'candidate' : 'confirmed'; const hasClip = candidate ? finding.hasCandidateClip : finding.hasConfirmedClip; return <li className={`audit-step audit-step--${findingTone(finding.evidenceStatus)}`} key={finding.id}><span className="audit-step__number">{String(finding.sequence).padStart(2, '0')}</span><div className="audit-step__body"><div className="audit-step__heading"><h3>{finding.stepName}</h3><StatusPill tone={findingTone(finding.evidenceStatus)}>{evidenceLabels[finding.evidenceStatus]}</StatusPill></div><p>{finding.evidence || '暂未返回文字证据。'}</p><div className="audit-step__facts"><button className="timestamp-button" disabled={start === null} onClick={() => seek(start)} type="button"><Play size={13} />{formatSeconds(start)} – {formatSeconds(end)}</button><span>证据 {finding.evidenceScore}%</span>{finding.occluded && <span>画面遮挡</span>}{hasClip && <a className="clip-link" href={evidenceClipUrl(workOrderId, audit.id, finding.sopStepId, kind)} rel="noreferrer" target="_blank"><ExternalLink size={13} />{candidate ? '候选片段' : '证据片段'}</a>}</div></div></li> })}</ol>}</div>
      </section>
      {audit.reviewRequests.length > 0 && <section className="review-summary"><div className="section-title"><span className="section-label">人工复核</span><strong>{audit.reviewRequests.filter((item) => item.status === 'PENDING').length} 项待处理</strong></div><div className="review-summary__list">{audit.reviewRequests.map((item) => <article key={item.id}><div><strong>{item.stepName}</strong><p>{item.question}</p></div><span>{item.status === 'PENDING' ? item.reason : item.status === 'CONFIRMED' ? '已确认' : '已驳回'}</span></article>)}</div></section>}
      {audit.status === 'COMPLETED' && audit.decision !== 'PASS' && <p className="notice notice--warning">该结果需要进入异常处置或人工复核，不能仅依据模型置信度放行。</p>}
    </div> : <LoadingState />}
  </StandaloneFrame>
}
