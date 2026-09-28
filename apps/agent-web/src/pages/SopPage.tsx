import { useEffect, useState } from 'react'
import { BookOpen, CheckCircle2, Circle } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { EmptyInline, ErrorState, LoadingState, StandaloneFrame, StatusPill } from '../components/StandaloneFrame'
import { readSop, type SopVersion } from '../lib/api'

export function SopPage() {
  const { versionId = '' } = useParams()
  const invalidLink = !versionId || versionId.startsWith('填写')
  const [sop, setSop] = useState<SopVersion | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (invalidLink) return
    readSop(versionId).then(setSop).catch((cause) => setError(cause instanceof Error ? cause.message : 'SOP 读取失败。'))
  }, [invalidLink, versionId])

  const displayError = error || (invalidLink ? '链接中缺少有效的 SOP 版本 ID。' : '')

  return <StandaloneFrame eyebrow="操作标准" title={sop?.name ?? 'SOP 详情'} description={sop ? `${sop.code} · ${sop.productCode} · 版本 ${sop.version}` : '读取已发布的操作规范和证据要求。'} status={sop ? <StatusPill tone={sop.status === 'PUBLISHED' ? 'success' : 'warning'}>{sop.status === 'PUBLISHED' ? '已发布' : sop.status}</StatusPill> : undefined}>
    {displayError ? <ErrorState message={displayError} onRetry={() => { setError(''); setSop(null); if (!invalidLink) void readSop(versionId).then(setSop).catch((cause) => setError(cause instanceof Error ? cause.message : 'SOP 读取失败。')) }} /> : !sop ? <LoadingState label="正在读取操作标准…" /> : <div className="sop-view">
      <section className="result-strip"><div><span className="section-label">标准信息</span><strong>{sop.name}</strong><small>发布于 {sop.publishedAt ? new Date(sop.publishedAt).toLocaleString('zh-CN') : '尚未发布'}</small></div><BookOpen size={28} /></section>
      <section className="steps-section"><div className="section-title"><span className="section-label">执行顺序</span><strong>{sop.steps.length} 个步骤</strong></div>{sop.steps.length === 0 ? <EmptyInline>该 SOP 版本尚未生成操作步骤，暂时不能用于视频审计。</EmptyInline> : <ol className="sop-steps">{sop.steps.slice().sort((a, b) => a.sequence - b.sequence).map((step) => <li key={step.id}><span className="step-index">{String(step.sequence).padStart(2, '0')}</span><div><div className="step-heading"><h2>{step.name}</h2><span className={step.required ? 'required-mark' : 'optional-mark'}>{step.required ? <CheckCircle2 size={14} /> : <Circle size={14} />}{step.required ? '必需' : '可选'}</span></div><p className="step-code">{step.code}</p>{step.preconditions.length > 0 && <div className="detail-line"><span>前置条件</span><p>{step.preconditions.join('；')}</p></div>}{step.evidenceRequirements.length > 0 && <div className="detail-line"><span>证据要求</span><p>{step.evidenceRequirements.join('；')}</p></div>}{step.sourceRefs.length > 0 && <div className="source-quote"><span>手册原文</span><p>“{step.sourceRefs[0].quote}”</p><small>{step.sourceRefs[0].page ? `第 ${step.sourceRefs[0].page} 页` : '原文引用'}</small></div>}</div></li>)}</ol>}</section>
    </div>}
  </StandaloneFrame>
}
