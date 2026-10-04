import React, { useEffect, useMemo, useRef, useState } from 'react'
import { View, money, short, useApp } from './store'
import Inspector from './components/Inspector'
import Overview from './views/Overview'
import Network from './views/Network'
import Risk from './views/Risk'
import Signals from './views/Signals'
import Sourcing from './views/Sourcing'
import Evidence from './views/Evidence'

const NAV: { v: View; t: string; q: string; title: string; sub: string }[] = [
  { v: 'overview', t: 'Situation', q: 'What needs a decision?', title: 'What needs a decision today', sub: 'Decisions, live alerts and where the exposure converges' },
  { v: 'network', t: 'Network', q: 'Where is the dependency?', title: 'Reconstructed supplier network', sub: 'Tier 3 → Tier 2 → Tier 1 → parts → products' },
  { v: 'risk', t: 'Risk', q: 'How bad, how sure?', title: 'Risk and evidence, scored separately', sub: '25 nodes, seven weighted factors, evidence graded A–D' },
  { v: 'signals', t: 'Signals', q: 'What changed outside?', title: 'External signals, triaged', sub: 'Only signals that touch the network become alerts' },
  { v: 'sourcing', t: 'Sourcing', q: 'What can we do?', title: 'Alternate sourcing', sub: 'Fit and supplier risk, scored separately' },
  { v: 'evidence', t: 'Evidence', q: 'Why do we believe it?', title: 'Evidence and provenance', sub: 'Every link, every rejected record, every source' },
]

export default function App() {
  const { d, err, view } = useApp()
  if (!d) return <div style={{ display: 'grid', placeItems: 'center', height: '100%', color: 'var(--ink-3)' }}>{err ? `Workbook could not be loaded: ${err}` : 'Loading NovaDrive.xlsx…'}</div>
  const V = { overview: Overview, network: Network, risk: Risk, signals: Signals, sourcing: Sourcing, evidence: Evidence }[view]
  const nv = NAV.find(n => n.v === view)!
  return (
    <div className="app">
      <Rail />
      <div className="main">
        <TopBar title={nv.title} sub={nv.sub} />
        <div className="scroll"><V /></div>
      </div>
      <Inspector /><Palette /><Toasts />
    </div>
  )
}

function Rail() {
  const { d, view, go, pulse, err } = useApp()
  const alerts = d.events.filter((e: any) => e.verdict === 'Alert').length
  const ref = useRef<HTMLInputElement>(null)
  const upload = async (f: File) => { const fd = new FormData(); fd.append('file', f); await fetch('/api/workbook', { method: 'POST', body: fd }) }
  return (
    <nav className="rail">
      <div className="brand"><b>NovaDrive</b><span>Supply-risk console</span></div>
      <ol className="journey">{NAV.map((n, i) => (
        <li key={n.v}><button className={view === n.v ? 'on' : ''} onClick={() => go(n.v)}>
          <span className="n">{i + 1}</span><span className="t">{n.t}{n.v === 'signals' && alerts > 0 && <span className="dot">{alerts}</span>}</span><span className="q">{n.q}</span>
        </button></li>))}</ol>
      <div className="rail-foot">
        <button className={`live ${pulse ? 'pulse' : ''} ${err || d.source.remote_error ? 'err' : ''}`} onClick={() => ref.current?.click()} title="Click to replace the workbook">
          <i /><span><b>{d.source.name}</b>{err ? 'Last save unreadable' : d.source.remote_error ? 'Cloud link failed, using last copy' : `Live link · saved ${d.source.modified.slice(11, 16)}`}</span>
        </button>
        <div style={{ marginTop: 8 }}>{d.meta.parse.classified}/{d.meta.parse.total} records parsed · as of {d.meta.as_of}</div>
        <input ref={ref} type="file" accept=".xlsx" hidden onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
      </div>
    </nav>
  )
}

function TopBar({ title, sub }: { title: string; sub: string }) {
  const { d, setPalette } = useApp()
  return (
    <header className="topbar">
      <div><h1>{title}</h1><div className="sub">{sub}</div></div>
      <div className="grow" />
      <button className="searchbtn" onClick={() => setPalette(true)}>Supplier, site, event, record<kbd>Ctrl K</kbd></button>
      <div className="asof"><b style={{ color: 'var(--ink-2)' }}>{money(d.total)}</b> revenue in scope<br />{d.nodes.length} nodes, {d.edges.length} links</div>
    </header>
  )
}

function Palette() {
  const { d, palette, setPalette, open, go, setSignal } = useApp()
  const [q, setQ] = useState(''); const [i, setI] = useState(0)
  useEffect(() => { setQ(''); setI(0) }, [palette])
  const items = useMemo(() => !d ? [] : [
    ...d.nodes.map((n: any) => ({ k: `Tier ${n.tier}`, l: short(n), h: `${n.site} ${n.zone} · risk ${n.risk}`, hay: `${n.name} ${n.site} ${n.zone} ${n.cap}`, a: () => open({ type: 'node', id: n.id }) })),
    ...d.components.map((c: any) => ({ k: 'Component', l: `${c.id} ${c.name}`, h: c.products.join(' '), hay: `${c.id} ${c.name}`, a: () => open({ type: 'component', id: c.id }) })),
    ...d.events.map((e: any) => ({ k: 'Signal', l: `${e.id} ${e.title}`, h: e.verdict, hay: `${e.id} ${e.title}`, a: () => { setSignal(e.id); go('signals') } })),
    ...d.evidence.map((r: any) => ({ k: 'Record', l: `${r.id} ${r.title}`, h: r.date, hay: `${r.id} ${r.title} ${r.detail}`, a: () => open({ type: 'record', id: r.id }) })),
  ], [d])
  if (!palette) return null
  const w = q.toLowerCase().split(/\s+/).filter(Boolean)
  const res = (w.length ? items.filter((x: any) => w.every(t => x.hay.toLowerCase().includes(t))) : items.filter((x: any) => x.k.startsWith('Tier'))).slice(0, 30)
  const pick = (x: any) => { setPalette(false); x.a() }
  return (
    <div className="cmdk" onClick={() => setPalette(false)}>
      <div className="box" onClick={e => e.stopPropagation()}>
        <input autoFocus placeholder="IonPeak, SITE-081, Z01, M10, EV-003, DOC-078…" value={q} onChange={e => { setQ(e.target.value); setI(0) }}
          onKeyDown={e => { if (e.key === 'ArrowDown') setI(x => Math.min(x + 1, res.length - 1)); if (e.key === 'ArrowUp') setI(x => Math.max(x - 1, 0)); if (e.key === 'Enter' && res[i]) pick(res[i]) }} />
        <div className="list">{res.map((x: any, j: number) => <div key={j} className={`it ${j === i ? 'on' : ''}`} onMouseEnter={() => setI(j)} onClick={() => pick(x)}><span className="k">{x.k}</span><span>{x.l}</span><span className="h">{x.h}</span></div>)}
          {!res.length && <div className="muted" style={{ padding: 16 }}>No match in the case data.</div>}</div>
      </div>
    </div>
  )
}

function Toasts() {
  const { toasts, dismiss } = useApp()
  useEffect(() => { if (toasts.length) { const t = setTimeout(() => dismiss(0), 9000); return () => clearTimeout(t) } }, [toasts])
  return <div className="toasts">{toasts.map((t, i) => (
    <div className="toast" key={t.at}><button className="x" onClick={() => dismiss(i)}>×</button><b>Workbook updated</b>
      {t.items.length ? <ul>{t.items.map((x: string, j: number) => <li key={j}>{x}</li>)}</ul> : <div style={{ color: '#c9d3dd' }}>No change to scores or alerts.</div>}</div>))}</div>
}
