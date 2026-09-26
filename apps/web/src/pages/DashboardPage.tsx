import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

import { StatusBadge } from '../components/StatusBadge'
import { listExceptions, listSops, listWorkOrders, type ExceptionCase, type SopVersionSummary, type WorkOrder } from '../lib/api'
import { auditDecisionLabels, workOrderStatusLabels } from '../lib/presentation'

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
      id: item.id,
      type: item.status === 'MANUAL_REVIEW' ? '证据复核' : item.status === 'REWORK_ASSIGNED' ? '返工跟进' : '异常处置',
      title: item.workOrderCode,
      detail: item.audit.summary,
      to: `/exceptions?id=${item.id}`,
      tone: item.status === 'MANUAL_REVIEW' ? 'warning' as const : 'danger' as const,
    })),
    ...reviewSops.map((item) => ({
      id: item.id,
      type: 'SOP 审核',
      title: `${item.name} / ${item.version}`,
      detail: item.status === 'APPROVED' ? '待发布' : '待确认步骤',
      to: `/sops?id=${item.id}`,
      tone: 'neutral' as const,
    })),
  ]
  const recentException = activeExceptions[0]

  return (
    <div className="dashboard-page">
      <header className="page-heading">
        <div><p className="eyebrow">质量工作台</p><h1>质量控制台</h1></div>
        <Link className="primary-action" to="/work-orders">创建检测工单<ArrowRight size={17} /></Link>
      </header>
      {error && <p className="form-error" role="alert">{error}</p>}
      <section className="signal-grid" aria-label="工作概览">
        <article className="focus-signal">
          <span className="signal-index">待处理</span><div className="focus-signal__number">{loading ? '–' : queue.length}</div>
          <div><h2>项需要判断</h2><p>{activeExceptions.length} 项异常 · {reviewSops.length} 个待发布 SOP</p></div>
          <Link to={activeExceptions.length ? '/exceptions' : '/sops'}>打开队列 <ArrowRight size={17} /></Link>
        </article>
        <div className="metric-rail">
          <article><span>工单总数</span><strong>{loading ? '–' : orders.length}</strong><small>全部记录</small></article>
          <article><span>检测通过</span><strong>{loading ? '–' : orders.filter((item) => ['VERIFIED', 'RELEASED', 'ARCHIVED'].includes(item.status)).length}</strong><small>含返工放行</small></article>
          <article><span>待复核</span><strong>{loading ? '–' : orders.filter((item) => item.status === 'MANUAL_REVIEW' || item.status === 'REWORK_SUBMITTED').length}</strong><small>需要人工处理</small></article>
        </div>
      </section>
      <div className="dashboard-columns">
        <section className="work-section" aria-labelledby="queue-title">
          <div className="section-heading"><div><span className="section-kicker">工作队列</span><h2 id="queue-title">待办事项</h2></div><Link to="/exceptions">查看异常</Link></div>
          {queue.length ? <div className="task-list">{queue.slice(0, 6).map((task) => (
            <Link className="task-row" key={`${task.type}-${task.id}`} to={task.to}>
              <StatusBadge tone={task.tone}>{task.type}</StatusBadge>
              <span className="task-row__content"><strong>{task.title}</strong><small>{task.detail}</small></span><ArrowRight size={17} />
            </Link>
          ))}</div> : <p className="section-empty">{loading ? '正在加载…' : '目前没有待处理事项。'}</p>}
        </section>
        <section className="work-section flow-section" aria-labelledby="focus-title">
          <div className="section-heading"><div><span className="section-kicker">最新异常</span><h2 id="focus-title">证据核对</h2></div>{recentException && <StatusBadge tone="warning">{auditDecisionLabels[recentException.decision]}</StatusBadge>}</div>
          {recentException ? <div className="current-exception">
            <strong>{recentException.workOrderCode}</strong>
            <p>{recentException.audit.summary}</p>
            <ul>{recentException.facts.slice(0, 3).map((fact, index) => <li key={`${index}-${fact}`}>{fact}</li>)}</ul>
            <Link className="text-action" to={`/exceptions?id=${recentException.id}`}>查看并处理 <ArrowRight size={17} /></Link>
          </div> : <p className="section-empty">{loading ? '正在加载…' : '当前没有待处理异常。'}</p>}
        </section>
      </div>
      <section className="work-section recent-section" aria-labelledby="recent-title">
        <div className="section-heading"><div><span className="section-kicker">最新记录</span><h2 id="recent-title">工单动态</h2></div><Link to="/work-orders">打开工单中心</Link></div>
        {orders.length ? <div className="work-order-table" role="table" aria-label="最近工单">
          <div className="work-order-row work-order-row--head" role="row"><span role="columnheader">工单</span><span role="columnheader">产品</span><span role="columnheader">更新时间</span><span role="columnheader">状态</span></div>
          {orders.slice(0, 6).map((order) => <Link className="work-order-row" key={order.id} role="row" to={`/work-orders?id=${order.id}`}>
            <strong data-label="工单" role="cell">{order.code}</strong><span data-label="产品" role="cell">{order.productCode}</span><span data-label="更新时间" role="cell">{formatTime(order.updatedAt)}</span>
            <span data-label="状态" role="cell"><StatusBadge tone={['VERIFIED', 'RELEASED', 'ARCHIVED'].includes(order.status) ? 'success' : 'warning'}>{workOrderStatusLabels[order.status] ?? order.status}</StatusBadge></span>
          </Link>)}
        </div> : <p className="section-empty">{loading ? '正在加载…' : '还没有工单记录。'}</p>}
      </section>
    </div>
  )
}
