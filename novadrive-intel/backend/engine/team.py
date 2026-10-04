"""Team-owned figures (sheets prefixed 'DB '): scorecard, signal verdicts, alert briefs, priorities,
alternates and headline. These are displayed exactly as entered in the workbook; the engine only
supplies the network, exposure paths and evidence around them."""
from __future__ import annotations

import pandas as pd

from .loader import clean


def _sheet(raw, name):
    df = raw.get(name)
    if df is None:
        return []
    df.columns = [str(c).strip() for c in df.columns]
    return [{k: clean(v) for k, v in r.items()} for _, r in df.dropna(how="all").iterrows()]


def load_team(path):
    raw = pd.read_excel(path, sheet_name=None)
    t = {k: _sheet(raw, f"DB {n}") for k, n in [("headline", "Headline"), ("scorecard", "Scorecard"), ("weights", "Weights"),
         ("signals", "Signals"), ("briefs", "Alert Briefs"), ("priorities", "Priorities"), ("alternates", "Alternates"), ("brief", "Sourcing Brief")]}
    t["headline"] = {r["Key"]: {"value": str(r["Value"]) if r["Value"] is not None else "", "label": r.get("Label") or ""} for r in t["headline"]}
    t["present"] = bool(t["scorecard"])
    return t


def apply_team(state, team):
    if not team["present"]:
        return state
    sc = {r["Entity ID"]: r for r in team["scorecard"]}
    for n in state["nodes"]:
        r = sc.get(n["id"])
        if r:
            n["risk"] = int(r["Risk"])
            n["grade"] = str(r["Confidence"]).strip().upper()
            n["reading"] = r["Reading"]
            n["label"] = r["Node"]
            n["rank"] = int(r["Rank"])
        else:
            n["grade"], n["reading"], n["label"], n["rank"] = None, "Not scored", n["short"], 999
    sig = {r["Event ID"]: r for r in team["signals"]}
    brief = {r["Event ID"]: r for r in team["briefs"]}
    for e in state["events"]:
        r = sig.get(e["id"], {})
        e["verdict"] = r.get("Verdict") or e["decision"].title()
        e["naive"] = r.get("Naive system")
        e["ours"] = r.get("Ours")
        e["priority"] = int(r["Priority"]) if r.get("Priority") else None
        e["brief"] = brief.get(e["id"])
    state["team"] = {k: team[k] for k in ("headline", "weights", "priorities", "alternates", "brief")}
    return state
