import { ArrowUpRight, ClipboardCheck, FileText, Flag, FolderArchive } from 'lucide-react'

import { StandaloneFrame } from '../components/StandaloneFrame'

const cards = [
  { href: '/sop/填写版本ID', icon: FileText, title: 'SOP 展示', detail: '查看已发布的操作步骤和证据要求。' },
  { href: '/audit/填写工单ID/填写审计ID', icon: ClipboardCheck, title: '视频审计结果', detail: '查看视频、步骤时间线和证据判定。' },
  { href: '/exception/填写异常ID', icon: Flag, title: '异常与返工复核', detail: '处理异常、提交返工并查看复核结果。' },
  { href: '/report/填写工单ID', icon: FolderArchive, title: '报告归档', detail: '查看报告事实、哈希和 PDF 文件。' },
]

export function LandingPage() {
  return (
    <StandaloneFrame eyebrow="独立结果入口" title="FlowGuard AI" description="选择一个展示页面，或让 AI 直接返回本次审计的结果链接。">
      <section className="entry-grid" aria-label="结果页面入口">
        {cards.map(({ href, icon: Icon, title, detail }) => <a className="entry-card" href={href} key={title}>
          <span className="entry-card__icon"><Icon size={22} /></span>
          <span><strong>{title}</strong><small>{detail}</small></span>
          <ArrowUpRight size={18} />
        </a>)}
      </section>
      <p className="page-note">此页面仅用于主动选择入口。AI 返回的审计页面会直接打开对应结果，不经过导航页。</p>
    </StandaloneFrame>
  )
}
