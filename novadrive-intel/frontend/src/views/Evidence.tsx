import React, { useMemo, useState } from 'react'
import { short, useApp } from '../store'
import { Grade } from '../components/ui'
import { Record } from '../components/Inspector'

const TRAPS = [
  { k: 'Look-alike names', docs: 'DOC-084, DOC-077', said: 'Ion Peak Trading (broker) vs IonPeak Semiconductor. Delta Consumer Plastics vs Delta Capacitor.', real: 'Matched on registry ID, never on name.', miss: 'A false insolvency alert on a key supplier.' },
  { k: 'Wrong role', docs: 'DOC-083, DOC-075/076', said: 'Harbor Freight only consolidates freight. CommonSpan and Jade Holdings are parents only.', real: 'Logistics firms and parents are not component makers.', miss: 'Freight or holding firms counted as suppliers.' },
  { k: 'Wrong site', docs: 'DOC-076, DOC-077', said: 'Jade HQ (SITE-901) makes nothing. IonPeak pilot line (SITE-900) is not qualified for our dies.', real: 'Risk attaches to SITE-081 and SITE-074.', miss: 'Hazard scored at the wrong location.' },
  { k: 'Expired link', docs: 'DOC-080', said: "Delta's 2022 housing pilot ended in Dec 2023.", real: 'Not a current H10 supply link.', miss: 'A phantom second source for housings.' },
  { k: 'Unproven link', docs: 'DOC-085, DOC-074/086', said: 'Solace to Grove is a sample evaluation. Alder to Quartz is a directory listing.', real: 'Kept as hypothesis, excluded from exposure.', miss: 'An inflated network and false redundancy.' },
  { k: 'Echoed evidence', docs: 'Source family ID', said: 'Repeated reports from one source family; shipment records only corroborate.', real: 'Counted once per family.', miss: 'Overconfidence in a single-source claim.' },
]
const CHECKS = [['E', 'Entity', 'Same legal entity?'], ['P', 'Plant', 'Correct site?'], ['C', 'Part', 'Relevant component?'], ['D', 'Date', 'Relationship current?'], ['N', 'Programme', 'For P1/P2/P3?'], ['S', 'Source', 'Independent source?']]
const CLS: Record<string, string> = { link: 'Creates a link', corroboration: 'Corroborates a link', inference: 'Inference', hypothesis: 'Hypothesis', ownership: 'Ownership', sole_source: 'No-alternative statement',
  facility: 'Facility clarification', rejection: 'Rules a link out', expired: 'Expired', role: 'Role clarification', gap: 'Evidence gap', research_lead: 'Research lead', out_of_scope: 'Out of scope', context: 'Context', unclassified: 'Not parsed' }
const TABS = [['ledger', 'Rejected & unresolved'], ['traps', 'Data traps'], ['links', 'All links'], ['records', 'All records'], ['trace', 'Trace a chokepoint']]

export default function Evidence() {
  const { d } = useApp()
  const [tab, setTab] = useState('ledger')
  const st = (s: string) => d.edges.filter((e: any) => e.status === s).length
  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 14, gap: 8 }}>
        {CHECKS.map(([k, t, q]) => <div key={k} className="panel row" style={{ padding: '7px 12px', gap: 9, flex: 1, minWidth: 160 }}>
          <span style={{ width: 26, height: 26, borderRadius: 3, background: 'var(--c3)', color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 800 }}>{k}</span><div><b style={{ fontSize: 13 }}>{t}</b><div className="small muted">{q}</div></div></div>)}
      </div>
      <div className="row" style={{ marginBottom: 14 }}>
        <div className="seg">{TABS.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
        <span className="grow" />
        <span className="small muted">{d.meta.parse.total} records → <b style={{ color: 'var(--ink)' }}>{st('confirmed')}</b> confirmed, <b style={{ color: 'var(--ink)' }}>{st('inference')}</b> inferred, <b style={{ color: 'var(--ink)' }}>{st('hypothesis')}</b> hypothesis links</span>
      </div>
      {tab === 'ledger' && <Ledger />}
      {tab === 'traps' && <Traps />}
      {tab === 'links' && <Links />}
      {tab === 'records' && <Records />}
      {tab === 'trace' && <Trace />}
    </div>
  )
}

function Ledger() {
  const { d, nodes, open } = useApp()
  const nm = (id: string) => (id === 'ND' ? 'NovaDrive' : nodes[id] ? short(nodes[id]) : d.entities[id]?.short || id)
  const rows = useMemo(() => {
    const out: any[] = []
    const cat: Record<string, string> = { 'Expired relationship': 'Expired link', 'Not a qualified alternative': 'Wrong site', 'Name look-alike': 'Look-alike name', 'Intermediary, not a supplier': 'Wrong role', 'Not a production link': 'Look-alike name', 'Research lead only': 'Unproven link' }
    const miss: Record<string, string> = Object.fromEntries(TRAPS.map(t => [t.k.replace('names', 'name'), t.miss]))
    d.rejected.forEach((x: any) => out.push({ what: `${x.src_name}${x.dst_name && x.dst_name !== 'component supply' && x.dst_name !== 'alternate die source' ? ' → ' + x.dst_name : ''}`, cat: cat[x.label] || x.label, status: x.status === 'unresolved' ? 'Unresolved' : 'Rejected', why: x.reason, recs: x.records, miss: miss[cat[x.label]] || '' }))
    d.edges.filter((e: any) => e.status !== 'confirmed').forEach((e: any) => out.push({ what: `${nm(e.src)} → ${nm(e.dst)}`, cat: 'Unproven link', status: e.status === 'inference' ? 'Kept as inference' : 'Kept as hypothesis',
      why: e.status === 'inference' ? 'Customer listing only; purchases and receiving line not identified' : 'Sample evaluation only; no serial-production award', recs: Array.from(new Set(e.support.map((s: any) => s.rec))), miss: 'An inflated network and false redundancy.' }))
    const parents: Record<string, any[]> = {}
    d.ownership.forEach((o: any) => (parents[o.parent] = parents[o.parent] || []).push(o))
    Object.entries(parents).forEach(([p, os]: any) => out.push({ what: `${d.entities[p].short} → ${os.map((o: any) => nm(o.child)).join(', ')}`, cat: 'Wrong role', status: 'Kept as ownership only', why: 'Parent / holding company; not a component maker', recs: [os[0].record], miss: 'Freight or holding firms counted as suppliers.' }))
    d.nodes.forEach((n: any) => n.facility_notes.filter((f: any) => /headquarters/i.test(f.note) && f.site !== n.site).forEach((f: any) => out.push({ what: `${short(n)} ${f.site}`, cat: 'Wrong site', status: 'Rejected as risk site', why: 'Registered headquarters; makes nothing', recs: [f.rec], miss: 'Hazard scored at the wrong location.' })))
    d.evidence.filter((r: any) => r.class === 'gap').forEach((r: any) => out.push({ what: `${r.title}`, cat: 'Unproven link', status: 'Unresolved', why: 'Upstream source not identified', recs: [r.id], miss: 'An inflated network and false redundancy.' }))
    d.evidence.filter((r: any) => r.class === 'out_of_scope').forEach((r: any) => out.push({ what: r.title, cat: 'Look-alike name', status: 'Out of scope', why: 'Shipment to an unrelated customer; not NovaDrive', recs: [r.id], miss: 'A false insolvency alert on a key supplier.' }))
    d.events.filter((e: any) => ['Merged', 'Suppressed', 'No action'].includes(e.verdict)).forEach((e: any) => out.push({ what: `${e.id} ${e.title}`, cat: e.verdict === 'Merged' ? 'Echoed evidence' : e.reason_code === 'stale' ? 'Stale signal' : e.verdict === 'No action' ? 'Wrong site' : 'Look-alike name', status: e.verdict === 'No action' ? 'No alert' : e.verdict,
      why: e.ours, recs: [e.family], miss: e.verdict === 'Merged' ? 'Two alerts for one event.' : e.reason_code === 'stale' ? 'An alert for a 2023 strike.' : e.verdict === 'No action' ? 'A disruption alert for an office move.' : 'A false alert on a key supplier.' }))
    return out
  }, [d])
  return (
    <section className="panel"><div className="ph"><h2>Rejected and unresolved evidence</h2><span>{rows.length} items that look like links or alerts but are not counted</span></div>
      <div className="pb"><table className="t">
        <thead><tr><th>Looks like a link</th><th>Trap</th><th>Decision</th><th>Why</th><th>If we had accepted it</th><th>Source</th></tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}><td style={{ fontWeight: 650 }}>{r.what}</td><td className="small">{r.cat}</td>
          <td><span className={`tag ${/Rejected|Suppressed|Out of scope|No alert|Merged/.test(r.status) ? 'act' : 'verify'}`}>{r.status}</span></td>
          <td className="small">{r.why}</td><td className="small muted">{r.miss}</td>
          <td className="small" style={{ whiteSpace: 'nowrap' }}>{r.recs.map((x: string) => d.evidence.find((e: any) => e.id === x) ? <button key={x} className="btn link" style={{ marginRight: 6 }} onClick={() => open({ type: 'record', id: x })}>{x}</button> : <span key={x} className="muted">{x} </span>)}</td></tr>)}</tbody>
      </table></div></section>
  )
}

function Traps() {
  return (
    <section className="panel"><div className="ph"><h2>Data traps we resolved</h2><span>six checks remove false links before scoring</span></div>
      <div className="pb"><table className="t">
        <thead><tr><th>#</th><th>Trap</th><th>Records</th><th>Data said</th><th>Reality</th><th>If missed</th></tr></thead>
        <tbody>{TRAPS.map((t, i) => <tr key={t.k}><td className="muted">{i + 1}</td><td style={{ fontWeight: 700 }}>{t.k}</td><td className="small muted" style={{ whiteSpace: 'nowrap' }}>{t.docs}</td><td>{t.said}</td><td style={{ color: 'var(--c3)', fontWeight: 600 }}>{t.real}</td><td style={{ color: 'var(--r3)' }}>{t.miss}</td></tr>)}</tbody>
      </table></div></section>
  )
}

function Links() {
  const { d, nodes, open } = useApp()
  const [f, setF] = useState('all')
  const nm = (id: string) => (id === 'ND' ? 'NovaDrive' : short(nodes[id]))
  const rows = d.edges.filter((e: any) => f === 'all' || e.status === f).sort((a: any, b: any) => (nodes[a.src].tier - nodes[b.src].tier) || b.confidence - a.confidence)
  return (
    <section className="panel"><div className="ph"><h2>All reconstructed links</h2><span className="grow" />
      <div className="seg">{[['all', 'All'], ['confirmed', 'Confirmed'], ['inference', 'Inferred'], ['hypothesis', 'Hypothesis']].map(([k, l]) => <button key={k} className={f === k ? 'on' : ''} onClick={() => setF(k)}>{l}</button>)}</div></div>
      <div className="pb"><table className="t">
        <thead><tr><th>Supplier → buyer</th><th>Tier</th><th>Supplies</th><th>Site</th><th>Status</th><th className="r">Independent sources</th><th>Records</th></tr></thead>
        <tbody>{rows.map((e: any) => <tr key={e.id} className="click" onClick={() => open({ type: 'node', id: e.src })}>
          <td><b>{nm(e.src)}</b> <span className="muted">→ {nm(e.dst)}</span></td><td>T{nodes[e.src].tier}</td>
          <td className="small">{e.inputs.join(', ') || e.components.map((c: string) => `${c} ${e.alloc[c]}%`).join(', ')}</td><td className="small">{e.sites.join(', ')}</td>
          <td><span className={`tag ${e.status === 'confirmed' ? 'verify' : e.status === 'inference' ? 'monitor' : 'dim'}`}>{e.status}</span></td>
          <td className="r"><b>{e.families}</b></td><td className="small muted">{Array.from(new Set(e.support.map((s: any) => s.rec))).join(', ')}</td></tr>)}</tbody>
      </table></div></section>
  )
}

function Records() {
  const { d, open } = useApp()
  const [q, setQ] = useState('')
  const [c, setC] = useState('all')
  const classes = Array.from(new Set(d.evidence.map((r: any) => r.class))) as string[]
  const rows = d.evidence.filter((r: any) => (c === 'all' || r.class === c) && (!q || `${r.id} ${r.title} ${r.detail}`.toLowerCase().includes(q.toLowerCase())))
  return (
    <section className="panel"><div className="ph"><h2>All {d.evidence.length} evidence records</h2><span>how each record was used</span><span className="grow" />
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Filter text…" style={{ border: '1px solid var(--line)', borderRadius: 4, padding: '5px 8px', fontSize: 13 }} />
      <select value={c} onChange={e => setC(e.target.value)} style={{ border: '1px solid var(--line)', borderRadius: 4, padding: '5px 8px', fontSize: 13 }}><option value="all">All uses</option>{classes.map(k => <option key={k} value={k}>{CLS[k] || k}</option>)}</select></div>
      <div className="pb"><table className="t">
        <thead><tr><th>Record</th><th>Date</th><th>Type</th><th>Source family</th><th>Used as</th><th>What it established</th></tr></thead>
        <tbody>{rows.map((r: any) => <tr key={r.id} className="click" onClick={() => open({ type: 'record', id: r.id })}>
          <td style={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{r.id}</td><td className="small" style={{ whiteSpace: 'nowrap' }}>{r.date}</td><td className="small">{r.type}</td><td className="small muted">{r.family}</td>
          <td><span className={`tag ${['link', 'corroboration', 'sole_source'].includes(r.class) ? 'verify' : ['expired', 'rejection', 'out_of_scope'].includes(r.class) ? 'act' : ['inference', 'hypothesis', 'gap', 'research_lead'].includes(r.class) ? 'monitor' : 'dim'}`}>{CLS[r.class] || r.class}</span></td>
          <td className="small">{r.summary}</td></tr>)}</tbody>
      </table></div></section>
  )
}

function Trace() {
  const { d, nodes } = useApp()
  const expo: string[] = (d.team.headline.exposure_nodes?.value || '').split(',').map((s: string) => s.trim()).filter((k: string) => nodes[k])
  const [sel, setSel] = useState(expo[0])
  const n = nodes[sel]
  const path = n.confidence.path.map((id: string) => d.edges.find((e: any) => e.id === id))
  return (
    <section className="panel"><div className="ph"><h2>Why do we believe it?</h2><span>every hop from the plant to the product, with its records</span><span className="grow" />
      <div className="seg">{expo.map(k => <button key={k} className={k === sel ? 'on' : ''} onClick={() => setSel(k)}>{short(nodes[k]).split(' ')[0]}</button>)}</div></div>
      <div className="pb">
        <div className="row" style={{ marginBottom: 14, gap: 6 }}>
          <span className="chip dark">{short(n)} {n.site}</span>{path.map((e: any) => <React.Fragment key={e.id}><span className="muted">→</span><span className="chip">{e.dst === 'ND' ? 'NovaDrive' : `${short(nodes[e.dst])} ${nodes[e.dst].site}`}</span></React.Fragment>)}
          <span className="muted">→</span>{n.components.map((c: string) => <span key={c} className="chip">{c}</span>)}<span className="muted">→</span>{n.products.map((p: string) => <span key={p} className="chip dark">{p}</span>)}
          <span className="grow" /><span className="small muted">evidence grade</span><Grade g={n.grade} />
        </div>
        <div className="g" style={{ gridTemplateColumns: `repeat(${path.length}, minmax(0,1fr))` }}>
          {path.map((e: any) => (
            <div key={e.id}>
              <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}><b>{short(nodes[e.src])} → {e.dst === 'ND' ? 'NovaDrive' : short(nodes[e.dst])}</b><span className="small muted">{e.families} independent sources</span></div>
              {Array.from(new Set(e.support.map((s: any) => s.rec))).map((r: any) => <Record key={r} id={r} />)}
            </div>))}
        </div>
      </div>
    </section>
  )
}
