import { Link } from 'react-router-dom'

import { Icon } from '../components/Icons'
import { StatusBadge } from '../components/StatusBadge'
import { WorkflowFigure } from '../components/WorkflowFigure'

const taskQueue = [
  { type: '异常确认', title: 'WO-2026-091 · 密封圈步骤未检测到', detail: 'A-03 工位 · 2 分钟前', tone: 'danger' as const },
  { type: 'SOP 审核', title: '泵体端盖装配 V1.3-r2', detail: 'AI 提取 4 个步骤 · 18 分钟前', tone: 'warning' as const },
  { type: '返工复核', title: 'WO-2026-084 · 返工视频已提交', detail: '操作员 07 · 34 分钟前', tone: 'neutral' as const },
]

const workOrders = [
  { code: 'WO-2026-090', product: 'PUMP-A01', station: 'A-03', status: '检测通过' },
  { code: 'WO-2026-089', product: 'PUMP-A01', station: 'A-02', status: '已归档' },
  { code: 'WO-2026-088', product: 'PUMP-B04', station: 'B-01', status: '人工复核' },
]

export function DashboardPage() {
  return (
    <div className="dashboard-page">
      <header className="page-heading">
        <div><p className="eyebrow">2026 年 9 月 22 日 · 晚班</p><h1>质量控制台</h1><p>先看证据，再作决定。当前有 3 项任务等待处理。</p></div>
        <Link className="primary-action" to="/work-orders">创建检测工单<Icon name="arrow" /></Link>
      </header>
      <section className="signal-grid" aria-label="今日质量概览">
        <article className="focus-signal">
          <span className="signal-index">01 / 审计队列</span><div className="focus-signal__number">3</div>
          <div><h2>项任务等待判断</h2><p>其中 1 项工单已自动阻断，需要班组长确认视频证据。</p></div>
          <Link to="/exceptions">进入处置台 <Icon name="arrow" /></Link>
        </article>
        <div className="metric-rail">
          <article><span>今日检测</span><strong>42</strong><small>较昨日 +6</small></article>
          <article><span>一次通过率</span><strong>95.2%</strong><small>目标 96%</small></article>
          <article><span>平均闭环</span><strong>18m</strong><small>缩短 4 分钟</small></article>
        </div>
      </section>
      <div className="dashboard-columns">
        <section className="work-section" aria-labelledby="queue-title">
          <div className="section-heading"><div><span className="section-kicker">需要你的判断</span><h2 id="queue-title">待办队列</h2></div><Link to="/exceptions">查看全部</Link></div>
          <div className="task-list">
            {taskQueue.map((task) => (
              <Link className="task-row" key={task.title} to="/exceptions">
                <StatusBadge tone={task.tone}>{task.type}</StatusBadge>
                <span className="task-row__content"><strong>{task.title}</strong><small>{task.detail}</small></span><Icon name="arrow" />
              </Link>
            ))}
          </div>
        </section>
        <section className="work-section flow-section" aria-labelledby="flow-title">
          <div className="section-heading"><div><span className="section-kicker">WO-2026-091</span><h2 id="flow-title">异常闭环进度</h2></div><StatusBadge tone="danger">工单已阻断</StatusBadge></div>
          <WorkflowFigure />
          <div className="evidence-note"><span>证据 02</span><p>第 2 步“安装绿色密封圈”在预期时间窗口内未被观察到。</p><time>00:09—00:18</time></div>
        </section>
      </div>
      <section className="work-section recent-section" aria-labelledby="recent-title">
        <div className="section-heading"><div><span className="section-kicker">最近 60 分钟</span><h2 id="recent-title">工单动态</h2></div><Link to="/work-orders">打开工单中心</Link></div>
        <div className="work-order-table" role="table" aria-label="最近工单">
          <div className="work-order-row work-order-row--head" role="row"><span role="columnheader">工单</span><span role="columnheader">产品</span><span role="columnheader">工位</span><span role="columnheader">状态</span></div>
          {workOrders.map((order) => (
            <Link className="work-order-row" key={order.code} role="row" to="/work-orders">
              <strong data-label="工单" role="cell">{order.code}</strong><span data-label="产品" role="cell">{order.product}</span><span data-label="工位" role="cell">{order.station}</span>
              <span data-label="状态" role="cell"><StatusBadge tone={order.status === '人工复核' ? 'warning' : 'success'}>{order.status}</StatusBadge></span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
