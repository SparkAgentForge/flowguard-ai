import './styles.css'

function ProcessMark() {
  return (
    <svg aria-hidden="true" className="process-mark" viewBox="0 0 48 48">
      <path d="M8 13h19M8 24h32M21 35h19" />
      <circle cx="32" cy="13" r="4" />
      <circle cx="16" cy="35" r="4" />
    </svg>
  )
}

export default function App() {
  return (
    <main className="launch-screen">
      <section className="launch-panel" aria-labelledby="page-title">
        <div className="brand-line">
          <ProcessMark />
          <span>FlowGuard AI</span>
        </div>
        <p className="eyebrow">装配工序审计平台</p>
        <h1 id="page-title">让每一次放行，都有证据。</h1>
        <p className="summary">
          前后端工程已经就绪。下一验收点将接入 SOP、工单与审计状态模型。
        </p>
        <div className="system-status" role="status">
          <span className="status-dot" />
          本地开发环境可用
        </div>
      </section>
    </main>
  )
}
