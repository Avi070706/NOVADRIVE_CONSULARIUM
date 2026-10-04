"""Turns scores, links and alerts into management findings: the headline, the
'dual-sourcing illusion' table and a ranked action queue. All text is generated from
the data so it stays correct when the workbook changes."""
from __future__ import annotations

from collections import defaultdict

from .network import ND
from .scoring import priority


def upstream_closure(n, suppliers, E, confirmed=True):
    out, stack = set(), [n]
    while stack:
        x = stack.pop()
        for s in suppliers.get(x, []):
            if confirmed and E[(s, x)]["status"] != "confirmed":
                continue
            if s not in out:
                out.add(s)
                stack.append(s)
    return out


def attention(nd, alert_nodes):
    a = nd["risk"] * (0.5 + 0.5 * nd["confidence"]["overall"] / 100)
    if nd["id"] in alert_nodes:
        a += 12
    if nd.get("acute"):
        a += 8
    return round(a, 1)


def node_actions(nd, nodes):
    f = nd["factors"]
    acts = []
    lt = f["substitutability"]["inputs"]["lead_time_weeks"]
    if nd["priority"] == "act":
        if nd["no_alt_evidence"] or nd["sole_source"]:
            acts.append(f"Start qualifying a second source now — ~{lt:.0f} weeks before it can carry volume.")
            acts.append("Agree buffer-stock targets with " + (", ".join(nodes[t]["short"] for t in nd["tier1"] if t in nodes) or "the buyer") + " to bridge the qualification window.")
        if nd["acute"]:
            acts.append("Ask for stock cover and a recovery plan; monitor payments and covenants weekly.")
    elif nd["priority"] == "verify":
        acts.append("Verify before acting: request financials and a source declaration (does the buyer have other sources of this input?).")
        if nd["missing"]:
            acts.append("Fill the data gaps: " + ", ".join(m.replace("_", " ") for m in nd["missing"]) + ".")
    elif nd["priority"] == "monitor":
        acts.append("Keep on the watch list; re-score when new indicators or events arrive.")
    else:
        acts.append("Routine supplier management.")
    if nd["events"]:
        acts.insert(0, "Respond to active signal " + ", ".join(nd["events"]) + " (see Signals).")
    return acts


def build_story(ents, nodes, edges, ownership, comps, products, alerts, total):
    E = {(e["src"], e["dst"]): e for e in edges}
    suppliers = defaultdict(list)
    for e in edges:
        suppliers[e["dst"]].append(e["src"])
    comp_name = {c["id"]: c["name"] for c in comps}
    alert_nodes = defaultdict(list)
    for a in alerts:
        if a["decision"] == "ALERT":
            for k in a["matched"]:
                alert_nodes[k].append(a["id"])

    for nd in nodes.values():
        nd["acute"] = nd["factors"]["financial"]["score"] >= 85 or nd["factors"]["operational"]["score"] >= 85
        nd["events"] = alert_nodes.get(nd["id"], [])
        p = priority(nd["risk"], nd["confidence"]["overall"], bool(nd["events"]))
        if nd["acute"] and nd["rev_share"] >= 0.5 and p in ("monitor", "routine"):
            p = "act" if nd["confidence"]["overall"] >= 60 else "verify"
        nd["priority"] = p
        nd["attention"] = attention(nd, alert_nodes)
        nd["actions"] = node_actions(nd, nodes)

    # dual-sourcing illusion: components with ≥2 Tier-1 sources that still share upstream nodes / owners
    owners = defaultdict(set)
    for o in ownership:
        owners[o["child"]].add(o["parent"])
    illusions = []
    for c in comps:
        t1 = [s for (s, d), e in E.items() if d == ND and c["id"] in e["components"] and e["status"] == "confirmed"]
        if not t1:
            continue
        alloc = {s: E[(s, ND)]["alloc"].get(c["id"]) for s in t1}
        shared = None
        for s in t1:
            up = {u for u in upstream_closure(s, suppliers, E) if c["id"] in nodes.get(u, {}).get("components", [])}
            shared = up if shared is None else shared & up
        shared = sorted(shared or [], key=lambda k: (nodes[k]["tier"], -nodes[k]["risk"]))
        common_owner = set.intersection(*(owners.get(s, set()) for s in t1)) if len(t1) > 1 else set()
        illusions.append({
            "component": c["id"], "name": c["name"], "tier1": t1, "alloc": alloc, "products": c["products"],
            "revenue": sum(p["revenue"] for p in products if p["id"] in c["products"]),
            "shared_upstream": shared, "common_owner": sorted(common_owner),
            "independent": len(t1) > 1 and not shared and not common_owner,
            "verdict": ("Single Tier-1 source" if len(t1) == 1 else
                        "Dual-sourced, but not independent" if (shared or common_owner) else "Independently dual-sourced"),
        })

    # action queue
    issues = []
    used = set()
    ranked = sorted(nodes.values(), key=lambda n: -n["attention"])

    def node_issue(nd, kind, title, why, nxt, extra_nodes=()):
        issues.append({
            "id": f"I-{nd['id']}", "kind": kind, "title": title, "nodes": [nd["id"], *extra_nodes], "events": nd["events"],
            "priority": nd["priority"], "risk": nd["risk"], "confidence": nd["confidence"]["overall"], "conf_label": nd["confidence"]["label"],
            "exposure": nd["rev"], "products": nd["products"], "why": why, "next": nxt, "attention": nd["attention"],
            "records": sorted({sp["rec"] for b in nd["buyers"] for sp in E[(nd["id"], b)]["support"]} | set(nd["no_alt_evidence"])),
        })
        used.add(nd["id"])

    for nd in ranked:
        if nd["tier"] >= 2 and len(nd["tier1"]) > 1 and nd["no_alt_evidence"]:
            node_issue(nd, "chokepoint", f"{nd['short']} is a hidden single point of failure",
                       [f"{len(nd['tier1'])} Tier-1 suppliers ({', '.join(nodes[t]['short'] for t in nd['tier1'])}) all depend on its {nd['site']} plant for {', '.join(sorted({i for b in nd['buyers'] for i in E[(nd['id'], b)]['inputs']})) or nd['cap']}.",
                        f"Evidence states no qualified alternative ({', '.join(nd['no_alt_evidence'])}).",
                        f"${nd['rev']:,.0f}m ({nd['rev_share']:.0%}) of revenue — {', '.join(nd['products'])}."],
                       [{"text": f"Open qualification of a second {nd['cap'].lower()} source (lead time ~{nd['factors']['substitutability']['inputs']['lead_time_weeks']:.0f} weeks).", "owner": "Sourcing + Engineering", "when": "Start now"},
                        {"text": "Agree buffer stock / safety-stock targets with the dependent Tier-1s until a second source is qualified.", "owner": "Procurement", "when": "2 weeks"}])
    for nd in ranked:
        if nd["id"] in used:
            continue
        if nd["acute"] and nd["rev_share"] >= 0.3:
            f = nd["factors"]
            node_issue(nd, "distress", f"{nd['short']} shows acute financial and delivery stress",
                       [f["financial"]["text"], f["operational"]["text"],
                        f"Sits behind {', '.join(nd['components'])} via {', '.join(nodes[t]['short'] for t in nd['tier1'])} → {', '.join(nd['products'])} (${nd['rev']:,.0f}m)."],
                       [{"text": f"Ask {', '.join(nodes[t]['short'] for t in nd['tier1'])} for stock cover and its back-up for {nd['cap'].lower()}.", "owner": "Procurement", "when": "48 h"},
                        {"text": "Screen alternate sources for the input now, before a default.", "owner": "Sourcing", "when": "1 week"}])
    # geographic cluster under an active alert
    for a in alerts:
        if a["decision"] == "ALERT" and a["type"] == "hazard" and len(a["matched"]) > 1:
            issues.append({"id": f"I-{a['id']}", "kind": "geography", "title": f"{len(a['matched'])} upstream sites share one hazard zone ({', '.join(a['zones'])})",
                           "nodes": a["matched"], "events": [a["id"], *a["merged"]], "priority": "verify",
                           "risk": max(nodes[k]["risk"] for k in a["matched"]), "confidence": None, "conf_label": "Exposure, not disruption",
                           "exposure": a["exposure"], "products": a["products"],
                           "why": [a["why"], "Diversification at Tier-1 does not help: the dependent plants are in the same zone."],
                           "next": a["actions"], "attention": 80, "records": []})
    # shared ownership
    by_parent = defaultdict(list)
    for o in ownership:
        if o["child"] in nodes and nodes[o["child"]]["tier"] == 1:
            by_parent[o["parent"]].append(o)
    for p, kids in by_parent.items():
        if len(kids) > 1:
            ks = [k["child"] for k in kids]
            comp_overlap = set.intersection(*(set(nodes[k]["components"]) for k in ks))
            if comp_overlap:
                issues.append({"id": f"I-own-{p}", "kind": "ownership", "title": f"Both {'/'.join(sorted(comp_overlap))} sources have the same parent",
                               "nodes": ks, "events": [], "priority": "monitor", "risk": None, "confidence": 85, "conf_label": "Registry record",
                               "exposure": max(nodes[k]["rev"] for k in ks), "products": sorted({x for k in ks for x in nodes[k]["products"]}),
                               "why": [f"{ents[p]['short']} consolidates {' and '.join(nodes[k]['short'] for k in ks)} ({kids[0]['record']}).",
                                       "Group-level financial or policy decisions can hit both 'alternative' suppliers at once."],
                               "next": [{"text": f"Add {ents[p]['short']} group-level financial monitoring; treat the pair as one counterparty in limits.", "owner": "Risk", "when": "1 month"}],
                               "attention": 55, "records": [kids[0]["record"]]})
    for nd in ranked:
        if nd["id"] in used or nd["tier"] != 1:
            continue
        if nd["sole_source"] and len(nd["products"]) >= 3:
            node_issue(nd, "single_source", f"{nd['short']} is the only Tier-1 source of {', '.join(nd['components'])} for every product",
                       [f"100% allocation of {', '.join(nd['components'])}; used in {', '.join(nd['products'])} (${nd['rev']:,.0f}m).",
                        nd["factors"]["substitutability"]["text"]],
                       [{"text": f"Qualify a second {', '.join(nd['components'])} source — and check it does not reuse the same upstream inputs.", "owner": "Sourcing", "when": "Quarter"}])
    gaps = [nd for nd in ranked if nd["priority"] == "verify" and nd["id"] not in used]
    if gaps:
        issues.append({"id": "I-gaps", "kind": "evidence_gap", "title": f"{len(gaps)} high-risk upstream nodes rest on thin evidence",
                       "nodes": [g["id"] for g in gaps], "events": [], "priority": "verify",
                       "risk": max(g["risk"] for g in gaps), "confidence": min(g["confidence"]["overall"] for g in gaps),
                       "conf_label": "Low/medium", "exposure": max(g["rev"] for g in gaps),
                       "products": sorted({p for g in gaps for p in g["products"]}),
                       "why": [", ".join(g["short"] for g in gaps) + " score high on structure, but each link rests on one disclosure and financial data is missing.",
                               "Verify before acting — the risk may be over- or under-stated."],
                       "next": [{"text": "Request supplier self-declarations and financials; confirm whether the buyer has other sources of the same input.", "owner": "Supplier risk", "when": "1 month"}],
                       "attention": 50, "records": []})
    order = {"act": 0, "verify": 1, "monitor": 2, "routine": 3}
    issues.sort(key=lambda i: (-(i["attention"] or 0)))
    for i, it in enumerate(issues):
        it["rank"] = i + 1

    # headline
    t1 = [n for n in nodes.values() if n["tier"] == 1 and n["status"] == "confirmed"]
    dual = [x for x in illusions if len(x["tier1"]) > 1]
    convergence = [n for n in nodes.values() if n["tier"] >= 2 and len(n["tier1"]) > 1]
    top = [n for n in ranked if n["tier"] >= 2][:3]
    headline = {
        "title": "Diversified at Tier-1. Concentrated upstream.",
        "t1_count": len(t1), "component_count": len(comps), "dual_sourced": [x["component"] for x in dual],
        "not_independent": [x["component"] for x in dual if not x["independent"]],
        "convergence": [n["id"] for n in convergence], "top": [n["id"] for n in top],
        "total": total,
        "text": (f"NovaDrive buys from {len(t1)} Tier-1 suppliers and dual-sources {len(dual)} of {len(comps)} components — "
                 + (f"but none of that dual-sourcing is independent. " if dual and all(not x["independent"] for x in dual) else f"but {sum(not x['independent'] for x in dual)} of those pairs share upstream dependencies. ")
                 + "; ".join(f"{n['short']} sits behind {n['rev_share']:.0%} of revenue" for n in top) + "."),
    }
    return {"issues": issues, "illusions": illusions, "headline": headline}
