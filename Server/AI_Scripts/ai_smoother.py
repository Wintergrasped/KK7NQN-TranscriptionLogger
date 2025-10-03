#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI Transcript Smoother & Callsign Fixer

Pipeline:
  1) Select transcripts from `transcriptions` where processed=1.
  2) Basic regex quality gate.
  3) Send to local vLLM /v1/chat/completions one at a time.
  4) Expect JSON: {"smoothed":"...","callsigns":["K7ABC","W7XYZ",...]}
  5) Insert into `smoothed_transcripts`.
  6) Backfill `callsign_log.transcript_id` in a time window.
  7) Flip `transcriptions.processed` to 2.

Hardened:
  - Robust JSON parsing & fail-open fallback
  - HTTP session retries + timeouts
  - SQL retries for 1205/1213/1317
  - Adaptive pacing and progress logs
"""

import os
import re
import json
import time
import logging
import traceback
from datetime import timedelta, datetime

import pymysql
from dotenv import load_dotenv

# ---------- ENV ----------
load_dotenv()

def env(key, default=None):
    v = os.getenv(key, default)
    return v.strip() if isinstance(v, str) else v

# ----------------- CONFIG -----------------
DB_HOST = env("DB_HOST", "127.0.0.1")
DB_USER = env("DB_USER", "USER-NAME")
DB_PASS = env("DB_PASS", "PASSWORD")
DB_NAME = env("DB_NAME", "DATABASE")
DB_PORT = int(env("DB_PORT", "3306"))

SOURCE_TABLE = "transcriptions"
# Only pull rows that are processed=1 (ready to smooth) unless overridden
FETCH_PROCESSED_STATUSES = tuple(int(x) for x in env("FETCH_PROCESSED_STATUSES", "1").split(","))
POST_PROCESS_SET_PROCESSED_TO = 2  # 2 = smoothed

# vLLM/OpenAI-compatible API
OPENAI_BASE_URL = env("OPENAI_BASE_URL", "http://192.168.0.104:8001/v1")
OPENAI_MODEL = env("OPENAI_MODEL", "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4")
OPENAI_API_KEY = env("OPENAI_API_KEY", "sk-no-auth-needed-for-local")
OPENAI_TIMEOUT = float(env("OPENAI_TIMEOUT", "60"))  # read timeout

# Batch size & pacing
MAX_ROWS_PER_RUN = int(env("MAX_ROWS_PER_RUN", "2000"))
TARGET_LATENCY_SEC = float(env("TARGET_LATENCY_SEC", "1.5"))
SLEEP_BETWEEN_CALLS = float(env("SLEEP_BETWEEN_CALLS", "0.0"))
MIN_SLEEP = 0.0
MAX_SLEEP = 1.0

# Input clamp to avoid giant prompts (chars)
MAX_CHARS_IN = int(env("MAX_CHARS_IN", "6000"))

# Time window (in seconds) to attach callsign_log entries
CALLSIGN_ATTACH_WINDOW_SEC = int(env("CALLSIGN_ATTACH_WINDOW_SEC", "120"))

# Basic regex quality gate
MIN_CHARS = int(env("MIN_CHARS", "12"))
MIN_WORDS = int(env("MIN_WORDS", "3"))

# Callsign regex (captures ITU-style ham calls)
CALLSIGN_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z]{1,4})(?:/[A-Z0-9]{1,4})?\b",
    re.IGNORECASE
)

# -------------- LOGGING -------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# -------------- HTTP SESSION (resilient) --------------
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session = requests.Session()
_retry = Retry(
    total=4, connect=4, read=4, backoff_factor=0.8,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=["POST"]
)
_session.headers.update({"Connection": "keep-alive"})
_session.mount("http://", HTTPAdapter(max_retries=_retry))
_session.mount("https://", HTTPAdapter(max_retries=_retry))

# -------------- DB HELPERS ----------------
def db_connect():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        read_timeout=60,
        write_timeout=60,
    )

RETRY_SQL_ERRORS = {1205, 1213, 1317}  # lock timeout, deadlock, interrupted

def exec_with_retry(conn, sql, params=(), attempts=5, sleep=0.3):
    for i in range(attempts):
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur
        except pymysql.err.OperationalError as e:
            code = e.args[0] if e.args else None
            if code in RETRY_SQL_ERRORS and i < attempts - 1:
                time.sleep(sleep * (1.6 ** i))
                continue
            raise

def fetch_unprocessed_transcripts(conn):
    placeholders = ",".join(["%s"] * len(FETCH_PROCESSED_STATUSES))
    sql = f"""
        SELECT t.id, t.filename, t.transcription, t.timestamp
        FROM {SOURCE_TABLE} t
        LEFT JOIN smoothed_transcripts s
               ON s.original_transcript_id = t.id
        WHERE t.processed IN ({placeholders})
          AND s.id IS NULL
          AND t.transcription IS NOT NULL
          AND t.transcription <> ''
        ORDER BY t.id ASC
        LIMIT %s
    """
    cur = exec_with_retry(conn, sql, (*FETCH_PROCESSED_STATUSES, MAX_ROWS_PER_RUN))
    return cur.fetchall()

def mark_transcript_processed(conn, tid: int, status: int):
    exec_with_retry(
        conn,
        f"UPDATE {SOURCE_TABLE} SET processed=%s WHERE id=%s",
        (status, tid)
    )

def insert_smoothed(conn, original_transcript_id: int, smoothed_text: str, callsigns: list):
    sql = """
        INSERT INTO smoothed_transcripts
            (original_transcript_id, smoothed_text, callsigns_json)
        VALUES (%s, %s, %s)
    """
    callsigns_json = json.dumps(sorted(set([str(c).upper() for c in callsigns])))
    exec_with_retry(conn, sql, (original_transcript_id, smoothed_text, callsigns_json))

def attach_callsigns(conn, tid: int, tstamp: datetime, callsigns: list):
    """
    For each callsign returned by AI, set transcript_id in callsign_log where:
      - callsign matches (case-insensitive)
      - transcript_id is NULL or 0
      - timestamp within ±CALLSIGN_ATTACH_WINDOW_SEC of the transcript's timestamp
    """
    if not tstamp or not callsigns:
        return

    start = (tstamp - timedelta(seconds=CALLSIGN_ATTACH_WINDOW_SEC)).strftime("%Y-%m-%d %H:%M:%S")
    end   = (tstamp + timedelta(seconds=CALLSIGN_ATTACH_WINDOW_SEC)).strftime("%Y-%m-%d %H:%M:%S")

    q = """
        UPDATE callsign_log
        SET transcript_id = %s
        WHERE (transcript_id IS NULL OR transcript_id = 0)
          AND UPPER(callsign) = %s
          AND timestamp BETWEEN %s AND %s
    """
    updated_total = 0
    # normalize & dedupe callsigns
    norm = sorted({re.sub(r"/[A-Z0-9]{1,4}$", "", cs.upper()) for cs in callsigns})
    for c in norm:
        cur = exec_with_retry(conn, q, (tid, c, start, end))
        updated_total += cur.rowcount
    if updated_total:
        logging.info(f"Attached {updated_total} callsign_log rows to transcript_id={tid}")

# -------------- QUALITY GATE --------------
def basic_quality_gate(text: str) -> bool:
    if not text:
        return False
    if len(text) < MIN_CHARS:
        return False
    words = re.findall(r"[A-Za-z0-9']+", text)
    if len(words) < MIN_WORDS:
        return False
    if len(set(text.strip())) < 3:
        return False
    return True

def clamp_input(s: str) -> str:
    return s if len(s) <= MAX_CHARS_IN else s[:MAX_CHARS_IN] + " …"

# -------------- ROBUST JSON HELPERS --------------
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
            if depth == 0: last_ok = i
    return frag[:last_ok+1] if last_ok != -1 else frag

def remove_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)

def best_effort_json_parse(raw: str):
    # 1) Quick path
    try:
        return json.loads(raw)
    except Exception:
        pass
    # 2) Sanitized variants
    base = strip_fences(raw)
    for v in (base, balance_braces(base), remove_trailing_commas(balance_braces(base))):
        try:
            return json.loads(v)
        except Exception:
            continue
    # 3) Last-ditch: salvage callsigns array
    m = re.search(r'"callsigns"\s*:\s*\[(.*?)\]', base, re.DOTALL | re.IGNORECASE)
    if m:
        arr = m.group(1)
        items = re.findall(r'["\']?([A-Za-z0-9/]{3,10})["\']?', arr)
        return {"smoothed": "", "callsigns": items}
    return None

# -------------- OPENAI CALL ---------------
def call_openai_smoother(raw_text: str) -> dict:
    """
    Returns dict: {"smoothed": str, "callsigns": [str, ...]}
    Bulletproof against malformed JSON and hung HTTP reads.
    """
    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    system = (
        "You are a careful transcript smoother for amateur radio logs.\n"
        "- Keep all original meaning; fix obvious ASR errors and punctuation.\n"
        "- Do NOT invent content. If unsure, leave as-is.\n"
        "- Extract amateur radio callsigns you see (e.g., KK7NQN, VO1UKZ, K9BDC).\n"
        "OUTPUT RULES:\n"
        "Return EXACTLY one JSON object and nothing else.\n"
        'Keys must be: "smoothed" (string) and "callsigns" (array of strings).\n'
        'Example: {"smoothed":"...","callsigns":["K7ABC","W7XYZ"]}\n'
    )
    raw_for_model = clamp_input(raw_text)
    user = f"INPUT TRANSCRIPT:\n{raw_for_model}\n\nReturn only JSON."

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.0,
        "seed": 7,
        "max_tokens": 1000,
        "response_format": {"type": "json_object"}
    }

    delay = 2.0
    for attempt in range(4):
        try:
            start = time.time()
            resp = _session.post(
                url, headers=headers, json=payload,
                timeout=(10, OPENAI_TIMEOUT)  # (connect, read)
            )
            if resp.status_code == 429:
                ra = resp.headers.get("Retry-After")
                wait = float(ra) if ra else delay
                time.sleep(wait); delay *= 1.8
                continue
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            obj = best_effort_json_parse(text)

            if not obj:
                # log payload for forensics, then fail-open
                try:
                    badpath = f"/tmp/ai_smoother_bad_{int(time.time())}.txt"
                    with open(badpath, "w", encoding="utf-8") as f:
                        f.write(text)
                except Exception:
                    pass
                smoothed = raw_text
                callsigns = sorted({m.group(1).upper() for m in CALLSIGN_RE.finditer(raw_text)})
                globals()["_last_llm_latency"] = time.time() - start
                return {"smoothed": smoothed, "callsigns": list(callsigns)}

            smoothed = (obj.get("smoothed") or "").strip() or raw_text
            callsigns = obj.get("callsigns", [])
            cleaned = []
            for c in callsigns:
                m = CALLSIGN_RE.search(str(c).upper())
                if m:
                    cleaned.append(m.group(1).upper())

            globals()["_last_llm_latency"] = time.time() - start
            return {"smoothed": smoothed, "callsigns": sorted(set(cleaned))}

        except requests.RequestException:
            if attempt == 3:
                smoothed = raw_text
                callsigns = sorted({m.group(1).upper() for m in CALLSIGN_RE.finditer(raw_text)})
                return {"smoothed": smoothed, "callsigns": list(callsigns)}
            time.sleep(delay); delay *= 1.8
        except Exception:
            if attempt == 3:
                smoothed = raw_text
                callsigns = sorted({m.group(1).upper() for m in CALLSIGN_RE.finditer(raw_text)})
                return {"smoothed": smoothed, "callsigns": list(callsigns)}
            time.sleep(delay); delay *= 1.8

# -------------- MAIN LOOP ----------------
def main():
    global SLEEP_BETWEEN_CALLS
    conn = db_connect()
    try:
        rows = fetch_unprocessed_transcripts(conn)
        if not rows:
            logging.info("No unprocessed transcripts found.")
            return

        logging.info(f"Processing up to {len(rows)} transcripts...")
        processed_count = 0

        for r in rows:
            tid = r["id"]
            text = r["transcription"] or ""
            ts = r.get("timestamp")

            # Normalize timestamp to datetime
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    ts = None

            if not basic_quality_gate(text):
                logging.info(f"[{tid}] Skipped by quality gate.")
                mark_transcript_processed(conn, tid, POST_PROCESS_SET_PROCESSED_TO)
                continue

            try:
                logging.info(f"[{tid}] -> sending to LLM ({len(text)} chars)")
                result = call_openai_smoother(text)
                logging.info(
                    f"[{tid}] <- LLM done; {len(result.get('smoothed',''))} chars; "
                    f"{len(result.get('callsigns', []))} callsigns"
                )

                smoothed = result.get("smoothed", "").strip() or text
                callsigns = result.get("callsigns", [])

                insert_smoothed(conn, tid, smoothed, callsigns)
                attach_callsigns(conn, tid, ts, callsigns)
                mark_transcript_processed(conn, tid, POST_PROCESS_SET_PROCESSED_TO)

                logging.info(f"[{tid}] Smoothed + attached {len(callsigns)} callsigns.")
                processed_count += 1

                # adaptive pacing
                lat = globals().get("_last_llm_latency", 0.0)
                if lat > TARGET_LATENCY_SEC:
                    SLEEP_BETWEEN_CALLS = min(MAX_SLEEP, SLEEP_BETWEEN_CALLS + 0.05)
                else:
                    SLEEP_BETWEEN_CALLS = max(MIN_SLEEP, SLEEP_BETWEEN_CALLS - 0.02)
                if SLEEP_BETWEEN_CALLS > 0:
                    time.sleep(SLEEP_BETWEEN_CALLS)

                if processed_count % 100 == 0:
                    # heartbeat
                    cur = exec_with_retry(conn, "SELECT COUNT(*) AS c FROM smoothed_transcripts")
                    c = cur.fetchone()["c"]
                    logging.info(f"Heartbeat: total smoothed so far = {c}")

            except Exception:
                logging.error(f"[{tid}] Error:\n{traceback.format_exc()}")
                # don't flip processed flag so we can retry this row later
                # tiny pause to avoid hot-spinning on a bad row
                time.sleep(0.2)

    finally:
        conn.close()

if __name__ == "__main__":
    main()
