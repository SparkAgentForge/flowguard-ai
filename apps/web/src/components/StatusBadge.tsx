import type { ReactNode } from 'react'
import { AlertTriangle, Check, Circle, CircleAlert } from 'lucide-react'

type StatusTone = 'success' | 'warning' | 'neutral' | 'danger'

export function StatusBadge({ children, tone }: { children: ReactNode; tone: StatusTone }) {
  const Icon = { success: Check, warning: AlertTriangle, danger: CircleAlert, neutral: Circle }[tone]
  return <span className={`status-badge status-badge--${tone}`}><Icon size={13} aria-hidden="true" />{children}</span>
}
