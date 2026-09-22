import type { ReactNode } from 'react'

export type IconName = 'overview' | 'document' | 'workOrder' | 'alert' | 'archive' | 'switch' | 'arrow'

const paths: Record<IconName, ReactNode> = {
  overview: <path d="M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-16v4h6V4h-6Z" />,
  document: <path d="M6 3h8l4 4v14H6V3Zm8 0v5h5M9 12h6M9 16h6" />,
  workOrder: <path d="M8 5H4v16h16V5h-4M8 3h8v5H8V3Zm0 10h8M8 17h5" />,
  alert: <path d="m12 3 9 17H3L12 3Zm0 6v5m0 3v.1" />,
  archive: <path d="M4 7h16v14H4V7Zm-1-4h18v4H3V3Zm6 9h6" />,
  switch: <path d="M5 8h13l-3-3m3 11H5l3 3" />,
  arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
}

export function Icon({ name }: { name: IconName }) {
  return <svg aria-hidden="true" className="icon" viewBox="0 0 24 24">{paths[name]}</svg>
}

export function BrandMark() {
  return (
    <svg aria-hidden="true" className="brand-mark" viewBox="0 0 48 48">
      <path d="M8 13h19M8 24h32M21 35h19" /><circle cx="32" cy="13" r="4" /><circle cx="16" cy="35" r="4" />
    </svg>
  )
}
