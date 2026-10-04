"""External-signal triage: freshness → duplicates → entity resolution → facility/geography
→ network traversal → exposure → management decision.

Each step is recorded so the UI can show exactly where (and why) a signal was stopped.
The same pipeline is used for the case Event Feed and for ad-hoc signals typed by the user.
"""
from __future__ import annotations

import re
from datetime import date

from .loader import norm
from .network import ND

STALE_DAYS = 180
NO_IMPACT = re.compile(r"no (factory )?(damage|shutdown)[^.]*confirmed|production continues|production remains|has not been assessed|no current", re.I)
DISRUPT = re.compile(r"\b(shut ?down|halt(ed)?|stopp(ed|age)|fire|explosion|outage|force majeure|strike)\b", re.I)
HQ = re.compile(r"\b(headquarters|head office|registered office|administrative)\b", re.I)
DUP = re.compile(r"republish|repeats|adds no independent|same .* bulletin", re.I)

TYPES = [
    ("hazard", re.compile(r"flood|storm|typhoon|earthquake|wildfire|heat ?wave|cyclone|weather", re.I)),
    ("financial", re.compile(r"covenant|insolven|restructur|bankrupt|delayed payments?|default|financing|liquidity", re.I)),
    ("logistics", re.compile(r"port|terminal|congestion|shipping|freight|vessel", re.I)),
    ("labour", re.compile(r"strike|walkout|labou?r dispute", re.I)),
    ("corporate", re.compile(r"headquarters|relocation|merger|acquisition|ownership", re.I)),
    ("reputational", re.compile(r"allegation|investigation|lawsuit|sanction|recall", re.I)),
    ("operational", re.compile(r"fire|explosion|outage|shutdown|halt|quality", re.I)),
]


def _days(a, b):
    try:
        return (date.fromisoformat(a) - date.fromisoformat(b)).days
    except Exception:
        return 0


PLACE = re.compile(r"\b([A-Z][a-z]+ (?:Arc|District|Ridge|Delta|Coast|Bay|Valley|Basin|Works))\b")


def zone_gazetteer(texts, ents, resolver=None):
    """Place names → zone codes, learned from the case text itself.

    'East Delta (Z01)' is stated; 'SITE-900 in Western Ridge' is derived from the site's zone in the
    Supplier Universe; a place named alongside exactly one located entity is marked as inferred.
    """
    gaz = {}
    site_zone = {s["id"]: s["zone"] for e in ents.values() for s in e["sites"]}
    for t in texts:
        for name, z in re.findall(r"([A-Z][a-z]+ [A-Z][a-z]+) \((Z\d\d)\)", t):
            gaz[name.lower()] = {"zone": z, "basis": "stated in evidence"}
        for name, z in re.findall(r"([A-Z][a-z]+ [A-Z][a-z]+) authority [^.]*? for (Z\d\d)", t):
            gaz.setdefault(name.lower(), {"zone": z, "basis": "stated in event"})
        for site, name in re.findall(r"(SITE-\d+) in ([A-Z][a-z]+ [A-Z][a-z]+)\b", t):
            if site in site_zone:
                gaz.setdefault(name.lower(), {"zone": site_zone[site], "basis": f"{site} is located there"})
    if resolver:
        for t in texts:
            places = [p for p in PLACE.findall(t) if p.lower() not in gaz and not p.endswith("Works")]
            if not places:
                continue
            found, _ = resolver.mentions(strip_places(t, gaz))
            zs = {ents[k]["reg_zone"] for k in found}
            if len(found) == 1 and len(zs) == 1:
                for p in places:
                    gaz.setdefault(p.lower(), {"zone": zs.pop() if len(zs) == 1 else None, "basis": f"inferred: {ents[found[0]]['short']} is described there"})
    return gaz


def strip_places(text, gaz):
    """Remove place names so 'East Delta' cannot match 'Delta …' and 'Harbor District' cannot match 'Harbor …'."""
    t = PLACE.sub(" ", text)
    for p in gaz:
        t = re.sub(re.escape(p), " ", t, flags=re.I)
    return t


class Context:
    def __init__(self, ents, nodes, products, resolver, gaz, as_of, total):
        self.ents, self.nodes, self.products, self.R, self.gaz, self.as_of, self.total = ents, nodes, products, resolver, gaz, as_of, total
        self.rev = {p["id"]: p["revenue"] for p in products}
        self.site_owner = {s["id"]: (k, s) for k, e in ents.items() for s in e["sites"]}


def triage(ev, ctx: Context, seen_families: dict, idx_by_family: dict):
    text = f"{ev['title']}. {ev['detail']}"
    steps = []
    out = {**ev, "steps": steps, "decision": None, "severity": None, "matched": [], "match_basis": {}, "zones": [], "sites": [],
           "components": [], "products": [], "tier1": [], "exposure": 0.0, "weekly": 0.0, "type": "other",
           "impact_status": None, "match_confidence": None, "headline": "", "why": "", "actions": [], "merged": [], "excluded": []}
    for t, rx in TYPES:
        if rx.search(text):
            out["type"] = t
            break

    # 1 freshness
    age = _days(ev["published"] or ctx.as_of, ev["effective"] or ev["published"] or ctx.as_of)
    recency = _days(ctx.as_of, ev["effective"] or ctx.as_of)
    ended = re.search(r"ended in \d{4}|dispute ended|no current", text, re.I)
    if age > STALE_DAYS or recency > 365 or (ended and age > 30):
        steps.append({"step": "Freshness", "status": "fail", "note": f"Effective {ev['effective']}, re-published {ev['published']} ({age} days later). The underlying event is over."})
        out.update(decision="SUPPRESSED", reason_code="stale", headline="Old event re-posted — not a current trigger",
                   why=f"The source re-posts an event from {ev['effective']}. Nothing indicates a current disruption.",
                   actions=[{"text": "No action. Logged as stale so it cannot raise a false alert.", "owner": "System", "when": "—"}])
        return out
    steps.append({"step": "Freshness", "status": "pass", "note": f"Effective {ev['effective']} — current as of {ctx.as_of}."})

    # 2 duplicates
    fam = ev.get("family")
    if (fam and fam in seen_families) or DUP.search(text):
        first = seen_families.get(fam) or next((m for m in re.findall(r"EV-\d+", text) if m != ev["id"]), None)
        steps.append({"step": "Duplicate check", "status": "fail", "note": f"Same source family {fam} as {first}. Adds no independent evidence."})
        out.update(decision="MERGED", reason_code="duplicate", merged_into=first, headline=f"Repeat of {first} — merged",
                   why=f"Re-publication of the same bulletin (source family {fam}). Counted once so repeated coverage cannot inflate the alert.",
                   actions=[{"text": f"Merged into {first}; corroboration count updated.", "owner": "System", "when": "—"}])
        return out
    if fam:
        seen_families[fam] = ev["id"]
    steps.append({"step": "Duplicate check", "status": "pass", "note": f"First report from source family {fam}."})

    # 3 entity resolution (place names removed first so they cannot masquerade as company names)
    ent_text = strip_places(text, ctx.gaz)
    found, negated = ctx.R.mentions(ent_text)
    regs = re.findall(r"REG-NO-\d+", text)
    amb = ctx.R.ambiguous_terms(ent_text)
    in_net = [k for k in found if k in ctx.nodes]
    off_net = [k for k in found if k not in ctx.nodes]
    out["excluded"] = [{"id": k, "name": ctx.ents[k]["short"], "why": "Explicitly negated in the signal"} for k in negated] + \
                      [{"id": k, "name": ctx.ents[k]["short"], "why": "In supplier universe but not in NovaDrive's network"} for k in off_net]
    # ambiguous short names ("Jade", "Delta") -> keep the network member only when context supports it
    for w, ks in amb.items():
        if any(k in found or k in negated for k in ks):
            continue
        net_ks = [k for k in ks if k in ctx.nodes]
        if len(net_ks) == 1:
            in_net.append(net_ks[0])
            out["match_basis"][net_ks[0]] = f"short name '{w}' — resolved to the only network member with that name"
    note = []
    if in_net:
        note.append("Network entities: " + ", ".join(ctx.ents[k]["short"] for k in in_net))
    if off_net or negated:
        note.append("Rejected look-alikes: " + ", ".join(ctx.ents[k]["short"] for k in [*off_net, *negated]))
    if regs:
        note.append("Registry IDs: " + ", ".join(regs))
    # 4 facility / geography
    zones = sorted(set(re.findall(r"\bZ\d\d\b", text)))
    office_event = bool(HQ.search(text)) and bool(in_net) and not DISRUPT.search(text)
    for place, g in ctx.gaz.items():
        if place in text.lower() and g["zone"] and g["zone"] not in zones and not office_event:
            zones.append(g["zone"])
    sites = sorted(set(re.findall(r"SITE-\d+", text)))
    places = re.findall(r"\b([A-Z][a-z]+ (?:Arc|District|Ridge|Delta|Coast|Bay|Valley|Basin))\b", text)
    unmapped = [p for p in places if p.lower() not in ctx.gaz]
    out["zones"], out["sites"] = zones, sites
    zone_nodes = [k for k, n in ctx.nodes.items() if n["zone"] in zones and n["status"] != "hypothesis"]

    if not in_net and not zone_nodes and not sites:
        if off_net or negated:
            steps.append({"step": "Entity resolution", "status": "fail", "note": "; ".join(note) or "No network entity."})
            names = ", ".join(ctx.ents[k]["short"] for k in off_net) or ", ".join(ctx.ents[k]["short"] for k in negated)
            out.update(decision="REJECTED", reason_code="entity_mismatch", headline=f"False positive avoided — concerns {names}" + (f", not {', '.join(ctx.ents[k]['short'] for k in negated)}" if negated and off_net else ""),
                       why=f"The signal names {', '.join(ctx.ents[k]['short'] for k in off_net) or 'an outside entity'}, which is not in NovaDrive's network"
                       + (f" and explicitly is not {', '.join(ctx.ents[k]['short'] for k in negated)}" if negated else "") + ". A name look-alike must not trigger an alert.",
                       actions=[{"text": "No alert. Logged as a resolved false positive.", "owner": "System", "when": "—"}])
            return out
        steps.append({"step": "Entity resolution", "status": "warn", "note": "No supplier named."})
        if out["type"] in ("logistics", "labour") or unmapped:
            steps.append({"step": "Facility & geography", "status": "warn",
                          "note": (f"'{', '.join(unmapped)}' is not mapped to any zone in the case data." if unmapped else "No facility or zone given.")})
            out.update(decision="WATCH", severity="LOW", reason_code="unmapped_geo", impact_status="Unassessed",
                       headline="Possible lane delay — no link to a network facility yet",
                       why="The signal cannot be tied to a supplier, facility or zone in the network. NovaDrive's observed inbound Tier-1 shipments move by ocean, so a lane check is proportionate; escalation is not.",
                       actions=[{"text": "Ask logistics whether open purchase orders route through the named port/lane.", "owner": "Logistics", "when": "48 h"},
                                {"text": "Escalate only if a NovaDrive shipment or a network facility is confirmed on the lane.", "owner": "Risk", "when": "On confirmation"}])
            return out
        out.update(decision="REJECTED", reason_code="no_match", headline="No match to the network", why="No supplier, facility or zone matched.",
                   actions=[{"text": "None.", "owner": "System", "when": "—"}])
        return out
    steps.append({"step": "Entity resolution", "status": "pass" if in_net else "skip", "note": "; ".join(note) or "No supplier named — matching on geography."})

    # HQ / office-only events: the facility is not a production site
    if office_event:
        k = in_net[0]
        node = ctx.nodes[k]
        office = [s for s in ctx.ents[k]["sites"] if not s["primary"]]
        parent_offices = [n for n in node.get("facility_notes", []) if "headquarters" in n["note"].lower()]
        steps.append({"step": "Facility & geography", "status": "fail",
                      "note": f"Event concerns an administrative office, not a plant. Production stays at {node['site']} ({node['zone']})."
                      + (f" {parent_offices[0]['site']} is recorded as HQ-only ({parent_offices[0]['rec']})." if parent_offices else "")})
        out.update(decision="INFO", severity="LOW", reason_code="office_only", matched=[k], impact_status="No supply impact",
                   headline=f"{node['short']} office move — production site unaffected",
                   why=f"Headquarters are not a supply facility; {node['short']}'s plant {node['site']} is unchanged.",
                   actions=[{"text": "No action. Update the supplier master address if needed.", "owner": "Procurement", "when": "Routine"}])
        return out

    matched = list(dict.fromkeys(in_net + zone_nodes + [ctx.site_owner[s][0] for s in sites if s in ctx.site_owner and ctx.site_owner[s][0] in ctx.nodes]))
    for k in matched:
        if k in in_net:
            out["match_basis"].setdefault(k, "named legal entity")
        elif ctx.nodes[k]["zone"] in zones:
            out["match_basis"][k] = f"production site {ctx.nodes[k]['site']} is in {ctx.nodes[k]['zone']}" + (" (node rests on an inference link)" if ctx.nodes[k]["status"] != "confirmed" else "")
        else:
            out["match_basis"][k] = "facility ID named in signal"
    geo_note = []
    if zones:
        geo_note.append(f"Zone {', '.join(zones)} contains {len(zone_nodes)} network production site(s)")
    if in_net:
        geo_note.append("Plant(s): " + ", ".join(f"{ctx.nodes[k]['short']} {ctx.nodes[k]['site']}" for k in in_net))
    steps.append({"step": "Facility & geography", "status": "pass", "note": "; ".join(geo_note)})

    # 5 traversal
    comps = sorted({c for k in matched for c in ctx.nodes[k]["components"]})
    prods = sorted({p for k in matched for p in ctx.nodes[k]["products"]})
    t1 = sorted({t for k in matched for t in ctx.nodes[k]["tier1"]})
    exposure = sum(ctx.rev.get(p, 0) for p in prods)
    out.update(matched=matched, components=comps, products=prods, tier1=t1, exposure=exposure, weekly=exposure / 52)
    steps.append({"step": "Network traversal", "status": "pass",
                  "note": f"{len(matched)} node(s) → {len(t1)} Tier-1 supplier(s) → components {', '.join(comps) or '—'} → products {', '.join(prods) or '—'}"})
    steps.append({"step": "Exposure", "status": "pass", "note": f"${exposure:,.0f}m annual revenue depends on the matched nodes (${exposure / 52:,.1f}m per week of stoppage)."})

    # 6 decision
    share = exposure / ctx.total if ctx.total else 0
    no_impact = bool(NO_IMPACT.search(text))
    disrupt = bool(DISRUPT.search(text)) and not no_impact
    node_risk = max((ctx.nodes[k]["risk"] for k in matched), default=0)
    stress = any(ctx.nodes[k]["factors"]["financial"]["score"] >= 85 or ctx.nodes[k]["factors"]["operational"]["score"] >= 85 for k in matched)
    sev = "HIGH" if (share >= 0.6 and (disrupt or node_risk >= 65 or stress)) else "MEDIUM" if share >= 0.3 or node_risk >= 60 else "LOW"
    impact = "Disruption reported" if disrupt else "Exposure only — no disruption confirmed" if no_impact else "Impact not yet known"
    mconf = "High" if in_net else "Medium" if zones else "Low"
    out.update(decision="ALERT", severity=sev, impact_status=impact, match_confidence=mconf)
    names = ", ".join(ctx.nodes[k]["short"] for k in matched[:4]) + (f" +{len(matched) - 4}" if len(matched) > 4 else "")
    if out["type"] == "hazard":
        out["headline"] = f"{', '.join(zones) or 'Site'} hazard watch over {len(matched)} upstream site{'s' if len(matched) != 1 else ''}"
        out["why"] = (f"The watch zone contains {names}. Together they sit behind {', '.join(prods)} (${exposure:,.0f}m, {share:.0%} of revenue). "
                      + ("No damage or shutdown is confirmed, so this is an exposure to verify, not a disruption." if no_impact else ""))
        out["actions"] = [
            {"text": "Request site-status confirmation from each matched plant.", "owner": "Supplier quality", "when": "24 h"},
            {"text": "Confirm weeks of cover for " + ", ".join(comps) + " at Tier-1 and in NovaDrive stock.", "owner": "Procurement", "when": "24 h"},
            {"text": "Pre-position expedite / allocation plan for the products at risk; re-check the watch in 24 h.", "owner": "S&OP", "when": "48 h"},
        ]
    elif out["type"] == "financial":
        out["headline"] = f"Financial stress at {names}"
        out["why"] = (f"{names} feeds {', '.join(comps)} → {', '.join(prods)} (${exposure:,.0f}m, {share:.0%} of revenue). "
                      + ("Its indicators already show acute stress. " if stress else "")
                      + ("Production continues — this is a continuity risk, not a stoppage." if no_impact else ""))
        out["actions"] = [
            {"text": f"Ask the Tier-1 ({', '.join(ctx.nodes[t]['short'] for t in t1 if t in ctx.nodes)}) for stock cover and its contingency for this input.", "owner": "Procurement", "when": "48 h"},
            {"text": "Open an alternate-source screen for the affected input.", "owner": "Sourcing", "when": "1 week"},
            {"text": "Monitor covenant outcome and payment behaviour; escalate on default or supply interruption.", "owner": "Risk", "when": "Weekly"},
        ]
    elif disrupt:
        out["headline"] = f"Disruption reported at {names}"
        out["why"] = f"{names} feeds {', '.join(comps) or '—'} → {', '.join(prods) or 'no confirmed product'} (${exposure:,.0f}m, {share:.0%} of revenue)."
        out["actions"] = [{"text": "Confirm scope and expected duration with the supplier.", "owner": "Supplier quality", "when": "Today"},
                          {"text": "Count weeks of cover for " + ", ".join(comps) + " across Tier-1 and NovaDrive stock.", "owner": "Procurement", "when": "24 h"}]
    else:
        out["headline"] = f"Signal touches {names}"
        out["why"] = f"Matched nodes feed {', '.join(prods) or 'no confirmed product'} (${exposure:,.0f}m)."
        out["actions"] = [{"text": "Verify impact directly with the supplier.", "owner": "Supplier quality", "when": "24 h"},
                          {"text": "Check stock cover for the affected components.", "owner": "Procurement", "when": "48 h"}]
    if disrupt:
        out["actions"].insert(0, {"text": "Activate the continuity plan for the affected components.", "owner": "CPO", "when": "Now"})
    steps.append({"step": "Decision", "status": "pass", "note": f"{sev} alert · {impact.lower()} · match confidence {mconf.lower()}"})
    return out


def run_feed(events, ctx):
    seen, idx = {}, {}
    out = [triage(ev, ctx, seen, idx) for ev in sorted(events, key=lambda e: (e["published"] or "", e["id"]))]
    by_id = {e["id"]: e for e in out}
    for e in out:
        if e["decision"] == "MERGED" and e.get("merged_into") in by_id:
            by_id[e["merged_into"]]["merged"].append(e["id"])
    return out
