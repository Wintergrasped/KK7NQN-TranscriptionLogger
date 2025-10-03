#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Topic Extractor for Operator Profiles (grounded by local callsign data)

State tracking:
  - transcriptions.analyzed: 0 = not analyzed, 1 = analyzed complete

Grounding (allowed callsigns):
  1) smoothed_transcripts.callsigns_json (trusted)
  2) callsign_log rows already linked by transcript_id (trusted)
  3) (optional) time-window scan if ENABLE_TIME_WINDOW_FALLBACK=1 (off by default)
  + regex hits from corrected transcript (supplement)

Writes:
  - callsign_topic_events (append-only facts)
  - extended_callsign_profile (aggregated rollup via upsert)
"""

import os
import re
import json
from datetime import datetime, timedelta

import pymysql
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------- ENV HELP ----------
def env(key, default=None):
    v = os.getenv(key, default)
    return v.strip() if isinstance(v, str) else v

# ---------- CONFIG ----------
DB_HOST = "127.0.0.1"
DB_USER = "DB_USER"
DB_PASS = "DB_PASS"
DB_NAME = "DB_NAME"
DB_PORT = int(env("DB_PORT", "3306"))

OPENAI_BASE_URL = env("OPENAI_BASE_URL", "http://192.168.0.104:8001/v1")
OPENAI_MODEL    = env("OPENAI_MODEL", "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4")
OPENAI_API_KEY  = env("OPENAI_API_KEY", "sk-no-auth-needed-for-local")
OPENAI_TIMEOUT  = float(env("OPENAI_TIMEOUT", "120"))

MAX_TARGETS_PER_RUN = int(env("MAX_TARGETS_PER_RUN", "2500"))
MAX_CHARS_IN        = int(env("MAX_CHARS_IN", "24000"))   # ~14k tokens-ish

# Time-window fallback is OFF by default (callsign_log.timestamp unreliable per your note)
ENABLE_TIME_WINDOW_FALLBACK = int(env("ENABLE_TIME_WINDOW_FALLBACK", "0"))
FALLBACK_TIME_WINDOW_SEC    = int(env("FALLBACK_TIME_WINDOW_SEC", "120"))

# ---------- REGEX ----------
# Core ham callsign: 1-2 letters + digit + 1-4 letters (strip suffixes separately)
CORE_CALLSIGN_RE   = re.compile(r"\b([A-Z]{1,2}\d[A-Z]{1,4})\b", re.IGNORECASE)
SUFFIXES_TRAIL_RE  = re.compile(r"/[A-Z0-9]{1,6}$")  # /P, /M, /QRP, /POTA, /SOTA, etc.
SSID_TRAIL_RE      = re.compile(r"-\d+$")            # -1, -2, etc.

def normalize_callsign(s: str):
    """Return clean uppercase callsign or None if not valid."""
    if not s:
        return None
    s = str(s).upper().strip()
    s = SUFFIXES_TRAIL_RE.sub("", s)
    s = SSID_TRAIL_RE.sub("", s)
    m = CORE_CALLSIGN_RE.search(s)
    if not m:
        return None
    cs = m.group(1).upper()
    return cs if len(cs) <= 20 else None

def extract_callsigns_regex(text: str) -> set[str]:
    out = set()
    if not text:
        return out
    for m in CORE_CALLSIGN_RE.finditer(text):
        cs = normalize_callsign(m.group(0))
        if cs:
            out.add(cs)
    return out

# ---------- HTTP (resilient session) ----------
_session = requests.Session()
_retry = Retry(
    total=4, connect=4, read=4, backoff_factor=0.8,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=["POST"]
)
_session.headers.update({"Connection": "keep-alive"})
_session.mount("http://", HTTPAdapter(max_retries=_retry))
_session.mount("https://", HTTPAdapter(max_retries=_retry))

# ---------- DB ----------
def db():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=True,
        read_timeout=60, write_timeout=60
    )

def fetch_targets(conn, limit: int):
    """
    Pick smoothed transcripts that have NOT been analyzed (t.analyzed=0)
    and have no topic events yet (idempotency).
    """
    sql = """
      SELECT t.id AS transcript_id, s.smoothed_text, t.timestamp
      FROM smoothed_transcripts s
      JOIN transcriptions t ON t.id = s.original_transcript_id
      LEFT JOIN (
        SELECT DISTINCT transcript_id FROM callsign_topic_events
      ) done ON done.transcript_id = t.id
      WHERE done.transcript_id IS NULL
        AND t.analyzed = 0
      ORDER BY t.id ASC
      LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (limit,))
        return cur.fetchall()

def mark_analyzed(conn, transcript_id: int):
    with conn.cursor() as cur:
        cur.execute("UPDATE transcriptions SET analyzed=1 WHERE id=%s", (transcript_id,))

def load_corrections(conn):
    """List of (detect, correct) from corrections table."""
    sql = "SELECT detect, correct FROM corrections WHERE detect IS NOT NULL AND correct IS NOT NULL"
    pairs = []
    with conn.cursor() as cur:
        cur.execute(sql)
        for r in cur.fetchall():
            d = (r["detect"] or "").strip()
            c = (r["correct"] or "").strip()
            if d and c:
                pairs.append((d, c))
    return pairs

def apply_corrections(text: str, pairs) -> str:
    """Apply detect->correct (case-insensitive); word boundaries if detect is alnum."""
    if not text or not pairs:
        return text
    out = text
    for detect, correct in pairs:
        pattern = r"\b" + re.escape(detect) + r"\b" if detect.isalnum() else re.escape(detect)
        out = re.sub(pattern, correct, out, flags=re.IGNORECASE)
    return out

def callsigns_from_smoothed(conn, transcript_id: int) -> set[str]:
    """Extract trusted callsigns from smoothed_transcripts.callsigns_json."""
    sql = "SELECT callsigns_json FROM smoothed_transcripts WHERE original_transcript_id=%s"
    out = set()
    with conn.cursor() as cur:
        cur.execute(sql, (transcript_id,))
        row = cur.fetchone()
        if row and row.get("callsigns_json"):
            try:
                arr = json.loads(row["callsigns_json"])
                for c in arr or []:
                    cs = normalize_callsign(c)
                    if cs:
                        out.add(cs)
            except Exception:
                pass
    return out

def allowed_callsigns_for_transcript(conn, transcript_id: int, tstamp) -> set[str]:
    """
    Build ALLOWED set WITHOUT trusting callsign_log.timestamp by default.
    Priority:
      1) smoothed_transcripts.callsigns_json
      2) callsign_log rows already linked by transcript_id
      3) (optional) time-window scan if ENABLE_TIME_WINDOW_FALLBACK=1
    """
    allowed = set()

    # 1) from smoothed JSON
    allowed |= callsigns_from_smoothed(conn, transcript_id)

    # 2) already-linked by transcript_id (reliable)
    sql_linked = """
      SELECT UPPER(callsign) AS cs
      FROM callsign_log
      WHERE transcript_id = %s
        AND callsign IS NOT NULL AND callsign <> ''
    """
    with conn.cursor() as cur:
        cur.execute(sql_linked, (transcript_id,))
        for row in cur.fetchall():
            cs = normalize_callsign(row["cs"])
            if cs:
                allowed.add(cs)

    # 3) optional time-window fallback (OFF by default)
    if ENABLE_TIME_WINDOW_FALLBACK and tstamp:
        try:
            if not isinstance(tstamp, datetime):
                tstamp = datetime.fromisoformat(str(tstamp))
        except Exception:
            tstamp = None
        if tstamp:
            start = (tstamp - timedelta(seconds=FALLBACK_TIME_WINDOW_SEC)).strftime("%Y-%m-%d %H:%M:%S")
            end   = (tstamp + timedelta(seconds=FALLBACK_TIME_WINDOW_SEC)).strftime("%Y-%m-%d %H:%M:%S")
            sql_win = """
              SELECT UPPER(callsign) AS cs
              FROM callsign_log
              WHERE (transcript_id IS NULL OR transcript_id = 0)
                AND callsign IS NOT NULL AND callsign <> ''
                AND timestamp BETWEEN %s AND %s
            """
            with conn.cursor() as cur:
                cur.execute(sql_win, (start, end))
                for row in cur.fetchall():
                    cs = normalize_callsign(row["cs"])
                    if cs:
                        allowed.add(cs)

    return allowed

# ---------- JSON RESCUE ----------
def strip_fences(s: str) -> str:
    s = s.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, flags=re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else s

def balance_braces(s: str) -> str:
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return s
    frag = s[start:end+1]
    depth = 0; last_ok = -1
    for i, ch in enumerate(frag):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_ok = i
    return frag[:last_ok+1] if last_ok != -1 else frag

def remove_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)

def best_effort_json_parse(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        pass
    base = strip_fences(raw)
    for v in (base, balance_braces(base), remove_trailing_commas(balance_braces(base))):
        try:
            return json.loads(v)
        except Exception:
            continue
    m = re.search(r'{"events"\s*:\s*\[.*\]}', base, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

# ---------- UTIL ----------
def clamp(s: str) -> str:
    return s if len(s) <= MAX_CHARS_IN else s[:MAX_CHARS_IN] + " …"

# ---------- LLM CALL ----------
def call_topics_llm(text: str, allowed_callsigns: list[str]) -> list[dict]:
    """
    Ask LLM for topic events; it MUST use only allowed callsigns (enforced in prompt and post-filter).
    """
    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    allowed_str = ", ".join(allowed_callsigns) if allowed_callsigns else ""
    constraints = (
        "Allowed callsigns for this transcript: [" + allowed_str + "]\n"
        "You MUST assign events ONLY to callsigns from this list.\n"
        "If you cannot confidently assign one of the allowed callsigns, omit the event entirely.\n"
    )

    system = (
        "You classify amateur radio conversations into concise technical/social topics.\n"
        "- Do not invent speakers or content.\n"
        "- Only use topics present in the text.\n"
        "Preferred topics: [\"Antennas\",\"Propagation\",\"HF\",\"VHF/UHF\",\"DMR\",\"D-STAR\",\"Fusion\",\"APRS\","
        "\"Winlink\",\"Digital-Modes\",\"SATCOM/Satellites\",\"Portable/POTA/SOTA\",\"Contesting\",\"Emergency/ARES\","
        "\"Licensing/Testing\",\"Repeater-Maintenance\",\"Troubleshooting\",\"Weather\",\"Nets/Admin\","
        "\"Equipment/Hardware\",\"Software/Logging\",\"General-Chat\"]\n"
        + constraints +
        "OUTPUT: Return EXACTLY one JSON object: "
        "{\"events\":[{\"callsign\":\"K7ABC\",\"topic\":\"Antennas\",\"confidence\":92,\"excerpt\":\"...\"}]}\n"
        "No markdown or code fences."
    )
    user = clamp(text)
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role":"system","content":system},{"role":"user","content":user}],
        "temperature": 0.0, "seed": 7, "max_tokens": 1000,
        "response_format": {"type": "json_object"}
    }
    r = _session.post(url, headers=headers, json=payload, timeout=(10, OPENAI_TIMEOUT))
    r.raise_for_status()
    data = r.json()
    content = (data.get("choices",[{}])[0].get("message",{}).get("content") or "").strip()

    obj = best_effort_json_parse(content)
    if not obj:
        return []

    events = obj.get("events", []) or []
    allowed_set = set(allowed_callsigns)
    out = []
    for e in events:
        cs  = normalize_callsign(e.get("callsign"))
        top = (e.get("topic") or "").strip()
        if not cs or not top:
            continue
        # enforce allowed set strictly
        if allowed_set and cs not in allowed_set:
            continue
        try:
            conf = int(e.get("confidence", 80))
        except Exception:
            conf = 80
        conf = max(0, min(conf, 100))
        ex   = (e.get("excerpt") or "").strip()[:512]
        out.append({"callsign": cs, "topic": top, "confidence": conf, "excerpt": ex})
    return out

# ---------- INSERT EVENTS ----------
def insert_events(conn, transcript_id: int, tstamp, events: list[dict]) -> int:
    if not events:
        return 0
    if not isinstance(tstamp, datetime):
        try:
            tstamp = datetime.fromisoformat(str(tstamp))
        except Exception:
            tstamp = datetime.utcnow()

    sql = """
      INSERT INTO callsign_topic_events
        (callsign, transcript_id, event_time, topic, topic_confidence, excerpt, source)
      VALUES (%s,%s,%s,%s,%s,%s,'LLM')
    """
    inserted = 0
    with conn.cursor() as cur:
        for e in events:
            cs = normalize_callsign(e.get("callsign"))
            if not cs:
                continue
            topic = (e.get("topic") or "").strip()
            if not topic:
                continue
            try:
                conf = int(e.get("confidence", 80))
            except Exception:
                conf = 80
            conf = max(0, min(conf, 100))
            excerpt = (e.get("excerpt") or "")[:512]
            cur.execute(sql, (cs, transcript_id, tstamp, topic, conf, excerpt))
            inserted += 1
    return inserted

# ---------- UPSERT PROFILES ----------
def upsert_profiles(conn, transcript_id: int):
    """
    Aggregate events from this transcript and upsert extended_callsign_profile.
    You can run a nightly job to compute topics_rollup_json properly.
    """
    agg = """
      SELECT callsign,
             COUNT(*) AS mentions,
             COUNT(DISTINCT topic) AS distinct_topics,
             MIN(event_time) AS min_t,
             MAX(event_time) AS max_t
      FROM callsign_topic_events
      WHERE transcript_id = %s
      GROUP BY callsign
    """
    upsert = """
      INSERT INTO extended_callsign_profile
        (callsign, first_seen, last_seen, total_mentions, total_utterances, total_nets, topics_rollup_json)
      VALUES (%s, %s, %s, %s, %s, %s, %s)
      ON DUPLICATE KEY UPDATE
        first_seen      = LEAST(COALESCE(first_seen, VALUES(first_seen)), VALUES(first_seen)),
        last_seen       = GREATEST(COALESCE(last_seen,  VALUES(last_seen)),  VALUES(last_seen)),
        total_mentions  = total_mentions   + VALUES(total_mentions),
        total_utterances= total_utterances + VALUES(total_utterances),
        total_nets      = total_nets       + VALUES(total_nets)
    """
    topics_rollup_for_insert = "[]"
    with conn.cursor() as cur:
        cur.execute(agg, (transcript_id,))
        for r in cur.fetchall():
            cur.execute(upsert, (
                r["callsign"],
                r["min_t"], r["max_t"],
                r["mentions"],  # mentions in this transcript
                r["mentions"],  # utterances proxy
                1,              # +1 net per transcript
                topics_rollup_for_insert
            ))

# ---------- MAIN ----------
def main():
    conn = db()
    try:
        targets = fetch_targets(conn, MAX_TARGETS_PER_RUN)
        if not targets:
            print("No new smoothed transcripts to classify.")
            return
        print(f"Classifying {len(targets)} transcripts...")

        corrections = load_corrections(conn)

        for row in targets:
            tid = row["transcript_id"]
            txt = row["smoothed_text"] or ""
            ts  = row["timestamp"]

            if not txt.strip():
                # Nothing to do; mark analyzed so we don't requeue forever
                mark_analyzed(conn, tid)
                continue

            # Apply corrections first
            txt_corr = apply_corrections(txt, corrections)

            # Build allowed callsigns set
            allowed = allowed_callsigns_for_transcript(conn, tid, ts)
            # Supplement with regex hits from corrected text
            allowed |= extract_callsigns_regex(txt_corr)
            allowed_list = sorted(allowed)

            try:
                events = call_topics_llm(txt_corr, allowed_list)
            except Exception as e:
                print(f"[{tid}] LLM error: {e}")
                # do not mark analyzed; allow retry next run
                continue

            n = insert_events(conn, tid, ts, events)
            upsert_profiles(conn, tid)
            mark_analyzed(conn, tid)
            print(f"[{tid}] allowed={len(allowed_list)} -> inserted {n} topic events")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
