import { Link } from 'react-router-dom'

import { StandaloneFrame } from '../components/StandaloneFrame'

export function NotFoundPage() {
  return <StandaloneFrame eyebrow="链接不可用" title="找不到这个结果页面" description="请检查链接中的业务 ID，或让 AI 重新返回结果链接。">
    <section className="state-panel"><strong>404 · 页面不存在</strong><p>结果页面不会猜测或替换缺失的工单、审计和异常 ID。</p><Link className="button button--dark" to="/">返回入口</Link></section>
  </StandaloneFrame>
}
