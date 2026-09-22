import { Link } from 'react-router-dom'

import { Icon } from '../components/Icons'

export function PlaceholderPage({ section }: { section: string }) {
  return (
    <section className="placeholder-page">
      <div className="placeholder-figure" aria-hidden="true">
        <svg viewBox="0 0 320 190"><path className="placeholder-grid" d="M30 35h260M30 85h260M30 135h260M80 15v155M160 15v155M240 15v155" /><path className="placeholder-path" d="M42 135 93 85l50 20 61-70 76 50" /><circle cx="42" cy="135" r="8" /><circle cx="93" cy="85" r="8" /><circle cx="143" cy="105" r="8" /><circle cx="204" cy="35" r="8" /><circle cx="280" cy="85" r="8" /></svg>
      </div>
      <p className="eyebrow">模块正在接入</p><h1>{section}</h1><p>基础工作台已经就绪，此模块将在对应验收点接入真实数据与操作流程。</p>
      <Link className="text-action" to="/">返回质量控制台 <Icon name="arrow" /></Link>
    </section>
  )
}
