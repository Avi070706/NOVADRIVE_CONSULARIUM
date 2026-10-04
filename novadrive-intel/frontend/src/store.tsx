import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

export type View = 'overview' | 'network' | 'risk' | 'signals' | 'sourcing' | 'evidence'
export type Insp = { type: 'node' | 'component' | 'record'; id: string }

export const money = (v: number, d = 0) => (v >= 1000 ? `$${(v / 1000).toFixed(2)}B` : `$${(v ?? 0).toFixed(d)}M`)
export const riskColor = (r: number | null | undefined) =>
  r == null ? 'var(--r0)' : r >= 75 ? 'var(--r3)' : r >= 65 ? 'var(--r2)' : r >= 50 ? 'var(--r1)' : 'var(--r0)'
/** reading text from the scorecard → css class */
export const readClass = (s: string = '') => { const t = s.toLowerCase(); return t.startsWith('act') ? 'act' : t.startsWith('verify') ? 'verify' : t.startsWith('monitor') ? 'monitor' : 'routine' }
export const short = (n: any) => (n?.label || n?.short || '').replace(/ \((inferred|hypothesis)\)/, '')

type Ctx = {
  d: any; err: string | null; view: View; go: (v: View, o?: { focus?: string | null; product?: string }) => void
  stack: Insp[]; open: (i: Insp) => void; back: () => void; close: () => void
  nodes: Record<string, any>; focus: string | null; setFocus: (s: string | null) => void
  product: string; setProduct: (p: string) => void; changed: Set<string>
  toasts: any[]; dismiss: (i: number) => void; palette: boolean; setPalette: (b: boolean) => void
  target: string | null; setTarget: (s: string | null) => void; signal: string | null; setSignal: (s: string | null) => void; pulse: boolean
}
const C = createContext<Ctx>(null as any)
export const useApp = () => useContext(C)

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [view, setView] = useState<View>(() => (location.hash.slice(1) as View) || 'overview')
  const [stack, setStack] = useState<Insp[]>([])
  const [focus, setFocus] = useState<string | null>(null)
  const [product, setProduct] = useState('all')
  const [changed, setChanged] = useState<Set<string>>(new Set())
  const [toasts, setToasts] = useState<any[]>([])
  const [palette, setPalette] = useState(false)
  const [target, setTarget] = useState<string | null>(null)
  const [signal, setSignal] = useState<string | null>(null)
  const [pulse, setPulse] = useState(false)
  const ver = useRef(0)

  const load = useCallback(async (announce = false) => {
    try {
      const r = await fetch('/api/state')
      if (!r.ok) throw new Error(r.statusText)
      const s = await r.json()
      ver.current = s.version
      setD(s); setErr(s.error)
      if (announce) {
        const ch = s.changes || []
        setChanged(new Set(ch.map((c: any) => c.id).filter(Boolean)))
        setToasts(t => [...t, { items: ch.slice(0, 5).map((c: any) => c.text), at: Date.now() }])
        setPulse(true); setTimeout(() => setPulse(false), 4000); setTimeout(() => setChanged(new Set()), 20000)
      }
    } catch (e: any) { setErr(String(e.message || e)) }
  }, [])
  useEffect(() => {
    load()
    const t = setInterval(async () => {
      try { const v = await (await fetch('/api/version')).json(); if (ver.current && v.version !== ver.current) load(true) } catch { /* restarting */ }
    }, 2000)
    return () => clearInterval(t)
  }, [load])
  useEffect(() => { location.hash = view; document.querySelector('.main')?.scrollTo(0, 0) }, [view])
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(p => !p) }
      if (e.key === 'Escape') { setPalette(false); setStack([]) }
    }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [])
  const nodes = useMemo(() => (d ? Object.fromEntries(d.nodes.map((n: any) => [n.id, n])) : {}), [d])
  const v: Ctx = {
    d, err, view, stack, nodes, focus, product, changed, toasts, palette, target, signal, pulse,
    go: (x, o) => { setView(x); if (o?.focus !== undefined) setFocus(o.focus); if (o?.product) setProduct(o.product); setStack([]) },
    open: i => setStack(s => [...s.filter(x => !(x.type === i.type && x.id === i.id)), i].slice(-5)),
    back: () => setStack(s => s.slice(0, -1)), close: () => setStack([]),
    setFocus, setProduct, dismiss: i => setToasts(t => t.filter((_, j) => j !== i)), setPalette, setTarget, setSignal,
  }
  return <C.Provider value={v}>{children}</C.Provider>
}
