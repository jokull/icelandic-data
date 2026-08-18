"""Reusable primitives for reverse-engineering **public** Power BI dashboards.

Every embedded public report (`https://app.powerbi.com/view?r=<token>`, whether
standalone or inside an `<iframe>` on some ministry's SPA) speaks the same
protocol. This module factors out the parts that are identical across every
such dashboard in this repo (samgongustofa, landlaeknir, vernd, farsaeld_barna,
ferdamalastofa, tekjusagan, vinnumalastofnun, maelabord_nautgripa, …). A
per-source script then supplies only what is genuinely source-specific: the SPA
URL, which section to open, and the slicer/column names.

WHAT IS GENERALIZABLE
---------------------
1. Embed token  — `?r=<base64({"k":resourceKey,"t":tenant,"c":cluster})>`.
   `embed_url()` builds it; `token_of()` / `key_of()` decode it.
2. Query endpoint — `https://wabi-<region>-<x>-api.analysis.windows.net/public/
   reports/querydata?synchronous=true`, header `x-powerbi-resourcekey: <key>`,
   NO bearer for public reports.
3. Auth reality — the anonymous grant is session-, origin- and rate-bound: a
   cold httpx client 401s after a few requests, and a POST from any origin other
   than the app.powerbi.com iframe is rejected. So the robust extraction is to
   REPLAY queries with `fetch()` executed *inside the iframe* (`replay()`),
   reusing the report's own live session. `discover()` sets that up.
4. Request body — a `SemanticQueryDataShapeCommand`; the POST must keep its
   top-level `modelId`/`version`/`cancelQueries` or you get 400. Capture the
   report's own request as a template and rewrite its `Where` (`where_in()`).
5. Response — a DSR (DataShapeResult), a *compressed* columnar format:
   `ValueDicts` (int→string), an `R` repeat-bitmask (carry the value from the
   previous row) and a `Ø` null-bitmask. `parse_dsr()` / `group_counts()`
   decode it. This is the single most-reinvented, most-error-prone piece.

WHAT IS NOT
-----------
The SPA URL, section anchors, slicer column names + literal formats, the
friendly dimension names, and whether the host is geo-fenced. Discover those
once with a `page.on("request")` listener (see `capture_requests`).

Requires Playwright (`uv run playwright install chromium`). Geo-fenced hosts
must be driven from an IP in the right country.
"""
from __future__ import annotations

import base64
import binascii
import copy
import json
from dataclasses import dataclass, field

QUERYDATA_HINT = "querydata"  # substring identifying a data request

# fetch() body run inside the app.powerbi.com iframe; returns JSON or {__status}.
_JS_REPLAY = """async ({url, key, payload}) => {
    const r = await fetch(url, {
        method: 'POST',
        headers: {
            'content-type': 'application/json;charset=UTF-8',
            'accept': 'application/json, text/plain, */*',
            'x-powerbi-resourcekey': key,
        },
        body: JSON.stringify(payload),
    });
    if (!r.ok) return {__status: r.status};
    return await r.json();
}"""


# ---------------------------------------------------------------------------
# embed token
# ---------------------------------------------------------------------------
def embed_url(key, tenant, *, cluster=8, page=None):
    """Build an app.powerbi.com/view URL from a resource key + tenant id."""
    payload = {"k": key, "t": tenant, "c": cluster}
    token = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    url = f"https://app.powerbi.com/view?r={token}"
    return f"{url}&pageName={page}" if page else url


def token_of(view_url):
    """Decode `?r=<token>` from an app.powerbi.com/view URL to its dict."""
    token = view_url.split("r=", 1)[1].split("&", 1)[0]
    token += "=" * (-len(token) % 4)
    try:
        return json.loads(base64.b64decode(token))
    except (binascii.Error, json.JSONDecodeError, ValueError):
        return {}


def key_of(view_url):
    """The resource key ('k') embedded in an app.powerbi.com/view URL."""
    return token_of(view_url).get("k")


# ---------------------------------------------------------------------------
# discovery + replay (Playwright)
# ---------------------------------------------------------------------------
@dataclass
class Discovery:
    frame: object                        # the app.powerbi.com/view iframe
    key: str                             # its resource key
    templates: dict = field(default_factory=dict)   # first-Select-column -> request body
    requests: list = field(default_factory=list)    # every (key, body) captured


def capture_requests(page, sink):
    """Register a request listener that appends (resourcekey, parsed-body) for
    every querydata POST to `sink`. Returns the listener so callers can remove
    it. Use directly when discovering a new dashboard's columns/literals."""
    def on_request(req):
        if QUERYDATA_HINT in req.url and req.post_data:
            try:
                sink.append((req.headers.get("x-powerbi-resourcekey"), json.loads(req.post_data)))
            except json.JSONDecodeError:
                pass
    page.on("request", on_request)
    return on_request


def _select_columns(body):
    q = body["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]["Query"]
    return [s["Column"]["Property"] for s in q.get("Select", []) if "Column" in s]


async def discover(page, spa_url, *, anchor=None, settle=10.0, goto_settle=3.0):
    """Open a dashboard and return a Discovery for its ACTIVE report.

    - navigates to `spa_url` (waits for networkidle),
    - optionally clicks a section link `a[href="<anchor>"]`,
    - finds the active app.powerbi.com/view iframe and decodes its key,
    - indexes each captured visual's request body by its first Select column,
      filtered to the active key so a neighbouring report cannot leak in.
    """
    import asyncio

    captured: list = []
    listener = capture_requests(page, captured)
    await page.goto(spa_url, wait_until="networkidle", timeout=90_000)
    await asyncio.sleep(goto_settle)
    if anchor:
        await page.eval_on_selector(f'a[href="{anchor}"]', "e => e.click()")
    await asyncio.sleep(settle)

    frame = next((f for f in page.frames if "app.powerbi.com/view" in f.url), None)
    if frame is None:
        page.remove_listener("request", listener)
        raise RuntimeError("no app.powerbi.com/view iframe — layout changed or not a public embed?")
    key = key_of(frame.url)

    templates = {}
    for k, body in captured:
        if k != key:
            continue
        try:
            cols = _select_columns(body)
            if cols:
                templates[cols[0]] = body
        except (KeyError, IndexError):
            pass
    page.remove_listener("request", listener)
    return Discovery(frame=frame, key=key, templates=templates, requests=captured)


def query_url(frame):
    """Best-effort querydata endpoint. The region cluster is baked into the
    wabi host; the public path is stable, so a fixed default works for every
    tenant observed so far. Override per-source if a dashboard differs."""
    return "https://wabi-europe-north-b-api.analysis.windows.net/public/reports/querydata?synchronous=true"


async def replay(frame, key, payload, *, url=None, retries=1, backoff=5.0):
    """POST `payload` from inside the iframe; return parsed JSON. Retries once
    on the transient 401/429 the anonymous grant throws under load."""
    import asyncio

    url = url or query_url(frame)
    for attempt in range(retries + 1):
        out = await frame.evaluate(_JS_REPLAY, {"url": url, "key": key, "payload": payload})
        if not (isinstance(out, dict) and out.get("__status")):
            return out
        if attempt == retries:
            raise RuntimeError(f"querydata HTTP {out['__status']}")
        await asyncio.sleep(backoff)


# ---------------------------------------------------------------------------
# query rewriting
# ---------------------------------------------------------------------------
def query_of(body):
    """The SemanticQuery inside a request body (Select/Where/OrderBy/Binding)."""
    return body["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]["Query"]


_query = query_of  # internal alias


def in_condition(column, values, *, source="q"):
    """An `In` filter. `values` are sent verbatim as literals — pass
    `"'text'"` for a text column, `"2023L"` for an integer column."""
    values = values if isinstance(values, (list, tuple)) else [values]
    return {"Condition": {"In": {
        "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": source}}, "Property": column}}],
        "Values": [[{"Literal": {"Value": v}}] for v in values],
    }}}


def where_in(body, column, values, *, replace=True, text=True):
    """Clone `body` and add/replace an In filter on `column`.

    `text=True` wraps each value as a text literal `'x'`; `text=False` passes it
    through (use `"2023L"` for integer/date literals). `replace=True` drops any
    existing filter on the same column first."""
    b = copy.deepcopy(body)
    q = _query(b)
    where = q.get("Where", [])
    if replace:
        where = [w for w in where if (w.get("Condition", {}).get("In", {}).get("Expressions", [{}])[0]
                                      .get("Column", {}).get("Property")) != column]
    lits = [f"'{v}'" if text else str(v) for v in (values if isinstance(values, (list, tuple)) else [values])]
    where.append(in_condition(column, lits))
    q["Where"] = where
    return b



def where_drop(body, *columns):
    """Clone `body` and remove any In filter on the named column(s)."""
    b = copy.deepcopy(body)
    q = _query(b)
    drop = set(columns)
    q["Where"] = [w for w in q.get("Where", [])
                  if (w.get("Condition", {}).get("In", {}).get("Expressions", [{}])[0]
                      .get("Column", {}).get("Property")) not in drop]
    return b

# ---------------------------------------------------------------------------
# DSR response decoding
# ---------------------------------------------------------------------------
def _dm0_rows(ds):
    """Decompress a DataSet's DM0 rows.

    DSR is columnar + compressed: `C` carries only the columns that are neither
    repeated nor null; the `R` bitmask marks columns carried over from the
    previous row; the `Ø` bitmask marks nulls; per-column `DN` names a
    `ValueDicts` entry mapping the integer code to a string. Bit i (LSB-first)
    corresponds to column i. Yields fully-reconstructed value lists."""
    vds = ds.get("ValueDicts", {})
    col_dn = None
    prev: list = []
    for ph in ds.get("PH", []):
        for row in ph.get("DM0", []):
            if "S" in row:                     # column descriptor (first row carries it)
                col_dn = [c.get("DN") for c in row["S"]]
            n = len(col_dn) if col_dn else len(row.get("C", []))
            R = row.get("R", 0)
            O = row.get("Ø", 0)
            C = row.get("C", [])
            cur, ci = [None] * n, 0
            for i in range(n):
                if O >> i & 1:
                    cur[i] = None
                elif R >> i & 1:
                    cur[i] = prev[i] if i < len(prev) else None
                else:
                    cur[i] = C[ci] if ci < len(C) else None
                    ci += 1
                dn = col_dn[i] if col_dn and i < len(col_dn) else None
                if dn and dn in vds and isinstance(cur[i], int) and 0 <= cur[i] < len(vds[dn]):
                    cur[i] = vds[dn][cur[i]]
            prev = cur
            yield cur, row


def group_counts(body, *, measure=0):
    """Convenience for the common `[dimension, measure]` visual → {label: value}.

    Handles both DM0 shapes: the flat categorical form (`C:[dim,measure]`, with
    R/Ø/ValueDict compression) and the measure-matrix form (`G0` + `X[].M0`,
    where `measure` picks which series). Sums duplicates."""
    out: dict = {}
    for res in body.get("results", []):
        dsr = (res.get("result") or {}).get("data", {}).get("dsr", {})
        for ds in dsr.get("DS", []):
            for cur, row in _dm0_rows(ds):
                if "X" in row:                 # measure-matrix form
                    label = cur[0] if cur else row.get("G0")
                    xs = row.get("X", [])
                    val = xs[measure].get("M0") if measure < len(xs) else None
                    if val is None and xs:
                        val = xs[0].get("M0")
                else:                          # flat form: last numeric column
                    label = cur[0] if cur else None
                    val = next((v for v in reversed(cur[1:]) if isinstance(v, (int, float))), None)
                if label is not None:
                    out[label] = out.get(label, 0) + (val or 0)
    return out


def parse_dsr(body):
    """Every DM0 row of every DataSet as a decoded value list (columns in
    Select order). The general escape hatch when `group_counts` is too narrow —
    e.g. multi-measure visuals or time series."""
    rows = []
    for res in body.get("results", []):
        dsr = (res.get("result") or {}).get("data", {}).get("dsr", {})
        for ds in dsr.get("DS", []):
            rows.extend(cur for cur, _ in _dm0_rows(ds))
    return rows
