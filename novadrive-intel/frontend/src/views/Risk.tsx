import React, { useState } from 'react'
import { money, readClass, riskColor, short, useApp } from '../store'
import { Grade, Reading, Tip } from '../components/ui'

export default function Risk() {
  const { d, open } = useApp()
  const [tier, setTier] = useState('all')
  const rows = [...d.nodes].filter((n: any) => n.rank < 999 && (tier === 'all' || n.tier === +tier)).sort((a: any, b: any) => a.rank - b.rank)
  const count = (r: string) => d.nodes.filter((n: any) => readClass(n.reading) === r).length
  return (
    <div className="page">
      <div className="pagehead">
        <div><h1>{count('act')} nodes to act on, {count('verify')} to verify first</h1><p>Act needs high risk and strong evidence; verify means high risk on thin evidence.</p></div>
        <span className="grow" />
        <div className="row" style={{ gap: 6 }}>{[['act', 'Act'], ['verify', 'Verify'], ['monitor', 'Monitor'], ['routine', 'Routine']].map(([k, l]) => <span key={k} className={`tag ${k}`} style={{ fontSize: 13, padding: '4px 10px' }}>{count(k)} {l}</span>)}</div>
      </div>
      <div className="g split" style={{ gridTemplateColumns: 'minmax(0,1.15fr) minmax(0,1fr)', alignItems: 'start' }}>
        <section className="panel">
          <div className="ph"><h2>Scorecard</h2><span className="grow" />
            <div className="seg">{['all', '1', '2', '3'].map(t => <button key={t} className={tier === t ? 'on' : ''} onClick={() => setTier(t)}>{t === 'all' ? 'All' : `T${t}`}</button>)}</div></div>
          <div className="pb" style={{ paddingTop: 4 }}>
            <table className="t">
              <thead><tr><th>#</th><th>Node</th><th>Tier</th><th>Risk</th><th>Conf.</th><th>Reading</th><th className="r">Exposed</th></tr></thead>
              <tbody>{rows.map((n: any) => (
                <tr key={n.id} className="click" onClick={() => open({ type: 'node', id: n.id })}>
                  <td className="muted">{n.rank}</td>
                  <td style={{ fontWeight: 600 }}>{n.label}</td>
                  <td>T{n.tier}</td>
                  <td><div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}><div className="bar" style={{ width: 90, height: 9 }}><i style={{ width: `${n.risk}%`, background: riskColor(n.risk) }} /></div><b className="num" style={{ color: riskColor(n.risk), fontSize: 16 }}>{n.risk}</b></div></td>
                  <td><Grade g={n.grade} /></td>
                  <td><Reading r={n.reading} /></td>
                  <td className="r small">{n.rev ? money(n.rev) : '–'}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </section>
        <div className="g">
          <section className="panel"><div className="ph"><h2>Risk vs evidence strength</h2><span>bubble size = revenue exposed</span></div><div className="pb"><Matrix /></div></section>
          <section className="panel"><div className="ph"><h2>How we score</h2></div>
            <div className="pb" style={{ display: 'grid', gap: 7 }}>
              {d.team.weights.map((w: any) => (
                <div key={w.Factor} style={{ display: 'grid', gridTemplateColumns: '52px 160px 1fr', gap: 10, alignItems: 'center' }}>
                  <span style={{ background: 'var(--ok)', color: '#fff', fontWeight: 800, textAlign: 'center', borderRadius: 6, padding: '3px 0' }}>{Math.round(w.Weight * 100)}%</span>
                  <b style={{ fontSize: 13.5 }}>{w.Factor}</b><span className="small muted">{w['What it measures']}</span>
                </div>))}
              <div className="banner" style={{ marginTop: 6 }}><b>Missing data = unknown, never low risk.</b> Weights are re-normalised and the gap is flagged.</div>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function Matrix() {
  const { d, open } = useApp()
  const [tip, setTip] = useState<any>(null)
  const G = ['A', 'B', 'C', 'D']
  const W = 560, H = 330, L = 40, B = 34, T = 10
  const x = (g: string) => L + ((G.indexOf(g) + 0.5) / 4) * (W - L - 10)
  const y = (r: number) => T + (1 - (r - 25) / 70) * (H - T - B)
  const pts = d.nodes.filter((n: any) => n.grade)
  // bee-swarm: place each bubble at the nearest free horizontal offset inside its grade column
  const R = (n: any) => 5 + 6 * Math.sqrt(n.rev_share)
  const placed: { x: number; y: number; r: number }[] = []
  const xy: Record<string, [number, number]> = {}
  ;[...pts].sort((a: any, b: any) => b.risk - a.risk).forEach((n: any) => {
    const cy = y(n.risk), r = R(n)
    for (const o of [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5]) {
      const cx = x(n.grade) + o * 15
      if (!placed.some(p => Math.hypot(p.x - cx, p.y - cy) < p.r + r + 2)) { placed.push({ x: cx, y: cy, r }); xy[n.id] = [cx, cy]; break }
    }
    if (!xy[n.id]) xy[n.id] = [x(n.grade), cy]
  })
  const labelled = new Set(pts.filter((n: any) => n.risk >= 70 || readClass(n.reading) === 'act').map((n: any) => n.id))
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%">
        <rect x={L} y={y(95)} width={(W - L - 10) / 2} height={y(65) - y(95)} fill="var(--r3-bg)" rx={6} />
        <rect x={L + (W - L - 10) / 2} y={y(95)} width={(W - L - 10) / 2} height={y(65) - y(95)} fill="var(--r1-bg)" rx={6} />
        <text x={L + 10} y={y(92)} fontSize="13" fontWeight="800" fill="var(--r3)">ACT — strong evidence</text>
        <text x={W - 18} y={y(92)} fontSize="13" fontWeight="800" fill="#8a6a12" textAnchor="end">VERIFY — thin evidence</text>
        {[30, 50, 70, 90].map(v => <g key={v}><line x1={L} x2={W - 10} y1={y(v)} y2={y(v)} stroke="var(--line-2)" /><text x={L - 8} y={y(v) + 4} fontSize="11" fill="var(--ink-3)" textAnchor="end">{v}</text></g>)}
        {G.map(g => <text key={g} x={x(g)} y={H - 12} textAnchor="middle" fontSize="13" fontWeight="800" fill="var(--c3)">Grade {g}</text>)}
        {pts.map((n: any) => { const r = R(n); const [cx, cy] = xy[n.id]
          return <g key={n.id} style={{ cursor: 'pointer' }} onClick={() => open({ type: 'node', id: n.id })}
            onMouseEnter={e => setTip({ x: e.clientX, y: e.clientY, html: <div><b>{short(n)}</b><br />Risk {n.risk} · grade {n.grade} · {n.reading}</div> })} onMouseLeave={() => setTip(null)}>
            <circle cx={cx} cy={cy} r={r} fill={riskColor(n.risk)} fillOpacity={0.85} stroke="#fff" strokeWidth="1.5" />
            {labelled.has(n.id) && n.grade === 'A' && <text x={cx + r + 4} y={cy + 4} fontSize="11" fontWeight="650" fill="var(--ink)">{short(n).split(' ')[0]}</text>}
          </g> })}
      </svg>
      <Tip tip={tip} />
    </>
  )
}
