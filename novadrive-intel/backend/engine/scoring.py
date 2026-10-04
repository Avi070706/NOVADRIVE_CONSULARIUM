"""Exposure propagation, explainable risk factors and (separately) assessment confidence."""
from __future__ import annotations

from collections import defaultdict, deque

from .network import ND

FACTORS = [
    {"key": "criticality", "label": "Business criticality", "weight": 0.20,
     "help": "Share of NovaDrive revenue whose products depend on this node, scaled by how much of the component flows through it."},
    {"key": "concentration", "label": "Concentration", "weight": 0.15,
     "help": "Effective share of NovaDrive's requirement for the affected component that passes through this node."},
    {"key": "network", "label": "Network dependence", "weight": 0.15,
     "help": "How many Tier-1 suppliers, components and products converge on this node."},
    {"key": "substitutability", "label": "Substitution difficulty", "weight": 0.15,
     "help": "Qualification lead time of the affected component, sole-source position and explicit evidence that no alternative is qualified."},
    {"key": "financial", "label": "Financial health", "weight": 0.15,
     "help": "Liquidity (current ratio) and leverage (net debt / EBITDA). Missing data is scored cautiously at 60, never as safe."},
    {"key": "operational", "label": "Operational", "weight": 0.10,
     "help": "Shipment timeliness level and trend, plus the assurance-gap index."},
    {"key": "geography", "label": "Geography", "weight": 0.10,
     "help": "Physical-hazard, logistics-friction and infrastructure indices of the production facility's zone."},
]
MISSING_DEFAULT = 60.0
OBSERVED_ONLY = 0.8  # weight when a node is the only *observed* source of an input, without evidence that no other source exists


def clip(v):
    return float(max(0.0, min(100.0, v)))


def build_scores(ents, net, products, comps, inds):
    edges = net["edges"]
    E = {(e["src"], e["dst"]): e for e in edges}
    rev = {p["id"]: p["revenue"] for p in products}
    total = sum(rev.values()) or 1.0
    lead = {c["id"]: c["lead_time"] for c in comps}
    comp_products = {c["id"]: set(c["products"]) for c in comps}

    buyers = defaultdict(list)
    suppliers = defaultdict(list)
    for e in edges:
        buyers[e["src"]].append(e["dst"])
        suppliers[e["dst"]].append(e["src"])

    # tiers: shortest path to NovaDrive over all candidate links
    tier = {ND: 0}
    q = deque([ND])
    while q:
        b = q.popleft()
        for s in suppliers[b]:
            if s not in tier:
                tier[s] = tier[b] + 1
                q.append(s)

    # (t1, component) pairs fed by each node — programme-scoped, confirmed-only and all-links variants
    def feeds(n, confirmed_only, seen=()):
        pairs = set()
        for b in buyers[n]:
            e = E[(n, b)]
            if confirmed_only and e["status"] != "confirmed":
                continue
            if b == ND:
                pairs |= {(n, c) for c in e["components"]}
            elif b not in seen:
                up = feeds(b, confirmed_only, seen + (n,))
                if e["programs"]:
                    up = {(t, c) for t, c in up if c in e["programs"]}
                pairs |= up
        return pairs

    # effective share of NovaDrive's requirement for component c that flows through node n
    def share(n, c, seen=()):
        tot = 0.0
        for b in buyers[n]:
            e = E[(n, b)]
            if e["status"] != "confirmed":
                continue
            if b == ND:
                tot += e["alloc"].get(c, 100) / 100 if c in e["components"] else 0
            elif b not in seen and (not e["programs"] or c in e["programs"]):
                peers = [s for s in suppliers[b] if E[(s, b)]["status"] == "confirmed" and set(E[(s, b)]["inputs"]) & set(e["inputs"])]
                # only-observed supplier ≠ proven sole supplier: discount unless evidence explicitly says no alternative exists
                certainty = 1.0 if (len(peers) > 1 or n in net["sole_source"]) else OBSERVED_ONLY
                tot += share(b, c, seen + (n,)) / max(1, len(peers)) * certainty
        return min(1.0, tot)

    # best (max-min) relationship confidence along any confirmed-or-not path to NovaDrive
    def path_conf(n, seen=()):
        best, best_path = 0, []
        for b in buyers[n]:
            e = E[(n, b)]
            if b == ND:
                c, p = e["confidence"], [e["id"]]
            elif b in seen:
                continue
            else:
                c2, p2 = path_conf(b, seen + (n,))
                c, p = min(e["confidence"], c2), [e["id"], *p2]
            if c > best:
                best, best_path = c, p
        return best, best_path

    nodes = {}
    for n, t in tier.items():
        if n == ND:
            continue
        ent = ents[n]
        pc = feeds(n, True)
        pa = feeds(n, False)
        comps_c = sorted({c for _, c in pc})
        comps_a = sorted({c for _, c in pa})
        prods_c = sorted({p for c in comps_c for p in comp_products.get(c, set())} |
                         {p for b in buyers[n] if b == ND for p in E[(n, b)]["products"]})
        prods_a = sorted({p for c in comps_a for p in comp_products.get(c, set())} | set(prods_c))
        t1c = sorted({x for x, _ in pc})
        t1a = sorted({x for x, _ in pa})
        rev_c = sum(rev.get(p, 0) for p in prods_c)
        rev_a = sum(rev.get(p, 0) for p in prods_a)
        eff = {c: round(share(n, c), 3) for c in comps_c}
        maxshare = max(eff.values() or [0])

        ind = inds.get(n, {})
        missing = [k for k, v in ind.items() if v is None] if ind else ["all indicators"]
        explain = {}

        # 1 criticality
        crit = 100 * rev_c / total * (0.4 + 0.6 * maxshare) if rev_c else 0
        explain["criticality"] = {"score": clip(crit), "inputs": {"revenue_dependent": rev_c, "revenue_share": rev_c / total, "max_share": maxshare},
                                  "text": f"${rev_c:,.0f}m of ${total:,.0f}m revenue ({rev_c / total:.0%}) depends on this node; up to {maxshare:.0%} of a component flows through it." if rev_c else "No confirmed path to a NovaDrive product."}
        # 2 concentration
        conc = 100 * maxshare
        worst = max(eff, key=eff.get) if eff else None
        observed_only = bool(nd_tier_gt1 := (t > 1)) and n not in net["sole_source"] and maxshare < 1
        explain["concentration"] = {"score": clip(conc), "inputs": {"effective_share": eff, "observed_only": observed_only},
                                    "text": (f"{eff[worst]:.0%} of NovaDrive's {worst} requirement flows through this node." if worst else "No confirmed component flow.")
                                    + (" It is the only source observed in the evidence, but no record proves its buyer has no other source (weighted at 80%)." if observed_only else "")}
        # 3 network dependence
        nT1, nC, nP = len(t1c), len(comps_c), len(prods_c)
        nB = len([b for b in buyers[n] if E[(n, b)]["status"] == "confirmed"])
        netd = clip(30 * max(0, nB - 1) + 12 * nT1 + 8 * nC + 6 * nP) if nC else 0
        explain["network"] = {"score": netd, "inputs": {"direct_buyers": nB, "tier1": t1c, "components": comps_c, "products": prods_c},
                              "text": (f"Supplies {nB} direct customers in the network. " if nB > 1 else "") + f"Feeds {nT1} Tier-1 supplier{'s' if nT1 != 1 else ''}, {nC} component{'s' if nC != 1 else ''} and {nP} product{'s' if nP != 1 else ''}."
                              + (" Several Tier-1 suppliers converge here, so Tier-1 dual-sourcing does not diversify this dependency." if nT1 > 1 else "")}
        # 4 substitutability
        lt = max([lead.get(c, 8) for c in comps_c] or [8])
        sole = bool(comps_c) and all(v >= 0.999 for v in eff.values())
        explicit = n in net["sole_source"]
        sub = 40 + 40 * min(lt / 16, 1) + (20 if sole else 0)
        if explicit:
            sub = 100
        explain["substitutability"] = {"score": clip(sub) if comps_c else 0, "inputs": {"lead_time_weeks": lt, "sole_source": sole, "no_alternative_records": net["sole_source"].get(n, [])},
                                       "text": (f"Evidence states no qualified alternative ({', '.join(net['sole_source'][n])}). " if explicit else "")
                                       + f"Qualifying a replacement for {', '.join(comps_c) or 'its output'} takes ~{lt:.0f} weeks"
                                       + ("; it is the only source on its path." if sole else "; another qualified source carries part of the volume.")}
        # 5 financial
        cr, nd = ind.get("current_ratio"), ind.get("net_debt")
        if cr is None or nd is None:
            fin, ftxt = MISSING_DEFAULT, "No financial data disclosed — scored cautiously at 60 and confidence reduced (missing ≠ safe)."
        else:
            fin = (clip((2.0 - cr) / 1.5 * 100) + clip((nd - 1) / 5 * 100)) / 2
            ftxt = f"Current ratio {cr:.2f} ({'weak' if cr < 1 else 'adequate' if cr < 1.6 else 'healthy'}), net debt / EBITDA {nd:.1f}x ({'high' if nd >= 4 else 'moderate' if nd >= 2.5 else 'low'})."
        explain["financial"] = {"score": clip(fin), "inputs": {"current_ratio": cr, "net_debt_ebitda": nd}, "text": ftxt, "missing": cr is None or nd is None}
        # 6 operational
        tm, ch, ag = ind.get("timeliness"), ind.get("timeliness_change"), ind.get("assurance_gap")
        lvl = clip((95 - (tm if tm is not None else 85)) / 20 * 100)
        trend = clip(-(ch or 0) / 10 * 100)
        agv = ag if ag is not None else MISSING_DEFAULT
        ops = 0.4 * lvl + 0.3 * trend + 0.3 * agv
        explain["operational"] = {"score": clip(ops), "inputs": {"timeliness": tm, "timeliness_change": ch, "assurance_gap": ag},
                                  "text": (f"On-time {tm:.1f}%" if tm is not None else "On-time n/a") + (f", {ch:+.1f}pp since January" if ch is not None else "")
                                  + (f"; assurance gap {ag:.0f}." if ag is not None else "; assurance gap not disclosed (scored 60)."), "missing": ag is None}
        # 7 geography
        hz, lg, inf = ind.get("hazard"), ind.get("logistics"), ind.get("infrastructure")
        geo = 0.5 * (hz if hz is not None else MISSING_DEFAULT) + 0.25 * (lg if lg is not None else MISSING_DEFAULT) + 0.25 * (inf if inf is not None else MISSING_DEFAULT)
        explain["geography"] = {"score": clip(geo), "inputs": {"hazard": hz, "logistics": lg, "infrastructure": inf},
                                "text": f"Zone {ent['zone']}: physical hazard {hz:.0f}, logistics friction {lg:.0f}, infrastructure {inf:.0f}." if hz is not None else f"Zone {ent['zone']}: indices missing (scored 60)."}

        # confidence (separate from risk)
        pconf, ppath = path_conf(n)
        fields = 8
        present = sum(1 for v in ind.values() if v is not None) if ind else 0
        completeness = present / fields
        overall = round(0.65 * pconf + 35 * completeness)
        nodes[n] = {
            "id": n, "name": ent["name"], "short": ent["short"], "tier": t, "type": ent["type"], "cap": ent["cap"],
            "site": ent["site"], "zone": ent["zone"], "market": ent["market"], "sites": ent["sites"],
            "components": comps_c, "components_all": comps_a, "products": prods_c, "products_all": prods_a,
            "tier1": t1c, "tier1_all": t1a, "rev": rev_c, "rev_all": rev_a, "rev_share": rev_c / total,
            "weekly_rev": rev_c / 52, "eff_share": eff, "buyers": buyers[n], "suppliers": suppliers[n],
            "factors": explain, "missing": missing, "sole_source": sole, "no_alt_evidence": net["sole_source"].get(n, []),
            "facility_notes": net["facility_notes"].get(n, []),
            "confidence": {"relationship": pconf, "path": ppath, "data": round(completeness * 100), "overall": overall,
                           "label": "High" if overall >= 70 else "Medium" if overall >= 45 else "Low"},
            "status": "confirmed" if pc else ("inference" if any(E[(n, b)]["status"] == "inference" for b in buyers[n]) else "hypothesis"),
        }
    weights = {f["key"]: f["weight"] for f in FACTORS}
    for nd in nodes.values():
        nd["risk"] = risk_of(nd, weights)
    return nodes, tier, total


def risk_of(nd, weights):
    tw = sum(weights.values()) or 1
    return round(sum(nd["factors"][k]["score"] * w for k, w in weights.items()) / tw)


def priority(risk, conf, event=False):
    if risk >= 65 and conf >= 60:
        return "act"
    if risk >= 65:
        return "verify"
    if risk >= 50 or event:
        return "monitor"
    return "routine"
