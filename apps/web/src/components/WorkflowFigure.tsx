const stages = [
  { label: 'SOP 发布', state: 'done', x: 34 },
  { label: '视频检测', state: 'done', x: 118 },
  { label: '异常确认', state: 'active', x: 202 },
  { label: '返工复核', state: 'pending', x: 286 },
  { label: '报告归档', state: 'pending', x: 370 },
] as const

export function WorkflowFigure() {
  return (
    <figure className="workflow-figure">
      <svg aria-labelledby="workflow-title workflow-description" role="img" viewBox="0 0 404 96">
        <title id="workflow-title">异常工单处理进度</title>
        <desc id="workflow-description">SOP 已发布且视频检测已完成，当前等待异常确认。</desc>
        <path className="workflow-track" d="M34 36H370" /><path className="workflow-progress" d="M34 36H202" />
        {stages.map((stage, index) => (
          <g className={`workflow-node workflow-node--${stage.state}`} key={stage.label}>
            <circle cx={stage.x} cy="36" r="11" />
            {stage.state === 'done' ? <path d={`M${stage.x - 5} 36l3 3 6-7`} /> : <text x={stage.x} y="40">{index + 1}</text>}
            <text className="workflow-label" x={stage.x} y="72">{stage.label}</text>
          </g>
        ))}
      </svg>
    </figure>
  )
}
