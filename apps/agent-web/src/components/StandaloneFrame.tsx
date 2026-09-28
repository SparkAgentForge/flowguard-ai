import type { ReactNode } from 'react'
import { ShieldCheck } from 'lucide-react'

export function StandaloneFrame({
  eyebrow,
  title,
  description,
  children,
  status,
}: {
  eyebrow: string
  title: string
  description?: string
  children: ReactNode
  status?: ReactNode
}) {
  return (
    <div className="standalone-shell">
      <header className="standalone-header">
        <a className="standalone-brand" href="/" aria-label="FlowGuard AI">
          <span className="brand-mark" aria-hidden="true"><ShieldCheck size={20} /></span>
          <span><strong>FlowGuard</strong><small>AI 审计结果</small></span>
        </a>
        <span className="standalone-status">{status ?? '结果展示'}</span>
      </header>
      <main className="standalone-main">
        <header className="standalone-heading">
          <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description && <p>{description}</p>}</div>
        </header>
        {children}
      </main>
      <footer className="standalone-footer">FlowGuard AI · 基于操作证据的质量审计</footer>
    </div>
  )
}

export function StatusPill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'success' | 'warning' | 'danger' | 'neutral' }) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <section className="state-panel state-panel--error"><strong>暂时无法显示</strong><p>{message}</p>{onRetry && <button className="button button--dark" onClick={onRetry} type="button">重新加载</button>}</section>
}

export function LoadingState({ label = '正在读取结果…' }: { label?: string }) {
  return <section className="state-panel"><span className="loading-dot" aria-hidden="true" /><strong>{label}</strong><p>请保持页面打开，数据准备好后会自动更新。</p></section>
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <section className="state-panel"><strong>{title}</strong><p>{detail}</p></section>
}

export function EmptyInline({ children }: { children: ReactNode }) {
  return <p className="empty-inline">{children}</p>
}
