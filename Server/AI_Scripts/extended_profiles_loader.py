#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extended Profiles Loader
- Builds Callsign, Net, and NCS "extended" profiles from existing TSN data.
- Map-Reduce style LLM summarization under ~16k token input limit.
- Writes current snapshots + append-only histories + metric reasons + activity/topic rollups.
- Idempotent upserts; safe to re-run.

Env Vars:
  DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME (default: repeater)
  OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL
  AI_ENABLE (default "1"), AI_MAX_CHARS (default 48000 ~ rough 16k tokens)
  WINDOW_DAYS (analysis window for freshness, default 365)
  BATCH_CALLSIGNS (default 200)


"""

import os, sys, time, json, math, hashlib, logging, random
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import pymysql
import requests
import uuid  # at top

# ----------------------------
# Config
# ----------------------------
DB_HOST = "192.168.0.128"
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = "DB_USER"
DB_PASS = "DB_PASS"
DB_NAME = "DB_NAME"

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://192.168.0.104:8001/v1")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "sk-local-placeholder")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4")

AI_ENABLE       = os.getenv("AI_ENABLE", "1") == "1"
AI_MAX_CHARS    = int(os.getenv("AI_MAX_CHARS", "48000"))  # ~16k tokens @ ~3 chars/token (rough)
WINDOW_DAYS     = int(os.getenv("WINDOW_DAYS", "365"))     # time window for freshness & load
BATCH_CALLSIGNS = int(os.getenv("BATCH_CALLSIGNS", "12000")) # process this many callsigns per run

REQUEST_TIMEOUT = 60
MAX_RETRIES     = 5
RETRY_BACKOFF   = 2.0

# Pacific local time recording (your standard practice)
PACIFIC_TZ = timezone(timedelta(hours=-7))  # PDT; if you need DST-aware, wire in pytz/zoneinfo.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ----------------------------
# DB helpers
# ----------------------------

def db_conn():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor
    )

def sql_one(cur, q, args=None):
    cur.execute(q, args or ())
    return cur.fetchone()

def sql_all(cur, q, args=None):
    cur.execute(q, args or ())
    return cur.fetchall()

def upsert(cur, table, data, uniq_keys):
    """
    INSERT ... ON DUPLICATE KEY UPDATE convenience for MySQL/MariaDB.
    uniq_keys: list[str] of columns that participate in a UNIQUE or PRIMARY KEY.
    """
    cols = list(data.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join([f"`{c}`" for c in cols])
    updates = ", ".join([f"`{c}`=VALUES(`{c}`)" for c in cols if c not in uniq_keys])
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    if updates:
        sql += f" ON DUPLICATE KEY UPDATE {updates}"
    cur.execute(sql, [data[c] for c in cols])

# ----------------------------
# LLM helpers
# ----------------------------

def _http_post_json(url, headers, payload):
    last = None
    for i in range(MAX_RETRIES):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
            if r.status_code in (200, 201):
                return r.json()
            if r.status_code in (429, 503):
                # backoff
                t = (RETRY_BACKOFF ** i) + random.random()
                logging.warning("LLM rate/overload (%s). Backing off %.1fs", r.status_code, t)
                time.sleep(t)
                last = r
                continue
            # other error
            logging.error("LLM error %s: %s", r.status_code, r.text[:500])
            last = r
            break
        except requests.RequestException as e:
            t = (RETRY_BACKOFF ** i) + random.random()
            logging.warning("LLM network error: %s. Backing off %.1fs", e, t)
            time.sleep(t)
            last = e
    raise RuntimeError(f"LLM request failed after retries: {last}")

def llm_chat_json(system_prompt, user_prompt, response_schema_hint=None):
    """
    Calls an OpenAI-compatible /chat/completions. Instruct the model to STRICT JSON.
    """
    logging.info("Calling LLM")
    if not AI_ENABLE:
        return {}
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    # Instruct strict JSON
    tool_hint = "Return ONLY valid JSON. Do not include markdown fences."
    if response_schema_hint:
        tool_hint += "\nSchema hint:\n" + json.dumps(response_schema_hint, indent=2)

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt + "\n\n" + tool_hint}
        ],
        "temperature": 0.2,
        "max_tokens": 1500
    }
    data = _http_post_json(url, headers, payload)
    try:
        content = data["choices"][0]["message"]["content"]
        # Strip any accidental code fences
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("` \n")
            # drop language tag if present
            if content.lower().startswith("json"):
                content = content[4:].strip()
        return json.loads(content)
    except Exception as e:
        logging.error("Failed to parse LLM JSON: %s ; raw=%s", e, str(data)[:500])
        raise

def est_chars_budget_left(used_chars: int) -> int:
    if AI_MAX_CHARS <= 0:
        return 1000
    return max(1000, AI_MAX_CHARS - used_chars)

# ----------------------------
# Domain helpers
# ----------------------------

def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))

def compute_bias_score(net_count, open_count, alpha=1.0, beta=1.0):
    """
    open_vs_net_bias_score in [-1, +1]
    ratio = (net+α)/(open+α)
    score = tanh( ln(ratio) / β )
    """
    ratio = (net_count + alpha) / (open_count + alpha)
    return math.tanh(math.log(ratio) / beta)

def normalize_callsign(s):
    if not s:
        return s
    return s.strip().upper()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# ----------------------------
# Data extraction
# ----------------------------

def fetch_distinct_callsigns(cur, limit=None):
    # Prefer `callsigns` table; fallback to `callsign_log`.
    rows = []
    try:
        rows = sql_all(cur, "SELECT callsign FROM callsigns")
    except Exception:
        rows = sql_all(cur, "SELECT DISTINCT callsign FROM callsign_log")
    calls = [normalize_callsign(r["callsign"]) for r in rows if r.get("callsign")]
    calls = sorted(set(calls))
    if limit:
        calls = calls[:limit]
    return calls

def fetch_activity_counts(cur, callsign, tmin):
    """
    Returns: open_qso_count, net_count, ncs_count, total_tx_segments, last_seen
    Schema-aware for:
      - callsign_log(callsign, transcript_id, timestamp)
      - transcription_analysis(transcription_id, is_net, net_id)
      - net_participation(net_id, callsign, last_seen_time, transmissions_count)
      - net_data(id, ncs_callsign, start_time)
    """
    logging.info("Trying to build activity counts for " + str(callsign))
    # 1) Total segments + last seen (from callsign_log)
    r = sql_one(cur, """
        SELECT COUNT(*) AS c, MAX(timestamp) AS last_seen
        FROM callsign_log
        WHERE callsign=%s AND (timestamp IS NULL OR timestamp >= %s)
    """, (callsign, tmin))
    total_segments = int(r["c"] or 0) if r else 0
    last_seen = r["last_seen"] if r else None

    # 2) Net segments (callsign_log joined to transcription_analysis)
    r = sql_one(cur, """
        SELECT COUNT(*) AS c
        FROM callsign_log cl
        JOIN transcription_analysis ta
          ON ta.transcription_id = cl.transcript_id
        WHERE cl.callsign=%s
          AND (cl.timestamp IS NULL OR cl.timestamp >= %s)
          AND ta.is_net = 1
    """, (callsign, tmin))
    net_segments = int(r["c"] or 0) if r else 0

    # 3) Open-QSO segments
    open_qso_segments = max(0, total_segments - net_segments)

    # 4) Net appearances (distinct nets the callsign participated in)
    r = sql_one(cur, """
        SELECT COUNT(DISTINCT np.net_id) AS c, MAX(np.last_seen_time) AS last_np
        FROM net_participation np
        WHERE (np.callsign = %s OR np.callsign = UPPER(%s))
          AND (np.last_seen_time IS NULL OR np.last_seen_time >= %s)
    """, (callsign, callsign, tmin))
    net_ct = int(r["c"] or 0) if r else 0
    if r and r["last_np"] and (last_seen is None or r["last_np"] > last_seen):
        last_seen = r["last_np"]

    # 5) NCS count (nets this callsign led)
    r = sql_one(cur, """
        SELECT COUNT(*) AS c, MAX(start_time) AS last_led
        FROM net_data
        WHERE ncs_callsign = %s
          AND (start_time IS NULL OR start_time >= %s)
    """, (callsign, tmin))
    ncs_ct = int(r["c"] or 0) if r else 0
    if r and r["last_led"] and (last_seen is None or r["last_led"] > last_seen):
        last_seen = r["last_led"]

    return open_qso_segments, net_ct, ncs_ct, total_segments, last_seen


def fetch_recent_transcript_snippets_for_callsign(cur, callsign, tmin, max_chars):
    """
    Pulls transcript rows where this callsign appears via callsign_log link.
    We gather snippets (filename + short text slice). We cap to max_chars.
    """
    logging.info("Trying to fetch recent snippets for " + str(callsign))
    # Find transcript ids this callsign was linked to
    rows = sql_all(cur, """
        SELECT DISTINCT transcript_id
        FROM callsign_log
        WHERE callsign=%s AND transcript_id IS NOT NULL AND transcript_id > 0
          AND (timestamp IS NULL OR timestamp >= %s)
        ORDER BY transcript_id DESC
        LIMIT 2000
    """, (callsign, tmin))

    transcript_ids = [r["transcript_id"] for r in rows if r["transcript_id"]]
    if not transcript_ids:
        return []

    # Fetch text for these transcripts (favor smaller recent chunks first)
    # We bound the total characters to max_chars.
    chunks = []
    total = 0
    # Prefer the smaller 'transcriptions' table; fall back to 'transcriptions_large' if needed
    def get_txn(ids, table):
        if not ids:
            return []
        fmt = ",".join(["%s"] * len(ids))
        q = f"SELECT id, filename, transcription FROM {table} WHERE id IN ({fmt})"
        return sql_all(cur, q, ids)

    # Split into batches of 500 ids to avoid IN too large
    batched_ids = [transcript_ids[i:i+500] for i in range(0, len(transcript_ids), 500)]
    tx_rows = []
    for batch in batched_ids:
        try:
            tx_rows.extend(get_txn(batch, "transcriptions"))
        except Exception:
            pass
        try:
            tx_rows.extend(get_txn(batch, "transcriptions_large"))
        except Exception:
            pass

    # Deduplicate by id (in case present in both tables)
    seen = set()
    dedup = []
    for r in tx_rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        dedup.append(r)

    # Newest first
    dedup.sort(key=lambda r: r["id"], reverse=True)

    for r in dedup:
        txt = (r.get("transcription") or "").strip()
        if not txt:
            continue
        # Take a trimmed slice to keep prompt compact
        slice_txt = txt[:1200]
        entry = {
            "id": r["id"],
            "filename": r.get("filename"),
            "text": slice_txt
        }
        entry_len = len(slice_txt)
        if total + entry_len > max_chars:
            break
        chunks.append(entry)
        total += entry_len

    return chunks

def fetch_distinct_net_ids(cur):
    try:
        rows = sql_all(cur, "SELECT DISTINCT net_id FROM net_data WHERE net_id IS NOT NULL AND net_id!=''")
        return [r["net_id"] for r in rows if r["net_id"]]
    except Exception:
        pass
    try:
        rows = sql_all(cur, "SELECT DISTINCT net_id FROM net_participation WHERE net_id IS NOT NULL AND net_id!=''")
        return [r["net_id"] for r in rows if r["net_id"]]
    except Exception:
        return []

def fetch_net_instances_and_text(cur, net_id, tmin, max_chars):
    """
    Pulls a sample of instances (by transcript span in net_data) and text snippets within budget.
    """
    logging.info("Fetching net instances and text for " + str(net_id))
    instances = []
    text_chunks = []
    total = 0
    # Prefer net_data if present
    has_net_data = False
    try:
        sql_all(cur, "SELECT 1 FROM net_data LIMIT 1")
        has_net_data = True
    except Exception:
        has_net_data = False

    if has_net_data:
        rows = sql_all(cur, """
            SELECT id, net_id, start_transcript_id, end_transcript_id, ncs_callsign, start_time, end_time
            FROM net_data
            WHERE net_id=%s
              AND (start_time IS NULL OR start_time >= %s)
            ORDER BY id DESC
            LIMIT 200
        """, (net_id, tmin))
        instances = rows or []
        # collect transcripts in ranges, but cap chars
        for inst in instances:
            st = inst.get("start_transcript_id")
            en = inst.get("end_transcript_id")
            if not st or not en or en < st:
                continue
            # Pull a few evenly spaced samples across the span (avoid huge pulls)
            span = en - st + 1
            sample_n = min(10, max(3, span // max(1, span // 10)))
            pick_ids = sorted(set([st + int(i * (span-1) / (sample_n-1 or 1)) for i in range(sample_n)]))
            fmt = ",".join(["%s"]*len(pick_ids))
            for table in ("transcriptions", "transcriptions_large"):
                try:
                    rows = sql_all(cur, f"SELECT id, filename, transcription FROM {table} WHERE id IN ({fmt}) ORDER BY id DESC", pick_ids)
                    for r in rows:
                        txt = (r.get("transcription") or "").strip()
                        if not txt:
                            continue
                        s = txt[:1000]
                        if total + len(s) > max_chars:
                            break
                        text_chunks.append({"id": r["id"], "filename": r.get("filename"), "text": s})
                        total += len(s)
                except Exception:
                    continue
            if total >= max_chars:
                break

    else:
        # Fallback: sample participants' recent transcripts for this net (from net_participation)
        rows = sql_all(cur, """
            SELECT DISTINCT callsign
            FROM net_participation
            WHERE net_id=%s AND (timestamp IS NULL OR timestamp >= %s)
            LIMIT 50
        """, (net_id, tmin))
        calls = [normalize_callsign(r["callsign"]) for r in rows]
        for cs in calls:
            chunks = fetch_recent_transcript_snippets_for_callsign(cur, cs, tmin, max(1000, max_chars//10))
            for c in chunks:
                if total + len(c["text"]) > max_chars:
                    break
                text_chunks.append(c)
                total += len(c["text"])
            if total >= max_chars:
                break

    return instances, text_chunks

def fetch_ncs_callsigns(cur, tmin):
    """
    Collect callsigns that served as NCS if detectable.
    """
    logging.info("Trying to find NCS Callsigns")
    nc = set()
    # net_data ncs_callsign
    try:
        rows = sql_all(cur, "SELECT DISTINCT ncs_callsign FROM net_data WHERE ncs_callsign IS NOT NULL AND ncs_callsign!='' AND (start_time IS NULL OR start_time >= %s)", (tmin,))
        for r in rows:
            nc.add(normalize_callsign(r["ncs_callsign"]))
    except Exception:
        pass
    # net_participation role=NCS
    try:
        rows = sql_all(cur, "SELECT DISTINCT callsign FROM net_participation WHERE role='NCS' AND (timestamp IS NULL OR timestamp >= %s)", (tmin,))
        for r in rows:
            nc.add(normalize_callsign(r["callsign"]))
    except Exception:
        pass
    return sorted(nc)

# ----------------------------
# Prompts (Map-Reduce)
# ----------------------------

CALLSIGN_SYSTEM = """You are an analyst of amateur-radio conversations (Part 97). 
Infer polite, neutral, evidence-based operator profiles from short transcript snippets.
Only use provided text; do not guess personal data. Output STRICT JSON.
Scoring range: 0.0 to 1.0. Keep reasons concise.
"""

CALLSIGN_USER_TMPL = """You will summarize the on-air behavior for callsign: {callsign}

Snippets (recent-first):
{snippets}

Return JSON with:
{schema}
"""

CALLSIGN_SCHEMA = {
  "callsign": "string",
  "latest_topic": "string",
  "most_topic": "string",
  "topic_coverage": {"<topic>": "weight float (0..1)"},
  "summary": "short neutral summary",
  "personal_summary": "short respectful bio-like line based ONLY on radio behavior",
  "friendly_score": "float 0..1",
  "serious_score": "float 0..1",
  "focus_score": "float 0..1",
  "helpful_score": "float 0..1",
  "technical_score": "float 0..1",
  "civility_score": "float 0..1",
  "metric_reasons": { "<metric_key>": "one-sentence reason cited from evidence"}
}

NET_SYSTEM = """You analyze recurring ham-radio nets (series). Build a canonical profile from sampled instances.
Return STRICT JSON; be concise, evidence-based, and neutral. Scores: 0..1.
"""

NET_USER_TMPL = """Net slug: {net_id}
Sampled instance metadata (most recent first):
{meta}

Text samples:
{text}

Return JSON with:
{schema}
"""

NET_SCHEMA = {
  "net_id": "string",
  "canonical_summary": "short neutral description",
  "friendliness_score": "float 0..1",
  "focus_score": "float 0..1",
  "diversity_score": "float 0..1",
  "activity_score": "float 0..1",
  "helpfulness_score": "float 0..1",
  "civility_score": "float 0..1",
  "typical_duration_min": "int (best estimate)",
  "typical_checkins": "int (best estimate)",
  "schedule_hint": "string like 'Daily 09:00 PT' if clear, else ''",
  "topic_coverage": {"<topic>": "weight float (0..1)"},
  "metric_reasons": { "<metric_key>": "one-sentence reason" }
}

NCS_SYSTEM = """You analyze net control operators (NCS) across many nets.
Return STRICT JSON. Scores 0..1; concise and neutral.
"""

NCS_USER_TMPL = """NCS callsign: {callsign}

Context:
- Nets led count: {nets_led_count}
- Nets led (unique slugs): {nets_led_unique}
- Avg checkins: {avg_checkins}
- Avg duration (min): {avg_duration}

Text samples from nets where this operator likely acted as NCS:
{text}

Return JSON with:
{schema}
"""

NCS_SCHEMA = {
  "callsign": "string",
  "control_style_summary": "short description",
  "friendliness_score": "float 0..1",
  "structure_score": "float 0..1",
  "inclusivity_score": "float 0..1",
  "clarity_score": "float 0..1",
  "civility_score": "float 0..1",
  "metric_reasons": { "<metric_key>": "one-sentence reason" }
}

# ----------------------------
# Core pipeline
# ----------------------------

def start_model_run(cur, model_name, prompt_hash, params=None, notes=None):
    data = {
        "run_uuid": uuid.uuid4().hex,
        "model_name": model_name,
        "model_params": json.dumps(params or {}),
        "prompt_hash": prompt_hash,
        "code_version": os.getenv("CODE_VERSION", ""),
        "notes": notes or "",
    }
    upsert(cur, "profile_model_runs", data, ["run_uuid"])
    # Fetch id
    r = sql_one(cur, "SELECT id FROM profile_model_runs WHERE run_uuid=%s", (data["run_uuid"],))
    return r["id"]

def build_callsign_profile(cur, callsign, tmin, model_run_id):
    logging.info("Trying to build Callsign Profile for " + str(callsign))
    # Activity stats
    open_qso, net_ct, ncs_ct, total_segments, last_seen = fetch_activity_counts(cur, callsign, tmin)
    # Snippets
    snippets = fetch_recent_transcript_snippets_for_callsign(cur, callsign, tmin, max_chars=max(2000, AI_MAX_CHARS-6000))
    if not snippets and total_segments == 0:
        # No data; write minimal activity stats & bail
        upsert(cur, "callsign_activity_stats", {
            "callsign": callsign, "total_tx_segments": 0, "open_qso_count": 0, "net_count": 0,
            "ncs_count": 0, "last_seen": None
        }, ["callsign"])
        return None

    upsert(cur, "callsign_activity_stats", {
        "callsign": callsign,
        "total_tx_segments": total_segments,
        "open_qso_count": open_qso,
        "net_count": net_ct,
        "ncs_count": ncs_ct,
        "last_seen": last_seen
    }, ["callsign"])

    # Topic stat priming (optional quick & dirty weights)
    # We’ll do a trivial frequency proxy by pulling top tokens from snippet headers.
    topic_hint = defaultdict(int)
    for s in snippets:
        # Not NLP; just seed a few generic buckets
        txt = s["text"].lower()
        for key in ("antenna","amp","propagation","aprs","dmr","fusion","winlink","emcomm","contest","dx","astronomy","rv","science","tech","net","check-in","qso","license","newbie","gear"):
            if key in txt:
                topic_hint[key] += 1

    # Map-Reduce single pass (snippets are already budgeted)
    cs_user = CALLSIGN_USER_TMPL.format(
        callsign=callsign,
        snippets="\n".join([f"- [{s['id']}] {s['text']}" for s in snippets[:200]]),
        schema=json.dumps(CALLSIGN_SCHEMA, indent=2)
    )
    schema_hash = sha256(json.dumps(CALLSIGN_SCHEMA, sort_keys=True))
    model_json = {}
    if AI_ENABLE:
        model_json = llm_chat_json(CALLSIGN_SYSTEM, cs_user, CALLSIGN_SCHEMA)
    else:
        model_json = {
          "callsign": callsign,
          "latest_topic": max(topic_hint, key=topic_hint.get) if topic_hint else "",
          "most_topic": max(topic_hint, key=topic_hint.get) if topic_hint else "",
          "topic_coverage": {k: min(1.0, v/5.0) for k, v in topic_hint.items()},
          "summary": "Automated fallback summary.",
          "personal_summary": "",
          "friendly_score": 0.6, "serious_score": 0.5, "focus_score": 0.5,
          "helpful_score": 0.5, "technical_score": 0.5, "civility_score": 0.8,
          "metric_reasons": {"friendly_score":"fallback","civility_score":"fallback"}
        }

    # Compute bias score
    bias = compute_bias_score(net_ct, open_qso, alpha=1.0, beta=1.0)
    bias_window = {"method": "tanh_log_ratio", "params": {"alpha":1.0,"beta":1.0}}

    # Snapshot upsert
    now = datetime.now(PACIFIC_TZ).replace(tzinfo=None)
    cp = {
        "callsign": callsign,
        "window_start": (datetime.now(PACIFIC_TZ) - timedelta(days=WINDOW_DAYS)).replace(tzinfo=None),
        "window_end": now,
        "latest_topic": model_json.get("latest_topic",""),
        "most_topic": model_json.get("most_topic",""),
        "topic_coverage": json.dumps(model_json.get("topic_coverage") or {}),
        "summary": model_json.get("summary") or "",
        "personal_summary": model_json.get("personal_summary") or "",
        "friendly_score": model_json.get("friendly_score"),
        "serious_score": model_json.get("serious_score"),
        "focus_score": model_json.get("focus_score"),
        "helpful_score": model_json.get("helpful_score"),
        "technical_score": model_json.get("technical_score"),
        "civility_score": model_json.get("civility_score"),
        "open_qso_count": open_qso,
        "net_count": net_ct,
        "ncs_count": ncs_ct,
        "open_vs_net_bias_score": bias,
        "open_vs_net_bias_window": json.dumps(bias_window),
        "confidence": min(1.0, 0.4 + 0.6*sigmoid((total_segments-10)/20.0)),
        "data_freshness": last_seen,
        "model_run_id": model_run_id,
    }
    upsert(cur, "callsign_profiles", cp, ["callsign"])

    # History & reasons
    hist_payload = {
        "callsign": callsign,
        "activity": {
            "open_qso_count": open_qso, "net_count": net_ct, "ncs_count": ncs_ct,
            "total_tx_segments": total_segments, "last_seen": str(last_seen) if last_seen else None
        },
        "llm": model_json
    }
    cur.execute("INSERT INTO callsign_profile_history (callsign, model_run_id, window_start, window_end, payload) VALUES (%s,%s,%s,%s,%s)",
                (callsign, model_run_id, cp["window_start"], cp["window_end"], json.dumps(hist_payload, ensure_ascii=False)))

    # Reasons
    reasons = model_json.get("metric_reasons") or {}
    for metric, text in reasons.items():
        cur.execute(
            "INSERT INTO callsign_metric_reasons (callsign, metric_key, reason_text, evidence, model_run_id) VALUES (%s,%s,%s,%s,%s)",
            (callsign, metric, str(text)[:1000], json.dumps({"sample_count": len(snippets)}), model_run_id)
        )

    # Topic stats upserts (optional)
    for topic, wt in (model_json.get("topic_coverage") or {}).items():
        upsert(cur, "callsign_topic_stats", {
            "callsign": callsign,
            "topic": topic[:256],
            "count_total": 0,  # unknown here; keep 0 or compute later
            "count_open_qso": 0,
            "count_net": 0,
            "first_seen": None,
            "last_seen": last_seen,
            "weight": float(wt)
        }, ["callsign","topic"])

    return cp

def build_net_profile(cur, net_id, tmin, model_run_id):
    instances, text_chunks = fetch_net_instances_and_text(cur, net_id, tmin, max_chars=max(3000, AI_MAX_CHARS-8000))
    # Aggregate activity stats (instances, avg duration, avg checkins)
    instances_count = len(instances)
    total_checkins = None
    avg_checkins = None
    avg_duration = None

    # try to pull metrics if columns exist:
    try:
        logging.info("Trying to build Net Profile for " + str(net_id))
        r = sql_one(cur, """
            SELECT COUNT(*) c,
                   AVG(checkins) avg_checkins,
                   AVG(TIMESTAMPDIFF(MINUTE, start_time, end_time)) avg_dur
            FROM net_data WHERE net_id=%s AND (start_time IS NULL OR start_time >= %s)
        """, (net_id, tmin))
        if r:
            instances_count = r["c"] or instances_count
            avg_checkins = float(r["avg_checkins"]) if r["avg_checkins"] is not None else None
            avg_duration = float(r["avg_dur"]) if r["avg_dur"] is not None else None
    except Exception:
        pass

    # Prepare meta + text for prompt
    meta_lines = []
    for inst in instances[:20]:
        meta_lines.append(f"- id:{inst.get('id')} ncs:{inst.get('ncs_callsign')} start:{inst.get('start_time')} end:{inst.get('end_time')} span:{inst.get('start_transcript_id')}..{inst.get('end_transcript_id')}")
    text_lines = [f"[{c['id']}] {c['text']}" for c in text_chunks[:200]]

    user = safe_format(
    NET_USER_TMPL,
        net_slug=net_slug,  # or net_id if you switched
        meta="\n".join(meta_lines) if meta_lines else "(no structured instance meta available)",
        text="\n".join(text_lines) if text_lines else "(no text samples found)",
        schema=json.dumps(NET_SCHEMA, indent=2)
    )

    model_json = {}
    if AI_ENABLE:
        model_json = llm_chat_json(NET_SYSTEM, user, NET_SCHEMA)
    else:
        model_json = {
          "net_id": net_id,
          "canonical_summary": "Automated fallback summary.",
          "friendliness_score": 0.7, "focus_score": 0.6, "diversity_score": 0.5,
          "activity_score": 0.6, "helpfulness_score": 0.5, "civility_score": 0.9,
          "typical_duration_min": int(avg_duration or 60),
          "typical_checkins": int(avg_checkins or 30),
          "schedule_hint": "",
          "topic_coverage": {},
          "metric_reasons": {"friendliness_score":"fallback"}
        }

    now = datetime.now(PACIFIC_TZ).replace(tzinfo=None)
    np = {
        "net_id": net_id,
        "window_start": (datetime.now(PACIFIC_TZ) - timedelta(days=WINDOW_DAYS)).replace(tzinfo=None),
        "window_end": now,
        "canonical_summary": model_json.get("canonical_summary") or "",
        "friendliness_score": model_json.get("friendliness_score"),
        "focus_score": model_json.get("focus_score"),
        "diversity_score": model_json.get("diversity_score"),
        "activity_score": model_json.get("activity_score"),
        "helpfulness_score": model_json.get("helpfulness_score"),
        "civility_score": model_json.get("civility_score"),
        "typical_duration_min": model_json.get("typical_duration_min"),
        "typical_checkins": model_json.get("typical_checkins"),
        "schedule_hint": model_json.get("schedule_hint") or "",
        "topic_coverage": json.dumps(model_json.get("topic_coverage") or {}),
        "confidence": 0.6 if text_chunks else 0.4,
        "data_freshness": None,
        "model_run_id": model_run_id,
    }
    upsert(cur, "net_profiles", np, ["net_id"])

    # activity_stats snapshot
    upsert(cur, "net_activity_stats", {
        "net_id": net_id,
        "instances_count": int(instances_count or 0),
        "total_checkins": int((avg_checkins or 0) * (instances_count or 0)) if avg_checkins is not None else 0,
        "avg_checkins": float(avg_checkins) if avg_checkins is not None else None,
        "avg_duration_min": float(avg_duration) if avg_duration is not None else None,
        "first_seen": None,
        "last_seen": None,
        "topic_coverage": json.dumps(model_json.get("topic_coverage") or {})
    }, ["net_id"])

    # History
    cur.execute("INSERT INTO net_profile_history (net_id, model_run_id, window_start, window_end, payload) VALUES (%s,%s,%s,%s,%s)",
                (net_id, model_run_id, np["window_start"], np["window_end"], json.dumps({"llm": model_json, "instances_sampled": len(instances), "text_samples": len(text_chunks)})))

    # Reasons
    for metric, text in (model_json.get("metric_reasons") or {}).items():
        cur.execute("INSERT INTO net_metric_reasons (net_id, metric_key, reason_text, evidence, model_run_id) VALUES (%s,%s,%s,%s,%s)",
                    (net_id, metric, str(text)[:1000], json.dumps({"instances_sampled": len(instances), "text_samples": len(text_chunks)}), model_run_id))

    return np

def build_ncs_profile(cur, callsign, tmin, model_run_id):
    # Derive coarse stats from net_data and/or net_participation
    nets_led_count = 0
    nets_led_unique = 0
    avg_checkins = None
    avg_duration = None

    # From net_data
    try:
        logging.info("Trying to build NCS Profile for " + str(callsign))
        r = sql_one(cur, """
            SELECT COUNT(*) c,
                   COUNT(DISTINCT net_id) u,
                   AVG(checkins) avg_c,
                   AVG(TIMESTAMPDIFF(MINUTE, start_time, end_time)) avg_d
            FROM net_data
            WHERE ncs_callsign=%s AND (start_time IS NULL OR start_time >= %s)
        """, (callsign, tmin))
        if r:
            nets_led_count = int(r["c"] or 0)
            nets_led_unique = int(r["u"] or 0)
            if r["avg_c"] is not None:
                avg_checkins = float(r["avg_c"])
            if r["avg_d"] is not None:
                avg_duration = float(r["avg_d"])
    except Exception:
        pass

    # Fallback via net_participation role=NCS
    if nets_led_count == 0:
        try:
            r = sql_one(cur,
                        "SELECT COUNT(*) c FROM net_participation "
                        "WHERE callsign=%s AND role='NCS' AND (timestamp IS NULL OR timestamp >= %s)",
                        (callsign, tmin))
            nets_led_count = int(r["c"] or 0) if r else 0
        except Exception:
            pass

    # Collect text samples: use nets where they were NCS
    text_chunks = []
    total = 0
    try:
        rows = sql_all(cur, """
            SELECT start_transcript_id, end_transcript_id
            FROM net_data
            WHERE ncs_callsign=%s AND (start_time IS NULL OR start_time >= %s)
            ORDER BY id DESC
            LIMIT 50
        """, (callsign, tmin))
        for row in rows:
            st, en = row.get("start_transcript_id"), row.get("end_transcript_id")
            if not st or not en or en < st:
                continue
            span = en - st + 1
            sample_n = min(8, max(3, span // 5))
            ids = sorted(set([st + int(i * (span - 1) / (sample_n - 1 or 1)) for i in range(sample_n)]))
            fmt = ",".join(["%s"] * len(ids))
            for table in ("transcriptions", "transcriptions_large"):
                try:
                    trs = sql_all(cur, f"SELECT id, filename, transcription FROM {table} "
                                       f"WHERE id IN ({fmt}) ORDER BY id DESC", ids)
                    for r in trs:
                        txt = (r.get("transcription") or "").strip()
                        if not txt:
                            continue
                        s = txt[:900]
                        if total + len(s) > max(2000, AI_MAX_CHARS - 8000):
                            break
                        text_chunks.append({"id": r["id"], "text": s})
                        total += len(s)
                except Exception:
                    continue
            if total >= max(2000, AI_MAX_CHARS - 8000):
                break
    except Exception:
        pass

    # ---- NEW: build meta_lines and text_lines safely ----
    meta_lines = [
        f"- nets_led_total: {nets_led_count}",
        f"- nets_led_unique: {nets_led_unique}",
        f"- avg_checkins: {avg_checkins if avg_checkins is not None else 'n/a'}",
        f"- avg_duration_min: {avg_duration if avg_duration is not None else 'n/a'}",
    ]

    # Turn collected chunks into simple lines for the prompt
    text_lines = []
    for ch in text_chunks or []:
        if isinstance(ch, dict):
            tid = ch.get("id", "?")
            snippet = (ch.get("text") or "").strip()
        elif isinstance(ch, (list, tuple)) and len(ch) >= 2:
            tid, snippet = ch[0], str(ch[1]).strip()
        else:
            continue
        if snippet:
            text_lines.append(f"[{tid}] {snippet}")

    # Build the prompt
    user = safe_format(
        NCS_USER_TMPL,
        callsign=callsign,
        meta="\n".join(meta_lines) if meta_lines else "(no structured meta)",
        text="\n".join(text_lines) if text_lines else "(no text samples found)",
        schema=json.dumps(NCS_SCHEMA, indent=2)
    )

    model_json = {}
    if AI_ENABLE:
        model_json = llm_chat_json(NCS_SYSTEM, user, NCS_SCHEMA)
    else:
        model_json = {
            "callsign": callsign,
            "control_style_summary": "Automated fallback summary.",
            "friendliness_score": 0.7,
            "structure_score": 0.6,
            "inclusivity_score": 0.6,
            "clarity_score": 0.7,
            "civility_score": 0.9,
            "metric_reasons": {"clarity_score": "fallback"},
        }

    now = datetime.now(PACIFIC_TZ).replace(tzinfo=None)
    np = {
        "callsign": callsign,
        "window_start": (datetime.now(PACIFIC_TZ) - timedelta(days=WINDOW_DAYS)).replace(tzinfo=None),
        "window_end": now,
        "nets_led_count": nets_led_count,
        "nets_led_unique": nets_led_unique,
        "avg_checkins": float(avg_checkins) if isinstance(avg_checkins, (int, float)) else None,
        "avg_duration_min": float(avg_duration) if isinstance(avg_duration, (int, float)) else None,
        "control_style_summary": model_json.get("control_style_summary") or "",
        "friendliness_score": model_json.get("friendliness_score"),
        "structure_score": model_json.get("structure_score"),
        "inclusivity_score": model_json.get("inclusivity_score"),
        "clarity_score": model_json.get("clarity_score"),
        "civility_score": model_json.get("civility_score"),
        "confidence": 0.6 if text_chunks else 0.4,
        "data_freshness": None,
        "model_run_id": model_run_id,
    }
    upsert(cur, "ncs_profiles", np, ["callsign"])

    cur.execute(
        "INSERT INTO ncs_profile_history (callsign, model_run_id, window_start, window_end, payload) VALUES (%s,%s,%s,%s,%s)",
        (callsign, model_run_id, np["window_start"], np["window_end"],
         json.dumps({"llm": model_json, "text_samples": len(text_chunks)})),
    )

    for metric, text in (model_json.get("metric_reasons") or {}).items():
        cur.execute(
            "INSERT INTO ncs_metric_reasons (callsign, metric_key, reason_text, evidence, model_run_id) VALUES (%s,%s,%s,%s,%s)",
            (callsign, metric, str(text)[:1000], json.dumps({"text_samples": len(text_chunks)}), model_run_id),
        )

    return np

# ----------------------------
# Main
# ----------------------------
class _SafeDict(dict):
    def __missing__(self, key):
        return ""  # swallow unknown placeholders instead of raising KeyError

def safe_format(tmpl: str, **kwargs) -> str:
    # Works like str.format but ignores unknown fields
    return tmpl.format_map(_SafeDict(**kwargs))
    
def main():
    conn = db_conn()
    try:
        with conn.cursor() as cur:
            # Resolve time window
            tmin = (datetime.now(PACIFIC_TZ) - timedelta(days=WINDOW_DAYS)).replace(tzinfo=None)

            # Create a model_run lineage row
            prompts_blob = {
                "callsign_system": CALLSIGN_SYSTEM,
                "callsign_schema": CALLSIGN_SCHEMA,
                "net_system": NET_SYSTEM,
                "net_schema": NET_SCHEMA,
                "ncs_system": NCS_SYSTEM,
                "ncs_schema": NCS_SCHEMA
            }
            prompt_hash = sha256(json.dumps(prompts_blob, sort_keys=True))
            model_run_id = start_model_run(cur, OPENAI_MODEL, prompt_hash, params={
                "temperature": 0.2, "max_tokens": 1500, "ai_max_chars": AI_MAX_CHARS, "window_days": WINDOW_DAYS
            }, notes="Extended profiles refresh")

            # ---- Callsigns ----
            calls = fetch_distinct_callsigns(cur, limit=BATCH_CALLSIGNS)
            logging.info("Processing %d callsigns", len(calls))
            c_done = 0
            for cs in calls:
                try:
                    build_callsign_profile(cur, cs, tmin, model_run_id)
                    c_done += 1
                    if c_done % 20 == 0:
                        conn.commit()
                        logging.info("Committed %d callsigns...", c_done)
                except Exception as e:
                    logging.exception("Callsign %s failed: %s", cs, e)
            conn.commit()
            logging.info("Callsigns complete: %d", c_done)

            # ---- Nets ----
            net_ids = fetch_distinct_net_ids(cur)
            logging.info("Processing %d net profiles", len(net_ids))
            n_done = 0
            for slug in net_ids:
                try:
                    build_net_profile(cur, slug, tmin, model_run_id)
                    n_done += 1
                    if n_done % 10 == 0:
                        conn.commit()
                        logging.info("Committed %d nets...", n_done)
                except Exception as e:
                    logging.exception("Net %s failed: %s", slug, e)
            conn.commit()
            logging.info("Nets complete: %d", n_done)

            # ---- NCS ----
            ncs_list = fetch_ncs_callsigns(cur, tmin)
            logging.info("Processing %d NCS profiles", len(ncs_list))
            x_done = 0
            for cs in ncs_list:
                try:
                    build_ncs_profile(cur, cs, tmin, model_run_id)
                    x_done += 1
                    if x_done % 10 == 0:
                        conn.commit()
                        logging.info("Committed %d NCS...", x_done)
                except Exception as e:
                    logging.exception("NCS %s failed: %s", cs, e)
            conn.commit()
            logging.info("NCS complete: %d", x_done)

            # Finish model run
            cur.execute("UPDATE profile_model_runs SET finished_at=CURRENT_TIMESTAMP WHERE id=%s", (model_run_id,))
            conn.commit()
            logging.info("Extended Profiles refresh done. model_run_id=%s", model_run_id)

    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
