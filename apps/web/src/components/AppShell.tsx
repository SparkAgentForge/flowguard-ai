import { NavLink, Outlet } from 'react-router-dom'

import { BrandMark, Icon, type IconName } from './Icons'

type NavigationItem = { label: string; path: string; icon: IconName; mobile: boolean }

const navigation: NavigationItem[] = [
  { label: '总览', path: '/', icon: 'overview', mobile: true },
  { label: 'SOP 中心', path: '/sops', icon: 'document', mobile: true },
  { label: '工单中心', path: '/work-orders', icon: 'workOrder', mobile: true },
  { label: '异常处置', path: '/exceptions', icon: 'alert', mobile: true },
  { label: '证据归档', path: '/reports', icon: 'archive', mobile: false },
]

function NavigationLink({ item }: { item: NavigationItem }) {
  return (
    <NavLink
      className={({ isActive }) => `navigation-link${isActive ? ' is-active' : ''}`}
      end={item.path === '/'}
      to={item.path}
    >
      <Icon name={item.icon} />
      <span>{item.label}</span>
    </NavLink>
  )
}

export function AppShell() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside className="sidebar">
        <NavLink className="brand" to="/" aria-label="FlowGuard AI 首页">
          <BrandMark />
          <span><strong>FlowGuard</strong><small>装配审计系统</small></span>
        </NavLink>
        <nav className="desktop-navigation" aria-label="主要导航">
          <p className="navigation-label">质量工作台</p>
          {navigation.map((item) => <NavigationLink item={item} key={item.path} />)}
        </nav>
        <a
          aria-label="在新标签页打开 FlowGuard AI GitHub 仓库"
          className="repository-link"
          href="https://github.com/SparkAgentForge/flowguard-ai"
          rel="noopener noreferrer"
          target="_blank"
        >
          <Icon name="github" />
          <span>GitHub 仓库</span>
          <span aria-hidden="true" className="external-mark">↗</span>
        </a>
        <div className="user-summary">
          <span className="avatar">质</span>
          <span><strong>质量工作台</strong><small>演示环境</small></span>
        </div>
      </aside>
      <div className="page-frame">
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
