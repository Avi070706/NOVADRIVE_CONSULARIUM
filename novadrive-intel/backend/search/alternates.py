"""Alternate-supplier discovery for a flagged node.

Two separate assessments (never blended):
  * Technical fit (0-100): evidence found for each criterion of a transparent framework.
  * Supplier risk screen: financial / operational / geographic / evidence-quality signals,
    each 'low', 'elevated', 'high' or 'unknown' — unknown is never treated as low.

Status ladder (a candidate never jumps to 'qualified' from public data):
  potential  → found in public sources for the right input
  screened   → desk screen shows the capability AND the application (still not approved)
  qualified  → only when NovaDrive / Tier-1 qualification evidence exists in the case data
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

PROFILES = {
    "dies": {"match": ["semiconductor", "die", "wafer"], "label": "Power semiconductor dies (SiC / IGBT)",
             "query": "silicon carbide power MOSFET bare die manufacturer industrial inverter EV charging",
             "tech": ["silicon carbide", "sic", "mosfet", "igbt", "bare die", "die", "power semiconductor", "trench"],
             "app": ["inverter", "industrial", "motor drive", "charging", "charger", "traction", "dc-dc", "energy storage", "power supplies"]},
    "substrates": {"match": ["printed circuit", "substrate", "pcb"], "label": "Printed circuit substrates for control / BMS boards",
                   "query": "industrial printed circuit board substrate manufacturer power electronics heavy copper automotive",
                   "tech": ["pcb", "printed circuit", "substrate", "heavy copper", "thick copper", "multilayer", "insulated metal", "hdi"],
                   "app": ["industrial", "automotive", "power", "inverter", "control", "converter", "medical"]},
    "film": {"match": ["dielectric", "film"], "label": "Dielectric film for DC-link capacitors",
             "query": "polypropylene capacitor film manufacturer BOPP dielectric film power electronics inverter",
             "tech": ["polypropylene", "bopp", "capacitor film", "dielectric", "metallised", "metallized", "film"],
             "app": ["capacitor", "inverter", "power electronics", "electrified", "ev ", "power capacitor", "automotive"]},
    "modules": {"match": ["power assembl"], "label": "Power assemblies / modules (M10/M20)",
                "query": "IGBT SiC power module manufacturer industrial inverter EV charger power assembly",
                "tech": ["power module", "igbt", "sic", "half-bridge", "power assembly", "module"],
                "app": ["inverter", "industrial", "drive", "charging", "charger", "power conversion"]},
    "control": {"match": ["control board"], "label": "Industrial control PCBA (C10)",
                "query": "industrial control board PCBA manufacturer EMS power electronics microcontroller",
                "tech": ["pcba", "control board", "ems", "electronics manufacturing", "microcontroller", "assembly"],
                "app": ["industrial", "power", "control", "automation", "inverter"]},
    "capacitor": {"match": ["capacitor"], "label": "DC-link film capacitors (C20)",
                  "query": "DC-link film capacitor manufacturer inverter power electronics",
                  "tech": ["film capacitor", "dc-link", "dc link", "polypropylene", "capacitor"],
                  "app": ["inverter", "power electronics", "ev", "renewable", "industrial", "charging"]},
    "bms": {"match": ["battery"], "label": "Battery-monitoring boards (B10)",
            "query": "battery management system BMS board manufacturer energy storage",
            "tech": ["bms", "battery management", "battery monitoring", "cell monitoring", "pcba"],
            "app": ["energy storage", "ess", "battery", "industrial", "storage"]},
    "cooling": {"match": ["cooling", "thermal"], "label": "Liquid cooling / cold plates (H20)",
                "query": "liquid cold plate manufacturer power electronics thermal management",
                "tech": ["cold plate", "liquid cooling", "thermal management", "heat sink", "heat exchanger"],
                "app": ["power electronics", "inverter", "charger", "battery", "industrial"]},
    "housing": {"match": ["housing", "alumin", "alloy"], "label": "Aluminium enclosures / alloy (H10)",
                "query": "aluminium enclosure fabrication manufacturer industrial electronics",
                "tech": ["enclosure", "aluminium", "aluminum", "cnc", "die casting", "fabrication", "housing"],
                "app": ["industrial", "electronics", "inverter", "automotive"]},
    "magnetics": {"match": ["magnetic"], "label": "Magnetic cores",
                  "query": "ferrite nanocrystalline magnetic core manufacturer power electronics inverter",
                  "tech": ["ferrite", "magnetic core", "nanocrystalline", "inductor", "transformer core"],
                  "app": ["power electronics", "inverter", "industrial", "ev", "charging"]},
    "ceramics": {"match": ["ceramic"], "label": "Ceramic substrates (DBC / AMB)",
                 "query": "DBC AMB ceramic substrate manufacturer power module silicon nitride",
                 "tech": ["dbc", "amb", "direct bonded copper", "silicon nitride", "alumina", "ceramic substrate"],
                 "app": ["power module", "inverter", "ev", "industrial"]},
    "mcu": {"match": ["microcontroller"], "label": "Microcontrollers",
            "query": "industrial microcontroller manufacturer motor control power conversion",
            "tech": ["microcontroller", "mcu", "arm", "dsp"], "app": ["industrial", "motor control", "power", "automotive"]},
}
FOOTPRINT = ["plant", "plants", "factory", "facilities", "production site", "sites", "austria", "japan", "india", "china", "korea", "usa",
             "u.s.", "europe", "asia", "malaysia", "200 mm", "200mm", "global", "worldwide", "germany"]
SCALE = ["mass production", "capacity", "high-volume", "employees", "largest", "expansion", "expand", "million", "billion", "leading"]
PRESENCE = ["automotive", "oem", "customers", "industrial", "leader", "dominates", "global leader", "decades", "years"]
QUAL = ["aec-q", "iatf", "iso 9001", "ipc", "ul ", "qualified", "qualification", "aqg324", "validation", "avalanche testing"]
FIT = [("technical", "Technical capability", 0.30), ("application", "Application relevance", 0.25), ("footprint", "Manufacturing footprint", 0.15),
       ("scale", "Scale", 0.10), ("presence", "Industry presence", 0.10), ("qualification", "Qualification readiness", 0.10)]
RISK_RX = {
    "financial": [(r"chapter 11|bankrupt|insolven|administration", "high"), (r"restructur|loss|negative .*margin|debt|covenant|layoff", "elevated")],
    "operational": [(r"recall|fire|explosion|shutdown|production delay|outage", "elevated")],
}
COMPANY = re.compile(r"\b(company|corporation|manufacturer|inc\.?|ag|gmbh|ltd|headquartered|founded|semiconductor maker)\b", re.I)
SKIP = re.compile(r"wikipedia\.org/wiki/(List_|Category:)|linkedin|youtube|facebook|reddit|alibaba|amazon|indiamart|made-in-china|patents\.|justia", re.I)


def profile_for(node: dict) -> tuple[str, dict]:
    hay = f"{node.get('cap', '')} {' '.join(node.get('inputs', []))}".lower()
    for key, p in PROFILES.items():
        if any(m in hay for m in p["match"]):
            return key, p
    return "generic", {"label": node.get("cap") or "Input", "query": f"{node.get('cap')} manufacturer industrial power electronics",
                       "tech": [w for w in (node.get("cap") or "").lower().split() if len(w) > 3], "app": ["industrial", "power", "inverter"]}


def _terms(text, terms):
    t = " " + text.lower() + " "
    return sorted({k.strip() for k in terms if k in t})


def assess(name, domain, sources, prof, today):
    """Score technical fit and a separate risk screen from the evidence text of a candidate."""
    text = " ".join(f"{s.get('title', '')} {s.get('note') or s.get('snippet', '')}" for s in sources)
    crit = []
    lists = {"technical": prof["tech"], "application": prof["app"], "footprint": FOOTPRINT, "scale": SCALE, "presence": PRESENCE, "qualification": QUAL}
    for key, label, w in FIT:
        hits = _terms(text, lists[key])
        sc = min(3, len(hits))
        where = [i for i, s in enumerate(sources) if _terms(f"{s.get('title', '')} {s.get('note') or s.get('snippet', '')}", lists[key])]
        crit.append({"key": key, "label": label, "weight": w, "score": sc, "terms": hits[:6], "sources": where})
    fit = round(sum(c["weight"] * c["score"] / 3 for c in crit) * 100)
    tech, app = crit[0]["score"], crit[1]["score"]
    stage = "screened" if tech >= 2 and app >= 2 and fit >= 55 else "potential"

    dims = []
    for key, label in (("financial", "Financial"), ("operational", "Operational")):
        level, note, src = "unknown", "No public signal found in the retrieved sources — needs due diligence.", None
        for i, s in enumerate(sources):
            st = f"{s.get('title', '')} {s.get('note') or s.get('snippet', '')}".lower()
            for rx, lv in RISK_RX[key]:
                if re.search(rx, st):
                    if level == "unknown" or (lv == "high" and level != "high"):
                        level, note, src = lv, s.get("note") or s.get("snippet"), i
        if key == "financial" and level == "high" and re.search(r"emerged|exit", text.lower()):
            level, note = "elevated", note + " (Restructuring completed — residual risk remains.)"
        dims.append({"key": key, "label": label, "level": level, "note": note, "source": src})
    fp = crit[2]["terms"]
    countries = [t for t in fp if t in ("austria", "japan", "india", "china", "korea", "usa", "u.s.", "malaysia", "germany")]
    geo = ("low" if len(countries) >= 3 else "elevated" if countries else "unknown")
    dims.append({"key": "geographic", "label": "Geographic", "level": geo,
                 "note": (f"Production stated in {', '.join(c.title() for c in countries)}." if countries else "Plant locations not stated in the sources.")
                 + (" Single-country footprint." if len(countries) == 1 else ""), "source": None})
    first_party = sum(1 for s in sources if domain and domain.split(".")[0] in (urlparse(s.get("url", "")).netloc or ""))
    eq = "low" if len(sources) >= 2 and first_party < len(sources) else "elevated" if len(sources) >= 2 else "high"
    dims.append({"key": "evidence", "label": "Evidence quality", "level": eq,
                 "note": f"{len(sources)} source(s), {first_party} from the company itself." + (" Mostly self-description — independent confirmation needed." if first_party == len(sources) else ""), "source": None})
    known = [d for d in dims if d["level"] != "unknown"]
    lv = {"low": 20, "elevated": 55, "high": 85}
    risk_score = round(sum(lv[d["level"]] for d in known) / len(known)) if known else None
    return {"name": name, "domain": domain, "stage": stage, "fit": fit, "criteria": crit,
            "risk": {"score": risk_score, "dims": dims, "unknown": len(dims) - len(known)}, "sources": sources}


def internal_options(node, state):
    """What the case data itself says about alternatives (qualified sources, look-alikes, prospects)."""
    nodes = {n["id"]: n for n in state["nodes"]}
    out = []
    for b in node["buyers"]:
        if b == "ND":
            continue
        peers = [e for e in state["edges"] if e["dst"] == b and e["src"] != node["id"] and set(e["inputs"]) & set(
            next(x for x in state["edges"] if x["src"] == node["id"] and x["dst"] == b)["inputs"])]
        if not peers:
            out.append({"name": f"No other {', '.join(next(x for x in state['edges'] if x['src'] == node['id'] and x['dst'] == b)['inputs'])} source at {nodes[b]['short']}",
                        "stage": "none", "note": "No second supplier of this input to this buyer appears in the evidence.", "records": []})
    if node["tier"] == 1:
        for c in node["components"]:
            for e in state["edges"]:
                if e["dst"] == "ND" and c in e["components"] and e["src"] != node["id"]:
                    peer = nodes[e["src"]]
                    shared = sorted(set(u for u in nodes if node["id"] in nodes[u]["tier1"] and e["src"] in nodes[u]["tier1"]))
                    out.append({"name": peer["short"], "stage": "qualified", "note": f"Already qualified for {c} ({e['alloc'].get(c)}% allocation)."
                                + (f" Shares upstream {', '.join(nodes[s]['short'] for s in shared[:3])} — switching volume does not remove that dependency." if shared else ""),
                                "records": [s["rec"] for s in e["support"]], "shared": shared})
    for fn in node.get("facility_notes", []):
        if "replacement" in fn["note"]:
            out.append({"name": f"{node['short']} {fn['site']}", "stage": "rejected", "note": fn["note"], "records": [fn["rec"]]})
    for r in state["evidence"]:
        for m in re.finditer(r"([A-Z][A-Za-z]+) is a prospective alternative", r["detail"]):
            if node["id"] in r.get("entities", []) or node["short"].split()[0] in r["detail"]:
                out.append({"name": m[1], "stage": "potential", "note": "Named in the case evidence as a prospective alternative only — not qualified, no capability data.",
                            "records": [r["id"]]})
    return out


def find_alternates(node, state, svc, snapshot_path: Path, live: bool, today: str):
    edge_inputs = sorted({i for e in state["edges"] if e["src"] == node["id"] for i in e["inputs"]})
    nn = {**node, "inputs": edge_inputs}
    key, prof = profile_for(nn)
    comps = {c["id"]: c for c in state["components"]}
    need_comps = [comps[c] for c in node["components"] if c in comps]
    known = {n["short"].split()[0].lower() for n in state["nodes"]} | {e["short"].split()[0].lower() for e in state["entities"].values()}

    snap = json.loads(snapshot_path.read_text()) if snapshot_path.exists() else {}
    snap_c = [assess(c["name"], c["domain"], [{**s, "provider": "Analyst snapshot"} for s in c["sources"]], prof, today)
              for c in snap.get("profiles", {}).get(key, [])]

    live_block = {"status": "skipped", "attempts": [], "candidates": []}
    if live:
        res = svc.search(prof["query"], 12)
        groups = {}
        wiki = res.get("provider") == "Wikipedia API"
        for r in res["results"]:
            if SKIP.search(r["url"]) or r["domain"].split(".")[0].lower() in known:
                continue
            # encyclopedia pages only count when they describe a company, never a technology topic
            if "wikipedia.org" in r["domain"] and (not wiki or not COMPANY.search(r["snippet"])):
                continue
            key = r["url"] if wiki else r["domain"]
            groups.setdefault(key, []).append({"title": r["title"], "url": r["url"], "snippet": r["snippet"],
                                                       "published": r.get("published"), "provider": r["provider"]})
        cands = []
        for key, srcs in groups.items():
            dom = key if not wiki else "wikipedia.org"
            name = srcs[0]["title"] if res.get("provider") == "Wikipedia API" else re.split(r"\s[|\-–:]\s", srcs[0]["title"])[-1].strip() or dom
            if res.get("provider") != "Wikipedia API" and len(name) > 40:
                name = dom
            cands.append(assess(name, dom, srcs, prof, today))
        cands = [c for c in cands if c["criteria"][0]["score"] > 0]
        cands.sort(key=lambda c: -c["fit"])
        live_block = {"status": res["status"], "provider": res.get("provider"), "retrieved": res.get("retrieved"),
                      "attempts": res["attempts"], "query": prof["query"], "candidates": cands[:8]}

    validate = [
        f"Electrical / thermal ratings against NovaDrive's {', '.join(c['id'] for c in need_comps) or 'component'} specification",
        "Quality system audit (IATF 16949 / ISO 9001) and PPAP-style first-article approval",
        "Capacity commitment, lead time and allocation terms",
        f"Qualification time: ~{max([c['lead_time'] for c in need_comps] or [8]):.0f} weeks indicative (Components Context)",
        "Re-qualification by the Tier-1 assembler if the input is changed inside its product",
        "Independence check: the candidate must not share the same plant, zone or owner as the incumbent",
    ]
    return {
        "node": {"id": node["id"], "name": node["short"], "tier": node["tier"], "site": node["site"], "zone": node["zone"]},
        "need": {"profile": key, "label": prof["label"], "inputs": edge_inputs, "components": [{"id": c["id"], "name": c["name"], "application": c["application"],
                 "use_case": c["use_case"], "screening": c["screening"], "lead_time": c["lead_time"]} for c in need_comps],
                 "products": node["products"], "revenue": node["rev"]},
        "query": prof["query"], "framework": [{"key": k, "label": l, "weight": w} for k, l, w in FIT],
        "internal": internal_options(node, state),
        "snapshot": {"retrieved": snap.get("retrieved"), "method": snap.get("method"), "about": snap.get("_about"), "candidates": snap_c},
        "live": live_block, "validate": validate,
    }
