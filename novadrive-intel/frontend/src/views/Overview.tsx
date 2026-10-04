import React, { useMemo, useState } from 'react'
import { money, readClass, riskColor, short, useApp } from '../store'
import { Grade, NodeChip, Reading, Verdict } from '../components/ui'
import { keyFacts } from '../components/Inspector'

export default function Overview() {
  return (
    <div className="page">
      <div className="g split" style={{ gridTemplateColumns: 'minmax(0,1.55fr) minmax(0,1fr)' }}>
        <Decisions />
        <Alerts />
      </div>
      <div className="g split" style={{ gridTemplateColumns: 'minmax(0,1.85fr) minmax(0,1fr)', marginTop: 16 }}>
        <Convergence />
        <TopRisks />
      </div>
      <div className="g split" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.3fr)', marginTop: 16 }}>
        <ProductExposure />
        <DualSourcing />
      </div>
    </div>
  )
}

function Decisions() {
  const { d, nodes, open, go, setTarget, setSignal } = useApp()
  return (
    <section className="panel">
      <div className="ph"><h2>Decisions needed</h2><span>ranked; click a supplier for the full picture</span></div>
      <div className="pb" style={{ display: 'grid', gap: 10 }}>
        {d.team.priorities.map((p: any) => {
          const ids = String(p.Nodes || '').split(',').map((s: string) => s.trim()).filter((k: string) => nodes[k])
          const ns = ids.map(k => nodes[k])
          const prods = Array.from(new Set(ns.flatMap((n: any) => n.products))).sort() as string[]
          const rev = d.products.filter((x: any) => prods.includes(x.id)).reduce((a: number, x: any) => a + x.revenue, 0)
          const evs = Array.from(new Set(ns.flatMap((n: any) => n.events))) as string[]
          const lead = ns.find((n: any) => keyFacts(n, d, nodes).length)
          const why = p.Why || (lead ? keyFacts(lead, d, nodes)[0].t : '')
          const worst = Math.max(...ns.map((n: any) => n.risk))
          return (
            <div key={p.Priority} style={{ display: 'grid', gridTemplateColumns: '34px 1fr auto', gap: 14, padding: '12px 14px', border: '1px solid var(--line)', borderLeft: `4px solid ${riskColor(worst)}`, borderRadius: 5 }}>
              <span className="num" style={{ fontSize: 26, color: 'var(--ink-3)', lineHeight: 1 }}>{p.Priority}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 15 }}>{p.Action}</div>
                <div className="small" style={{ color: 'var(--ink-2)', margin: '3px 0 7px' }}>{why}</div>
                <div className="row" style={{ gap: 5 }}>
                  {ids.map(k => <NodeChip key={k} id={k} />)}
                  {evs.map(e => <span key={e} className="chip sig click" onClick={() => { setSignal(e); go('signals') }}>{e}</span>)}
                </div>
              </div>
              <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
                <div><b className="num" style={{ fontSize: 22 }}>{money(rev)}</b><div className="small muted">{prods.join(' ')} at stake</div></div>
                {p.Priority === 2 || /second-source|alternat/i.test(p.Action)
                  ? <button className="btn pri" onClick={() => { setTarget(ids[0]); go('sourcing') }}>See alternatives</button>
                  : <button className="btn" onClick={() => open({ type: 'node', id: ids[0] })}>Details</button>}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function Alerts() {
  const { d, go, setSignal, nodes } = useApp()
  const live = d.events.filter((e: any) => e.verdict === 'Alert' || e.verdict === 'Watch').sort((a: any, b: any) => (a.priority || 9) - (b.priority || 9))
  const cnt = (v: string) => d.events.filter((e: any) => e.verdict === v).length
  return (
    <section className="panel">
      <div className="ph"><h2>Live signals</h2><span>{d.events.length} received, {cnt('Alert')} alerts</span><span className="grow" /><button className="btn link" onClick={() => go('signals')}>All signals</button></div>
      <div className="pb" style={{ display: 'grid', gap: 0 }}>
        {live.map((e: any) => (
          <div key={e.id} onClick={() => { setSignal(e.id); go('signals') }} style={{ cursor: 'pointer', padding: '11px 0', borderBottom: '1px solid var(--line-2)' }}>
            <div className="row" style={{ justifyContent: 'space-between' }}><Verdict e={e} /><span className="small muted">{e.id} · {e.published}</span></div>
            <div style={{ fontWeight: 700, margin: '5px 0 3px', fontSize: 14.5 }}>{e.brief?.Title || e.title}</div>
            {e.matched?.length > 0
              ? <div className="small" style={{ color: 'var(--ink-2)' }}>{e.matched.length} plant{e.matched.length > 1 ? 's' : ''} ({e.matched.slice(0, 3).map((k: string) => short(nodes[k]).split(' ')[0]).join(', ')}{e.matched.length > 3 ? '…' : ''}) → {e.products.join(', ')} · <b>{money(e.exposure)}</b> · {e.impact_status?.toLowerCase()}</div>
              : <div className="small" style={{ color: 'var(--ink-2)' }}>{e.ours}</div>}
          </div>
        ))}
        <div className="row small muted" style={{ marginTop: 10, gap: 14 }}>
          <span>Filtered out:</span><span><b style={{ color: 'var(--ink)' }}>{cnt('Suppressed')}</b> false or stale</span><span><b style={{ color: 'var(--ink)' }}>{cnt('Merged')}</b> duplicate</span><span><b style={{ color: 'var(--ink)' }}>{cnt('No action')}</b> no supply impact</span>
        </div>
      </div>
    </section>
  )
}

function Convergence() {
  const { d, nodes, open } = useApp()
  const [hv, setHv] = useState<string | null>(null)
  const expo: string[] = (d.team.headline.exposure_nodes?.value || '').split(',').map((s: string) => s.trim()).filter((k: string) => nodes[k])
  const up = useMemo(() => {
    const conv = d.nodes.filter((n: any) => n.tier === 2 && n.tier1.length > 1 && !expo.includes(n.id)).sort((a: any, b: any) => b.risk - a.risk).slice(0, 3)
    return [...expo.map((k: string) => nodes[k]), ...conv]
  }, [d])
  const t1 = d.nodes.filter((n: any) => n.tier === 1 && n.status === 'confirmed').sort((a: any, b: any) => (a.components[0] || '').localeCompare(b.components[0] || ''))
  const W = 860, H = 350, top = 40
  const X = [150, 390, 590, 700]
  const y = (i: number, n: number) => top + ((H - top - 6) * (i + 0.5)) / n
  const P: Record<string, number[]> = {}
  up.forEach((n: any, i: number) => (P[n.id] = [X[0], y(i, up.length)]))
  t1.forEach((n: any, i: number) => (P[n.id] = [X[1], y(i, t1.length)]))
  d.components.forEach((c: any, i: number) => (P[c.id] = [X[2], y(i, d.components.length)]))
  let acc = top + 4
  const sp = H - top - 10 - 2 * 10
  d.products.forEach((p: any) => { const hh = (p.revenue / d.total) * sp; P[p.id] = [X[3], acc, hh]; acc += hh + 10 })
  const cv = (a: number[], b: number[]) => { const m = (a[0] + b[0]) / 2; return `M${a[0]},${a[1]} C${m},${a[1]} ${m},${b[1]} ${b[0]},${b[1]}` }
  const H_ = hv ? nodes[hv] : null
  const hot = new Set<string>(H_ ? [H_.id, ...H_.tier1, ...H_.components, ...H_.products] : [])
  const on = (k: string) => !H_ || hot.has(k)
  return (
    <section className="panel">
      <div className="ph"><h2>Where the exposure converges</h2><span>8 Tier-1 suppliers draw on a few shared upstream plants; hover one to trace it</span></div>
      <div className="pb" style={{ paddingTop: 0 }}>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', maxHeight: 380 }}>
          <style>{`.dr{stroke-dasharray:500;stroke-dashoffset:500;animation:dr 1s ease-out forwards}@keyframes dr{to{stroke-dashoffset:0}}`}</style>
          {[['Upstream plants', X[0] - 130], ['Tier-1 suppliers', X[1] - 68], ['Parts', X[2] - 22], ['Products', X[3]]].map(([t, x]) => <text key={t} x={x} y={16} fontSize="12" fontWeight="700" fill="var(--ink-2)">{t}</text>)}
          {d.components.map((c: any) => c.products.map((p: string) => <path key={c.id + p} d={cv([P[c.id][0] + 24, P[c.id][1]], [X[3], P[p][1] + P[p][2] / 2])} fill="none" stroke={on(c.id) && on(p) ? '#a9b7c4' : '#eef1f4'} strokeWidth="1.2" />))}
          {t1.map((n: any) => n.components.map((c: string) => <path key={n.id + c} d={cv([P[n.id][0] + 68, P[n.id][1]], [P[c][0] - 24, P[c][1]])} fill="none" stroke={on(n.id) && on(c) ? '#a9b7c4' : '#eef1f4'} strokeWidth="1.2" />))}
          {up.map((u: any, i: number) => u.tier1.map((t: string) => P[t] && <path key={u.id + t} className="dr" style={{ animationDelay: `${i * 0.12}s` }} d={cv([P[u.id][0] + 10, P[u.id][1]], [P[t][0] - 68, P[t][1]])} fill="none" stroke={riskColor(u.risk)} strokeWidth={hv === u.id ? 3.4 : 2.1} opacity={!H_ || hv === u.id ? 0.9 : 0.1} />))}
          {up.map((u: any) => (
            <g key={u.id} transform={`translate(${P[u.id][0]},${P[u.id][1]})`} style={{ cursor: 'pointer' }} onMouseEnter={() => setHv(u.id)} onMouseLeave={() => setHv(null)} onClick={() => open({ type: 'node', id: u.id })} opacity={on(u.id) ? 1 : 0.4}>
              <rect x={-146} y={-18} width={158} height={36} fill="transparent" />
              <circle r={expo.includes(u.id) ? 10 : 7} fill={riskColor(u.risk)} stroke="#fff" strokeWidth="2" />
              {u.events.length > 0 && <circle r={expo.includes(u.id) ? 16 : 12} fill="none" stroke="var(--sig)" strokeWidth="1.5" strokeDasharray="3 2" />}
              <text x={-22} y={-1} textAnchor="end" fontSize="13.5" fontWeight="700" fill="var(--ink)">{short(u).split(' ')[0]}</text>
              <text x={-22} y={13} textAnchor="end" fontSize="11" fill="var(--ink-3)">{u.site} {u.zone} · {u.risk} {u.grade}</text>
            </g>
          ))}
          {t1.map((n: any) => (
            <g key={n.id} transform={`translate(${P[n.id][0]},${P[n.id][1]})`} opacity={on(n.id) ? 1 : 0.35} style={{ cursor: 'pointer' }} onClick={() => open({ type: 'node', id: n.id })}>
              <rect x={-68} y={-12} width={136} height={24} rx={3} fill="#fff" stroke={hot.has(n.id) ? 'var(--ink)' : 'var(--line)'} />
              <text x={-60} y={4} fontSize="12" fill="var(--ink)">{short(n).split(' ')[0]}</text>
              <text x={60} y={4} fontSize="11" fill="var(--ink-3)" textAnchor="end">{Object.values(n.eff_share).map((v: any) => Math.round(v * 100) + '%').join('/')}</text>
            </g>
          ))}
          {d.components.map((c: any) => <g key={c.id} transform={`translate(${P[c.id][0]},${P[c.id][1]})`} opacity={on(c.id) ? 1 : 0.35} style={{ cursor: 'pointer' }} onClick={() => open({ type: 'component', id: c.id })}><rect x={-24} y={-11} width={48} height={22} rx={3} fill={hot.has(c.id) ? 'var(--ink)' : 'var(--sunken)'} stroke="var(--line)" /><text textAnchor="middle" y={4} fontSize="12" fontWeight="700" fill={hot.has(c.id) ? '#fff' : 'var(--ink)'}>{c.id}</text></g>)}
          {d.products.map((p: any) => <g key={p.id} opacity={on(p.id) ? 1 : 0.35}><rect x={X[3]} y={P[p.id][1]} width={9} height={P[p.id][2]} fill={H_ && on(p.id) ? riskColor(H_.risk) : 'var(--ink)'} />
            <text x={X[3] + 17} y={P[p.id][1] + P[p.id][2] / 2 - 3} fontSize="13" fontWeight="700" fill="var(--ink)">{p.id} {p.name.split(' ')[0]}</text>
            <text x={X[3] + 17} y={P[p.id][1] + P[p.id][2] / 2 + 13} fontSize="12" fill="var(--ink-3)">{money(p.revenue)}</text></g>)}
        </svg>
        <div className="row small muted" style={{ gap: 14 }}>
          <span>Line colour = upstream plant's risk</span><span>Percentages = Tier-1 allocation</span><span style={{ color: 'var(--sig)' }}>Dashed ring = live signal</span>
        </div>
      </div>
    </section>
  )
}

function TopRisks() {
  const { d, open, go } = useApp()
  const rows = [...d.nodes].filter((n: any) => n.rank < 999).sort((a: any, b: any) => a.rank - b.rank).slice(0, 10)
  return (
    <section className="panel">
      <div className="ph"><h2>Highest risk</h2><span>risk, evidence grade, reading</span><span className="grow" /><button className="btn link" onClick={() => go('risk')}>All 25</button></div>
      <div className="pb" style={{ display: 'grid', gap: 7 }}>
        {rows.map((n: any) => (
          <div key={n.id} onClick={() => open({ type: 'node', id: n.id })} style={{ display: 'grid', gridTemplateColumns: '1fr 70px 26px 22px 74px', gap: 8, alignItems: 'center', cursor: 'pointer' }}>
            <span style={{ fontWeight: 600, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{short(n)} <span className="muted small">T{n.tier}</span></span>
            <div className="bar"><i style={{ width: `${n.risk}%`, background: riskColor(n.risk) }} /></div>
            <b className="num r" style={{ color: riskColor(n.risk) }}>{n.risk}</b>
            <Grade g={n.grade} />
            <span className={`tag ${readClass(n.reading)}`} style={{ justifySelf: 'start' }}>{String(n.reading).split(',')[0]}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function ProductExposure() {
  const { d, nodes, go } = useApp()
  const expo: string[] = (d.team.headline.exposure_nodes?.value || '').split(',').map((s: string) => s.trim()).filter((k: string) => nodes[k])
  const max = Math.max(...d.products.map((p: any) => p.revenue))
  return (
    <section className="panel">
      <div className="ph"><h2>Products at stake</h2><span>which critical node reaches each product</span></div>
      <div className="pb">
        <div style={{ display: 'grid', gridTemplateColumns: `1fr ${expo.map(() => '64px').join(' ')}`, gap: '10px 6px', alignItems: 'center' }}>
          <span />{expo.map(k => <span key={k} className="small" style={{ textAlign: 'center', fontWeight: 700, color: 'var(--ink-2)' }}>{short(nodes[k]).split(' ')[0]}</span>)}
          {d.products.map((p: any) => (
            <React.Fragment key={p.id}>
              <div style={{ cursor: 'pointer' }} onClick={() => go('network', { product: p.id, focus: null })}>
                <div className="row" style={{ justifyContent: 'space-between' }}><b>{p.id} {p.name.split(' ')[0]}</b><b className="num">{money(p.revenue)}</b></div>
                <div className="bar" style={{ marginTop: 3 }}><i style={{ width: `${(p.revenue / max) * 100}%`, background: 'var(--ink)' }} /></div>
                <div className="small muted">{p.weekly_units?.toLocaleString()} units/wk · {money(p.revenue / 52, 1)}/wk</div>
              </div>
              {expo.map(k => { const hit = nodes[k].products.includes(p.id); const c = riskColor(nodes[k].risk)
                return <div key={k} style={{ display: 'grid', placeItems: 'center' }}><span style={{ width: 22, height: 22, borderRadius: 3, background: hit ? c : 'transparent', border: `2px solid ${hit ? c : 'var(--line)'}` }} title={hit ? `${short(nodes[k])} reaches ${p.id}` : 'not exposed'} /></div> })}
            </React.Fragment>
          ))}
        </div>
      </div>
    </section>
  )
}

function DualSourcing() {
  const { d, nodes, open } = useApp()
  return (
    <section className="panel">
      <div className="ph"><h2>Is the dual sourcing real?</h2><span>Tier-1 split per part and what sits behind it</span></div>
      <div className="pb" style={{ paddingTop: 0 }}>
        <table className="t">
          <thead><tr><th>Part</th><th>Tier-1 split</th><th>Shared upstream</th><th>Verdict</th></tr></thead>
          <tbody>{d.illusions.map((x: any) => (
            <tr key={x.component} className="click" onClick={() => open({ type: 'component', id: x.component })}>
              <td><b>{x.component}</b> <span className="muted small">{x.products.join(' ')}</span></td>
              <td style={{ width: 170 }}>
                <div style={{ display: 'flex', gap: 2, height: 7 }}>{x.tier1.map((t: string, i: number) => <i key={t} style={{ flex: x.alloc[t] || 1, background: i ? 'var(--ink-3)' : 'var(--ink)' }} />)}</div>
                <div className="small muted">{x.tier1.map((t: string) => `${short(nodes[t]).split(' ')[0]} ${x.alloc[t]}%`).join(' / ')}</div>
              </td>
              <td>{x.tier1.length > 1 ? <>{x.shared_upstream.filter((k: string) => nodes[k].tier === 2).slice(0, 3).map((k: string) => <span key={k} className="chip" style={{ marginRight: 4, borderLeft: `3px solid ${riskColor(nodes[k].risk)}` }}>{short(nodes[k]).split(' ')[0]}</span>)}
                {x.common_owner.map((k: string) => <span key={k} className="chip">owner {d.entities[k].short.split(' ')[0]}</span>)}</> : <span className="muted small">—</span>}</td>
              <td className="small" style={{ fontWeight: 700, color: x.tier1.length > 1 ? (x.independent ? 'var(--ok)' : 'var(--r3)') : 'var(--ink-2)' }}>{x.verdict}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </section>
  )
}
