"""Reconstructs the Tier-1..Tier-N supplier network from the Relationship Evidence sheet.

Every evidence record is classified (link, corroboration, ownership, sole-source,
facility clarification, rejection, research lead ...). Nothing is silently dropped:
records the parser does not understand are reported as 'unclassified' so an analyst
can review them in the UI.

Relationship confidence is computed from *independent source families*: several
records from the same family count once.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .loader import norm

ND = "ND"
ND_NAME = "NovaDrive Technologies"

# Evidence strength per record kind (points; capped at 100 per relationship).
STRENGTH = {
    "award": 50,            # company programme disclosure naming NovaDrive, component, site, allocation
    "input": 50,            # company disclosure naming an upstream input supplier, input and site
    "qualification": 35,    # qualification register (approved relationship + site)
    "technical": 20,        # joint technical / programme register statement
    "shipment": 15,         # observed shipment between the parties
    "logistics": 10,        # shipment via an intermediary, goods match the input
    "customer_index": 25,   # supplier lists the buyer among customers (inference only)
    "sample": 10,           # sample evaluation, no production award (hypothesis)
}
KIND_LABEL = {
    "award": "Production award disclosure", "input": "Input-supplier disclosure", "qualification": "Qualification register",
    "technical": "Technical sourcing statement", "shipment": "Shipment observation", "logistics": "Shipment via intermediary",
    "customer_index": "Customer-programme index", "sample": "Sample evaluation",
}

RX = {
    "award": re.compile(r"^(?P<s>.+?) has been named a production supplier to NovaDrive Technologies for component (?P<c>\w+), used in (?P<p>[P\d,\s]+)\. Production takes place at (?P<site>SITE-\d+).*?through (?P<until>\d{1,2} \w+ \d{4}).*?approximately (?P<a>\d+)%", re.S),
    "qualification": re.compile(r"names (?P<s>.+?), site (?P<site>SITE-\d+), as qualified for NovaDrive Technologies.*? in the (?P<c>\w+) program", re.S),
    "input": re.compile(r"^(?P<b>.+?) identifies (?P<s>.+?) as an? active production input supplier for its (?P<prog>[^.]+?) programs?\. The supplied input is (?P<inp>.+?), manufactured at (?P<site>SITE-\d+)", re.S),
    "customer_index": re.compile(r"^(?P<s>.+?) lists (?P<b>.+?) among industrial customers\..*?capability is (?P<inp>[^.]+)\..*?mentions (?P<prog>[A-Z]\d\d(?:/[A-Z]\d\d)*) applications.*?reported as (?P<site>SITE-\d+)", re.S),
    "sample": re.compile(r"^(?P<s>.+?) has completed a sample evaluation with (?P<b>.+?)\.", re.S),
    "shipment": re.compile(r"shipper '(?P<s>[^']+)' to consignee '(?P<b>[^']+)', origin (?P<origin>[^,]+), goods '(?P<g>[^']+)'"),
    "owner_consolidates": re.compile(r"^(?P<p>.+?) \(ORG-\d+\) consolidates (?P<c>.+?) as controlled subsidiaries"),
    "owner_parent": re.compile(r"^(?P<p>.+?) \(ORG-\d+\) is the accounting parent of (?P<c>.+?) \(ORG-\d+\)"),
    "trade_dir": re.compile(r"^(?P<a>.+?) lists the .+? among its target sectors\. (?P<b>.+?) appears in the same", re.S),
}
NO_ALT = re.compile(r"no second [\w\s-]*?source is currently qualified|no presently qualified independent|not a qualified replacement", re.I)
REJECT_HINTS = re.compile(r"do not treat|did not convert|does not connect|unrelated|not a subsidiary|should not assert|not production", re.I)


class Resolver:
    """Resolves free-text organisation mentions to Supplier Universe entity IDs."""

    def __init__(self, ents: dict):
        self.ents = ents
        self.by_norm = {e["norm"]: k for k, e in ents.items()}
        first = defaultdict(list)
        for k, e in ents.items():
            first[e["norm"].split()[0]].append(k)
        # unique first-word aliases only ('Aster', 'IonPeak'); ambiguous ones ('Delta', 'Jade') need more context
        self.alias = {w: ks[0] for w, ks in first.items() if len(ks) == 1}
        self.ambiguous = {w: ks for w, ks in first.items() if len(ks) > 1}

    def exact(self, text: str):
        n = norm(text)
        if n in self.by_norm:
            return self.by_norm[n]
        for full, k in sorted(self.by_norm.items(), key=lambda x: -len(x[0])):
            if n.startswith(full) or full == n:
                return k
        return None

    def mentions(self, text: str, allow_alias=True):
        """Entities mentioned in text: full names first, then unique aliases.

        Returns (found, negated) where negated are entities explicitly excluded
        ("... not IonPeak Semiconductor").
        """
        low = " " + norm(text) + " "
        found, negated = [], set()
        taken = low
        for full, k in sorted(self.by_norm.items(), key=lambda x: -len(x[0])):
            if f" {full} " in taken:
                if re.search(r"\bnot (the )?" + re.escape(full) + r"\b", low):
                    negated.add(k)
                else:
                    found.append(k)
                taken = taken.replace(f" {full} ", " | ")
        if allow_alias:
            for w, k in self.alias.items():
                if k in found or k in negated:
                    continue
                if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", taken):
                    if re.search(r"\bnot (the )?" + re.escape(w) + r"\b", taken):
                        negated.add(k)
                    else:
                        found.append(k)
        return found, negated

    def ambiguous_terms(self, text: str):
        low = " " + norm(text) + " "
        return {w: ks for w, ks in self.ambiguous.items() if re.search(r"(?<![a-z0-9])" + w + r"(?![a-z0-9])", low)}


def _is_nd(text: str) -> bool:
    return "novadrive" in norm(text).replace(" ", "")


def build_network(ents: dict, records: list[dict], comps: list[dict]):
    R = Resolver(ents)
    site_owner = {s["id"]: k for k, e in ents.items() for s in e["sites"]}
    edges: dict[tuple, dict] = {}
    ownership, rejected, notes = [], [], []
    sole_source: dict[str, list[str]] = defaultdict(list)
    facility_notes: dict[str, list[dict]] = defaultdict(list)
    classification: dict[str, dict] = {}

    def edge(s, b):
        key = (s, b)
        if key not in edges:
            edges[key] = {"id": f"{s}>{b}", "src": s, "dst": b, "kinds": set(), "support": [], "components": set(),
                          "programs": set(), "alloc": {}, "sites": set(), "inputs": set(), "products": set(), "until": None}
        return edges[key]

    def support(e, rec, kind, note=""):
        e["kinds"].add(kind)
        e["support"].append({"rec": rec["id"], "family": rec["family"], "kind": kind, "points": STRENGTH[kind], "note": note})

    def classify(rec, cls, summary, links=(), entities=()):
        classification[rec["id"]] = {"class": cls, "summary": summary, "links": list(links), "entities": list(entities)}

    pending = []
    for rec in records:
        d = rec["detail"]
        expired = "expired" in rec["status"].lower()
        if expired:
            found, _ = R.mentions(d)
            ent = found[0] if found else None
            rejected.append({"id": f"X-{rec['id']}", "src": ent, "src_name": ents[ent]["short"] if ent else "Unknown",
                             "dst": ND, "dst_name": ND_NAME, "status": "rejected", "label": "Expired relationship",
                             "reason": "Award ended " + (re.search(r"ended on ([^.]+)", d).group(1) if re.search(r"ended on ([^.]+)", d) else "") + "; not a current link",
                             "records": [rec["id"]]})
            classify(rec, "expired", "Expired award — not a current supply link", entities=[ent] if ent else [])
            continue
        m = RX["award"].search(d)
        if m and (s := R.exact(m["s"])):
            e = edge(s, ND)
            c = m["c"]
            e["components"].add(c); e["sites"].add(m["site"]); e["alloc"][c] = int(m["a"])
            e["products"] |= {p.strip() for p in m["p"].split(",") if p.strip()}
            e["until"] = m["until"]
            support(e, rec, "award", f"{c} · {m['a']}% planning allocation · {m['site']}")
            classify(rec, "link", f"{ents[s]['short']} → NovaDrive: {c} ({m['a']}% allocation)", [e["id"]], [s])
            continue
        m = RX["qualification"].search(d)
        if m and (s := R.exact(m["s"])):
            pending.append(("qual", rec, s, m))
            continue
        m = RX["input"].search(d)
        if m and (s := R.exact(m["s"])) and (b := R.exact(m["b"])):
            e = edge(s, b)
            e["programs"] |= set(re.findall(r"[A-Z]\d\d", m["prog"]))
            e["inputs"].add(m["inp"].strip().lower()); e["sites"].add(m["site"])
            support(e, rec, "input", f"{m['inp'].strip()} for {m['prog']} · {m['site']}")
            classify(rec, "link", f"{ents[s]['short']} → {ents[b]['short']}: {m['inp'].strip()}", [e["id"]], [s, b])
            continue
        m = RX["customer_index"].search(d)
        if m and (s := R.exact(m["s"])) and (b := R.exact(m["b"])):
            e = edge(s, b)
            e["programs"] |= set(re.findall(r"[A-Z]\d\d", m["prog"]))
            e["inputs"].add(m["inp"].strip().lower()); e["sites"].add(m["site"])
            support(e, rec, "customer_index", "Listed among customers; purchases and receiving line not identified")
            classify(rec, "inference", f"{ents[s]['short']} → {ents[b]['short']}: customer listing only", [e["id"]], [s, b])
            continue
        m = RX["sample"].search(d)
        if m and (s := R.exact(m["s"])) and (b := R.exact(m["b"])):
            e = edge(s, b)
            e["inputs"].add((ents[s]["cap"] or "").lower())
            for c in comps:
                if c["id"] in d:
                    e["programs"].add(c["id"])
            support(e, rec, "sample", "Sample evaluation completed; no serial-production award")
            classify(rec, "hypothesis", f"{ents[s]['short']} → {ents[b]['short']}: sample evaluation only", [e["id"]], [s, b])
            continue
        m = RX["shipment"].search(d)
        if m:
            pending.append(("ship", rec, None, m))
            continue
        m = RX["owner_consolidates"].search(d) or RX["owner_parent"].search(d)
        if m and (p := R.exact(m["p"])):
            kids = [R.exact(x) for x in re.split(r",| and ", m["c"]) if x.strip()]
            kids = [k for k in kids if k]
            for k in kids:
                ownership.append({"parent": p, "child": k, "record": rec["id"]})
            classify(rec, "ownership", f"{ents[p]['short']} owns {', '.join(ents[k]['short'] for k in kids)}", entities=[p, *kids])
            pending.append(("facility", rec, None, None))  # ownership notes may also clarify facilities
            continue
        m = RX["trade_dir"].search(d)
        if m:
            b = R.exact(m["b"])
            rejected.append({"id": f"U-{rec['id']}", "src": None, "src_name": m["a"].replace(" Ltd.", ""), "dst": b,
                             "dst_name": ents[b]["short"] if b else m["b"], "status": "unresolved", "label": "Research lead only",
                             "reason": "Directory listing only; no supply relationship stated", "records": [rec["id"]]})
            classify(rec, "research_lead", f"{m['a']} ↔ {m['b']}: research lead only", entities=[b] if b else [])
            continue
        pending.append(("other", rec, None, None))

    # second pass: records that corroborate / clarify existing links
    for kind, rec, s, m in pending:
        d = rec["detail"]
        if kind == "qual":
            e = edges.get((s, ND))
            if e is None:
                e = edge(s, ND); e["components"].add(m["c"]); e["sites"].add(m["site"])
            support(e, rec, "qualification", f"{m['c']} serial approval · {m['site']}")
            classify(rec, "corroboration", f"Qualification confirms {ents[s]['short']} {m['c']} at {m['site']}", [e["id"]], [s])
            continue
        if kind == "ship":
            shipper, consignee = R.exact(m["s"]), (ND if _is_nd(m["b"]) else R.exact(m["b"]))
            if shipper and consignee and (shipper, consignee) in edges:
                e = edges[(shipper, consignee)]
                support(e, rec, "shipment", f"{m['g']} from {m['origin']}")
                classify(rec, "corroboration", f"Shipment observed {ents[shipper]['short']} → {'NovaDrive' if consignee == ND else ents[consignee]['short']}", [e["id"]], [shipper])
                continue
            if shipper and consignee and "logistic" in (ents[shipper]["type"] or "").lower():
                goods = m["g"].lower()
                hits = [e for (src, dst), e in edges.items() if dst == consignee and any(i in goods for i in e["inputs"])]
                for e in hits:
                    support(e, rec, "logistics", f"{m['g']} consolidated by {ents[shipper]['short']} (intermediary, not the manufacturer)")
                classify(rec, "corroboration" if hits else "context",
                         f"{ents[shipper]['short']} forwarded {m['g']} to {ents[consignee]['short']} — intermediary, not a supplier",
                         [e["id"] for e in hits], [shipper, consignee])
                continue
            if shipper and not consignee:
                classify(rec, "out_of_scope", f"{ents[shipper]['short']} shipment to a non-NovaDrive customer", entities=[shipper])
                continue
            classify(rec, "unclassified", "Shipment parties could not be resolved")
            continue
        # free-text clarifications
        found, negated = R.mentions(d)
        sites = re.findall(r"SITE-\d+", d)
        did = False
        if NO_ALT.search(d):
            owners = {site_owner[x] for x in sites if x in site_owner}
            for o in owners:
                sole_source[o].append(rec["id"])
            # corroborate the links between the sole-source owner and buyers named in the statement
            links = []
            for o in owners:
                for b in found:
                    if (o, b) in edges:
                        support(edges[(o, b)], rec, "technical", "Same qualified source confirmed for this programme")
                        links.append(edges[(o, b)]["id"])
            for x in sites:
                if x in site_owner and re.search(re.escape(x) + r"[^.]*?(research|pilot)[^.]*?\.\s*It is not a qualified replacement", d):
                    facility_notes[site_owner[x]].append({"site": x, "rec": rec["id"], "note": "Research/pilot site — not a qualified replacement"})
                    o = site_owner[x]
                    rejected.append({"id": f"X-{rec['id']}-{x}", "src": o, "src_name": f"{ents[o]['short']} {x}", "dst": None, "dst_name": "alternate die source",
                                     "status": "rejected", "label": "Not a qualified alternative",
                                     "reason": "Different process; not the die plant",
                                     "records": [rec["id"]]})
            if rec["id"] not in classification or classification[rec["id"]]["class"] != "ownership":
                classify(rec, "sole_source", "No qualified alternative source: " + ", ".join(ents[o]["short"] for o in owners), links, list(owners) + found)
            did = True
        for x in sites:
            if x in site_owner and re.search(re.escape(x) + r"(?:(?!SITE-)[^.;])*?(headquarters|does not manufacture)", d, re.I):
                facility_notes[site_owner[x]].append({"site": x, "rec": rec["id"], "note": "Registered headquarters — not a production site"})
                did = True
        if REJECT_HINTS.search(d) and not (rec["id"] in classification and classification[rec["id"]]["class"] == "ownership"):
            # identity / scope rejections
            if "packaging" in d.lower() and _is_nd(d):
                tgt = [k for k in found if "packag" in (ents[k]["cap"] or "").lower()]
                for k in tgt:
                    rejected.append({"id": f"X-{rec['id']}-{k}", "src": k, "src_name": ents[k]["short"], "dst": ND, "dst_name": ND_NAME,
                                     "status": "rejected", "label": "Not a production link",
                                     "reason": "Not Delta Capacitor; packaging trial only",
                                     "records": [rec["id"]]})
            nd_ = norm(d)
            for k in found:
                if re.search(re.escape(ents[k]["norm"]) + r"\b[^.]{0,80}?\b(unrelated|not a subsidiary)", nd_):
                    rel = [o for o in found if o != k] + sorted(negated)
                    rejected.append({"id": f"X-{rec['id']}-{k}", "src": k, "src_name": ents[k]["short"], "dst": rel[0] if rel else None,
                                     "dst_name": ents[rel[0]]["short"] if rel else "", "status": "rejected", "label": "Name look-alike",
                                     "reason": f"Broker, different legal entity from {ents[rel[0]]['short'] if rel else 'the network'}",
                                     "records": [rec["id"]]})
            if not did:
                classify(rec, "rejection", "Clarifies a relationship that must NOT be assumed", entities=found)
            did = True
        inter = [k for k in found if "logistic" in (ents[k]["type"] or "").lower() or "intermediar" in (ents[k]["type"] or "").lower()]
        if inter and re.search(r"does not manufacture|should not automatically be classified", d):
            for k in inter:
                rejected.append({"id": f"X-{rec['id']}-{k}", "src": k, "src_name": ents[k]["short"], "dst": None, "dst_name": "component supply",
                                 "status": "rejected", "label": "Intermediary, not a supplier",
                                 "reason": "Freight consolidator, not a component maker",
                                 "records": [rec["id"]]})
            if rec["id"] not in classification:
                classify(rec, "role", "Role clarification: " + ", ".join(ents[k]["short"] for k in inter) + " — intermediary, not a manufacturer", entities=found)
            did = True
        if re.search(r"unverified|not a supplier declaration", d, re.I) and rec["id"] not in classification:
            classify(rec, "gap", "Upstream sourcing unverified: " + ", ".join(ents[k]["short"] for k in found), entities=found)
            did = True
        if not did and rec["id"] not in classification:
            classify(rec, "context" if found else "unclassified", "Context record" if found else "Not parsed — review manually", entities=found)
        elif rec["id"] not in classification:
            classify(rec, "facility", "Facility clarification", entities=found)

    # finalise edges: status + confidence from independent families
    out_edges = []
    for (s, b), e in edges.items():
        fam_best = {}
        for sp in e["support"]:
            fam_best[sp["family"]] = max(fam_best.get(sp["family"], 0), sp["points"])
        score = min(100, sum(fam_best.values()))
        kinds = e["kinds"]
        if kinds & {"award", "input", "qualification"}:
            status = "confirmed"
        elif "customer_index" in kinds:
            status = "inference"
        else:
            status = "hypothesis"
        if status == "inference":
            score = min(score, 45)
        if status == "hypothesis":
            score = min(score, 20)
        label = "Strong" if score >= 75 else "Moderate" if score >= 50 else "Weak"
        out_edges.append({
            "id": e["id"], "src": s, "dst": b, "status": status, "confidence": score, "conf_label": label,
            "families": len(fam_best), "records": len(e["support"]),
            "support": e["support"], "components": sorted(e["components"]), "programs": sorted(e["programs"]),
            "alloc": e["alloc"], "sites": sorted(e["sites"]), "inputs": sorted(e["inputs"]), "products": sorted(e["products"]),
            "until": e["until"],
        })
    return {"edges": out_edges, "ownership": ownership, "rejected": rejected, "sole_source": dict(sole_source),
            "facility_notes": dict(facility_notes), "classification": classification, "resolver": R}
