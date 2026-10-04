import React from 'react'
import { money, riskColor, short, useApp } from '../store'
import { Grade, NodeChip, Reading, Risk } from './ui'

export function Record({ id, open = false }: { id: string; open?: boolean }) {
  const { d } = useApp()
  const r = d.evidence.find((x: any) => x.id === id)
  if (!r) return null
  return (
    <details className="rec" open={open}>
      <summary><b>{r.id}</b><span style={{ flex: 1 }}>{r.type}</span><span className="muted">{r.date}</span></summary>
      <div className="d">{r.detail}<div className="small muted" style={{ marginTop: 6 }}>Source family {r.family}</div></div>
    </details>
  )
}

export function keyFacts(n: any, d: any, nodes: any) {
  const f: { t: string; c: string }[] = []
  if (n.tier > 1 && n.tier1.length > 1) f.push({ t: `Shared by ${n.tier1.length} Tier-1 suppliers (${n.tier1.map((t: string) => short(nodes[t]).split(' ')[0]).join(', ')}): Tier-1 dual sourcing does not remove this dependency`, c: 'var(--r3)' })
  if (n.no_alt_evidence.length) f.push({ t: `No qualified second source (${n.no_alt_evidence.join(', ')})`, c: 'var(--r3)' })
  if (n.acute) f.push({ t: n.factors.financial.text + ' ' + n.factors.operational.text, c: 'var(--r2)' })
  const own = d.ownership.find((o: any) => o.child === n.id)
  if (own) f.push({ t: `Owned by ${d.entities[own.parent].short} (${own.record})`, c: 'var(--r2)' })
  const hz = n.factors.geography.inputs.hazard
  if (hz != null && hz >= 60) f.push({ t: `Plant in ${n.zone}${d.zones[n.zone]?.name ? ' ' + d.zones[n.zone].name : ''}, hazard index ${hz}`, c: 'var(--r2)' })
  if (n.status !== 'confirmed') f.push({ t: n.status === 'inference' ? 'Link inferred from a customer listing; not confirmed' : 'Sample evaluation only; hypothesis, excluded from exposure', c: 'var(--r0)' })
  if (n.missing.length) f.push({ t: 'Financial data not disclosed: treated as unknown, not low risk', c: 'var(--r0)' })
  return f
}

function NodeView({ n }: { n: any }) {
  const { d, nodes, go, setTarget, open } = useApp()
  const path = n.confidence.path.map((id: string) => d.edges.find((e: any) => e.id === id))
  const recs = Array.from(new Set(d.edges.filter((e: any) => e.src === n.id).flatMap((e: any) => e.support.map((s: any) => s.rec)))) as string[]
  return (
    <>
      <div className="stat3 sec">
        <div><span>Risk</span><b><Risk v={n.risk} size={30} /></b></div>
        <div><span>Evidence</span><b style={{ marginTop: 4 }}><Grade g={n.grade} /></b></div>
        <div><span>Reading</span><b style={{ marginTop: 6 }}><Reading r={n.reading} /></b></div>
      </div>
      <div className="sec">
        <h4>Exposure</h4>
        <div className="row"><b className="num" style={{ fontSize: 24, color: 'var(--ink)' }}>{n.rev ? money(n.rev) : 'Not in exposure'}</b>{n.products.map((p: string) => <span key={p} className="chip dark">{p}</span>)}</div>
      </div>
      <div className="sec">
        <h4>Path to NovaDrive</h4>
        <div className="row" style={{ gap: 4 }}>
          <NodeChip id={n.id} />
          {path.map((e: any) => <React.Fragment key={e.id}><span className="muted">→</span>{e.dst === 'ND' ? <span className="chip dark">NovaDrive</span> : <NodeChip id={e.dst} />}</React.Fragment>)}
          <span className="muted">→</span>{n.components.map((c: string) => <span key={c} className="chip click" onClick={() => open({ type: 'component', id: c })}>{c}</span>)}
        </div>
      </div>
      {keyFacts(n, d, nodes).length > 0 && <div className="sec"><h4>Why it scores this way</h4><ul className="facts">{keyFacts(n, d, nodes).map((f, i) => <li key={i} style={{ ['--c' as any]: f.c }}>{f.t}</li>)}</ul></div>}
      {n.events.length > 0 && <div className="sec"><h4>Live signals</h4>{n.events.map((id: string) => { const e = d.events.find((x: any) => x.id === id); return <div key={id} className="small" style={{ marginBottom: 4 }}><b>{id}</b> {e?.brief?.Title || e?.title}</div> })}</div>}
      <div className="row sec">
        <button className="btn pri" onClick={() => { setTarget(n.id); go('sourcing') }}>Alternate sources</button>
        <button className="btn" onClick={() => go('network', { focus: n.id })}>Show on network</button>
      </div>
      <div className="sec"><h4>Evidence records ({recs.length})</h4>{recs.map(r => <Record key={r} id={r} />)}</div>
    </>
  )
}

function ComponentView({ c }: { c: any }) {
  const { d, nodes } = useApp()
  const t1 = d.edges.filter((e: any) => e.dst === 'ND' && e.components.includes(c.id))
  const up = d.nodes.filter((n: any) => n.tier > 1 && n.components.includes(c.id)).sort((a: any, b: any) => b.risk - a.risk)
  return (
    <>
      <div className="sec small">{c.application}</div>
      <div className="stat3 sec">
        <div><span>Products</span><b className="num">{c.products.join(' ')}</b></div>
        <div><span>Tier-1 sources</span><b className="num">{t1.length}</b></div>
        <div><span>Qualify new source</span><b className="num">{c.lead_time} wk</b></div>
      </div>
      <div className="sec"><h4>Tier-1 split</h4>{t1.map((e: any) => <div key={e.id} className="row" style={{ marginBottom: 6 }}><NodeChip id={e.src} /><b>{e.alloc[c.id]}%</b></div>)}</div>
      <div className="sec"><h4>Upstream dependencies</h4><div className="row">{up.map((n: any) => <NodeChip key={n.id} id={n.id} />)}</div></div>
    </>
  )
}

export default function Inspector() {
  const { stack, back, close, d, nodes } = useApp()
  const top = stack[stack.length - 1]
  if (!top) return null
  let title = '', sub: React.ReactNode = null, body: React.ReactNode = null
  if (top.type === 'node') {
    const n = nodes[top.id]; if (!n) return null
    title = short(n)
    sub = <>Tier {n.tier} · {n.cap} · {n.site}, {n.zone}{d.zones[n.zone]?.name ? ` ${d.zones[n.zone].name}` : ''}</>
    body = <NodeView n={n} />
  } else if (top.type === 'component') {
    const c = d.components.find((x: any) => x.id === top.id)
    title = `${c.id} ${c.name}`; body = <ComponentView c={c} />
  } else {
    title = `Record ${top.id}`; body = <Record id={top.id} open />
  }
  return (
    <>
      <div className="scrim" onClick={close} />
      <aside className="drawer" role="dialog" aria-label={title}>
        <div className="dh">
          <button className="x" onClick={close} aria-label="Close">×</button>
          {stack.length > 1 && <button className="back" onClick={back}>Back</button>}
          <h3>{title}</h3>
          {sub && <div className="small muted" style={{ marginTop: 4 }}>{sub}</div>}
        </div>
        <div className="db">{body}</div>
      </aside>
    </>
  )
}
