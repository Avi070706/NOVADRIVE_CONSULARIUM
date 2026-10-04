import React from 'react'
import { readClass, riskColor, short, useApp } from '../store'

export const Grade = ({ g }: { g?: string | null }) =>
  g ? <span className={`grade ${g}`} title={`Evidence grade ${g}`}>{g}</span> : <span className="muted">–</span>

export const Reading = ({ r }: { r?: string }) => <span className={`tag ${readClass(r)}`}>{r}</span>

export const Risk = ({ v, size = 18 }: { v: number; size?: number }) =>
  <span className="num" style={{ color: riskColor(v), fontSize: size }}>{v}</span>

export function RiskBar({ v, w = 120 }: { v: number; w?: number }) {
  return <div className="bar" style={{ width: w }}><i style={{ width: `${v}%`, background: riskColor(v) }} /></div>
}

export function NodeChip({ id }: { id: string }) {
  const { nodes, open } = useApp()
  const n = nodes[id]
  if (!n) return null
  return <span className="chip click" onClick={e => { e.stopPropagation(); open({ type: 'node', id }) }} style={{ borderLeft: `4px solid ${riskColor(n.risk)}` }}>{short(n)}</span>
}

export function Tip({ tip }: { tip: { x: number; y: number; html: React.ReactNode } | null }) {
  if (!tip) return null
  return <div className="tip" style={{ left: Math.min(tip.x + 14, window.innerWidth - 300), top: tip.y + 14 }}>{tip.html}</div>
}

export function Verdict({ e }: { e: any }) {
  const cls = e.verdict === 'Alert' ? (e.priority === 1 ? 'alert1' : 'alert2') : e.verdict === 'Watch' ? 'watch' : 'dim'
  return <span className={`tag ${cls}`}>{e.verdict === 'Alert' && e.priority ? `Priority ${e.priority} alert` : e.verdict}</span>
}
