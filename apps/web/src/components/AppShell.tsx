import { useState } from 'react'
import { Pin, PinOff } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { BrandMark, Icon, type IconName } from './Icons'

type NavigationItem = { label: string; path: string; icon: IconName; mobile: boolean }

const navigation: NavigationItem[] = [
  { label: '总览', path: '/', icon: 'overview', mobile: true },
  { label: 'SOP 中心', path: '/sops', icon: 'document', mobile: true },
  { label: '工单中心', path: '/work-orders', icon: 'workOrder', mobile: true },
  { label: '异常处置', path: '/exceptions', icon: 'alert', mobile: true },
  { label: '证据归档', path: '/reports', icon: 'archive', mobile: true },
]

function NavigationLink({ item, collapsed = false }: { item: NavigationItem; collapsed?: boolean }) {
  return (
    <NavLink
      className={({ isActive }) => `navigation-link${isActive ? ' is-active' : ''}`}
      end={item.path === '/'}
      to={item.path}
      aria-label={item.label}
      title={collapsed ? item.label : undefined}
    >
      <Icon name={item.icon} />
      <span>{item.label}</span>
    </NavLink>
  )
}

export function AppShell() {
  const [pinned, setPinned] = useState(() => {
    try { return localStorage.getItem('flowguard-sidebar-pinned') === 'true' }
    catch { return false }
  })
  const [hovered, setHovered] = useState(false)
  const [keyboardFocus, setKeyboardFocus] = useState(false)
  const collapsed = !pinned && !hovered && !keyboardFocus

  function togglePinned() {
    const next = !pinned
    setPinned(next)
    try { localStorage.setItem('flowguard-sidebar-pinned', String(next)) }
    catch { /* Pinning still works when browser storage is unavailable. */ }
  }
  const { pathname } = useLocation()
  const pageTitle = navigation.find((item) => item.path === pathname)?.label ?? '质量工作台'

  return (
    <div className={`app-shell${!pinned ? ' sidebar-auto' : ''}${collapsed ? ' sidebar-collapsed' : ''}`}>
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside
        className="sidebar"
        id="workspace-sidebar"
        onPointerEnter={(event) => { if (event.pointerType !== 'touch') setHovered(true) }}
        onPointerLeave={() => setHovered(false)}
        onPointerDown={() => setKeyboardFocus(false)}
        onFocusCapture={(event) => { if (event.target.matches(':focus-visible')) setKeyboardFocus(true) }}
        onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setKeyboardFocus(false) }}
      >
        <NavLink className="brand" to="/" aria-label="FlowGuard AI 首页">
          <BrandMark />
          <span><strong>FlowGuard</strong></span>
        </NavLink>
        <button className="sidebar-pin" type="button" onClick={togglePinned} aria-label={pinned ? '取消固定侧边栏' : '固定侧边栏'} title={pinned ? '取消固定侧边栏' : '固定侧边栏'} aria-pressed={pinned}>
          {pinned ? <PinOff size={17} /> : <Pin size={17} />}
          <span>{pinned ? '已固定' : '固定侧边栏'}</span>
        </button>
        <nav className="desktop-navigation" aria-label="主要导航">
          {navigation.map((item) => <NavigationLink item={item} key={item.path} collapsed={collapsed} />)}
        </nav>
        <a
          aria-label="在新标签页打开 FlowGuard AI GitHub 仓库"
          className="repository-link"
          title={collapsed ? 'GitHub 仓库' : undefined}
          href="https://github.com/SparkAgentForge/flowguard-ai"
          rel="noopener noreferrer"
          target="_blank"
        >
          <Icon name="github" />
          <span>GitHub 仓库</span>
          <span aria-hidden="true" className="external-mark">↗</span>
        </a>
      </aside>
      <div className="page-frame">
        <header className="workspace-header">
          <div className="workspace-header__navigation">
            <span>{pageTitle}</span>
          </div>
          <span className="environment-label">演示环境</span>
        </header>
        <header className="mobile-header">
          <NavLink className="brand" to="/" aria-label="FlowGuard AI 首页">
            <BrandMark /><strong>FlowGuard</strong>
          </NavLink>
          <div className="mobile-header__actions">
            <span className="mobile-role">演示环境</span>
            <a
              aria-label="在新标签页打开 FlowGuard AI GitHub 仓库"
              className="mobile-repository-link"
              href="https://github.com/SparkAgentForge/flowguard-ai"
              rel="noopener noreferrer"
              target="_blank"
            >
              <Icon name="github" />
            </a>
          </div>
        </header>
        <main id="main-content" className="main-content"><Outlet /></main>
      </div>
      <nav className="mobile-navigation" aria-label="移动端主要导航">
        {navigation.filter((item) => item.mobile).map((item) => <NavigationLink item={item} key={item.path} />)}
      </nav>
    </div>
  )
}
