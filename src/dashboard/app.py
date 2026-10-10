"""
Automotive SWE V-Cycle AI Assistant — engineer review console.

Reads the agent pipeline's work products from data/output/ and presents them for
the mandatory human review gate: SWE.1 software requirements, SWE.6 qualification
test cases, bidirectional traceability, standards grounding, validation findings,
data-integrity checks, and the timing evidence behind the speed claim.

Design decisions worth defending in the report
----------------------------------------------
1. Agent output files are never mutated. Review decisions and human edits live in
   review_state.json, seeded once from any review_status already present in the
   agent output. The unedited first draft therefore survives as evidence, and the
   human edit delta becomes a measurable quality signal.
2. Duplicate requirement IDs are real in this dataset. Every record is addressed
   by a unique key derived from id + source section, so two requirements sharing
   an ID cannot share a review decision or silently overwrite one another.
3. Every loader degrades gracefully. A missing or malformed artifact surfaces in
   the Data Health panel instead of a stack trace on stage.
4. Field names are resolved through aliases, so the UI survives the difference
   between the Week 1 schema (test_id / requirement_id) and what the generator
   currently emits (tc_id / req_id).

Visual system
-------------
iOS light, in the style of the iPhone Settings app: #F2F2F7 grouped canvas, white
cards, hairline separators, SF system font, iOS system colours for status. Chart
hues are iOS systemBlue plus darkened iOS orange and pink, validated against the
#F2F2F7 chart surface (lightness band, chroma floor, all-pairs CVD separation,
normal-vision separation, 3:1 contrast — all pass). Series cap is 3; further
categories fold into "Other" rather than inventing a fourth hue.

Colours are pinned in CSS rather than inherited from Streamlit's theme, so the
page renders identically whether or not the viewer's theme toggle says Light.

Run:  streamlit run app.py
Env:  SWE_DATA_DIR   override the data/output directory
      SWE_PIPELINE   shell command executed by the Run Pipeline control
"""

from __future__ import annotations

import difflib
import inspect
import io
import json
import os
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# =====================================================================
# PAGE CONFIG
# =====================================================================

st.set_page_config(
    page_title="SWE V-Cycle Assistant",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_VERSION = "3.0"


def _wide(fn) -> dict:
    """Full-width kwargs for whichever Streamlit version is installed."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {"use_container_width": True}
    if "width" in params:
        return {"width": "stretch"}
    if "use_container_width" in params:
        return {"use_container_width": True}
    return {}


WIDE = _wide(st.dataframe)
PLOT_CFG = {"displayModeBar": False}

# =====================================================================
# DESIGN TOKENS — iOS light
#
# iPhone Settings palette: #F2F2F7 grouped canvas, white cards, hairline
# separators, SF system font, iOS system colours.
#
# Chart series are iOS systemBlue plus darkened iOS orange and pink, validated
# against the #F2F2F7 chart surface: lightness band, chroma floor, all-pairs
# CVD separation, normal-vision separation and 3:1 contrast all pass. Series
# cap is 3 — further categories fold into "Other" rather than inventing a
# fourth hue.
# =====================================================================

BG = "#F2F2F7"          # systemGroupedBackground
CARD = "#FFFFFF"        # secondarySystemGroupedBackground
CARD_2 = "#E9E9EF"      # fills / hover
SEP = "rgba(60,60,67,0.22)"
LABEL = "#000000"
LABEL_2 = "rgba(60,60,67,0.62)"
LABEL_3 = "rgba(60,60,67,0.42)"
ACCENT = "#007AFF"      # systemBlue

SERIES = ["#007AFF", "#C77400", "#C72342"]
SEQ = SERIES[0]
GRID = "rgba(60,60,67,0.13)"

STATUSES = ["Approved", "Needs Clarification", "Rejected", "Pending"]

# Apple's increased-contrast light variants. Reserved for status only — never
# reused as a series hue, and always paired with a glyph and a text label so
# colour never stands alone.
STATUS_COLOR = {
    "Approved": "#248A3D",
    "Needs Clarification": "#B25000",
    "Rejected": "#D70015",
    "Pending": "#8E8E93",
}
STATUS_ICON = {
    "Approved": "✓",
    "Needs Clarification": "!",
    "Rejected": "✕",
    "Pending": "○",
}
SEV_STYLE = {
    "error": ("#D70015", "✕", "Errors"),
    "warning": ("#B25000", "!", "Warnings"),
    "info": ("#8E8E93", "·", "Informational"),
    "pass": ("#248A3D", "✓", "Checks passed"),
}

FONT = ('-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", '
        '"Helvetica Neue", "Segoe UI", system-ui, sans-serif')

# Colours are pinned explicitly rather than inherited, so the page renders the
# same whether or not the viewer's Streamlit theme toggle is set to Light.
st.markdown(
    f"""
<style>
html, body, .stApp, [class*="css"] {{ font-family: {FONT}; }}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
    background: {BG} !important;
}}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1500px; }}

.stApp p, .stApp li, .stApp label, .stApp span,
[data-testid="stMarkdownContainer"] {{ color: {LABEL}; }}
.stApp a {{ color: {ACCENT}; }}

/* iOS Large Title */
h1 {{
    font-size: 2.45rem !important; font-weight: 700 !important;
    letter-spacing: -0.028em !important; color: {LABEL} !important;
    margin-bottom: 0.1rem !important;
}}
h2 {{ font-size: 1.35rem !important; font-weight: 650 !important;
     letter-spacing: -0.018em !important; color: {LABEL} !important; }}
h3 {{ font-size: 1.05rem !important; font-weight: 600 !important;
     letter-spacing: -0.01em !important; color: {LABEL} !important; }}

/* Sidebar: iOS Settings */
section[data-testid="stSidebar"] {{
    background: {CARD} !important;
    border-right: 1px solid {SEP};
}}
section[data-testid="stSidebar"] * {{ color: {LABEL}; }}

/* Navigation rows.
   These are ordinary buttons, not a styled radio group, on purpose: a radio
   needs structural selectors to hide its dot, and those break between Streamlit
   versions — when the DOM shifts, the rule hides the label instead and the menu
   goes blank. Buttons carry their text in the button element itself, so the
   worst a CSS miss can do here is leave a row looking plain. */
section[data-testid="stSidebar"] div[data-testid="stButton"] > button {{
    display: flex;
    justify-content: flex-start;
    width: 100%;
    padding: 9px 13px;
    margin-bottom: 2px;
    border-radius: 11px;
    border: 1px solid {SEP};
    background: {BG};
    color: {LABEL} !important;
    font-size: 0.93rem;
    font-weight: 450;
    letter-spacing: -0.01em;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {{
    color: {LABEL} !important;
    font-weight: 450;
    width: 100%;
    text-align: left;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button > div {{
    width: 100%;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {{
    background: {CARD_2};
    border-color: {SEP};
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #FFFFFF !important;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] p {{
    color: #FFFFFF !important;
    font-weight: 600;
}}

/* Metric cards as grouped cells */
div[data-testid="stMetric"], div[data-testid="metric-container"] {{
    background: {CARD}; border: 1px solid {SEP};
    border-radius: 16px; padding: 15px 17px;
}}
div[data-testid="stMetricLabel"] p {{
    color: {LABEL_2} !important; font-size: 0.78rem !important;
    font-weight: 500 !important; letter-spacing: 0.01em;
}}
div[data-testid="stMetricValue"] {{
    color: {LABEL}; font-weight: 600; letter-spacing: -0.02em;
}}

/* Expanders as inset list rows */
div[data-testid="stExpander"] {{
    background: {CARD}; border: 1px solid {SEP};
    border-radius: 14px; margin-bottom: 7px; overflow: hidden;
}}
div[data-testid="stExpander"] summary {{ padding: 11px 15px; }}
div[data-testid="stExpander"] summary p {{
    font-size: 0.93rem !important; letter-spacing: -0.01em;
}}

/* Buttons */
div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {{
    border-radius: 11px; border: 1px solid {SEP};
    background: {CARD}; color: {ACCENT};
    font-weight: 550; font-size: 0.88rem;
    letter-spacing: -0.01em; padding: 0.42rem 0.9rem;
    transition: background 120ms ease;
}}
div[data-testid="stButton"] > button:hover,
div[data-testid="stDownloadButton"] > button:hover {{
    background: {CARD_2}; border-color: {SEP}; color: {ACCENT};
}}
div[data-testid="stButton"] > button[kind="primary"] {{
    background: {ACCENT}; color: #FFFFFF; border-color: {ACCENT};
}}

/* Inputs and tables */
div[data-baseweb="input"], div[data-baseweb="select"] > div, .stTextArea textarea {{
    border-radius: 11px !important;
    background: {CARD} !important;
    border-color: {SEP} !important;
    color: {LABEL} !important;
}}
div[data-testid="stDataFrame"], div[data-testid="stDataFrameResizable"] {{
    border-radius: 12px; border: 1px solid {SEP}; background: {CARD};
}}
hr {{ border-color: {SEP} !important; }}

/* Custom pieces */
.ios-head {{
    color: {LABEL_2}; font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.05em; text-transform: uppercase;
    padding: 2px 4px 6px 4px;
}}
.ios-sub {{
    color: {LABEL_2}; font-size: 0.95rem;
    letter-spacing: -0.01em; margin-top: -2px;
}}
.ios-note {{ color: {LABEL_3}; font-size: 0.8rem; letter-spacing: -0.005em; }}
.ios-card {{
    background: {CARD}; border: 1px solid {SEP};
    border-radius: 16px; padding: 15px 18px; margin-bottom: 9px;
    color: {LABEL};
}}
.ios-pill {{
    display: inline-block; padding: 2.5px 10px; margin: 2px 5px 2px 0;
    border-radius: 999px; background: {BG}; border: 1px solid {SEP};
    color: {LABEL_2}; font-size: 0.74rem; font-weight: 500;
}}
.ios-kv {{ color: {LABEL}; font-size: 0.9rem; margin: 5px 0; letter-spacing: -0.008em; }}
.ios-kv b {{ color: {LABEL_2}; font-weight: 500; }}
.ios-quote {{
    border-left: 3px solid {ACCENT}; padding: 7px 0 7px 13px; margin: 8px 0;
    color: {LABEL_2}; font-size: 0.87rem; font-style: italic;
}}
.ios-row {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 2px; border-bottom: 1px solid {SEP};
    color: {LABEL}; font-size: 0.9rem;
}}
.ios-row:last-child {{ border-bottom: none; }}
.ios-row span.v {{ color: {LABEL_2}; font-variant-numeric: tabular-nums; }}
</style>
""",
    unsafe_allow_html=True,
)


# =====================================================================
# PATHS
# =====================================================================

DATA_DIR = Path(os.getenv("SWE_DATA_DIR", "data/output"))

REQ_FILE = DATA_DIR / "requirements.json"
TC_FILE = DATA_DIR / "testcases.json"
VALIDATION_FILE = DATA_DIR / "validation_report.json"
TRACE_FILE = DATA_DIR / "traceability_matrix.json"
METRICS_FILE = DATA_DIR / "metrics.json"
REVIEW_FILE = DATA_DIR / "review_state.json"

# =====================================================================
# FIELD ALIASES
# =====================================================================

REQ_ID_KEYS = ("req_id", "requirement_id", "requirement", "id", "ID")
REQ_TEXT_KEYS = ("text", "requirement_text", "description", "statement")
REQ_RATIONALE_KEYS = ("rationale", "reason", "justification")
REQ_CATEGORY_KEYS = ("category", "type", "req_type", "classification")
REQ_SOURCE_KEYS = ("source_section", "source", "section_id", "spec_section")
REQ_EXCERPT_KEYS = ("trace_source_excerpt", "source_excerpt", "excerpt", "quote")
REQ_VERIF_KEYS = ("verification_criteria", "acceptance_criteria", "verification")
REQ_SAFETY_KEYS = ("safety_relevant", "is_safety_relevant", "safety")
REQ_ASIL_KEYS = ("asil_suggestion", "asil", "suggested_asil", "asil_proposed")

TC_ID_KEYS = ("tc_id", "test_id", "testcase_id", "test_case_id", "id", "ID")
TC_REQ_KEYS = ("req_id", "requirement_id", "traceability", "trace_to", "covers")
TC_TITLE_KEYS = ("title", "name", "summary")
TC_OBJECTIVE_KEYS = ("objective", "purpose", "goal")
TC_ENV_KEYS = ("test_environment", "environment", "test_level", "level")
TC_TECHNIQUE_KEYS = ("technique", "test_technique", "method", "istqb_technique")
TC_PRECOND_KEYS = ("preconditions", "precondition", "setup", "pre_conditions")
TC_STEPS_KEYS = ("test_steps", "steps", "procedure", "actions")
TC_EXPECTED_KEYS = ("expected_results", "expected_result", "expected", "pass_criteria")

GROUNDING_KEYS = ("grounding_refs", "grounding", "standards_refs", "references")
FORWARD_KEYS = ("forward_trace", "downstream", "derived_elements")
TRACE_TESTS_KEYS = ("tests", "test_ids", "testcases", "test_cases", "covered_by")


def pick(rec: dict, keys, default=None):
    for key in keys:
        if key in rec:
            val = rec[key]
            if val not in (None, "", [], {}):
                return val
    return default


def as_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in {"yes", "y", "true", "t", "1", "safety"}
    return False


def as_text(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, tuple)):
        return "\n".join(as_text(v) for v in val)
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def as_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, str):
        return [val] if val.strip() else []
    return [val]


def asil_class(raw: str) -> str:
    """Collapse 'QM', 'QM (S0, E0, C0)' and 'ASIL QM (...)' onto one label."""
    upper = as_text(raw).upper()
    for level in ("ASIL D", "ASIL C", "ASIL B", "ASIL A"):
        if level in upper and "QM" not in upper.split(level)[0]:
            return level
    if "QM" in upper:
        return "QM"
    return as_text(raw).strip() or "not proposed"


# =====================================================================
# LOADING — every read reports its own failure instead of raising
# =====================================================================


def read_json(path: Path):
    try:
        if not path.exists():
            return None, "file not found"
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None, "file is empty"
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}: {exc.msg}"
    except Exception as exc:  # noqa: BLE001 — a demo must never die on IO
        return None, f"{type(exc).__name__}: {exc}"


def records_from(payload, id_keys) -> list[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("requirements", "testcases", "test_cases", "items", "data",
                    "results", "links", "matrix"):
            val = payload.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
        if payload and all(isinstance(v, dict) for v in payload.values()):
            out = []
            for key, val in payload.items():
                rec = dict(val)
                if not pick(rec, id_keys):
                    rec[id_keys[0]] = key
                out.append(rec)
            return out
    return []


def normalise_requirement(rec: dict, index: int) -> dict:
    raw_asil = as_text(pick(rec, REQ_ASIL_KEYS, ""))
    return {
        "index": index,
        "rid": as_text(pick(rec, REQ_ID_KEYS, f"REQ-{index + 1:03d}")),
        "uid": "",
        "text": as_text(pick(rec, REQ_TEXT_KEYS, "")),
        "rationale": as_text(pick(rec, REQ_RATIONALE_KEYS, "")),
        "category": as_text(pick(rec, REQ_CATEGORY_KEYS, "Uncategorised")),
        "source": as_text(pick(rec, REQ_SOURCE_KEYS, "")),
        "excerpt": as_text(pick(rec, REQ_EXCERPT_KEYS, "")),
        "verification": as_text(pick(rec, REQ_VERIF_KEYS, "")),
        "safety": as_bool(pick(rec, REQ_SAFETY_KEYS, False)),
        "asil_raw": raw_asil,
        "asil": asil_class(raw_asil),
        "grounding": [as_text(g) for g in as_list(pick(rec, GROUNDING_KEYS, []))],
        "forward": [as_text(g) for g in as_list(pick(rec, FORWARD_KEYS, []))],
        "file_review": as_text(rec.get("review_status", "")),
        "raw": rec,
    }


def normalise_testcase(rec: dict, index: int) -> dict:
    return {
        "index": index,
        "tid": as_text(pick(rec, TC_ID_KEYS, f"TC-{index + 1:03d}")),
        "rid": as_text(pick(rec, TC_REQ_KEYS, "")),
        "title": as_text(pick(rec, TC_TITLE_KEYS, "")),
        "objective": as_text(pick(rec, TC_OBJECTIVE_KEYS, "")),
        "env": as_text(pick(rec, TC_ENV_KEYS, "Unspecified")),
        "technique": as_text(pick(rec, TC_TECHNIQUE_KEYS, "")),
        "preconditions": as_text(pick(rec, TC_PRECOND_KEYS, "")),
        "steps": [as_text(s) for s in as_list(pick(rec, TC_STEPS_KEYS, []))],
        "expected": [as_text(e) for e in as_list(pick(rec, TC_EXPECTED_KEYS, []))],
        "grounding": [as_text(g) for g in as_list(pick(rec, GROUNDING_KEYS, []))],
        "forward": [as_text(g) for g in as_list(pick(rec, FORWARD_KEYS, []))],
        "file_review": as_text(rec.get("review_status", "")),
        "raw": rec,
    }


def assign_uids(records: list[dict], id_field: str) -> None:
    """Duplicate IDs are real in this dataset — give every record a unique key.

    Without this, two requirements sharing an ID would share a review decision
    and overwrite each other's edits.
    """
    counts = Counter(r[id_field] for r in records)
    used: set[str] = set()
    for rec in records:
        uid = rec[id_field]
        if counts[uid] > 1:
            uid = f"{rec[id_field]}@{rec['source']}" if rec.get("source") else uid
        while uid in used:
            uid = f"{rec[id_field]}#{rec['index'] + 1}"
        used.add(uid)
        rec["uid"] = uid


def file_signature() -> tuple:
    sig = []
    for path in (REQ_FILE, TC_FILE, VALIDATION_FILE, TRACE_FILE, METRICS_FILE):
        try:
            stat = path.stat()
            sig.append((path.name, stat.st_mtime_ns, stat.st_size))
        except OSError:
            sig.append((path.name, 0, 0))
    return tuple(sig)


@st.cache_data(show_spinner=False)
def load_artifacts(_signature: tuple):
    problems: list[tuple[str, str]] = []

    req_payload, err = read_json(REQ_FILE)
    if err:
        problems.append((REQ_FILE.name, err))
    requirements = [normalise_requirement(r, i)
                    for i, r in enumerate(records_from(req_payload, REQ_ID_KEYS))]
    assign_uids(requirements, "rid")

    tc_payload, err = read_json(TC_FILE)
    if err:
        problems.append((TC_FILE.name, err))
    testcases = [normalise_testcase(t, i)
                 for i, t in enumerate(records_from(tc_payload, TC_ID_KEYS))]
    for tc in testcases:
        tc["source"] = ""
    assign_uids(testcases, "tid")

    trace_payload, err = read_json(TRACE_FILE)
    if err:
        problems.append((TRACE_FILE.name, err))

    val_payload, err = read_json(VALIDATION_FILE)
    if err:
        problems.append((VALIDATION_FILE.name, err))

    met_payload, err = read_json(METRICS_FILE)
    if err:
        problems.append((METRICS_FILE.name, err))
    metrics = met_payload if isinstance(met_payload, dict) else {}

    return requirements, testcases, trace_payload, val_payload, metrics, problems


# =====================================================================
# REVIEW STATE — kept apart from the agent's own output
# =====================================================================


def load_review() -> dict:
    payload, _ = read_json(REVIEW_FILE)
    if not isinstance(payload, dict):
        payload = {}
    for key in ("requirements", "testcases", "meta"):
        if not isinstance(payload.get(key), dict):
            payload[key] = {}
    return payload


def save_review(state: dict) -> bool:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = REVIEW_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, REVIEW_FILE)
        return True
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not write review state: {exc}")
        return False


def seed_review(state: dict, requirements: list[dict], testcases: list[dict]) -> dict:
    """Carry any review_status already in the agent output into the review store.

    Runs once. Without it, decisions recorded before this console existed would
    silently reappear as Pending.
    """
    if state.get("meta", {}).get("seeded"):
        return state
    for bucket, records in (("requirements", requirements), ("testcases", testcases)):
        for rec in records:
            status = rec.get("file_review", "")
            if status in STATUSES and status != "Pending":
                entry = state.setdefault(bucket, {}).setdefault(rec["uid"], {})
                entry.setdefault("status", status)
                entry.setdefault("source", "seeded from agent output")
    state.setdefault("meta", {})["seeded"] = True
    save_review(state)
    return state


def status_of(state: dict, bucket: str, key: str) -> str:
    status = state.get(bucket, {}).get(key, {}).get("status", "Pending")
    return status if status in STATUSES else "Pending"


def set_decision(bucket: str, key: str, status: str, comment: str | None = None) -> None:
    state = load_review()
    entry = state.setdefault(bucket, {}).setdefault(key, {})
    entry["status"] = status
    entry["source"] = "reviewed in console"
    if comment is not None:
        entry["comment"] = comment
    entry["decided_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_review(state)


def set_edit(bucket: str, key: str, field: str, original: str, edited: str) -> None:
    state = load_review()
    entry = state.setdefault(bucket, {}).setdefault(key, {})
    edits = entry.setdefault("edits", {})
    if edited.strip() == original.strip():
        edits.pop(field, None)
    else:
        edits[field] = edited
    entry["edited_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_review(state)


def effective(state: dict, bucket: str, key: str, field: str, original: str) -> str:
    return state.get(bucket, {}).get(key, {}).get("edits", {}).get(field, original)


def retention(original: str, edited: str) -> float:
    if not original.strip():
        return 1.0
    return difflib.SequenceMatcher(None, original.split(), edited.split()).ratio()


# =====================================================================
# DERIVED VIEWS
# =====================================================================


def build_links(testcases: list[dict], trace_payload) -> list[dict]:
    """Union of the stored matrix and the links implied by each test case.

    The matrix in this project uses {"requirement": ..., "tests": [...]}, which
    is why TRACE_TESTS_KEYS exists alongside the single-id aliases.
    """
    seen: set[tuple[str, str]] = set()
    links: list[dict] = []

    for rec in records_from(trace_payload, REQ_ID_KEYS):
        rid = as_text(pick(rec, REQ_ID_KEYS, ""))
        tests = as_list(pick(rec, TRACE_TESTS_KEYS, [])) or as_list(pick(rec, TC_ID_KEYS, []))
        for tid in tests:
            tid = as_text(tid)
            if rid or tid:
                pair = (rid, tid)
                if pair not in seen:
                    seen.add(pair)
                    links.append({"req_id": rid, "test_id": tid, "origin": "matrix"})

    for tc in testcases:
        pair = (tc["rid"], tc["tid"])
        if tc["rid"] and pair not in seen:
            seen.add(pair)
            links.append({"req_id": tc["rid"], "test_id": tc["tid"], "origin": "derived"})

    return links


def coverage_view(requirements: list[dict], testcases: list[dict], links: list[dict]) -> dict:
    req_ids = {r["rid"] for r in requirements}
    tc_ids = {t["tid"] for t in testcases}

    tests_per_req: dict[str, set[str]] = {rid: set() for rid in req_ids}
    orphans: list[dict] = []

    for link in links:
        rid, tid = link["req_id"], link["test_id"]
        if rid in tests_per_req:
            if tid:
                tests_per_req[rid].add(tid)
        elif rid:
            orphans.append({"test_id": tid, "points_to": rid,
                            "problem": "requirement ID does not exist"})

    for tc in testcases:
        if not tc["rid"]:
            orphans.append({"test_id": tc["tid"], "points_to": "—",
                            "problem": "no requirement link"})

    dangling = [{"req_id": l["req_id"], "test_id": l["test_id"],
                 "problem": "test case ID does not exist"}
                for l in links if l["test_id"] and l["test_id"] not in tc_ids]

    covered = {rid for rid, tests in tests_per_req.items() if tests}
    uncovered = sorted(req_ids - covered)
    pct = (len(covered) / len(req_ids) * 100) if req_ids else 0.0

    safety_ids = {r["rid"] for r in requirements if r["safety"]}
    safety_uncovered = sorted(safety_ids - covered)

    return {
        "tests_per_req": tests_per_req,
        "covered": covered,
        "uncovered": uncovered,
        "pct": pct,
        "orphans": orphans,
        "dangling": dangling,
        "safety_total": len(safety_ids),
        "safety_uncovered": safety_uncovered,
        "unique_reqs": len(req_ids),
    }


def integrity_view(requirements: list[dict], testcases: list[dict]) -> dict:
    """Checks the pipeline's own validator does not perform."""
    rid_counts = Counter(r["rid"] for r in requirements)
    dup_groups = {rid: [r for r in requirements if r["rid"] == rid]
                  for rid, n in rid_counts.items() if n > 1}

    tid_counts = Counter(t["tid"] for t in testcases)
    dup_tests = sorted(tid for tid, n in tid_counts.items() if n > 1)

    # ASIL spelling drift: several raw strings collapsing onto one class.
    asil_variants: dict[str, set[str]] = {}
    for r in requirements:
        asil_variants.setdefault(r["asil"], set()).add(r["asil_raw"] or "—")
    asil_drift = {k: sorted(v) for k, v in asil_variants.items() if len(v) > 1}

    # Grounding that is identical everywhere is not evidence of grounding.
    ground_sets = Counter(tuple(sorted(r["grounding"])) for r in requirements)
    uniform_grounding = (
        len(ground_sets) == 1 and len(requirements) > 1 and
        bool(next(iter(ground_sets)))
    )
    distinct_refs = {g for r in requirements for g in r["grounding"]}

    # forward_trace entries that look like test IDs but match no test case.
    tc_ids = {t["tid"] for t in testcases}
    broken_forward: list[dict] = []
    for r in requirements:
        for item in r["forward"]:
            if item.upper().startswith("TC") and item not in tc_ids:
                broken_forward.append({"requirement": r["rid"], "forward_trace": item,
                                       "problem": "no test case with this ID"})

    missing_fields = []
    for r in requirements:
        gaps = [name for name, val in (("text", r["text"]), ("rationale", r["rationale"]),
                                       ("verification_criteria", r["verification"]),
                                       ("source_section", r["source"])) if not val.strip()]
        if gaps:
            missing_fields.append({"requirement": r["rid"], "missing": ", ".join(gaps)})

    empty_steps = [t["tid"] for t in testcases if not t["steps"]]
    empty_expected = [t["tid"] for t in testcases if not t["expected"]]

    return {
        "dup_groups": dup_groups,
        "dup_tests": dup_tests,
        "asil_drift": asil_drift,
        "uniform_grounding": uniform_grounding,
        "distinct_refs": sorted(distinct_refs),
        "broken_forward": broken_forward,
        "missing_fields": missing_fields,
        "empty_steps": empty_steps,
        "empty_expected": empty_expected,
    }


def parse_validation(payload) -> tuple[list[dict], set[str], bool]:
    """Flatten a validation report into rows, whatever shape it arrived in.

    Handles this project's nested form — {"requirements": {"check", "passed",
    "duplicates"}, "traceability": {...}, "hallucination_review": {...}} — as
    well as plain lists and errors/warnings/passed buckets.
    """
    rows: list[dict] = []
    flagged: set[str] = set()

    def add(severity: str, check: str, target: str, message: str) -> None:
        rows.append({"severity": severity, "check": check,
                     "target": target, "message": message})

    def add_generic(item, default_sev=""):
        if isinstance(item, dict):
            sev = as_text(pick(item, ("severity", "level", "type", "status"),
                               default_sev or "info")).strip().lower() or "info"
            sev = {"fail": "error", "failed": "error", "critical": "error",
                   "warn": "warning", "issue": "warning", "passed": "pass",
                   "ok": "pass"}.get(sev, sev)
            add(sev,
                as_text(pick(item, ("check", "rule", "name", "id", "validator"), "")),
                as_text(pick(item, ("target", "req_id", "test_id", "element", "ref"), "")),
                as_text(pick(item, ("message", "detail", "description", "text", "msg"), "")))
        elif item not in (None, ""):
            add(default_sev or "info", "", "", as_text(item))

    if isinstance(payload, list):
        for item in payload:
            add_generic(item)
        return rows, flagged, bool(rows)

    if not isinstance(payload, dict):
        return rows, flagged, False

    understood = False

    # Bucketed form
    for key, sev in (("errors", "error"), ("failures", "error"), ("failed", "error"),
                     ("warnings", "warning"), ("issues", "warning"),
                     ("passed", "pass"), ("passes", "pass"),
                     ("findings", ""), ("checks", ""), ("results", "")):
        val = payload.get(key)
        if isinstance(val, list):
            understood = True
            for item in val:
                add_generic(item, sev)

    # Nested named-check form (this project's actual output)
    for section, body in payload.items():
        if not isinstance(body, dict):
            continue
        understood = True
        check = as_text(body.get("check", section))

        if "passed" in body:
            if body.get("passed"):
                add("pass", check, section, "Check passed")
            else:
                add("error", check, section, "Check failed")

        for field, sev, label in (("duplicates", "error", "Duplicate ID"),
                                  ("orphan_requirements", "error",
                                   "Requirement has no test case"),
                                  ("orphan_tests", "error",
                                   "Test case has no requirement"),
                                  ("missing", "error", "Missing"),
                                  ("violations", "error", "Violation")):
            for item in as_list(body.get(field)):
                add(sev, check, as_text(item), label)

        if "coverage_percent" in body:
            add("pass" if float(body.get("coverage_percent") or 0) >= 100 else "warning",
                check, section,
                f"Traceability coverage {float(body.get('coverage_percent') or 0):.1f}%")

        if "requirements" in body and isinstance(body.get("requirements"), list):
            for item in body["requirements"]:
                target = as_text(item)
                flagged.add(target)
                add("warning", check, target,
                    "Flagged by the pipeline for human review")

    return rows, flagged, understood


# =====================================================================
# CHART HELPERS
# =====================================================================


def style_fig(fig: go.Figure, height: int = 300, horizontal: bool = False) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=LABEL_2),
        margin=dict(l=4, r=18, t=6, b=4),
        height=height,
        hoverlabel=dict(bgcolor=CARD_2, bordercolor=SEP,
                        font=dict(color=LABEL, family=FONT)),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0,
                    font=dict(color=LABEL_2, size=12), bgcolor="rgba(0,0,0,0)"),
        bargap=0.34,
    )
    value_axis = dict(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False,
                      title=None, tickfont=dict(color=LABEL_3, size=12),
                      linecolor="rgba(0,0,0,0)")
    cat_axis = dict(showgrid=False, zeroline=False, title=None,
                    tickfont=dict(color=LABEL_2, size=12), linecolor="rgba(0,0,0,0)")
    if horizontal:
        fig.update_xaxes(**value_axis)
        fig.update_yaxes(**cat_axis)
    else:
        fig.update_yaxes(**value_axis)
        fig.update_xaxes(**cat_axis)
    return fig


def bar_h(labels, values, color=SEQ, suffix="", height=None) -> go.Figure:
    """Single-series horizontal bar: one measure, one hue, labelled directly."""
    fig = go.Figure(go.Bar(
        x=list(values), y=list(labels), orientation="h",
        marker=dict(color=color, line=dict(color=CARD, width=2)),
        text=[f"{v:g}{suffix}" for v in values], textposition="outside",
        textfont=dict(color=LABEL_2, size=12, family=FONT),
        hovertemplate="%{y}<br>%{x:g}" + suffix + "<extra></extra>",
        cliponaxis=False,
    ))
    rows = max(len(list(labels)), 1)
    return style_fig(fig, height=height or max(150, 32 * rows + 60), horizontal=True)


def status_bar(counts: dict[str, int], key_prefix: str = "") -> go.Figure:
    """Review funnel as one stacked bar: legend plus inline counts, never colour alone."""
    fig = go.Figure()
    for status in STATUSES:
        value = counts.get(status, 0)
        if not value:
            continue
        fig.add_bar(
            x=[value], y=["Review"], orientation="h",
            name=f"{STATUS_ICON[status]} {status}",
            marker=dict(color=STATUS_COLOR[status], line=dict(color=CARD, width=2)),
            text=[str(value)], textposition="inside", insidetextanchor="middle",
            textfont=dict(color="#FFFFFF", size=12, family=FONT),
            hovertemplate=f"{status}: %{{x}}<extra></extra>",
        )
    fig.update_layout(barmode="stack", showlegend=True)
    fig = style_fig(fig, height=138, horizontal=True)
    fig.update_xaxes(showgrid=False, showticklabels=False)
    fig.update_yaxes(showticklabels=False)
    return fig


def esc(text) -> str:
    return as_text(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pills(items, empty="none recorded") -> str:
    if not items:
        return f'<span class="ios-note">{empty}</span>'
    return "".join(f'<span class="ios-pill">{esc(i)}</span>' for i in items)


def kv(label: str, value, empty: str = "—") -> None:
    st.markdown(f'<div class="ios-kv"><b>{esc(label)}</b> &nbsp;{esc(value) or empty}</div>',
                unsafe_allow_html=True)


def badge(status: str) -> str:
    color = STATUS_COLOR.get(status, LABEL_3)
    return (f'<span class="ios-pill" style="border-color:{color};color:{color}">'
            f'{STATUS_ICON.get(status, "·")} {status}</span>')


def title_block(title: str, subtitle: str) -> None:
    st.markdown(f"# {title}")
    st.markdown(f'<div class="ios-sub">{esc(subtitle)}</div>', unsafe_allow_html=True)
    st.write("")


# =====================================================================
# LOAD
# =====================================================================

requirements, testcases, trace_payload, validation_payload, metrics, problems = (
    load_artifacts(file_signature())
)
review = seed_review(load_review(), requirements, testcases)
links = build_links(testcases, trace_payload)
cov = coverage_view(requirements, testcases, links)
integ = integrity_view(requirements, testcases)
findings, flagged_ids, findings_understood = parse_validation(validation_payload)

req_status_counts = {s: 0 for s in STATUSES}
for r in requirements:
    req_status_counts[status_of(review, "requirements", r["uid"])] += 1

tc_status_counts = {s: 0 for s in STATUSES}
for t in testcases:
    tc_status_counts[status_of(review, "testcases", t["uid"])] += 1

total_reqs = len(requirements)
total_tcs = len(testcases)
approved_reqs = req_status_counts["Approved"]
reviewed_reqs = total_reqs - req_status_counts["Pending"]
safety_reqs = sum(1 for r in requirements if r["safety"])
grounded_reqs = sum(1 for r in requirements if r["grounding"])

retentions = [retention(r["text"], effective(review, "requirements", r["uid"], "text", r["text"]))
              for r in requirements]
edited_count = sum(1 for r in requirements
                   if review.get("requirements", {}).get(r["uid"], {}).get("edits"))
mean_retention = (sum(retentions) / len(retentions) * 100) if retentions else 100.0

integrity_issues = (
    len(integ["dup_groups"]) + len(integ["dup_tests"]) + len(integ["asil_drift"])
    + len(integ["broken_forward"]) + len(integ["missing_fields"])
    + len(integ["empty_steps"]) + len(integ["empty_expected"])
    + (1 if integ["uniform_grounding"] else 0)
)

# =====================================================================
# SIDEBAR
# =====================================================================

st.sidebar.markdown(
    f'<div style="padding:4px 2px 10px 2px">'
    f'<div style="font-size:1.12rem;font-weight:650;letter-spacing:-0.02em;color:{LABEL}">'
    f'Power Window ECU</div>'
    f'<div style="font-size:0.78rem;color:{LABEL_3}">SWE.1 · SWE.6 · v{APP_VERSION}</div>'
    f"</div>",
    unsafe_allow_html=True,
)

NAV = ["Overview", "Requirements", "Test Cases", "Traceability",
       "Data Integrity", "Validation", "Speed Evidence", "Analytics", "Export"]

if st.session_state.get("nav_page") not in NAV:
    st.session_state["nav_page"] = NAV[0]

st.sidebar.markdown('<div class="ios-head">Sections</div>', unsafe_allow_html=True)

for _name in NAV:
    if st.sidebar.button(
        _name,
        key=f"nav_{_name}",
        type="primary" if st.session_state["nav_page"] == _name else "secondary",
        **WIDE,
    ):
        st.session_state["nav_page"] = _name
        st.rerun()

page = st.session_state["nav_page"]

st.sidebar.write("")

if problems:
    st.sidebar.warning(f"{len(problems)} artifact(s) unavailable")
elif integrity_issues:
    st.sidebar.info(f"{integrity_issues} data integrity finding(s)")
else:
    st.sidebar.success("All artifacts loaded")

with st.sidebar.expander("Data health"):
    st.caption(f"Reading from `{DATA_DIR}`")
    issues = dict(problems)
    for path in (REQ_FILE, TC_FILE, TRACE_FILE, VALIDATION_FILE, METRICS_FILE):
        issue = issues.get(path.name)
        st.markdown(f"{'✕' if issue else '✓'} `{path.name}`" + (f" — {issue}" if issue else ""))
    st.markdown(f"{'✓' if REVIEW_FILE.exists() else '○'} `{REVIEW_FILE.name}` — "
                f"{'present' if REVIEW_FILE.exists() else 'not created yet'}")

with st.sidebar.expander("Manual baseline"):
    st.caption("Used for the speed claim. These are your estimates — state the "
               "source in the report.")
    min_per_req = st.number_input("Minutes per requirement, by hand", 1.0, 240.0,
                                  float(review.get("meta", {}).get("min_per_req", 20.0)), step=1.0)
    min_per_tc = st.number_input("Minutes per test case, by hand", 1.0, 240.0,
                                 float(review.get("meta", {}).get("min_per_tc", 15.0)), step=1.0)
    if st.button("Save baseline", **WIDE):
        state = load_review()
        state.setdefault("meta", {}).update({"min_per_req": min_per_req,
                                             "min_per_tc": min_per_tc})
        save_review(state)
        st.rerun()

with st.sidebar.expander("Demo controls"):
    st.caption("Review state lives in its own file. Agent output is never modified.")
    if st.checkbox("I want to clear all review decisions"):
        if st.button("Reset review state", type="primary", **WIDE):
            meta = load_review().get("meta", {})
            meta.pop("seeded", None)
            save_review({"requirements": {}, "testcases": {}, "meta": meta})
            load_artifacts.clear()
            st.rerun()

    pipeline_cmd = os.getenv("SWE_PIPELINE", "")
    if pipeline_cmd:
        st.caption(f"Pipeline: `{pipeline_cmd}`")
        if st.checkbox("Enable pipeline run"):
            if st.button("Run pipeline now", **WIDE):
                with st.spinner("Running the agent pipeline…"):
                    started = time.perf_counter()
                    try:
                        proc = subprocess.run(pipeline_cmd, shell=True, capture_output=True,
                                              text=True, timeout=1800)
                        st.session_state["pipeline_log"] = (
                            f"exit {proc.returncode} in {time.perf_counter() - started:.1f}s\n\n"
                            f"{proc.stdout[-4000:]}\n{proc.stderr[-2000:]}")
                    except Exception as exc:  # noqa: BLE001
                        st.session_state["pipeline_log"] = f"{type(exc).__name__}: {exc}"
                load_artifacts.clear()
                st.rerun()
    else:
        st.caption("Set `SWE_PIPELINE` to enable an in-app pipeline run.")

if st.session_state.get("pipeline_log"):
    with st.sidebar.expander("Last pipeline run"):
        st.code(st.session_state["pipeline_log"])

# =====================================================================
# EMPTY STATE
# =====================================================================

if not requirements and not testcases:
    title_block("No work products", f"The console reads from {DATA_DIR}.")
    st.error("Nothing to review yet — `requirements.json` and `testcases.json` are "
             "both unreadable or absent.")
    st.markdown(
        "**Likely causes**\n\n"
        "- the pipeline has not been run yet;\n"
        "- it wrote somewhere else — point `SWE_DATA_DIR` at that folder;\n"
        "- Streamlit was started from a different working directory than the repo root."
    )
    for name, issue in problems:
        st.markdown(f"- `{name}` — {issue}")
    st.stop()

# =====================================================================
# OVERVIEW
# =====================================================================

if page == "Overview":
    title_block("Power Window Controller",
                "Standards-grounded agent pipeline · specification → SWE.1 requirements "
                "→ validation → SWE.6 qualification tests → traceability → engineer review")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Requirements", total_reqs)
    c2.metric("Test cases", total_tcs)
    c3.metric("Coverage", f"{cov['pct']:.0f}%")
    c4.metric("Safety-relevant", safety_reqs)
    c5.metric("Flagged for review", len(flagged_ids))

    notes = []
    if cov["unique_reqs"] != total_reqs:
        notes.append(f"{total_reqs} records but only {cov['unique_reqs']} unique IDs "
                     f"({total_reqs - cov['unique_reqs']} duplicated)")
    if total_reqs:
        notes.append(f"{safety_reqs / total_reqs * 100:.0f}% of requirements are "
                     f"safety-relevant")
    notes.append(f"coverage measured over unique requirement IDs"
                 if cov["uncovered"] == [] else
                 f"{len(cov['uncovered'])} requirement(s) uncovered")
    st.markdown(f'<div class="ios-note">{esc(" · ".join(notes))}</div>',
                unsafe_allow_html=True)

    st.write("")
    left, right = st.columns([3, 2])

    with left:
        st.markdown("### Review gate")
        st.plotly_chart(status_bar(req_status_counts), **WIDE, config=PLOT_CFG,
                        key="ov_review")
        st.progress(approved_reqs / total_reqs if total_reqs else 0.0)
        st.markdown(
            f'<div class="ios-note">{approved_reqs} of {total_reqs} requirements approved · '
            f'{reviewed_reqs} reviewed · {req_status_counts["Pending"]} pending</div>',
            unsafe_allow_html=True)

    with right:
        st.markdown("### First-draft retention")
        st.metric("Agent wording kept", f"{mean_retention:.0f}%")
        st.markdown(
            f'<div class="ios-note">{edited_count} of {total_reqs} requirements edited '
            "during review. Report this next to the speed number — it is the quality "
            "counterweight.</div>", unsafe_allow_html=True)

    st.write("")
    st.markdown("### What needs attention")

    attention = []
    if integ["dup_groups"]:
        attention.append(("error", f"{len(integ['dup_groups'])} requirement IDs are used "
                                   f"more than once", "Data Integrity"))
    if flagged_ids:
        attention.append(("warning", f"{len(flagged_ids)} requirements flagged by the "
                                     f"pipeline for human review", "Validation"))
    if integ["uniform_grounding"]:
        attention.append(("warning", "Every requirement cites exactly the same grounding "
                                     "references", "Data Integrity"))
    if cov["uncovered"]:
        attention.append(("error", f"{len(cov['uncovered'])} requirements have no test case",
                          "Traceability"))
    if cov["safety_uncovered"]:
        attention.append(("error", f"{len(cov['safety_uncovered'])} safety-relevant "
                                   f"requirements uncovered", "Traceability"))
    if integ["broken_forward"]:
        attention.append(("warning", f"{len(integ['broken_forward'])} forward_trace entries "
                                     f"name a test case that does not exist", "Data Integrity"))
    if integ["asil_drift"]:
        attention.append(("warning", "ASIL suggestions use inconsistent wording for the "
                                     "same class", "Data Integrity"))
    if req_status_counts["Pending"] == total_reqs and total_reqs:
        attention.append(("info", "No requirement has been through the review gate yet",
                          "Requirements"))

    if attention:
        rows = "".join(
            f'<div class="ios-row"><span>'
            f'<span style="color:{SEV_STYLE[sev][0]};font-weight:700">{SEV_STYLE[sev][1]}</span>'
            f'&nbsp;&nbsp;{esc(msg)}</span>'
            f'<span class="v">{esc(where)}</span></div>'
            for sev, msg, where in attention)
        st.markdown(f'<div class="ios-card">{rows}</div>', unsafe_allow_html=True)
        st.markdown('<div class="ios-note">Shown deliberately. A pipeline that reports its '
                    'own gaps is more defensible than one that looks perfect.</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="ios-card">✓ No coverage, integrity or validation issues '
                    'outstanding.</div>', unsafe_allow_html=True)

    st.write("")
    cat_counts = Counter(r["category"] for r in requirements)
    if cat_counts:
        st.markdown("### Requirements by category")
        ordered = sorted(cat_counts.items(), key=lambda kv_: kv_[1])
        st.plotly_chart(bar_h([k for k, _ in ordered], [v for _, v in ordered]),
                        **WIDE, config=PLOT_CFG, key="ov_cat")

# =====================================================================
# REQUIREMENTS
# =====================================================================

elif page == "Requirements":
    title_block("Requirements", "SWE.1 — the agent proposes, the engineer decides. "
                                "Edits are stored apart from the agent output.")

    rows = [{
        "ID": r["rid"],
        "Requirement": (r["text"][:95] + "…") if len(r["text"]) > 95 else r["text"],
        "Category": r["category"],
        "Safety": "yes" if r["safety"] else "",
        "ASIL": r["asil"],
        "Tests": len(cov["tests_per_req"].get(r["rid"], set())),
        "Section": r["source"],
        "Review": f'{STATUS_ICON[status_of(review, "requirements", r["uid"])]} '
                  f'{status_of(review, "requirements", r["uid"])}',
    } for r in requirements]
    st.dataframe(pd.DataFrame(rows), **WIDE, hide_index=True, height=290)

    st.write("")
    f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
    search = f1.text_input("Search", placeholder="text, ID, section…")
    cat_filter = f2.selectbox("Category", ["All"] + sorted({r["category"] for r in requirements}))
    status_filter = f3.selectbox("Review", ["All"] + STATUSES)
    lens = f4.selectbox("Lens", ["All", "Safety-relevant", "Flagged for review",
                                 "Duplicate IDs", "Edited"])

    shown = []
    for r in requirements:
        status = status_of(review, "requirements", r["uid"])
        if search and search.lower() not in json.dumps(r["raw"], ensure_ascii=False).lower():
            continue
        if cat_filter != "All" and r["category"] != cat_filter:
            continue
        if status_filter != "All" and status != status_filter:
            continue
        if lens == "Safety-relevant" and not r["safety"]:
            continue
        if lens == "Flagged for review" and r["rid"] not in flagged_ids:
            continue
        if lens == "Duplicate IDs" and r["rid"] not in integ["dup_groups"]:
            continue
        if lens == "Edited" and not review.get("requirements", {}).get(r["uid"], {}).get("edits"):
            continue
        shown.append(r)

    per_page = 20
    pages = max((len(shown) + per_page - 1) // per_page, 1)
    nav1, nav2 = st.columns([1, 3])
    page_no = nav1.number_input("Page", 1, pages, 1, step=1, key="req_page")
    nav2.markdown(f'<div class="ios-note" style="padding-top:34px">'
                  f'{len(shown)} of {total_reqs} requirements · page {int(page_no)} of {pages}'
                  f"</div>", unsafe_allow_html=True)
    window = shown[(int(page_no) - 1) * per_page: int(page_no) * per_page]

    for r in window:
        uid = r["uid"]
        status = status_of(review, "requirements", uid)
        entry = review.get("requirements", {}).get(uid, {})
        marks = []
        if r["safety"]:
            marks.append("safety")
        if r["rid"] in flagged_ids:
            marks.append("flagged")
        if r["rid"] in integ["dup_groups"]:
            marks.append("duplicate ID")
        if entry.get("edits"):
            marks.append("edited")
        head = f'{STATUS_ICON[status]}  {r["rid"]}  ·  {r["category"]}'
        if marks:
            head += f'   —   {" · ".join(marks)}'

        with st.expander(head):
            st.markdown(badge(status) +
                        (f'<span class="ios-pill">{esc(r["source"])}</span>' if r["source"] else ""),
                        unsafe_allow_html=True)

            if r["rid"] in integ["dup_groups"]:
                others = [x["source"] or "—" for x in integ["dup_groups"][r["rid"]]]
                st.warning(f"This ID is used by {len(others)} requirements "
                           f"(sections: {', '.join(others)}). Review each separately — "
                           f"they are tracked under distinct keys here.")

            if r["rid"] in flagged_ids:
                st.warning("The pipeline flagged this requirement for human review — "
                           "verify it against the source specification.")

            current = effective(review, "requirements", uid, "text", r["text"])
            edited_text = st.text_area("Requirement text", current, height=120, key=f"rt_{uid}")

            if entry.get("edits", {}).get("text"):
                st.caption(f"Edited · {retention(r['text'], current) * 100:.0f}% of the "
                           f"agent's wording retained")
                with st.popover("Show agent's original"):
                    st.write(r["text"] or "—")

            if r["excerpt"]:
                st.markdown(f'<div class="ios-kv"><b>Source excerpt — backward trace</b></div>'
                            f'<div class="ios-quote">“{esc(r["excerpt"])}”</div>',
                            unsafe_allow_html=True)

            ca, cb = st.columns(2)
            with ca:
                kv("Rationale", r["rationale"])
                kv("Source section", r["source"])
                kv("Verification criteria", r["verification"])
            with cb:
                kv("Safety relevant", "yes" if r["safety"] else "no")
                kv("ASIL — agent suggestion", r["asil_raw"], empty="not proposed")
                st.markdown('<div class="ios-note">The agent proposes a classification. '
                            'ASIL assignment stays an engineering decision.</div>',
                            unsafe_allow_html=True)
                st.markdown(f'<div class="ios-kv"><b>Standards grounding</b></div>'
                            f'{pills(r["grounding"])}', unsafe_allow_html=True)

            linked = sorted(cov["tests_per_req"].get(r["rid"], set()))
            st.markdown(f'<div class="ios-kv"><b>Forward trace — {len(linked)} test case(s)'
                        f'</b></div>{pills(linked, "no test case covers this requirement")}',
                        unsafe_allow_html=True)

            comment = st.text_input("Reviewer comment", entry.get("comment", ""),
                                    key=f"rc_{uid}",
                                    placeholder="why rejected, what needs clarifying…")

            b1, b2, b3, b4 = st.columns(4)
            if b1.button("Save edit", key=f"rs_{uid}", **WIDE):
                set_edit("requirements", uid, "text", r["text"], edited_text)
                st.rerun()
            if b2.button("Approve", key=f"ra_{uid}", **WIDE):
                set_edit("requirements", uid, "text", r["text"], edited_text)
                set_decision("requirements", uid, "Approved", comment)
                st.rerun()
            if b3.button("Clarify", key=f"rq_{uid}", **WIDE):
                set_decision("requirements", uid, "Needs Clarification", comment)
                st.rerun()
            if b4.button("Reject", key=f"rj_{uid}", **WIDE):
                set_decision("requirements", uid, "Rejected", comment)
                st.rerun()

# =====================================================================
# TEST CASES
# =====================================================================

elif page == "Test Cases":
    title_block("Test Cases", "SWE.6 — each qualification test traces forward from "
                              "exactly one requirement.")

    req_by_id: dict[str, dict] = {}
    for r in requirements:
        req_by_id.setdefault(r["rid"], r)

    rows = [{
        "TC ID": t["tid"],
        "Requirement": t["rid"] or "— unlinked —",
        "Title": t["title"] or t["objective"][:70],
        "Environment": t["env"],
        "Steps": len(t["steps"]),
        "Expected": len(t["expected"]),
        "Review": f'{STATUS_ICON[status_of(review, "testcases", t["uid"])]} '
                  f'{status_of(review, "testcases", t["uid"])}',
    } for t in testcases]
    st.dataframe(pd.DataFrame(rows), **WIDE, hide_index=True, height=290)

    st.write("")
    g1, g2, g3 = st.columns([3, 2, 2])
    tc_search = g1.text_input("Search", placeholder="title, step text, environment…")
    env_filter = g2.selectbox("Environment", ["All"] + sorted({t["env"] for t in testcases}))
    tc_status_filter = g3.selectbox("Review", ["All"] + STATUSES)

    shown_tcs = []
    for t in testcases:
        status = status_of(review, "testcases", t["uid"])
        if tc_search and tc_search.lower() not in json.dumps(t["raw"], ensure_ascii=False).lower():
            continue
        if env_filter != "All" and t["env"] != env_filter:
            continue
        if tc_status_filter != "All" and status != tc_status_filter:
            continue
        shown_tcs.append(t)

    per_page = 20
    pages = max((len(shown_tcs) + per_page - 1) // per_page, 1)
    n1, n2 = st.columns([1, 3])
    tc_page = n1.number_input("Page", 1, pages, 1, step=1, key="tc_page")
    n2.markdown(f'<div class="ios-note" style="padding-top:34px">{len(shown_tcs)} of '
                f'{total_tcs} test cases · page {int(tc_page)} of {pages}</div>',
                unsafe_allow_html=True)

    for t in shown_tcs[(int(tc_page) - 1) * per_page: int(tc_page) * per_page]:
        uid = t["uid"]
        status = status_of(review, "testcases", uid)
        parent = req_by_id.get(t["rid"])
        head = f'{STATUS_ICON[status]}  {t["tid"]}'
        if not parent:
            head += "   —   orphan"

        with st.expander(head):
            st.markdown(badge(status) + f'<span class="ios-pill">{esc(t["env"])}</span>',
                        unsafe_allow_html=True)
            st.markdown(f"**{esc(t['title'])}**" if t["title"] else "")

            if parent:
                kv("Covers", f'{parent["rid"]} — {parent["text"][:170]}')
            else:
                st.warning("This test case does not resolve to a known requirement ID.")
                kv("Declared requirement", t["rid"], empty="none")

            kv("Objective", t["objective"])
            if t["technique"]:
                kv("Technique", t["technique"])
            kv("Preconditions", t["preconditions"])

            st.markdown('<div class="ios-kv"><b>Test steps</b></div>', unsafe_allow_html=True)
            if t["steps"]:
                for n, step in enumerate(t["steps"], 1):
                    st.markdown(f"{n}. {step}")
            else:
                st.markdown('<div class="ios-note">no steps recorded</div>',
                            unsafe_allow_html=True)

            st.markdown('<div class="ios-kv"><b>Expected results</b></div>',
                        unsafe_allow_html=True)
            if t["expected"]:
                for item in t["expected"]:
                    st.markdown(f"- {item}")
            else:
                st.markdown('<div class="ios-note">no expected result recorded</div>',
                            unsafe_allow_html=True)

            st.markdown(f'<div class="ios-kv"><b>Standards grounding</b></div>'
                        f'{pills(t["grounding"])}', unsafe_allow_html=True)

            tc_comment = st.text_input("Reviewer comment",
                                       review.get("testcases", {}).get(uid, {}).get("comment", ""),
                                       key=f"tc_{uid}")
            d1, d2, d3 = st.columns(3)
            if d1.button("Approve", key=f"ta_{uid}", **WIDE):
                set_decision("testcases", uid, "Approved", tc_comment)
                st.rerun()
            if d2.button("Clarify", key=f"tq_{uid}", **WIDE):
                set_decision("testcases", uid, "Needs Clarification", tc_comment)
                st.rerun()
            if d3.button("Reject", key=f"tj_{uid}", **WIDE):
                set_decision("testcases", uid, "Rejected", tc_comment)
                st.rerun()

# =====================================================================
# TRACEABILITY
# =====================================================================

elif page == "Traceability":
    title_block("Traceability", "Backward: every requirement names its source section. "
                                "Forward: every requirement should be covered by a test.")

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Trace links", len(links))
    t2.metric("Coverage", f"{cov['pct']:.0f}%")
    t3.metric("Uncovered", len(cov["uncovered"]))
    t4.metric("Safety gaps", len(cov["safety_uncovered"]))

    if cov["unique_reqs"] != total_reqs:
        st.info(f"Coverage is measured over **{cov['unique_reqs']} unique requirement IDs**, "
                f"not the {total_reqs} records in the file. {total_reqs - cov['unique_reqs']} "
                f"records share an ID with another — see Data Integrity. A reviewer will ask "
                f"about this, so say it before they do.")

    st.write("")
    if cov["safety_uncovered"]:
        st.markdown("### Safety-relevant requirements without a test case")
        st.dataframe(pd.DataFrame([
            {"Requirement": rid,
             "Text": next((r["text"] for r in requirements if r["rid"] == rid), "")}
            for rid in cov["safety_uncovered"]]), **WIDE, hide_index=True)
        st.write("")

    cu, co = st.columns(2)
    with cu:
        st.markdown("### Uncovered requirements")
        if cov["uncovered"]:
            st.dataframe(pd.DataFrame([
                {"Requirement": rid,
                 "Safety": "yes" if any(r["rid"] == rid and r["safety"] for r in requirements) else "",
                 "Text": next((r["text"][:120] for r in requirements if r["rid"] == rid), "")}
                for rid in cov["uncovered"]]), **WIDE, hide_index=True, height=250)
        else:
            st.markdown('<div class="ios-card">✓ Every requirement ID is covered by at '
                        'least one test case.</div>', unsafe_allow_html=True)

    with co:
        st.markdown("### Trace integrity")
        broken = cov["orphans"] + cov["dangling"]
        if broken:
            st.dataframe(pd.DataFrame(broken), **WIDE, hide_index=True, height=250)
        else:
            st.markdown('<div class="ios-card">✓ No orphan test cases and no dangling '
                        'trace links.</div>', unsafe_allow_html=True)

    st.write("")
    dist = Counter(len(tests) for tests in cov["tests_per_req"].values())
    if dist:
        st.markdown("### Test cases per requirement")
        keys = sorted(dist)
        st.plotly_chart(
            bar_h([f"{k} test{'s' if k != 1 else ''}" for k in keys], [dist[k] for k in keys]),
            **WIDE, config=PLOT_CFG, key="tr_dist")
        if dist.get(1, 0) > sum(dist.values()) * 0.7:
            st.markdown('<div class="ios-note">Most requirements have exactly one test case. '
                        'That is worth naming as a limitation: one test per requirement '
                        'usually means the happy path only, not boundaries and error '
                        'paths.</div>', unsafe_allow_html=True)

    st.write("")
    st.markdown("### Traceability matrix")
    matrix_df = pd.DataFrame([{
        "Requirement": rid,
        "Safety": "yes" if any(r["rid"] == rid and r["safety"] for r in requirements) else "",
        "Source section": next((r["source"] for r in requirements if r["rid"] == rid), ""),
        "Test cases": ", ".join(sorted(tests)) if tests else "— none —",
        "Count": len(tests),
    } for rid, tests in sorted(cov["tests_per_req"].items())])
    st.dataframe(matrix_df, **WIDE, hide_index=True, height=360)
    st.download_button("Download matrix (CSV)",
                       matrix_df.to_csv(index=False).encode("utf-8"),
                       "traceability_matrix.csv", "text/csv")

# =====================================================================
# DATA INTEGRITY
# =====================================================================

elif page == "Data Integrity":
    title_block("Data Integrity",
                "Checks run by this console over the agent output, beyond what the "
                "pipeline's own validators report.")

    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Duplicate req IDs", len(integ["dup_groups"]))
    i2.metric("Broken forward refs", len(integ["broken_forward"]))
    i3.metric("Incomplete records", len(integ["missing_fields"]))
    i4.metric("Distinct grounding refs", len(integ["distinct_refs"]))

    st.write("")

    if integ["dup_groups"]:
        st.markdown("### Requirement IDs used more than once")
        st.markdown('<div class="ios-note">Each record is tracked under its own key here, '
                    'so reviews do not collide — but the IDs must be made unique before the '
                    'work products are credible. Two requirements with the same ID cannot '
                    'both be traced.</div>', unsafe_allow_html=True)
        dup_rows = []
        for rid, group in sorted(integ["dup_groups"].items()):
            for rec in group:
                dup_rows.append({"ID": rid, "Section": rec["source"],
                                 "Category": rec["category"],
                                 "Text": rec["text"][:110]})
        st.dataframe(pd.DataFrame(dup_rows), **WIDE, hide_index=True, height=300)
        st.write("")

    if integ["uniform_grounding"]:
        st.markdown("### Grounding references are identical across every requirement")
        st.markdown(
            f'<div class="ios-card">All {total_reqs} requirements cite exactly the same set: '
            f'{", ".join(integ["distinct_refs"])}.<br><br>'
            'Grounding that never varies is not evidence that any individual requirement '
            'was grounded — it looks like the whole retrieved context being stapled to every '
            'output. Expect to be asked about this. The strongest fix is to record, per '
            'requirement, which retrieved chunk actually supported it.</div>',
            unsafe_allow_html=True)
        st.write("")

    if integ["asil_drift"]:
        st.markdown("### ASIL suggestions worded inconsistently")
        st.dataframe(pd.DataFrame([{"Normalised class": k, "Raw values in the file": ", ".join(v)}
                                   for k, v in integ["asil_drift"].items()]),
                     **WIDE, hide_index=True)
        st.markdown('<div class="ios-note">The console groups these for charting. The '
                    'generator should emit one canonical spelling.</div>',
                    unsafe_allow_html=True)
        st.write("")

    if integ["broken_forward"]:
        st.markdown("### forward_trace entries that name a non-existent test case")
        st.dataframe(pd.DataFrame(integ["broken_forward"]), **WIDE, hide_index=True, height=200)
        st.markdown('<div class="ios-note">The requirement-side forward_trace and the actual '
                    'test case IDs were generated independently and do not agree. The '
                    'traceability matrix is the reliable link; forward_trace is not.</div>',
                    unsafe_allow_html=True)
        st.write("")

    if integ["dup_tests"]:
        st.markdown("### Duplicate test case IDs")
        st.dataframe(pd.DataFrame({"Test case ID": integ["dup_tests"]}), **WIDE, hide_index=True)
        st.write("")

    if integ["missing_fields"]:
        st.markdown("### Requirements with empty mandatory fields")
        st.dataframe(pd.DataFrame(integ["missing_fields"]), **WIDE, hide_index=True, height=220)
        st.write("")

    if integ["empty_steps"] or integ["empty_expected"]:
        st.markdown("### Test cases missing steps or expected results")
        st.dataframe(pd.DataFrame({
            "Problem": (["no test steps"] * len(integ["empty_steps"]) +
                        ["no expected result"] * len(integ["empty_expected"])),
            "Test case": integ["empty_steps"] + integ["empty_expected"],
        }), **WIDE, hide_index=True, height=200)
        st.write("")

    if not integrity_issues:
        st.markdown('<div class="ios-card">✓ No duplicate IDs, no broken forward references, '
                    'no incomplete records, and grounding references vary across '
                    'requirements.</div>', unsafe_allow_html=True)

# =====================================================================
# VALIDATION
# =====================================================================

elif page == "Validation":
    title_block("Validation", "Schema, uniqueness, traceability and review checks "
                              "reported by the pipeline's own validators.")

    if validation_payload is None:
        st.warning("No validation report was produced. The validators are a core guardrail "
                   "of this project, so an absent report is itself a finding.")
    elif not findings_understood:
        st.info("A validation report exists but its structure was not recognised, so it is "
                "shown raw rather than summarised incorrectly.")
        st.json(validation_payload)
    else:
        buckets = Counter(r["severity"] if r["severity"] in SEV_STYLE else "info"
                          for r in findings)
        order = [b for b in ("error", "warning", "info", "pass") if buckets.get(b)]
        cols = st.columns(max(len(order), 1))
        for col, bucket in zip(cols, order):
            color, icon, name = SEV_STYLE[bucket]
            col.metric(f"{icon} {name}", buckets[bucket])

        if buckets.get("error"):
            st.markdown(f'<div class="ios-card" style="border-color:{SEV_STYLE["error"][0]}">'
                        f'<b style="color:{SEV_STYLE["error"][0]}">✕ {buckets["error"]} '
                        f'finding(s) would block release.</b></div>', unsafe_allow_html=True)
        elif buckets.get("warning"):
            st.markdown(f'<div class="ios-card" style="border-color:{SEV_STYLE["warning"][0]}">'
                        f'<b style="color:{SEV_STYLE["warning"][0]}">! {buckets["warning"]} '
                        f'warning(s), no blocking errors.</b></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="ios-card">✓ No errors or warnings reported.</div>',
                        unsafe_allow_html=True)

        st.write("")
        severities = sorted({r["severity"] for r in findings})
        chosen = st.multiselect("Severity", severities,
                                default=[s for s in severities if s != "pass"])
        table = [r for r in findings if not chosen or r["severity"] in chosen]
        st.dataframe(
            pd.DataFrame(table).rename(columns={"severity": "Severity", "check": "Check",
                                                "target": "Target", "message": "Finding"}),
            **WIDE, hide_index=True, height=min(430, 36 * max(len(table), 1) + 44))

        if flagged_ids:
            st.markdown("### Flagged for human review")
            st.markdown('<div class="ios-note">The pipeline marked these requirements as '
                        'needing verification against the source specification. Open them '
                        'with the "Flagged for review" lens on the Requirements page.</div>',
                        unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([
                {"Requirement": rid,
                 "Text": next((r["text"] for r in requirements if r["rid"] == rid), ""),
                 "Section": next((r["source"] for r in requirements if r["rid"] == rid), "")}
                for rid in sorted(flagged_ids)]), **WIDE, hide_index=True)

        with st.expander("Raw validation report"):
            st.json(validation_payload)

# =====================================================================
# SPEED EVIDENCE
# =====================================================================

elif page == "Speed Evidence":
    title_block("Speed Evidence", "The project's primary claim: agents produce first-draft "
                                  "work products substantially faster than manual authoring.")

    TOTAL_KEYS = ("total_seconds", "elapsed_seconds", "generation_seconds",
                  "runtime_seconds", "duration_seconds", "pipeline_seconds",
                  "total_time_s", "wall_clock_seconds")
    raw_total = pick(metrics, TOTAL_KEYS)
    try:
        agent_seconds = float(raw_total) if raw_total is not None else None
    except (TypeError, ValueError):
        agent_seconds = None

    stage_raw = pick(metrics, ("stage_timings", "timings", "stages", "durations"), {})
    stages: dict[str, float] = {}
    if isinstance(stage_raw, dict):
        for name, val in stage_raw.items():
            try:
                stages[str(name)] = float(val)
            except (TypeError, ValueError):
                continue
    elif isinstance(stage_raw, list):
        for item in stage_raw:
            if isinstance(item, dict):
                try:
                    stages[as_text(pick(item, ("stage", "name", "step"), ""))] = float(
                        pick(item, ("seconds", "duration", "elapsed", "time"), 0))
                except (TypeError, ValueError):
                    continue

    if agent_seconds is None and stages:
        agent_seconds = sum(stages.values())

    measured = agent_seconds is not None
    if not measured:
        st.warning("`metrics.json` carries no pipeline timing, so the headline number below "
                   "is whatever you type in. **Add timing instrumentation before the "
                   "report** — a claimed speed-up with no measured denominator is the "
                   "weakest point in this project.")
        agent_seconds = st.number_input("Measured pipeline wall-clock (seconds)",
                                        1.0, 100000.0, 600.0, step=30.0)

    min_req = float(review.get("meta", {}).get("min_per_req", 20.0))
    min_tc = float(review.get("meta", {}).get("min_per_tc", 15.0))
    manual_minutes = total_reqs * min_req + total_tcs * min_tc
    agent_minutes = agent_seconds / 60.0
    speedup = (manual_minutes / agent_minutes) if agent_minutes > 0 else 0.0

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Agent wall-clock", f"{agent_minutes:.1f} min",
              help="From metrics.json" if measured else "Entered manually — not measured")
    s2.metric("Manual estimate", f"{manual_minutes / 60:.1f} h")
    s3.metric("Speed-up", f"{speedup:.0f}×")
    s4.metric("Effort avoided", f"{max(manual_minutes - agent_minutes, 0) / 60:.1f} h")

    st.write("")
    st.markdown("### Manual authoring vs agent pipeline")
    label_agent = "Agent pipeline (measured)" if measured else "Agent pipeline (entered, not measured)"
    fig = go.Figure(go.Bar(
        x=[manual_minutes, agent_minutes],
        y=["Manual authoring (estimated)", label_agent],
        orientation="h",
        marker=dict(color=[SERIES[1], SERIES[0]], line=dict(color=CARD, width=2)),
        text=[f"{manual_minutes:.0f} min", f"{agent_minutes:.1f} min"],
        textposition="outside", textfont=dict(color=LABEL_2, size=13, family=FONT),
        hovertemplate="%{y}<br>%{x:.1f} minutes<extra></extra>", cliponaxis=False,
    ))
    st.plotly_chart(style_fig(fig, height=190, horizontal=True), **WIDE,
                    config=PLOT_CFG, key="sp_cmp")
    st.markdown(f'<div class="ios-note">Both bars are minutes on one axis. Manual estimate = '
                f'{total_reqs} requirements × {min_req:g} min + {total_tcs} test cases × '
                f'{min_tc:g} min. Adjust the baseline in the sidebar.</div>',
                unsafe_allow_html=True)

    if stages:
        st.write("")
        st.markdown("### Where the pipeline spends its time")
        ordered = sorted(stages.items(), key=lambda kv_: kv_[1])
        st.plotly_chart(bar_h([k for k, _ in ordered], [round(v, 1) for _, v in ordered],
                              suffix=" s"), **WIDE, config=PLOT_CFG, key="sp_stages")

    st.write("")
    st.markdown("### Caveats to state out loud")
    st.markdown(f"""
- The agent figure covers **first-draft generation only**. Human review is real cost:
  {reviewed_reqs} of {total_reqs} requirements have been through the gate so far.
- First-draft retention is **{mean_retention:.0f}%**, so the drafts are not free of rework.
  Report speed and retention together, never speed alone.
- The manual baseline is self-estimated. The strongest version of this claim is a timed
  manual authoring run over a subset of the same specification.
- {len(integ['dup_groups'])} duplicate requirement IDs mean the raw count of
  {total_reqs} overstates distinct output by {total_reqs - cov['unique_reqs']}.
""")

    other = {k: v for k, v in metrics.items()
             if k not in TOTAL_KEYS and k not in ("stage_timings", "timings", "stages")}
    if other:
        with st.expander("All metrics recorded by the pipeline"):
            st.json(other)

# =====================================================================
# ANALYTICS
# =====================================================================

elif page == "Analytics":
    title_block("Analytics", "Distribution of the generated work products.")

    a1, a2 = st.columns(2)

    with a1:
        st.markdown("### Requirements by category")
        counts = Counter(r["category"] for r in requirements)
        ordered = sorted(counts.items(), key=lambda kv_: kv_[1])
        st.plotly_chart(bar_h([k for k, _ in ordered], [v for _, v in ordered]),
                        **WIDE, config=PLOT_CFG, key="an_cat")

        st.markdown("### ASIL suggestions")
        asil_counts = Counter(r["asil"] for r in requirements)
        ordered = sorted(asil_counts.items(), key=lambda kv_: kv_[1])
        st.plotly_chart(bar_h([k for k, _ in ordered], [v for _, v in ordered],
                              color=SERIES[2]), **WIDE, config=PLOT_CFG, key="an_asil")
        st.markdown('<div class="ios-note">Proposed by the agent, never assigned. '
                    'Spelling variants are collapsed — see Data Integrity.</div>',
                    unsafe_allow_html=True)

    with a2:
        st.markdown("### Test cases by environment")
        env_counts = Counter(t["env"] for t in testcases)
        ordered = sorted(env_counts.items(), key=lambda kv_: kv_[1])
        st.plotly_chart(bar_h([k for k, _ in ordered], [v for _, v in ordered],
                              color=SERIES[1]), **WIDE, config=PLOT_CFG, key="an_env")

        st.markdown("### Requirements by source section")
        sec_counts = Counter(r["source"] or "—" for r in requirements)
        top = sec_counts.most_common(10)
        if len(sec_counts) > 10:
            top.append(("Other", sum(v for _, v in sec_counts.most_common()[10:])))
        ordered = sorted(top, key=lambda kv_: kv_[1])
        st.plotly_chart(bar_h([k for k, _ in ordered], [v for _, v in ordered]),
                        **WIDE, config=PLOT_CFG, key="an_sec")

    st.write("")
    st.markdown("### Review progress")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown('<div class="ios-note">Requirements</div>', unsafe_allow_html=True)
        st.plotly_chart(status_bar(req_status_counts), **WIDE, config=PLOT_CFG, key="an_rr")
    with r2:
        st.markdown('<div class="ios-note">Test cases</div>', unsafe_allow_html=True)
        st.plotly_chart(status_bar(tc_status_counts), **WIDE, config=PLOT_CFG, key="an_rt")

    st.write("")
    st.markdown("### Guardrail summary")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Coverage", f"{cov['pct']:.0f}%")
    g2.metric("Safety-relevant", f"{(safety_reqs / total_reqs * 100) if total_reqs else 0:.0f}%")
    g3.metric("First-draft retention", f"{mean_retention:.0f}%")
    g4.metric("Integrity findings", integrity_issues)
    st.markdown('<div class="ios-note">These are the guardrails proving the speed-up was '
                'not bought with bad output. Present them beside the speed number, not on '
                'a separate slide.</div>', unsafe_allow_html=True)

# =====================================================================
# EXPORT
# =====================================================================

elif page == "Export":
    title_block("Export", "Work products carrying the reviewed text, the agent's original, "
                          "and the review decision.")

    req_export = pd.DataFrame([{
        "req_id": r["rid"],
        "unique_key": r["uid"],
        "text": effective(review, "requirements", r["uid"], "text", r["text"]),
        "agent_original_text": r["text"],
        "rationale": r["rationale"],
        "category": r["category"],
        "source_section": r["source"],
        "source_excerpt": r["excerpt"],
        "safety_relevant": r["safety"],
        "asil_suggestion": r["asil_raw"],
        "asil_class": r["asil"],
        "verification_criteria": r["verification"],
        "grounding_refs": "; ".join(r["grounding"]),
        "test_cases": ", ".join(sorted(cov["tests_per_req"].get(r["rid"], set()))),
        "flagged_for_review": r["rid"] in flagged_ids,
        "duplicate_id": r["rid"] in integ["dup_groups"],
        "review_status": status_of(review, "requirements", r["uid"]),
        "reviewer_comment": review.get("requirements", {}).get(r["uid"], {}).get("comment", ""),
    } for r in requirements])

    tc_export = pd.DataFrame([{
        "tc_id": t["tid"],
        "req_id": t["rid"],
        "title": t["title"],
        "objective": t["objective"],
        "test_environment": t["env"],
        "preconditions": t["preconditions"],
        "test_steps": " | ".join(t["steps"]),
        "expected_results": " | ".join(t["expected"]),
        "grounding_refs": "; ".join(t["grounding"]),
        "review_status": status_of(review, "testcases", t["uid"]),
        "reviewer_comment": review.get("testcases", {}).get(t["uid"], {}).get("comment", ""),
    } for t in testcases])

    trace_export = (pd.DataFrame(links) if links
                    else pd.DataFrame(columns=["req_id", "test_id", "origin"]))
    findings_export = (pd.DataFrame(findings) if findings
                       else pd.DataFrame(columns=["severity", "check", "target", "message"]))

    tables = {"Requirements": req_export, "Test cases": tc_export,
              "Trace links": trace_export, "Validation": findings_export}

    choice = st.selectbox("Dataset", list(tables))
    st.dataframe(tables[choice], **WIDE, hide_index=True, height=420)

    st.write("")
    e1, e2, e3 = st.columns(3)

    e1.download_button(f"{choice} (CSV)",
                       tables[choice].to_csv(index=False).encode("utf-8"),
                       f"{choice.lower().replace(' ', '_')}.csv", "text/csv", **WIDE)

    try:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for name, frame in tables.items():
                frame.to_excel(writer, sheet_name=name[:31], index=False)
        e2.download_button("All work products (Excel)", buffer.getvalue(),
                           "swe_work_products.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           **WIDE)
    except Exception:  # noqa: BLE001 — openpyxl may not be installed
        e2.caption("Excel export needs `openpyxl`")

    lines = [
        "# SWE.1 / SWE.6 work products — Power Window Controller",
        "",
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · {total_reqs} requirements "
        f"({cov['unique_reqs']} unique IDs) · {total_tcs} test cases · "
        f"{cov['pct']:.0f}% coverage · {approved_reqs} approved · "
        f"{mean_retention:.0f}% first-draft retention",
        "",
    ]
    for r in requirements:
        status = status_of(review, "requirements", r["uid"])
        lines += [
            f"## {r['rid']} — {status}",
            "",
            effective(review, "requirements", r["uid"], "text", r["text"]),
            "",
            f"- Section: {r['source'] or '—'} · Category: {r['category']}",
            f"- Safety relevant: {'yes' if r['safety'] else 'no'}"
            + (f" · ASIL suggested: {r['asil_raw']}" if r["asil_raw"] else ""),
            f"- Verification: {r['verification'] or '—'}",
            f"- Grounding: {', '.join(r['grounding']) or '—'}",
            "",
        ]
        for tid in sorted(cov["tests_per_req"].get(r["rid"], set())):
            tc = next((t for t in testcases if t["tid"] == tid), None)
            if tc:
                lines += [f"  - **{tc['tid']}** ({tc['env']}) {tc['title'] or tc['objective'][:80]}", ""]

    e3.download_button("Report extract (Markdown)", "\n".join(lines).encode("utf-8"),
                       "swe_work_products.md", "text/markdown", **WIDE)
