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
        <section className="station-panel" aria-label="当前工位">
          <div className="station-panel__heading"><span className="live-indicator" />工位在线</div>
          <strong>泵体端盖 · A-03</strong><span>最后同步 16:42</span>
          <svg aria-hidden="true" viewBox="0 0 180 36">
            <path d="M2 25h18l7-12 12 18 13-8 11 2 13-17 12 20 12-9 16 5 12-13 13 14 15-5 22 2" />
          </svg>
        </section>
        <div className="user-summary">
          <span className="avatar">质</span>
          <span><strong>质量演示账号</strong><small>质检员</small></span>
          <button aria-label="切换角色" className="icon-button" type="button"><Icon name="switch" /></button>
        </div>
      </aside>
      <div className="page-frame">
        <header className="mobile-header">
          <NavLink className="brand" to="/" aria-label="FlowGuard AI 首页">
            <BrandMark /><strong>FlowGuard</strong>
          </NavLink>
          <span className="mobile-role">质检员</span>
        </header>
        <main id="main-content" className="main-content"><Outlet /></main>
      </div>
      <nav className="mobile-navigation" aria-label="移动端主要导航">
        {navigation.filter((item) => item.mobile).map((item) => <NavigationLink item={item} key={item.path} />)}
      </nav>
    </div>
  )
}
