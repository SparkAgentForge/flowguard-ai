import { type ChangeEvent, type FormEvent, useRef, useState } from 'react'

import { Icon } from '../components/Icons'
import { StatusBadge } from '../components/StatusBadge'
import { runSopAction, type SopVersion, updateSop, uploadAndExtractSop } from '../lib/api'

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
  const [version, setVersion] = useState<SopVersion | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

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
      setVersion(await uploadAndExtractSop(file, ACTOR_ID))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '文档处理失败，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    if (!version) return
    setBusy(true)
    setError('')
    try {
      setVersion(await updateSop(version, ACTOR_ID))
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
      setVersion(await runSopAction(version.id, target.action, ACTOR_ID))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '状态更新失败，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  function updateStep(index: number, field: 'name' | 'evidenceRequirements', value: string) {
    if (!version) return
    setVersion({
      ...version,
      steps: version.steps.map((step, stepIndex) => stepIndex === index
        ? { ...step, [field]: field === 'evidenceRequirements' ? [value] : value }
        : step),
    })
  }

  const canEdit = version?.status === 'AI_EXTRACTED' || version?.status === 'IN_REVIEW'

  return (
    <div className="sop-workspace">
      <header className="page-heading sop-heading">
        <div><p className="eyebrow">文档到可执行标准</p><h1>SOP 审核台</h1><p>上传操作手册，由 AI 整理为步骤；工程师逐条核对来源和证据要求后再发布。</p></div>
        {version && <StatusBadge tone={version.status === 'PUBLISHED' ? 'success' : 'warning'}>{statusLabels[version.status]}</StatusBadge>}
      </header>

      {!version ? (
        <div className="sop-intake-grid">
          <form className="upload-panel" onSubmit={extract}>
            <span className="section-kicker">01 / 导入手册</span>
            <div className="upload-illustration" aria-hidden="true">
              <svg viewBox="0 0 360 190"><path d="M84 24h126l66 66v76H84V24Z" /><path d="M210 24v66h66M124 118h112M124 142h76" /><path className="upload-arrow" d="M48 102h70m-18-18 18 18-18 18" /></svg>
            </div>
            <h2>把纸面规则变成检测步骤</h2>
            <p>支持 PDF、DOCX，单个文件不超过 20 MiB。原文页码和引用会保留，方便人工复核。</p>
            <input ref={inputRef} accept=".pdf,.docx" className="visually-hidden" id="sop-file" onChange={selectFile} type="file" />
            <button className="file-picker" onClick={() => inputRef.current?.click()} type="button">
              <span>{file?.name ?? '选择操作手册'}</span><span>{file ? '更换文件' : 'PDF / DOCX'}</span>
            </button>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="primary-action" disabled={busy} type="submit">{busy ? '正在提取步骤…' : '开始 AI 整理'}<Icon name="arrow" /></button>
          </form>
          <section className="review-route" aria-labelledby="route-title">
            <span className="section-kicker">02 / 审核路径</span><h2 id="route-title">发布前，必须经过人的判断</h2>
            <ol>
              <li><strong>AI 整理</strong><span>识别步骤、前置条件和视频证据要求</span></li>
              <li><strong>工程师复核</strong><span>逐条对照原文，修正遗漏或错误</span></li>
              <li><strong>批准发布</strong><span>形成有版本、有来源、可追溯的 SOP</span></li>
            </ol>
            <aside><strong>安全边界</strong><p>AI 生成内容不会直接投入检测。未经人工批准的版本始终保持不可发布状态。</p></aside>
          </section>
        </div>
      ) : (
        <div className="sop-review-layout">
          <section className="sop-editor">
            <div className="section-heading"><div><span className="section-kicker">{version.code} · {version.version}</span><h2>{version.name}</h2></div><span>{version.steps.length} 个步骤</span></div>
            <div className="step-editor-list">
              {version.steps.map((step, index) => (
                <article className="step-editor" key={step.id || step.code}>
                  <span className="step-number">{String(index + 1).padStart(2, '0')}</span>
                  <div className="step-fields">
                    <label>步骤名称<input disabled={busy || !canEdit} onChange={(event) => updateStep(index, 'name', event.target.value)} value={step.name} /></label>
                    <label>视频证据要求<textarea disabled={busy || !canEdit} onChange={(event) => updateStep(index, 'evidenceRequirements', event.target.value)} rows={2} value={step.evidenceRequirements[0] ?? ''} /></label>
                    <blockquote><span>原文依据{step.sourceRefs[0]?.page ? ` · 第 ${step.sourceRefs[0].page} 页` : ''}</span>{step.sourceRefs[0]?.quote ?? '暂无原文引用'}</blockquote>
                  </div>
                </article>
              ))}
            </div>
          </section>
          <aside className="review-actions">
            <span className="section-kicker">审核决策</span><h2>{statusLabels[version.status]}</h2>
            <p>核对步骤顺序、操作名称、视频证据要求和原文引用。内容修改会写入修订记录。</p>
            {error && <p className="form-error" role="alert">{error}</p>}
            {canEdit && <button className="secondary-action" disabled={busy} onClick={save} type="button">保存修订</button>}
            {nextAction[version.status] && <button className="primary-action" disabled={busy} onClick={advance} type="button">{busy ? '处理中…' : nextAction[version.status]?.label}<Icon name="arrow" /></button>}
            {version.status === 'PUBLISHED' && <div className="published-note"><strong>版本已生效</strong><span>后续工单可选择此版本进行检测。</span></div>}
          </aside>
        </div>
      )}
    </div>
  )
}
