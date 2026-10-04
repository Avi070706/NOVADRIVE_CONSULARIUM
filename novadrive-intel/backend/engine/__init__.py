"""NovaDrive supply-intelligence engine: workbook → network → scores → alerts → story."""
from __future__ import annotations

from pathlib import Path

from . import loader as L
from .events import Context, run_feed, triage, zone_gazetteer
from .network import KIND_LABEL, ND, build_network
from .scoring import FACTORS, build_scores
from .story import build_story
from .team import apply_team, load_team


def build(path: Path) -> dict:
    wb = L.load(path)
    ents, recs, comps, prods, inds, evs = L.universe(wb), L.evidence(wb), L.components(wb), L.products(wb), L.indicators(wb), L.events(wb)
    net = build_network(ents, recs, comps)
    nodes, tier, total = build_scores(ents, net, prods, comps, inds)
    dates = [r["date"] for r in recs if r["date"]] + [e["published"] for e in evs if e["published"]]
    as_of = max(dates) if dates else None
    gaz = zone_gazetteer([r["detail"] for r in recs] + [f"{e['title']}. {e['detail']}" for e in evs], ents, net["resolver"])
    ctx = Context(ents, nodes, prods, net["resolver"], gaz, as_of, total)
    alerts = run_feed(evs, ctx)
    story = build_story(ents, nodes, net["edges"], net["ownership"], comps, prods, alerts, total)

    cls = net["classification"]
    evidence = [{**r, **cls.get(r["id"], {"class": "unclassified", "summary": "Not parsed", "links": [], "entities": []})} for r in recs]
    zones = {}
    for n in nodes.values():
        z = zones.setdefault(n["zone"], {"zone": n["zone"], "nodes": [], "hazard": None, "events": [], "name": None})
        z["nodes"].append(n["id"])
        h = n["factors"]["geography"]["inputs"]["hazard"]
        if h is not None:
            z["hazard"] = max(z["hazard"] or 0, h)
    for name, g in gaz.items():
        if g["zone"] in zones:
            zones[g["zone"]]["name"] = name.title()
    for a in alerts:
        for z in a["zones"]:
            if z in zones and a["decision"] == "ALERT":
                zones[z]["events"].append(a["id"])
    for p in prods:
        p["components"] = [c["id"] for c in comps if p["id"] in c["products"]]

    unclassified = [e["id"] for e in evidence if e["class"] == "unclassified"]
    out = {
        "meta": {"file": path.name, "as_of": as_of, "sheets": wb.sheet_names, "warnings": wb.warnings,
                 "counts": {"entities": len(ents), "evidence": len(recs), "events": len(evs), "indicators": len(inds)},
                 "parse": {"total": len(recs), "classified": len(recs) - len(unclassified), "unclassified": unclassified}},
        "factors": FACTORS, "kind_labels": KIND_LABEL,
        "products": prods, "components": comps, "entities": {k: {kk: v for kk, v in e.items() if kk != "norm"} for k, e in ents.items()},
        "nodes": list(nodes.values()), "edges": net["edges"], "ownership": net["ownership"], "rejected": net["rejected"],
        "evidence": evidence, "events": alerts, "zones": zones, "gazetteer": gaz, "total": total, **story,
    }
    return apply_team(out, load_team(path))


def test_signal(state_ctx, title: str, detail: str, published: str | None, effective: str | None):
    ev = {"id": "TEST", "title": title, "detail": detail, "published": published or state_ctx.as_of,
          "effective": effective or published or state_ctx.as_of, "family": "USER-TEST", "source_type": "Analyst input"}
    return triage(ev, state_ctx, {}, {})


def context_for(path: Path):
    """Rebuild the matching context (used by the 'test a signal' endpoint)."""
    wb = L.load(path)
    ents, recs, comps, prods, inds, evs = L.universe(wb), L.evidence(wb), L.components(wb), L.products(wb), L.indicators(wb), L.events(wb)
    net = build_network(ents, recs, comps)
    nodes, tier, total = build_scores(ents, net, prods, comps, inds)
    dates = [r["date"] for r in recs if r["date"]] + [e["published"] for e in evs if e["published"]]
    gaz = zone_gazetteer([r["detail"] for r in recs] + [f"{e['title']}. {e['detail']}" for e in evs], ents, net["resolver"])
    alerts = run_feed(evs, Context(ents, nodes, prods, net["resolver"], gaz, max(dates), total))
    build_story(ents, nodes, net["edges"], net["ownership"], comps, prods, alerts, total)
    return Context(ents, nodes, prods, net["resolver"], gaz, max(dates), total)
