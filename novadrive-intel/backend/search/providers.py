"""Pluggable web-search providers with fallback, circuit breaking and a disk cache.

Order (first configured + healthy wins):
  1. Tavily      TAVILY_API_KEY      — built for research agents, returns page content
  2. Brave       BRAVE_API_KEY       — independent index, reliable API
  3. SerpAPI     SERPAPI_API_KEY     — Google results
  4. DuckDuckGo  (pip install ddgs)  — keyless but unofficial and frequently rate-limited
  5. Wikipedia   keyless             — encyclopedic company/technology pages
  6. GDELT       keyless             — worldwide news index; last resort

If every provider fails, the service returns the last cached result for the query (labelled
with its retrieval date) or an explicit 'unavailable' status. It never invents results.
"""
from __future__ import annotations

import html
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

TIMEOUT = float(os.environ.get("SEARCH_TIMEOUT", "8"))
COOLDOWN = 120  # seconds a failing provider is skipped
UA = "NovaDrive-SupplyIntel/1.0 (case-study prototype)"


@dataclass
class Result:
    title: str
    url: str
    snippet: str
    provider: str
    published: str | None = None
    domain: str = field(default="")

    def __post_init__(self):
        self.domain = urlparse(self.url).netloc.replace("www.", "")
        self.snippet = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", self.snippet or ""))).strip()[:500]
        self.title = html.unescape(re.sub(r"<[^>]+>", "", self.title or "")).strip()


class Provider:
    name = "base"
    label = "Base"
    keyless = False

    def configured(self) -> bool:
        return True

    def search(self, query: str, n: int) -> list[Result]:
        raise NotImplementedError


class Tavily(Provider):
    name, label = "tavily", "Tavily"

    def configured(self):
        return bool(os.environ.get("TAVILY_API_KEY"))

    def search(self, query, n):
        r = httpx.post("https://api.tavily.com/search", timeout=TIMEOUT,
                       json={"api_key": os.environ["TAVILY_API_KEY"], "query": query, "max_results": n, "search_depth": "basic"})
        r.raise_for_status()
        return [Result(x.get("title", ""), x["url"], x.get("content", ""), self.name, x.get("published_date")) for x in r.json().get("results", [])]


class Brave(Provider):
    name, label = "brave", "Brave Search"

    def configured(self):
        return bool(os.environ.get("BRAVE_API_KEY"))

    def search(self, query, n):
        r = httpx.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": min(n, 20)}, timeout=TIMEOUT,
                      headers={"X-Subscription-Token": os.environ["BRAVE_API_KEY"], "Accept": "application/json"})
        r.raise_for_status()
        return [Result(x.get("title", ""), x["url"], x.get("description", ""), self.name, x.get("age")) for x in r.json().get("web", {}).get("results", [])]


class SerpApi(Provider):
    name, label = "serpapi", "SerpAPI (Google)"

    def configured(self):
        return bool(os.environ.get("SERPAPI_API_KEY"))

    def search(self, query, n):
        r = httpx.get("https://serpapi.com/search.json", timeout=TIMEOUT,
                      params={"q": query, "num": n, "engine": "google", "api_key": os.environ["SERPAPI_API_KEY"]})
        r.raise_for_status()
        return [Result(x.get("title", ""), x["link"], x.get("snippet", ""), self.name, x.get("date")) for x in r.json().get("organic_results", [])]


class DuckDuckGo(Provider):
    name, label, keyless = "duckduckgo", "DuckDuckGo (unofficial)", True

    def configured(self):
        if os.environ.get("DISABLE_DDG"):
            return False
        try:
            import ddgs  # noqa: F401
            return True
        except ImportError:
            try:
                import duckduckgo_search  # noqa: F401
                return True
            except ImportError:
                return False

    def search(self, query, n):
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        res = list(DDGS(timeout=int(TIMEOUT)).text(query, max_results=n))
        return [Result(x.get("title", ""), x.get("href") or x.get("url", ""), x.get("body", ""), self.name) for x in res if x.get("href") or x.get("url")]


class Wikipedia(Provider):
    name, label, keyless = "wikipedia", "Wikipedia API", True

    def search(self, query, n):
        r = httpx.get("https://en.wikipedia.org/w/api.php", timeout=TIMEOUT, headers={"User-Agent": UA},
                      params={"action": "query", "list": "search", "srsearch": query, "srlimit": n, "format": "json", "srprop": "snippet|timestamp"})
        r.raise_for_status()
        return [Result(x["title"], "https://en.wikipedia.org/wiki/" + x["title"].replace(" ", "_"), x.get("snippet", ""), self.name, x.get("timestamp", "")[:10])
                for x in r.json().get("query", {}).get("search", [])]


class Gdelt(Provider):
    """GDELT DOC 2.0: free, keyless index of worldwide news (good for capability and risk news)."""
    name, label, keyless = "gdelt", "GDELT news", True

    def search(self, query, n):
        q = " ".join(w for w in query.split() if len(w) > 2)[:120]
        r = httpx.get("https://api.gdeltproject.org/api/v2/doc/doc", timeout=TIMEOUT, headers={"User-Agent": UA},
                      params={"query": f"({' OR '.join(q.split()[:2])}) {' '.join(q.split()[2:5])} sourcelang:english", "mode": "artlist",
                              "maxrecords": n, "format": "json", "sort": "hybridrel"})
        r.raise_for_status()
        arts = r.json().get("articles", []) if r.text.strip().startswith("{") else []
        return [Result(a.get("title", ""), a["url"], a.get("title", ""), self.name, (a.get("seendate") or "")[:8]) for a in arts]


PROVIDERS = [Tavily(), Brave(), SerpApi(), DuckDuckGo(), Wikipedia(), Gdelt()]


class SearchService:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.lock = threading.Lock()
        self.down_until: dict[str, float] = {}
        self.last_error: dict[str, str] = {}
        try:
            self.cache = json.loads(cache_path.read_text())
        except Exception:
            self.cache = {}

    def status(self):
        now = time.time()
        return [{"name": p.name, "label": p.label, "configured": p.configured(), "keyless": p.keyless,
                 "cooling_down": self.down_until.get(p.name, 0) > now, "last_error": self.last_error.get(p.name)} for p in PROVIDERS]

    def _save(self):
        try:
            self.cache_path.write_text(json.dumps(self.cache, indent=1))
        except Exception:
            pass

    def search(self, query: str, n: int = 10, only: list[str] | None = None) -> dict:
        attempts = []
        now = time.time()
        for p in PROVIDERS:
            if only and p.name not in only:
                continue
            if not p.configured():
                attempts.append({"provider": p.label, "status": "not configured"})
                continue
            if self.down_until.get(p.name, 0) > now:
                attempts.append({"provider": p.label, "status": "cooling down", "error": self.last_error.get(p.name)})
                continue
            t0 = time.time()
            try:
                res = [r for r in p.search(query, n) if r.url.startswith("http")]
                ms = int((time.time() - t0) * 1000)
                if not res:
                    attempts.append({"provider": p.label, "status": "no results", "ms": ms})
                    continue
                attempts.append({"provider": p.label, "status": "ok", "ms": ms, "count": len(res)})
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                payload = {"provider": p.label, "retrieved": stamp, "results": [asdict(r) for r in res]}
                with self.lock:
                    self.cache[query] = payload
                    self._save()
                return {"status": "live", **payload, "attempts": attempts}
            except Exception as e:  # network, auth, rate-limit, parsing — all non-fatal
                msg = f"{type(e).__name__}: {str(e)[:140]}"
                self.down_until[p.name] = time.time() + COOLDOWN
                self.last_error[p.name] = msg
                attempts.append({"provider": p.label, "status": "failed", "error": msg, "ms": int((time.time() - t0) * 1000)})
        if query in self.cache:
            return {"status": "cached", **self.cache[query], "attempts": attempts}
        return {"status": "unavailable", "provider": None, "retrieved": None, "results": [], "attempts": attempts}
