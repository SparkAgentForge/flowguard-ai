import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ClipboardCheck, FileText, ListChecks } from 'lucide-react'

import { StatusBadge } from '../components/StatusBadge'
import { listExceptions, listSops, listWorkOrders, type ExceptionCase, type SopVersionSummary, type WorkOrder } from '../lib/api'
import { workOrderStatusLabels, workOrderStatusTone } from '../lib/presentation'

const openStatuses = new Set(['PENDING', 'MANUAL_REVIEW', 'CONFIRMED', 'REWORK_ASSIGNED', 'REWORK_SUBMITTED', 'REWORK_REVIEW'])

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

export function DashboardPage() {
  const [orders, setOrders] = useState<WorkOrder[]>([])
  const [exceptions, setExceptions] = useState<ExceptionCase[]>([])
  const [sops, setSops] = useState<SopVersionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState('')

  useEffect(() => {
    Promise.all([listWorkOrders(), listExceptions(), listSops(true)])
      .then(([nextOrders, nextExceptions, nextSops]) => {
        setOrders(nextOrders)
        setExceptions(nextExceptions)
        setSops(nextSops)
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : '无法读取工作台数据'))
      .finally(() => setLoading(false))
  }, [])

  const activeExceptions = exceptions.filter((item) => openStatuses.has(item.status))
  const reviewSops = sops.filter((item) => item.status !== 'PUBLISHED')
  const queue = [
    ...activeExceptions.map((item) => ({
      id: `exception-${item.id}`,
      type: item.status === 'MANUAL_REVIEW' ? '证据复核' : item.status.startsWith('REWORK') ? '返工跟进' : '异常处置',
      title: item.workOrderCode,
      detail: item.audit.summary,
      to: `/exceptions?id=${item.id}`,
      tone: ['PENDING', 'CONFIRMED'].includes(item.status) ? 'danger' as const : 'warning' as const,
      facts: item.facts,
      next: item.status.startsWith('REWORK') ? '查看返工进展，对照原 SOP 完成复核。' : '核对视频证据，填写依据后提交人工决定。',
    })),
    ...reviewSops.map((item) => ({
      id: `sop-${item.id}`,
      type: 'SOP 审核',
      title: `${item.name} / ${item.version}`,
      detail: item.status === 'APPROVED' ? '待发布' : '待确认步骤',
      to: `/sops?id=${item.id}`,
      tone: 'neutral' as const,
      facts: [`SOP 编号：${item.code}`, `产品型号：${item.productCode}`],
      next: '检查操作步骤与证据要求，审核通过后发布。',
    })),
  ]
  const selected = queue.find((item) => item.id === selectedId) ?? queue[0]
  const firstUse = !loading && !error && !orders.length && !sops.length

  return (
    <div className="dashboard-page">
      <header className="page-heading">
        <div><h1>质量工作台</h1></div>
        <Link className="primary-action" to="/work-orders">创建检测工单<ArrowRight size={17} /></Link>
      </header>
      {error && <p className="form-error" role="alert">{error}</p>}
      <section className="overview-metrics" aria-label="工作概览">
        <article className={queue.length ? 'needs-attention' : ''}><span>待处理事项</span><strong>{loading || error ? '—' : queue.length}</strong><small>异常 {activeExceptions.length} · SOP 审核 {reviewSops.length}</small></article>
        <article><span>工单总数</span><strong>{loading || error ? '—' : orders.length}</strong></article>
        <article><span>检测通过</span><strong>{loading || error ? '—' : orders.filter((item) => ['VERIFIED', 'RELEASED', 'ARCHIVED'].includes(item.status)).length}</strong><small>含返工放行</small></article>
        <article><span>待复核工单</span><strong>{loading || error ? '—' : orders.filter((item) => ['MANUAL_REVIEW', 'REWORK_SUBMITTED', 'REWORK_REVIEW'].includes(item.status)).length}</strong></article>
      </section>
      {firstUse && <section className="getting-started" aria-labelledby="start-title">
        <div className="getting-started__intro"><span className="empty-symbol"><ClipboardCheck size={22} /></span><div><h2 id="start-title">尚未导入 SOP</h2></div><Link className="secondary-action" to="/sops">上传 SOP<ArrowRight size={15} /></Link></div>
      </section>}
      <div className="dashboard-columns">
        <section className="work-section queue-section" aria-labelledby="queue-title">
          <div className="section-heading"><h2 id="queue-title">待处理事项 <span className="section-count">{loading || error ? '—' : queue.length}</span></h2><Link to="/exceptions">查看异常<ArrowRight size={14} /></Link></div>
          {queue.length ? <div className="task-list">{queue.slice(0, 6).map((task) => (
            <button type="button" className={`task-row${selected?.id === task.id ? ' is-selected' : ''}`} key={task.id} onClick={() => setSelectedId(task.id)} aria-pressed={selected?.id === task.id} aria-controls="task-summary">
              <span className="task-row__content"><strong>{task.title}</strong><small>{task.detail}</small></span>
              <StatusBadge tone={task.tone}>{task.type}</StatusBadge><ArrowRight size={15} />
            </button>
          ))}</div> : <div className="workspace-empty"><ListChecks size={25} aria-hidden="true" /><h3>{loading ? '正在加载待办…' : error ? '待办加载失败' : '暂无待处理事项'}</h3>{error && <p>请刷新页面后重试。</p>}</div>}
        </section>
        <section id="task-summary" className="work-section summary-section" aria-labelledby="focus-title" aria-live="polite">
          <div className="section-heading"><h2 id="focus-title">事项摘要</h2>{selected && <StatusBadge tone={selected.tone}>{selected.type}</StatusBadge>}</div>
          {selected ? <div className="current-exception">
            <strong>{selected.title}</strong><p>{selected.detail}</p>
            {selected.facts.length > 0 && <ul>{selected.facts.slice(0, 3).map((fact, index) => <li key={`${index}-${fact}`}>{fact}</li>)}</ul>}
            <div className="next-step"><span>下一步</span><p>{selected.next}</p></div>
            <Link className="primary-action" to={selected.to}>查看并处理<ArrowRight size={15} /></Link>
          </div> : <div className="workspace-empty"><FileText size={25} aria-hidden="true" /><h3>请选择一条待办</h3></div>}
        </section>
      </div>
      <section className="work-section recent-section" aria-labelledby="recent-title">
        <div className="section-heading"><h2 id="recent-title">最近工单</h2><Link to="/work-orders">打开工单中心</Link></div>
        {orders.length ? <div className="work-order-table" role="table" aria-label="最近工单">
          <div className="work-order-row work-order-row--head" role="row"><span role="columnheader">工单</span><span role="columnheader">产品</span><span role="columnheader">更新时间</span><span role="columnheader">状态</span></div>
          {orders.slice(0, 6).map((order) => <Link className="work-order-row" key={order.id} role="row" to={`/work-orders?id=${order.id}`}>
            <strong data-label="工单" role="cell">{order.code}</strong><span data-label="产品" role="cell">{order.productCode}</span><span data-label="更新时间" role="cell">{formatTime(order.updatedAt)}</span>
            <span data-label="状态" role="cell"><StatusBadge tone={workOrderStatusTone(order.status)}>{workOrderStatusLabels[order.status] ?? order.status}</StatusBadge></span>
          </Link>)}
        </div> : <p className="section-empty">{loading ? '正在加载…' : error ? '工单加载失败，请刷新重试。' : '暂无工单'}</p>}
      </section>
    </div>
  )
}
