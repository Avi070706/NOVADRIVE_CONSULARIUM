import React, { useEffect, useState } from 'react'
import { money, useApp } from '../store'
import { NodeChip, Verdict } from '../components/ui'

const STEPS = ['Freshness', 'Duplicate check', 'Entity resolution', 'Facility & geography', 'Network traversal', 'Exposure', 'Decision']
const SC: Record<string, string> = { pass: 'var(--ok)', skip: 'var(--ok)', warn: 'var(--r2)', fail: 'var(--ink)' }

export default function Signals() {
  const { d, signal, setSignal } = useApp()
  const [sel, setSel] = useState(signal || 'EV-001')
  const [test, setTest] = useState(false)
  useEffect(() => { if (signal) { setSel(signal); setSignal(null) } }, [signal])
  const ev = d.events.find((e: any) => e.id === sel) || d.events[0]
  const alerts = d.events.filter((e: any) => e.verdict === 'Alert').length
  return (
    <div className="page">
      <div className="pagehead">
        <div><h1>From {d.events.length} external signals to {alerts} management alerts</h1><p>Only signals that touch a NovaDrive plant, zone or supplier become alerts.</p></div>
        <span className="grow" /><button className="btn" onClick={() => setTest(true)}>Test a new signal</button>
      </div>
      <div className="g split" style={{ gridTemplateColumns: 'minmax(0,1.2fr) minmax(0,1fr)', alignItems: 'start' }}>
        <section className="panel"><div className="pb" style={{ paddingTop: 16 }}>
          <table className="t">
            <thead><tr><th>Signal</th><th>Naive system</th><th>Ours</th><th>Verdict</th></tr></thead>
            <tbody>{d.events.map((e: any) => (
              <tr key={e.id} className={`click ${e.id === ev.id ? 'sel' : ''}`} onClick={() => setSel(e.id)}>
                <td><b>{e.id}</b> {e.title}</td>
                <td className="muted">{e.naive}</td>
                <td style={{ color: 'var(--c3)', fontWeight: 650 }}>{e.ours}</td>
                <td><Verdict e={e} /></td>
              </tr>))}</tbody>
          </table>
        </div></section>
        <Brief e={ev} />
      </div>
      {test && <TestModal onClose={() => setTest(false)} />}
    </div>
  )
}

function Brief({ e }: { e: any }) {
  const { d, go, setTarget, nodes } = useApp()
  const b = e.brief
  const live = e.verdict === 'Alert' || e.verdict === 'Watch'
  const accent = e.verdict === 'Alert' ? (e.priority === 1 ? 'var(--r3)' : 'var(--r2)') : e.verdict === 'Watch' ? 'var(--ok)' : 'var(--r0)'
  const stepMap = Object.fromEntries(e.steps.map((s: any) => [s.step, s]))
  return (
    <section className="panel" style={{ borderTop: `5px solid ${accent}`, background: live ? 'var(--sunken)' : '#fff' }}>
      <div className="pb" style={{ paddingTop: 16 }}>
        <div className="row" style={{ justifyContent: 'space-between' }}><Verdict e={e} /><span className="small muted">{e.id} · {e.published}</span></div>
        <h2 style={{ fontSize: 26, margin: '8px 0 12px' }}>{b?.Title || e.title}</h2>
        {[['What', b?.What || e.detail], [live ? 'Why it matters' : 'Why no alert', b?.['Why it matters'] || e.why], ['Next action', b?.['Next action'] || e.actions?.[0]?.text]].map(([k, v]) => v && (
          <div key={k} style={{ marginBottom: 12 }}><div style={{ fontWeight: 700, color: '#8a6a12', fontSize: 13 }}>{k}</div><div style={{ fontSize: 14.5 }}>{v}</div></div>))}
        {e.matched?.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 12px', alignItems: 'center', padding: '12px 0', borderTop: '1px solid var(--line)' }}>
            <span className="small muted">Plants hit</span><div className="row" style={{ gap: 5 }}>{e.matched.map((k: string) => <NodeChip key={k} id={k} />)}</div>
            <span className="small muted">Parts → products</span><div className="row" style={{ gap: 5 }}>{e.components.map((c: string) => <span key={c} className="chip">{c}</span>)}<span className="muted">→</span>{e.products.map((p: string) => <span key={p} className="chip dark">{p}</span>)}</div>
            <span className="small muted">Revenue exposed</span><b className="num" style={{ fontSize: 22, color: 'var(--ink)' }}>{money(e.exposure)}</b>
          </div>)}
        <div style={{ borderTop: '1px solid var(--line)', paddingTop: 10 }}>
          <div className="small muted" style={{ marginBottom: 6 }}>How it was matched</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 4 }}>
            {STEPS.map(s => { const st = stepMap[s]; return (
              <div key={s} title={st ? st.note : 'not reached'}>
                <div style={{ height: 6, borderRadius: 3, background: st ? SC[st.status] : 'var(--line-2)' }} />
                <div style={{ fontSize: 10.5, color: st ? 'var(--ink-2)' : 'var(--ink-3)', marginTop: 3, lineHeight: 1.2 }}>{s}</div>
              </div>) })}
          </div>
        </div>
        {e.verdict === 'Alert' && e.matched?.length > 0 && (
          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn pri" onClick={() => { setTarget([...e.matched].sort((a, b) => nodes[b].risk - nodes[a].risk)[0]); go('sourcing') }}>Alternate sources</button>
            <button className="btn" onClick={() => go('network', { focus: e.matched[0] })}>Show on network</button>
          </div>)}
      </div>
    </section>
  )
}

const PRESETS = [
  ['Fire halts die production at IonPeak SITE-074', 'A fire at the IonPeak Semiconductor plant stopped production of power dies.'],
  ['Ion Peak Trading warehouse fire', 'Fire damages the Ion Peak Trading broker warehouse in Harbor District.'],
  ['Typhoon warning for Z06', 'Authorities issue a typhoon warning covering zone Z06. No damage is confirmed.'],
]

function TestModal({ onClose }: { onClose: () => void }) {
  const [t, setT] = useState(''), [dt, setDt] = useState(''), [r, setR] = useState<any>(null), [busy, setBusy] = useState(false)
  const run = async (a = t, b = dt) => {
    setBusy(true)
    const res = await fetch('/api/signal', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ title: a, detail: b }) })
    setR(await res.json()); setBusy(false)
  }
  const label: Record<string, string> = { ALERT: 'Alert', WATCH: 'Watch', INFO: 'No action', MERGED: 'Merged', SUPPRESSED: 'Suppressed', REJECTED: 'Suppressed' }
  return (
    <div className="modal" onClick={onClose}><div className="box" onClick={e => e.stopPropagation()}>
      <h2 style={{ fontSize: 22, marginBottom: 12 }}>Test a new signal</h2>
      <input value={t} onChange={e => setT(e.target.value)} placeholder="Headline" style={{ width: '100%', padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6, marginBottom: 8 }} />
      <textarea value={dt} onChange={e => setDt(e.target.value)} placeholder="Detail (optional)" rows={2} style={{ width: '100%', padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6 }} />
      <div className="row" style={{ margin: '10px 0' }}><button className="btn pri" disabled={!t || busy} onClick={() => run()}>{busy ? 'Matching…' : 'Run'}</button>
        {PRESETS.map(([a, b]) => <button key={a} className="chip click" onClick={() => { setT(a); setDt(b); run(a, b) }}>{a}</button>)}</div>
      {r && <div className="banner" style={{ background: r.decision === 'ALERT' ? 'var(--r3-bg)' : 'var(--sunken)' }}>
        <b>{label[r.decision] || r.decision}</b>{r.severity ? ` · ${r.severity.toLowerCase()} severity` : ''} — {r.headline}
        {r.matched?.length > 0 && <div style={{ marginTop: 6 }}>{r.components.join(', ')} → {r.products.join(', ')} · {money(r.exposure)}</div>}
      </div>}
    </div></div>
  )
}
