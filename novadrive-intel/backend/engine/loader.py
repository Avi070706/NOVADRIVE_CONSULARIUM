"""Reads the NovaDrive workbook into plain Python structures.

Sheets are located by keyword (not exact name) and columns by keyword, so the
workbook can be edited, re-ordered or renamed slightly without breaking the app.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

SHEET_KEYS = {
    "business": ["business"],
    "components": ["component"],
    "universe": ["universe"],
    "evidence": ["relationship", "evidence"],
    "indicators": ["indicator"],
    "events": ["event"],
}


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip())


def clean(v):
    if _blank(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        return v.strip()
    return v


def num(v):
    v = clean(v)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def date(v):
    v = clean(v)
    if v is None:
        return None
    try:
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    except Exception:
        return str(v)[:10]


def norm(name: str) -> str:
    """Normalise an organisation name for matching.

    Keeps word boundaries so that 'IonPeak Semiconductor' and 'Ion Peak Trading'
    never collapse into the same key.
    """
    s = str(name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(ltd|limited|llc|inc|plc|co|corp)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def short(name: str) -> str:
    return re.sub(r"\s+(Ltd\.?|Limited|LTD)$", "", str(name).strip())


@dataclass
class Workbook:
    path: Path
    sheets: dict[str, list[dict]] = field(default_factory=dict)
    sheet_names: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _col(df: pd.DataFrame, *keys: str):
    for c in df.columns:
        lc = str(c).lower()
        if all(k in lc for k in keys):
            return c
    return None


def load(path: Path) -> Workbook:
    raw = pd.read_excel(path, sheet_name=None)
    wb = Workbook(path=path)
    for key, needles in SHEET_KEYS.items():
        found = None
        for name in raw:
            if name.startswith("DB "):
                continue
            if any(n in name.lower() for n in needles):
                if key == "components" and "business" in name.lower():
                    continue
                found = name
                break
        if found is None:
            wb.warnings.append(f"Sheet for '{key}' not found")
            wb.sheets[key] = []
            continue
        df = raw[found]
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all")
        wb.sheet_names[key] = found
        wb.sheets[key] = [{"__row": i + 2, **{c: r[c] for c in df.columns}} for i, (_, r) in enumerate(df.iterrows())]
        wb.sheets[key + "__df"] = df  # type: ignore[assignment]
    return wb


def products(wb: Workbook):
    df = wb.sheets.get("business__df")
    out = []
    if df is None:
        return out
    c_id, c_name = _col(df, "product", "id"), _col(df, "product", "name")
    c_rev, c_units = _col(df, "revenue"), _col(df, "weekly")
    c_foot, c_ctx = _col(df, "footprint"), _col(df, "context")
    for _, r in df.iterrows():
        pid = clean(r[c_id])
        if not pid:
            continue
        foot = clean(r[c_foot]) or ""
        plants = [{"plant": m[0].strip(), "share": int(m[1])} for m in re.findall(r"([A-Za-z ]+?)\s*\((\d+)%\)", foot)]
        out.append({
            "id": pid, "name": clean(r[c_name]) or pid,
            "revenue": num(r[c_rev]) or 0.0, "weekly_units": num(r[c_units]),
            "footprint": foot, "plants": plants, "context": clean(r[c_ctx]) if c_ctx else None,
        })
    return out


def components(wb: Workbook):
    df = wb.sheets.get("components__df")
    out = []
    if df is None:
        return out
    c_id, c_name = _col(df, "component", "id"), _col(df, "component", "name")
    c_app, c_lt, c_crit = _col(df, "application"), _col(df, "lead"), _col(df, "criteria")
    for _, r in df.iterrows():
        cid = clean(r[c_id])
        if not cid:
            continue
        crit = clean(r[c_crit]) or ""
        prods = re.search(r"Products Using This Component:\s*((?:P\d+[,\s]*)+)", crit)
        use = re.search(r"Application / Use Case:\s*(.+?)\s+\d\.", crit)
        screen = re.search(r"Supplier Screening Criteria:\s*(.+)$", crit)
        out.append({
            "id": cid, "name": clean(r[c_name]) or cid, "application": clean(r[c_app]) or "",
            "lead_time": num(r[c_lt]) or 8.0,
            "products": re.findall(r"P\d+", prods.group(1)) if prods else [],
            "use_case": use.group(1).strip() if use else "",
            "screening": screen.group(1).strip() if screen else crit,
        })
    return out


def universe(wb: Workbook):
    df = wb.sheets.get("universe__df")
    ents = {}
    if df is None:
        return ents
    g = lambda *k: _col(df, *k)
    cols = dict(id=g("entity", "id"), name=g("legal"), type=g("entity", "type"), cap=g("public", "capab"),
                market=g("registered", "market"), rzone=g("registered", "zone"), site=g("primary", "facility", "id"),
                site_name=g("primary", "facility", "name"), zone=g("facility", "zone"), role=g("facility", "role"),
                fcap=g("facility", "capab"), other=g("other"))
    for _, r in df.iterrows():
        eid = clean(r[cols["id"]])
        if not eid:
            continue
        other = clean(r[cols["other"]]) if cols["other"] else None
        sites = [{"id": clean(r[cols["site"]]), "name": clean(r[cols["site_name"]]), "zone": clean(r[cols["zone"]]),
                  "role": clean(r[cols["role"]]), "capability": clean(r[cols["fcap"]]), "primary": True}]
        if other:
            m = re.match(r"(SITE-\d+)\s*-\s*(.+?)\s*\((.+?),\s*(Z\d\d)\)", other)
            if m:
                sites.append({"id": m[1], "name": m[2], "zone": m[4], "role": m[3], "capability": m[3], "primary": False})
        name = clean(r[cols["name"]])
        ents[eid] = {
            "id": eid, "name": name, "short": short(name), "norm": norm(name), "type": clean(r[cols["type"]]),
            "cap": clean(r[cols["cap"]]), "market": clean(r[cols["market"]]), "reg_zone": clean(r[cols["rzone"]]),
            "site": sites[0]["id"], "zone": sites[0]["zone"], "sites": sites, "other": other,
        }
    return ents


def evidence(wb: Workbook):
    df = wb.sheets.get("evidence__df")
    out = []
    if df is None:
        return out
    g = lambda *k: _col(df, *k)
    c = dict(id=g("evidence", "id"), date=g("date"), type=g("evidence", "type"), fam=g("family"), title=g("title"),
             detail=g("detail"), status=g("status"), loc=g("locator"))
    for _, r in df.iterrows():
        eid = clean(r[c["id"]])
        if not eid:
            continue
        out.append({
            "id": eid, "date": date(r[c["date"]]), "type": clean(r[c["type"]]) or "",
            "family": clean(r[c["fam"]]) or eid, "title": clean(r[c["title"]]) or "",
            "detail": clean(r[c["detail"]]) or "", "status": clean(r[c["status"]]) or "",
            "locator": clean(r[c["loc"]]) if c["loc"] else None,
        })
    return out


IND_FIELDS = [
    ("current_ratio", ("current", "ratio")), ("net_debt", ("net debt",)), ("timeliness", ("timeliness", "avg")),
    ("timeliness_change", ("timeliness", "change")), ("assurance_gap", ("assurance",)), ("hazard", ("physical",)),
    ("logistics", ("logistics",)), ("infrastructure", ("infrastructure",)),
]


def indicators(wb: Workbook):
    df = wb.sheets.get("indicators__df")
    out = {}
    if df is None:
        return out
    cid = _col(df, "entity")
    for _, r in df.iterrows():
        eid = clean(r[cid])
        if not eid:
            continue
        rec = {}
        for key, needles in IND_FIELDS:
            col = _col(df, *needles)
            rec[key] = num(r[col]) if col else None
        out[eid] = rec
    return out


def events(wb: Workbook):
    df = wb.sheets.get("events__df")
    out = []
    if df is None:
        return out
    g = lambda *k: _col(df, *k)
    c = dict(id=g("event", "id"), pub=g("published"), eff=g("effective"), title=g("title"), detail=g("detail"),
             fam=g("family"), stype=g("source", "type"))
    for _, r in df.iterrows():
        eid = clean(r[c["id"]])
        if not eid:
            continue
        out.append({"id": eid, "published": date(r[c["pub"]]), "effective": date(r[c["eff"]]),
                    "title": clean(r[c["title"]]) or "", "detail": clean(r[c["detail"]]) or "",
                    "family": clean(r[c["fam"]]) or eid, "source_type": clean(r[c["stype"]]) if c["stype"] else None})
    return out
