import React, { useMemo, useState } from 'react'
import { money, riskColor, short, useApp } from '../store'
import { Grade, Reading, Tip } from '../components/ui'

const NW = 188, NH = 40, GAP = 12
type P = { x: number; y: number; w: number; h: number }
const GC: Record<string, string> = { A: 'var(--c3)', B: 'var(--c2)', C: 'var(--c1)', D: '#fff' }

export default function Network() {
  const { d, nodes, open, focus, setFocus, product, setProduct, changed } = useApp()
  const [lens, setLens] = useState<'tier' | 'zone'>('tier')
  const [ghosts, setGhosts] = useState(true)
  const [hover, setHover] = useState<string | null>(null)
  const [tip, setTip] = useState<any>(null)

  const visible = useMemo(() => d.nodes.filter((n: any) => product === 'all' || n.products_all.includes(product)), [d, product])
  const vis = new Set(visible.map((n: any) => n.id))
  const comps = d.components.filter((c: any) => product === 'all' || c.products.includes(product))
  const prods = d.products.filter((p: any) => product === 'all' || p.id === product)

  const layout = useMemo(() => {
    const pos: Record<string, P> = {}
    const X: Record<string, number> = { 3: 24, 2: 266, 1: 508, c: 760, p: 892 }
    const cols: Record<number, any[]> = { 1: [], 2: [], 3: [] }
    visible.forEach((n: any) => cols[Math.min(n.tier, 3)].push(n))
    cols[1].sort((a, b) => (a.components[0] || '').localeCompare(b.components[0] || ''))
    const bary = (n: any, ref: Record<string, number>) => { const ys = n.buyers.map((b: string) => ref[b]).filter((v: any) => v != null); return ys.length ? ys.reduce((a: number, b: number) => a + b, 0) / ys.length : 1e6 }
    let bands: any[] = [], height = 0
    if (lens === 'tier') {
      const yr: Record<string, number> = {}
      cols[1].forEach((n, i) => (yr[n.id] = i))
      cols[2].sort((a, b) => bary(a, yr) - bary(b, yr)); cols[2].forEach((n, i) => (yr[n.id] = (i * cols[1].length) / cols[2].length))
      cols[3].sort((a, b) => bary(a, yr) - bary(b, yr))
      const H = Math.max(...[1, 2, 3].map(t => cols[t].length)) * (NH + GAP) + 70
      ;[1, 2, 3].forEach(t => { const n = cols[t].length; const st = Math.min(NH + GAP * 3, (H - 70) / Math.max(1, n)); const y0 = 50 + ((H - 70) - st * n) / 2; cols[t].forEach((nd, i) => (pos[nd.id] = { x: X[t], y: y0 + i * st, w: NW, h: NH })) })
      height = H
    } else {
      const zs = Array.from(new Set(visible.map((n: any) => n.zone))).sort((a: any, b: any) => (d.zones[b].events.length - d.zones[a].events.length) || ((d.zones[b].hazard || 0) - (d.zones[a].hazard || 0)))
      let y = 50
      zs.forEach((z: any) => {
        const rows = Math.max(...[1, 2, 3].map(t => cols[t].filter(n => n.zone === z).length))
        ;[1, 2, 3].forEach(t => cols[t].filter(n => n.zone === z).sort((a, b) => b.risk - a.risk).forEach((nd, i) => (pos[nd.id] = { x: X[t], y: y + 24 + i * (NH + GAP), w: NW, h: NH })))
        const h = rows * (NH + GAP) + 28; bands.push({ z, y, h }); y += h + 8
      })
      height = y + 10
    }
    const ch = Math.max(height, comps.length * 52 + 70)
    comps.forEach((c: any, i: number) => (pos['C:' + c.id] = { x: X.c, y: 50 + ((ch - 70) * (i + 0.5)) / comps.length - 16, w: 92, h: 32 }))
    const tot = prods.reduce((a: number, p: any) => a + p.revenue, 0)
    let acc = 50
    prods.forEach((p: any) => { const h = Math.max(54, ((ch - 90) * p.revenue) / tot); pos['P:' + p.id] = { x: X.p, y: acc, w: 150, h: h - 12 }; acc += h })
    return { pos, bands, height: Math.max(ch, acc) + (ghosts ? 40 + Math.ceil(d.rejected.length / 6) * 64 : 10) }
  }, [visible, lens, comps, prods, ghosts])
  const { pos, bands } = layout

  const sel = hover || focus
  const lit = useMemo(() => {
    if (!sel || !nodes[sel]) return null
    const s = new Set<string>([sel]); const up = [sel], dn = [sel]
    while (up.length) { const x = up.pop()!; d.edges.forEach((e: any) => { if (e.dst === x && !s.has(e.src)) { s.add(e.src); up.push(e.src) } }) }
    while (dn.length) { const x = dn.pop()!; d.edges.forEach((e: any) => { if (e.src === x && e.dst !== 'ND' && !s.has(e.dst)) { s.add(e.dst); dn.push(e.dst) } }) }
    nodes[sel].components.forEach((c: string) => s.add('C:' + c)); nodes[sel].products.forEach((p: string) => s.add('P:' + p))
    return s
  }, [sel, d])

  const cv = (a: P, b: P) => { const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2, m = (x1 + x2) / 2; return `M${x1},${y1} C${m},${y1} ${m},${y2} ${x2},${y2}` }
  const W = 1060
  const links: React.ReactNode[] = []
  d.edges.forEach((e: any) => {
    if (!vis.has(e.src)) return
    const a = pos[e.src]
    const tg = e.dst === 'ND' ? e.components.filter((c: string) => pos['C:' + c]).map((c: string) => 'C:' + c) : vis.has(e.dst) ? [e.dst] : []
    tg.forEach((t: string) => {
      const b = pos[t]; if (!a || !b) return
      const on = !lit || (lit.has(e.src) && lit.has(t))
      links.push(<path key={e.id + t} d={cv(a, b)} fill="none" stroke={lit && on ? 'var(--ink)' : '#9fb0c0'} strokeWidth={0.8 + e.confidence / 40}
        strokeDasharray={e.status === 'inference' ? '6 4' : e.status === 'hypothesis' ? '1.5 4' : undefined} opacity={on ? (lit ? 0.9 : 0.55) : 0.08} strokeLinecap="round" />)
    })
  })
  comps.forEach((c: any) => c.products.forEach((p: string) => {
    const a = pos['C:' + c.id], b = pos['P:' + p]; if (!a || !b) return
    const on = !lit || (lit.has('C:' + c.id) && lit.has('P:' + p))
    links.push(<path key={c.id + p} d={cv(a, b)} fill="none" stroke={lit && on ? 'var(--ink)' : '#9fb0c0'} strokeWidth={1.3} opacity={on ? 0.55 : 0.08} />)
  }))
  const fn = focus ? nodes[focus] : null

  return (
    <div className="page full">
      <div className="row" style={{ padding: '10px 26px', background: '#fff', borderBottom: '1px solid var(--line)', gap: 16, fontSize: 12.5 }}>
        <div className="seg">{['all', ...d.products.map((p: any) => p.id)].map(p => <button key={p} className={product === p ? 'on' : ''} onClick={() => setProduct(p)}>{p === 'all' ? 'All products' : p}</button>)}</div>
        <div className="seg"><button className={lens === 'tier' ? 'on' : ''} onClick={() => setLens('tier')}>By tier</button><button className={lens === 'zone' ? 'on' : ''} onClick={() => setLens('zone')}>By zone</button></div>
        <label className="row" style={{ gap: 5 }}><input type="checkbox" checked={ghosts} onChange={e => setGhosts(e.target.checked)} />Rejected links</label>
        <span className="grow" /><span className="muted">Click to trace · double-click for details</span>
      </div>
      <div style={{ flex: 1, overflow: 'auto', position: 'relative', background: 'var(--sunken)' }} onClick={() => setFocus(null)}>
        <svg width={W} height={layout.height} style={{ display: 'block', minWidth: W }}>
          {[['Tier 3', 24], ['Tier 2', 266], ['Tier 1', 508], ['Parts', 760], ['Products', 892]].map(([t, x]) => <text key={t as string} x={x as number} y={30} fontSize="12.5" fontWeight="700" fill="var(--ink-2)">{t}</text>)}
          {lens === 'zone' && bands.map((b: any) => { const hot = d.zones[b.z].events.length > 0
            return <g key={b.z}><rect x={12} y={b.y} width={714} height={b.h} rx={4} fill={hot ? 'var(--sig-bg)' : '#fff'} stroke={hot ? '#d9c8ec' : 'var(--line-2)'} />
              <text x={22} y={b.y + 15} fontSize="11.5" fontWeight="700" fill={hot ? 'var(--sig)' : 'var(--ink-3)'}>{b.z}{d.zones[b.z].name ? ` ${d.zones[b.z].name}` : ''} · hazard {d.zones[b.z].hazard ?? 'n/a'}{hot ? ` · ${d.zones[b.z].events.join(', ')} active` : ''}</text></g> })}
          {links}
          {d.ownership.filter((o: any) => pos[o.child]).reduce((acc: any[], o: any) => { const g = acc.find(x => x.p === o.parent); g ? g.k.push(o.child) : acc.push({ p: o.parent, k: [o.child] }); return acc }, [])
            .filter((g: any) => g.k.length > 1).map((g: any) => { const ys = g.k.map((k: string) => pos[k].y + NH / 2); const x = pos[g.k[0]].x - 14
              return <g key={g.p} opacity={lit ? 0.4 : 1}><path d={`M${x + 8},${Math.min(...ys)} H${x} V${Math.max(...ys)} H${x + 8}`} fill="none" stroke="var(--ink-2)" strokeDasharray="3 2" />
                <text transform={`translate(${x - 5},${(Math.min(...ys) + Math.max(...ys)) / 2}) rotate(-90)`} fontSize="10.5" fill="var(--ink-2)" textAnchor="middle">owner {d.entities[g.p].short.split(' ')[0]}</text></g> })}
          {visible.map((n: any) => {
            const p = pos[n.id]; if (!p) return null
            const on = !lit || lit.has(n.id)
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} opacity={on ? 1 : 0.18} style={{ cursor: 'pointer' }}
                onMouseEnter={e => { setHover(n.id); setTip({ x: e.clientX, y: e.clientY, html: <div><b>{short(n)}</b><br />{n.cap}, {n.site} {n.zone}<br />Risk {n.risk} · evidence {n.grade} · {n.reading}<br />{n.rev ? `${money(n.rev)} depends on it` : 'not in confirmed exposure'}</div> }) }}
                onMouseLeave={() => { setHover(null); setTip(null) }} onClick={e => { e.stopPropagation(); setFocus(n.id) }} onDoubleClick={() => open({ type: 'node', id: n.id })}>
                {n.events.length > 0 && <rect x={-5} y={-5} width={NW + 10} height={NH + 10} rx={6} fill="none" stroke="var(--sig)" strokeWidth={1.8} strokeDasharray="4 3" />}
                {changed.has(n.id) && <rect x={-3} y={-3} width={NW + 6} height={NH + 6} rx={5} fill="none" stroke="var(--ok)" strokeWidth={2} />}
                <rect width={NW} height={NH} rx={4} fill="#fff" stroke={focus === n.id ? 'var(--ink)' : '#b7c3cf'} strokeWidth={focus === n.id ? 2 : 1} strokeDasharray={n.status === 'inference' ? '5 3' : n.status === 'hypothesis' ? '1.5 3' : undefined} />
                <rect width={5} height={NH} fill={riskColor(n.risk)} />
                <text x={13} y={16} fontSize="12.5" fontWeight="650" fill="var(--ink)">{short(n).length > 18 ? short(n).slice(0, 17) + '…' : short(n)}</text>
                <text x={13} y={31} fontSize="11" fill="var(--ink-3)">{n.site} {n.zone}{n.rev ? `  ${money(n.rev)}` : ''}</text>
                <text x={NW - 34} y={26} fontSize="17" fontWeight="800" textAnchor="end" fill={riskColor(n.risk)} style={{ fontVariationSettings: "'wdth' 78" }}>{n.risk}</text>
                <g transform={`translate(${NW - 28},11)`}><rect width={18} height={18} rx={2} fill={GC[n.grade] || '#fff'} stroke={n.grade === 'D' ? 'var(--ink-3)' : 'none'} strokeDasharray="1.5 1.5" />
                  <text x={9} y={13} fontSize="11" fontWeight="800" textAnchor="middle" fill={n.grade === 'A' || n.grade === 'B' ? '#fff' : 'var(--c3)'}>{n.grade}</text></g>
                {n.buyers.length > 1 && <g transform={`translate(${NW - 92},-9)`}><rect width={48} height={15} rx={2} fill="var(--ink)" /><text x={24} y={11} fontSize="10.5" fill="#fff" textAnchor="middle" fontWeight="700">feeds {n.buyers.length}</text></g>}
              </g>
            )
          })}
          {comps.map((c: any) => { const p = pos['C:' + c.id]; const on = !lit || lit.has('C:' + c.id)
            return <g key={c.id} transform={`translate(${p.x},${p.y})`} opacity={on ? 1 : 0.2} style={{ cursor: 'pointer' }} onClick={e => { e.stopPropagation(); open({ type: 'component', id: c.id }) }}>
              <rect width={p.w} height={p.h} rx={3} fill="var(--ink)" /><text x={10} y={14} fontSize="12" fontWeight="700" fill="#fff">{c.id}</text><text x={10} y={26} fontSize="10" fill="#a9b6c4">{c.lead_time} wk to qualify</text></g> })}
          {prods.map((pr: any) => { const p = pos['P:' + pr.id]; const on = !lit || lit.has('P:' + pr.id)
            return <g key={pr.id} transform={`translate(${p.x},${p.y})`} opacity={on ? 1 : 0.2}>
              <rect width={8} height={p.h} fill={lit && on && sel ? riskColor(nodes[sel]?.risk) : 'var(--ink)'} />
              <text x={16} y={18} fontSize="14" fontWeight="760" fill="var(--ink)">{pr.id}</text><text x={16} y={34} fontSize="11.5" fill="var(--ink-2)">{pr.name.split(' ')[0]}</text><text x={16} y={49} fontSize="11.5" fill="var(--ink-3)">{money(pr.revenue)}</text></g> })}
          {ghosts && <text x={24} y={layout.height - Math.ceil(d.rejected.length / 6) * 64 - 14} fontSize="12.5" fontWeight="700" fill="var(--ink-2)">Rejected — looked connected, is not</text>}
          {ghosts && d.rejected.map((g: any, i: number) => (
            <g key={g.id} transform={`translate(${24 + (i % 6) * 172},${layout.height - Math.ceil(d.rejected.length / 6) * 64 + Math.floor(i / 6) * 64})`} onMouseEnter={e => setTip({ x: e.clientX, y: e.clientY, html: <div><b>{g.label}</b><br />{g.reason}<br />{g.records.join(', ')}</div> })} onMouseLeave={() => setTip(null)}>
              <rect width={162} height={52} rx={4} fill="none" stroke="var(--ink-3)" strokeDasharray="3 3" />
              <text x={10} y={18} fontSize="12" fontWeight="650" fill="var(--ink-3)" textDecoration="line-through">{g.src_name.slice(0, 22)}</text>
              <text x={10} y={33} fontSize="11" fill="var(--ink-2)">{g.label}</text><text x={10} y={46} fontSize="10.5" fill="var(--ink-3)">{g.records.join(', ')}</text>
            </g>))}
        </svg>
        <div className="panel" style={{ position: 'absolute', right: 16, bottom: 16, padding: '10px 12px', fontSize: 12, display: 'grid', gridTemplateColumns: 'auto auto', gap: '5px 12px', alignItems: 'center' }} onClick={e => e.stopPropagation()}>
          <b style={{ gridColumn: 'span 2' }}>How to read</b>
          <svg width="28" height="10"><rect width="6" height="10" fill="var(--r3)" /><rect x="7" width="6" height="10" fill="var(--r2)" /><rect x="14" width="6" height="10" fill="var(--r1)" /><rect x="21" width="6" height="10" fill="var(--r0)" /></svg><span>risk stripe and score</span>
          <span className="row" style={{ gap: 2 }}><span className="grade A" style={{ width: 13, height: 13, fontSize: 8 }}>A</span><span className="grade C" style={{ width: 13, height: 13, fontSize: 8 }}>C</span></span><span>evidence grade</span>
          <svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="#7d8fa1" strokeWidth="2.6" /></svg><span>confirmed link</span>
          <svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="#7d8fa1" strokeWidth="1.6" strokeDasharray="6 4" /></svg><span>inferred</span>
          <svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="#7d8fa1" strokeWidth="1.4" strokeDasharray="1.5 4" /></svg><span>hypothesis</span>
          <svg width="28" height="12"><rect x="1" y="1" width="26" height="10" rx="2" fill="none" stroke="var(--sig)" strokeDasharray="4 3" /></svg><span>live signal</span>
        </div>
        {fn && (
          <div className="panel" style={{ position: 'absolute', right: 16, top: 16, width: 300, padding: '12px 14px', boxShadow: 'var(--pop)' }} onClick={e => e.stopPropagation()}>
            <div className="row" style={{ justifyContent: 'space-between' }}><b style={{ fontSize: 15 }}>{short(fn)}</b><Grade g={fn.grade} /></div>
            <div className="row" style={{ margin: '6px 0', gap: 10 }}><b className="num" style={{ fontSize: 28, color: riskColor(fn.risk) }}>{fn.risk}</b><Reading r={fn.reading} /></div>
            <div className="small">{fn.tier1.length > 1 ? `Feeds ${fn.tier1.length} Tier-1s → ` : ''}{fn.components.join(', ')} → {fn.products.join(', ') || 'no confirmed product'}{fn.rev ? <> · <b>{money(fn.rev)}</b></> : ''}</div>
            <div className="row" style={{ marginTop: 10 }}><button className="btn pri" onClick={() => open({ type: 'node', id: fn.id })}>Details</button><button className="btn" onClick={() => setFocus(null)}>Clear</button></div>
          </div>
        )}
      </div>
      <Tip tip={tip} />
    </div>
  )
}
