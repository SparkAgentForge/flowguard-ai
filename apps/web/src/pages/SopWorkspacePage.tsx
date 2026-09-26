import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

import { StatusBadge } from '../components/StatusBadge'
import { listSops, readSop, runSopAction, type SopVersion, type SopVersionSummary, updateSop, uploadAndExtractSop } from '../lib/api'

const ACTOR_ID = 'quality-demo'

const statusLabels: Record<SopVersion['status'], string> = {
  DRAFT: '草稿',
  AI_EXTRACTED: '待人工审核',
  IN_REVIEW: '审核中',
  APPROVED: '已批准',
  PUBLISHED: '已发布',
}

const nextAction: Partial<Record<SopVersion['status'], { action: 'submit-review' | 'approve' | 'publish'; label: string }>> = {
  AI_EXTRACTED: { action: 'submit-review', label: '提交人工审核' },
  IN_REVIEW: { action: 'approve', label: '确认内容正确' },
  APPROVED: { action: 'publish', label: '发布 SOP' },
}

export function SopWorkspacePage() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const [versions, setVersions] = useState<SopVersionSummary[]>([])
  const [version, setVersion] = useState<SopVersion | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    listSops(true).then(setVersions).catch((cause) => setError(cause instanceof Error ? cause.message : '无法加载 SOP 版本'))
  }, [])

  const versionId = searchParams.get('id')
  useEffect(() => {
    if (!versionId) return
    let active = true
    readSop(versionId).then((next) => { if (active) { setVersion(next); setDirty(false) } })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '无法加载 SOP') })
    return () => { active = false }
  }, [versionId])

  function selectVersion(id: string) {
    if (dirty && !window.confirm('当前修改尚未保存，确定切换版本吗？')) return
    setError('')
    setSearchParams({ id })
  }

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null)
    setError('')
  }

  async function extract(event: FormEvent) {
    event.preventDefault()
    if (!file) return setError('请先选择 PDF 或 DOCX 操作手册。')
    setBusy(true)
    setError('')
    try {
      const next = await uploadAndExtractSop(file, ACTOR_ID)
      setVersion(next)
      setVersions((current) => [{ id: next.id, sopId: next.sopId, code: next.code, name: next.name, productCode: next.productCode, version: next.version, status: next.status, publishedAt: next.publishedAt }, ...current.filter((item) => item.id !== next.id)])
      setSearchParams({ id: next.id })
      setDirty(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '文档处理失败，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    if (!version) return
    if (!version.name.trim() || !version.productCode.trim() || version.steps.some((step) => !step.name.trim() || !step.code.trim())) return setError('请填写 SOP 名称、产品编码及所有步骤名称。')
    setBusy(true)
    setError('')
    try {
      const next = await updateSop(version, ACTOR_ID)
      setVersion(next)
      setDirty(false)
      setVersions((current) => current.map((item) => item.id === next.id ? { ...item, name: next.name, productCode: next.productCode } : item))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存失败，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  async function advance() {
    if (!version) return
    const target = nextAction[version.status]
    if (!target) return
    setBusy(true)
    setError('')
    try {
      const saved = dirty ? await updateSop(version, ACTOR_ID) : version
      const next = await runSopAction(saved.id, target.action, ACTOR_ID)
      setVersion(next)
      setDirty(false)
      setVersions((current) => current.map((item) => item.id === next.id ? { ...item, name: next.name, productCode: next.productCode, status: next.status, publishedAt: next.publishedAt } : item))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '状态更新失败，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  function updateStep(index: number, field: 'name' | 'evidenceRequirements' | 'preconditions' | 'required', value: string | boolean) {
    if (!version) return
    setDirty(true)
    setVersion({
      ...version,
      steps: version.steps.map((step, stepIndex) => stepIndex === index
        ? { ...step, [field]: field === 'evidenceRequirements' || field === 'preconditions' ? String(value).split('\n') : value }
        : step),
    })
  }

  const canEdit = version?.status === 'AI_EXTRACTED' || version?.status === 'IN_REVIEW'

  return (
    <div className="sop-workspace">
      <header className="page-heading sop-heading">
        <div><p className="eyebrow">标准作业程序</p><h1>SOP 审核台</h1></div>
        {version && <StatusBadge tone={version.status === 'PUBLISHED' ? 'success' : 'warning'}>{statusLabels[version.status]}</StatusBadge>}
      </header>
      <section className="sop-version-section">
        <div className="section-heading"><div><span className="section-kicker">版本记录</span><h2>操作标准</h2></div><button className="secondary-action" onClick={() => { if (dirty && !window.confirm('当前修改尚未保存，确定导入新手册吗？')) return; setVersion(null); setFile(null); setDirty(false); setError(''); setSearchParams({}) }} type="button">导入新手册</button></div>
        {versions.length ? <div className="sop-version-list">{versions.map((item) => <button aria-pressed={version?.id === item.id} className={version?.id === item.id ? 'is-active' : ''} key={item.id} onClick={() => selectVersion(item.id)} type="button"><strong>{item.name}</strong><small>{item.code} / {item.version} · {item.productCode}</small><StatusBadge tone={item.status === 'PUBLISHED' ? 'success' : 'warning'}>{statusLabels[item.status]}</StatusBadge></button>)}</div> : <p className="section-empty">还没有 SOP 版本。</p>}
      </section>

      {!version ? (
        <div className="sop-intake-grid">
          <form className="upload-panel" onSubmit={extract}>
            <span className="section-kicker">导入手册</span>
            <h2>上传操作手册</h2>
            <p>PDF 或 DOCX · 最大 20 MiB</p>
            <input ref={inputRef} accept=".pdf,.docx" className="visually-hidden" id="sop-file" onChange={selectFile} type="file" />
            <button className="file-picker" onClick={() => inputRef.current?.click()} type="button">
              <span>{file?.name ?? '选择操作手册'}</span><span>{file ? '更换文件' : 'PDF / DOCX'}</span>
            </button>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="primary-action" disabled={busy || !file} type="submit">{busy ? '正在提取步骤…' : '提取 SOP'}<ArrowRight size={17} /></button>
          </form>
        </div>
      ) : (
        <div className="sop-review-layout">
          <section className="sop-editor">
            <div className="section-heading"><div><span className="section-kicker">{version.code} · {version.version}</span><h2>{version.name}</h2></div><span>{version.steps.length} 个步骤</span></div>
            <div className="sop-meta-fields"><label>SOP 名称<input disabled={busy || !canEdit} onChange={(event) => { setVersion({ ...version, name: event.target.value }); setDirty(true) }} value={version.name} /></label><label>产品编码<input disabled={busy || !canEdit} onChange={(event) => { setVersion({ ...version, productCode: event.target.value }); setDirty(true) }} value={version.productCode} /></label></div>
            <div className="step-editor-list">
              {version.steps.map((step, index) => (
                <article className="step-editor" key={step.id || step.code}>
                  <span className="step-number">{String(index + 1).padStart(2, '0')}</span>
                  <div className="step-fields">
                    <label>步骤名称<input disabled={busy || !canEdit} onChange={(event) => updateStep(index, 'name', event.target.value)} value={step.name} /></label>
                    <label className="step-required"><input checked={step.required} disabled={busy || !canEdit} onChange={(event) => updateStep(index, 'required', event.target.checked)} type="checkbox" />必需步骤</label>
                    <label>前置条件（每行一项）<textarea disabled={busy || !canEdit} onChange={(event) => updateStep(index, 'preconditions', event.target.value)} rows={2} value={step.preconditions.join('\n')} /></label>
                    <label>视频证据要求（每行一项）<textarea disabled={busy || !canEdit} onChange={(event) => updateStep(index, 'evidenceRequirements', event.target.value)} rows={2} value={step.evidenceRequirements.join('\n')} /></label>
                    <blockquote><span>原文依据{step.sourceRefs[0]?.page ? ` · 第 ${step.sourceRefs[0].page} 页` : ''}</span>{step.sourceRefs[0]?.quote ?? '暂无原文引用'}</blockquote>
                  </div>
                </article>
              ))}
            </div>
          </section>
          <aside className="review-actions">
            <span className="section-kicker">审核决策</span><h2>{statusLabels[version.status]}</h2>
            <p>{dirty ? '有未保存的修改。提交审核前将先保存当前内容。' : `${version.steps.filter((step) => step.required).length} 个必需步骤 · ${version.steps.length - version.steps.filter((step) => step.required).length} 个可选步骤`}</p>
            {error && <p className="form-error" role="alert">{error}</p>}
            {canEdit && <button className="secondary-action" disabled={busy} onClick={save} type="button">保存修订</button>}
            {nextAction[version.status] && <button className="primary-action" disabled={busy} onClick={advance} type="button">{busy ? '处理中…' : nextAction[version.status]?.label}<ArrowRight size={17} /></button>}
            {version.status === 'PUBLISHED' && <div className="published-note"><strong>版本已生效</strong><span>后续工单可选择此版本进行检测。</span></div>}
          </aside>
        </div>
      )}
    </div>
  )
}
