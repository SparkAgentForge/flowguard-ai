import type { ReactNode } from 'react'

type StatusTone = 'success' | 'warning' | 'neutral' | 'danger'

export function StatusBadge({ children, tone }: { children: ReactNode; tone: StatusTone }) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>
}
