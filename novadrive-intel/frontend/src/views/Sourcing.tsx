import React, { useEffect, useMemo, useState } from 'react'
import { money, short, useApp } from '../store'

const RL = ['Low', 'Medium', 'Elevated', 'Unknown']
const RC: Record<string, string> = { Low: 'var(--ok)', Medium: 'var(--r1)', Elevated: 'var(--r3)', Unknown: 'var(--r0)' }

export default function Sourcing() {
  const { d, nodes, target, setTarget } = useApp()
  const expo: string[] = (d.team.headline.exposure_nodes?.value || '').split(',').map((s: string) => s.trim()).filter((k: string) => nodes[k])
  const teamTargets = Array.from(new Set(d.team.alternates.map((a: any) => a['Target Entity ID']))) as string[]
  const targets = Array.from(new Set([...teamTargets, ...expo, ...(target && nodes[target] ? [target] : [])]))
  const id = target && nodes[target] ? target : targets[0]
  const n = nodes[id]
  const team = d.team.alternates.filter((a: any) => a['Target Entity ID'] === id)
  const brief = d.team.brief.find((b: any) => b['Target Entity ID'] === id)
  const [auto, setAuto] = useState<any>(null)
  const [live, setLive] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { setAuto(null); setLive(null); fetch(`/api/alternates?node=${id}&live=0`).then(r => r.json()).then(setAuto) }, [id])
  const runLive = async () => { setBusy(true); try { setLive((await (await fetch(`/api/alternates?node=${id}&live=1`)).json()).live) } finally { setBusy(false) } }

  const cands = useMemo(() => team.length
    ? team.map((a: any) => ({ name: a.Candidate, foot: a['Production footprint'], ev: a['Public evidence'], src: a.Source, date: a['Source date'], url: a['Source URL'], fit: +a['Fit (0-5)'], risk: a.Risk, take: a.Takeaway, team: true }))
      .sort((a: any, b: any) => b.fit - a.fit)
    : (auto?.snapshot.candidates || []).map((c: any) => ({ name: c.name, foot: (c.criteria.find((k: any) => k.key === 'footprint')?.terms || []).join(', ') || 'not stated', ev: c.sources[0]?.note, src: c.sources[0]?.publisher, date: c.sources[0]?.published || auto.snapshot.retrieved,
      url: c.sources[0]?.url, fit: Math.round(c.fit / 2) / 10, risk: c.risk.score == null ? 'Unknown' : c.risk.score < 35 ? 'Low' : c.risk.score < 60 ? 'Medium' : 'Elevated', take: null, team: false })).sort((a: any, b: any) => b.fit - a.fit),
  [id, auto])
  const spec = brief?.['Search spec'] || (auto ? `${auto.need.label} · ${auto.need.components.map((c: any) => c.id).join('/')} · ${auto.need.components[0]?.use_case || ''}` : '')
  const validate = brief?.['Still to validate']?.split(';').map((s: string) => s.trim()) || auto?.validate || []
  const fw = (brief?.['Fit framework'] || '').split(';').map((s: string) => s.trim()).filter(Boolean).map((s: string) => { const m = s.match(/(.+?)\s+(\d+)%/); return m ? [m[1], +m[2]] : null }).filter(Boolean) as [string, number][]
  const inputName = auto?.need.inputs?.[0] || n.cap.toLowerCase()

  return (
    <div className="page">
      <div className="pagehead">
        <div><h1>Credible options for {short(n).split(' ')[0]} {inputName.replace('power semiconductor ', '')}</h1>
          <p>{money(n.rev)} of revenue sits behind this input. No candidate below is qualified yet.</p></div>
        <span className="grow" />
        <div className="seg">{targets.map(k => <button key={k} className={k === id ? 'on' : ''} onClick={() => setTarget(k)}>{short(nodes[k]).split(' ')[0]}</button>)}</div>
      </div>

      <div className="banner" style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 16, fontSize: 14 }}>
        <b style={{ color: 'var(--ink)', whiteSpace: 'nowrap' }}>Search built from the component</b><span>{spec}</span>
        <span className="grow" />{!team.length && <span className="tag dim">Auto desk screen</span>}
      </div>

      <div className="g split" style={{ gridTemplateColumns: 'minmax(0,1.35fr) minmax(0,1fr)', alignItems: 'start' }}>
        <div className="g" style={{ gridTemplateColumns: '1fr 1fr' }}>
          {cands.map((c: any, i: number) => (
            <section key={c.name} className="panel" style={{ padding: '16px 18px', borderTop: `5px solid ${RC[c.risk]}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div><div className="small muted">Option {i + 1}</div><h2 style={{ fontSize: 21 }}>{c.name}</h2></div>
                <div style={{ textAlign: 'right' }}><b className="num" style={{ fontSize: 34, lineHeight: 1 }}>{c.fit.toFixed(1)}</b><span className="muted"> /5 fit</span></div>
              </div>
              <div className="bar" style={{ height: 8 }}><i style={{ width: `${(c.fit / 5) * 100}%`, background: 'var(--ink)' }} /></div>
              <div className="row" style={{ gap: 6 }}><span className="tag" style={{ background: RC[c.risk], color: '#fff' }}>{c.risk} risk</span><span className="tag dim">Desk screen · not qualified</span></div>
              <div className="small"><b>Footprint</b> {c.foot}</div>
              <div className="small"><b>Evidence</b> {c.ev} {c.url && <a href={c.url} target="_blank" rel="noreferrer">({c.src}, {c.date})</a>}</div>
              {c.take && <div className="small muted" style={{ borderTop: '1px solid var(--line-2)', paddingTop: 8 }}>{c.take}</div>}
            </section>
          ))}
          {!cands.length && <div className="panel pb muted" style={{ gridColumn: 'span 2', padding: 20 }}>No screened candidates for this input yet. Run a live web search.</div>}
        </div>

        <div className="g">
          <section className="panel"><div className="ph"><h2>Fit vs supplier risk</h2><span>scored separately</span></div><div className="pb"><Chart cands={cands} /></div></section>
          <section className="panel"><div className="ph"><h2>Before any switch</h2></div>
            <div className="pb">
              <div className="row" style={{ gap: 6 }}>{validate.map((v: string) => <span key={v} className="chip" style={{ padding: '4px 10px', fontSize: 12.5 }}>☐ {v}</span>)}</div>
              {fw.length > 0 && <div style={{ marginTop: 14 }}><div className="small muted" style={{ marginBottom: 6 }}>Fit framework (0–5 each, weighted)</div>
                <div style={{ display: 'flex', height: 26, borderRadius: 5, overflow: 'hidden' }}>{fw.map(([k, w], i) => <div key={k} title={`${k} ${w}%`} style={{ flex: w, background: ['#14202e', '#2f4357', '#4a5e73', '#6f8499', '#a3b2c1', '#cdd6df'][i], color: i < 3 ? '#fff' : 'var(--ink)', fontSize: 11, fontWeight: 700, display: 'grid', placeItems: 'center', whiteSpace: 'nowrap', overflow: 'hidden' }}>{w}%</div>)}</div>
                <div className="row small muted" style={{ gap: 10, marginTop: 4 }}>{fw.map(([k, w]) => <span key={k}>{k} {w}%</span>)}</div></div>}
              {auto?.internal?.length > 0 && <div className="small" style={{ marginTop: 14, color: 'var(--ink-2)' }}><b>Case data today:</b> {auto.internal.filter((o: any) => o.stage !== 'none').map((o: any) => `${o.name} — ${o.note}`).join(' · ') || 'no second source named in the evidence'}</div>}
            </div>
          </section>
          <section className="panel"><div className="ph"><h2>Find more candidates</h2><span>live public web search</span><span className="grow" /><button className="btn pri" disabled={busy} onClick={runLive}>{busy ? 'Searching…' : 'Search the web'}</button></div>
            <div className="pb small">
              {!live && <span className="muted">Searches public sources for makers of {inputName}. New results are listed with their source and are not added to the scored options until reviewed.</span>}
              {live && live.status === 'unavailable' && <div className="banner warn"><b>Couldn't reach a search service from this server.</b> Nothing was invented. Check the server's internet access{' '}or add a free Tavily key (TAVILY_API_KEY).
                <div className="row" style={{ gap: 4, marginTop: 6 }}>{live.attempts.filter((x: any) => x.status !== 'not configured').map((x: any) => <span key={x.provider} className="chip" title={x.error || ''}>{x.provider}: {x.status}</span>)}</div></div>}
              {live && live.status !== 'unavailable' && <>
                <div className="muted" style={{ marginBottom: 6 }}>{live.status === 'live' ? `Live results via ${live.provider}, ${live.retrieved}` : `Showing last results (${live.provider}, ${live.retrieved}); search service unreachable now`}</div>
                {live.candidates.map((c: any) => <div key={c.domain} className="row" style={{ padding: '7px 0', borderTop: '1px solid var(--line-2)', justifyContent: 'space-between' }}>
                  <span><b>{c.name}</b> <a href={c.sources[0].url} target="_blank" rel="noreferrer">{c.domain}</a><div className="muted" style={{ maxWidth: 380 }}>{(c.sources[0].snippet || '').slice(0, 140)}</div></span>
                  <span className="tag dim">fit {(c.fit / 20).toFixed(1)}/5 · {c.stage === 'screened' ? 'desk-screened' : 'potential'}</span></div>)}
                {!live.candidates.length && <span className="muted">The search ran but found no manufacturers matching this input.</span>}</>}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function Chart({ cands }: { cands: any[] }) {
  const W = 520, H = 230, L = 86, B = 30
  const lo = Math.min(3.5, ...cands.map(c => c.fit - 0.2)), hi = 5
  const x = (f: number) => L + ((f - lo) / (hi - lo)) * (W - L - 20)
  const levels = RL.filter(l => l !== 'Unknown' || cands.some(c => c.risk === 'Unknown'))
  const y = (r: string) => 14 + ((levels.indexOf(r) + 0.5) / levels.length) * (H - B - 14)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%">
      <rect x={x(4.2)} y={4} width={x(hi) - x(4.2)} height={y(levels[0]) + 22} fill="var(--ok-bg)" rx={6} />
      <text x={W - 26} y={y(levels[0]) + 19} textAnchor="end" fontSize="11" fontWeight="700" fill="var(--c3)">best zone</text>
      {levels.map(l => <g key={l}><line x1={L} x2={W - 20} y1={y(l)} y2={y(l)} stroke="var(--line-2)" /><text x={L - 10} y={y(l) + 4} textAnchor="end" fontSize="12.5" fontWeight="700" fill={RC[l]}>{l}</text></g>)}
      {[lo, (lo + hi) / 2, hi].map(v => <text key={v} x={x(v)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--ink-3)">{v.toFixed(1)}</text>)}
      <text x={L - 10} y={H - 8} fontSize="11" fill="var(--ink-3)" textAnchor="end">fit</text>
      {cands.map(c => <g key={c.name}><circle cx={x(c.fit)} cy={y(c.risk)} r={11} fill={RC[c.risk]} stroke="#fff" strokeWidth="2" />
        <text x={x(c.fit)} y={y(c.risk) - 16} textAnchor="middle" fontSize="12.5" fontWeight="700" fill="var(--ink)">{c.name}</text></g>)}
    </svg>
  )
}
