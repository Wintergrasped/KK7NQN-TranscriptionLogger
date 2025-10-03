#!/usr/bin/env python3
"""
Transcript_Analyzer.py — regex-first with optional AI assist (full, updated)

What this does
--------------
1) Builds time-bounded sessions of transcripts.
2) Uses regex/heuristics to score each session as a likely net.
3) If likely a net and AI is enabled, sends the session text (as JSON-lines) to
   an AI backend to refine: net_name, club_name, NCS callsign, participants,
   operator topics, and a summary.
4) Creates `net_data` ONLY when we have a *good* net name. Otherwise skips and
   marks transcripts for re-scan later.
5) Populates per-transcript analysis, net participation, and callsign_topics.

Env vars (with defaults)
------------------------
DB_HOST(127.0.0.1) DB_PORT(3306) DB_USER(user) DB_PASS(pass) DB_NAME(database)
CPU_THRESHOLD(50) BATCH_LIMIT(2000) SESSION_GAP_MIN(10) DRY_RUN(0)
NET_NAME_MAX(255) CLUB_NAME_MAX(255) NET_NAME_WORDS_MAX(10) NET_NAME_CHARS_MAX(60)
RESCAN_MINUTES(120)
AI_ENABLE(0) AI_MODEL(gpt-4o-mini) AI_BASE_URL(https://api.openai.com/v1)
AI_API_KEY("") AI_TIMEOUT(20) AI_MAX_TOKENS(600) AI_MIN_CONF(0.65)
AI_FORCE(0) AI_LOG(0)

Run
---
DRY_RUN=1 AI_ENABLE=1 AI_LOG=1 AI_FORCE=1 python3 Transcript_Analyzer.py
python3 Transcript_Analyzer.py
"""
from __future__ import annotations
import os
import re
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# Optional deps
try:
    import psutil  # type: ignore
except Exception:
    psutil = None
try:
    import mysql.connector as mysql  # type: ignore
except Exception:
    mysql = None

# AI backend (local file ai_backend.py)
try:
    from ai_backend import ai_infer_session, should_call_ai
except Exception:
    def ai_infer_session(*a, **kw):
        return None
    def should_call_ai(*a, **kw):
        return False

# --------------- Logging & Config ---------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TranscriptAnalyzer")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = "DB_USER"
DB_PASS = "DB_PASS"
DB_NAME = "DB_NAME"

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", "50"))
BATCH_LIMIT = int(os.getenv("BATCH_LIMIT", "2000"))
SESSION_GAP_MIN = int(os.getenv("SESSION_GAP_MIN", "10"))
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

NET_NAME_MAX = int(os.getenv("NET_NAME_MAX", "255"))
CLUB_NAME_MAX = int(os.getenv("CLUB_NAME_MAX", "255"))
NET_NAME_WORDS_MAX = int(os.getenv("NET_NAME_WORDS_MAX", "10"))
NET_NAME_CHARS_MAX = int(os.getenv("NET_NAME_CHARS_MAX", "60"))
RESCAN_MINUTES = int(os.getenv("RESCAN_MINUTES", "120"))

AI_MIN_CONF = float(os.getenv("AI_MIN_CONF", "0.65"))
AI_FORCE = os.getenv("AI_FORCE", "0") == "1"
AI_LOG = os.getenv("AI_LOG", "0") == "1"

# --------------- Regexes ---------------
CALLSIGN_RE = re.compile(r"\b([A-KN-PR-Z]{1,2}\d{1,4}[A-Z]{1,3})(?:\/[A-Z0-9]+)?\b", re.I)

NET_STRONG_PHRASES = [
    r"\bwelcome to (?:the )?.+? net\b",
    r"\bnet control\b",
    r"\bany (?:more )?check[- ]?ins\b",
    r"\blate check[- ]?ins\b",
    r"\bwe (?:will )?now close the net\b",
    r"\bdirected net\b",
]
NET_WEAK_PHRASES = [
    r"\broll call\b",
    r"\btraffic (?:for|from) the net\b",
    r"\bnet logger\b",
]

PHRASE_NET_NAME_PATS = [
    re.compile(r"\bwelcome to (?:the )?(.+?) net\b", re.I),
    re.compile(r"\bthis is (?:the )?(.+?) net\b", re.I),
    re.compile(r"\byou(?:'re| are) (?:listening )?to (?:the )?(.+?) net\b", re.I),
]

BAD_NAME_STARTS = (
    "this", "join us", "be an", "please", "remember", "check in", "check-in",
    "good morning", "good evening", "good afternoon", "host here", "and thanks",
    "mostest", "you’re", "you're", "look", "speak", "mention", "here", "off her",
)
BAD_NAME_KEYWORDS = (
    "check in", "check-in", "i.o", " i o ", "listen in", "thank you",
    "closing", "signal report", "traffic", "directed", "social", "formal",
    "back to net", "back to you net", "back to net control", "back to control",
)

PSRG_PAT = re.compile(r"\bpsrg\b|puget\s+sound\s+repeater\s+group|ww7\s*psr", re.I)
TIME_NAME_PAT = re.compile(r"\b(?:(9\s*o'?clock)|noon|9\s*p\.?m\.?)\b", re.I)

TRAILING_TRIM_RE = re.compile(r"[\s\-:–—|,;]+$")
CTRL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")

THIS_IS_CALLSIGN_RE = re.compile(r"\bthis is\s+([A-Z0-9/]{3,})\b", re.I)
THIS_IS_PHONETIC_RE = re.compile(r"\bthis is\s+(?:[a-z]+\s+){2,8}(?:[a-z]+)\b", re.I)
IO_CHECKIN_RE = re.compile(r"\b(with\s+an?\s*i\s*o|will\s+be\s+an?\s*i\s*o)\b", re.I)

STOP_TOKENS = (
    " on ", " for ", " with ", " tonight ", " this ", " starting ", " beginning ",
    " presented ", " hosted ", " brought to you ", " at ", " from ", " via ", " over ",
)

# --------------- Data Models ---------------
@dataclass
class Transcript:
    id: int
    timestamp: datetime
    text: str

@dataclass
class Session:
    transcripts: List[Transcript] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def add(self, t: Transcript):
        self.transcripts.append(t)
        if not self.start_time or t.timestamp < self.start_time:
            self.start_time = t.timestamp
        if not self.end_time or t.timestamp > self.end_time:
            self.end_time = t.timestamp

    @property
    def ids(self) -> List[int]:
        return [t.id for t in self.transcripts]

    @property
    def duration_sec(self) -> int:
        if not (self.start_time and self.end_time):
            return 0
        return int((self.end_time - self.start_time).total_seconds())

    @property
    def text_blob(self) -> str:
        return "\n".join(t.text for t in self.transcripts)

# --------------- Helpers ---------------
def clean_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = CTRL_CHARS_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = TRAILING_TRIM_RE.sub("", s)
    return s or None


def limit_str(s: Optional[str], maxlen: int) -> Optional[str]:
    if s is None:
        return None
    if len(s) > maxlen:
        logger.warning("Truncating value len=%d to %d: %r", len(s), maxlen, s[:80] + "…")
        return s[:maxlen]
    return s


def cpu_ok() -> bool:
    if psutil is None:
        logger.info("psutil not installed; skipping CPU check and proceeding.")
        return True
    usage = psutil.cpu_percent(interval=1.5)
    logger.info(f"CPU usage: {usage:.1f}% (threshold {CPU_THRESHOLD:.1f}%)")
    return usage < CPU_THRESHOLD


def get_db():
    if mysql is None:
        raise RuntimeError("mysql-connector-python not installed")
    cnx = mysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
                        database=DB_NAME, autocommit=False)
    return cnx

# --------- Phonetic corrections map ---------
def load_corrections_map(cur) -> Dict[str, str]:
    """Load corrections table into {detect -> correct} lowercased."""
    try:
        cur.execute("SELECT `detect`,`correct` FROM corrections")
        rows = cur.fetchall()
        mp = {}
        for det, cor in rows:
            d = (det or "").strip().lower()
            c = (cor or "").strip().lower()
            if d and c:
                mp[d] = c
        return mp
    except Exception:
        return {}

def normalize_callsign_or_phonetic(s: Optional[str], corr: Optional[Dict[str,str]] = None) -> Optional[str]:
    """
    Turn phonetics like 'Victor Alpha 3 Echo Whiskey Victor' -> 'VA3EWV'.
    Returns valid callsign (per CALLSIGN_RE) or None.
    """
    if not s:
        return None
    s0 = clean_text(s) or ""
    s0 = s0.replace("-", " ").replace("/", " ").strip()
    if CALLSIGN_RE.fullmatch(s0.upper()):
        return s0.upper()
    corr = corr or {}
    out = []
    for tok in re.split(r"\s+", s0.lower()):
        if not tok:
            continue
        if tok in corr:
            out.append(corr[tok])
        else:
            out.append(re.sub(r"[^a-z0-9]", "", tok))
    flat = "".join(out).upper()
    m = CALLSIGN_RE.search(flat)
    return m.group(1).upper() if m else None

# --------------- Name extraction (regex) ---------------
def clip_net_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    name = clean_text(name)
    if not name:
        return None
    low = " " + name.lower() + " "
    for token in STOP_TOKENS:
        i = low.find(token)
        if i != -1:
            name = name[:i-1]
            break
    parts = name.split()
    if len(parts) > NET_NAME_WORDS_MAX:
        name = " ".join(parts[:NET_NAME_WORDS_MAX])
    if len(name) > NET_NAME_CHARS_MAX:
        name = name[:NET_NAME_CHARS_MAX].rstrip()
    return name or None


def looks_like_good_name(name: Optional[str]) -> bool:
    if not name:
        return False
    nm = name.strip()
    if len(nm) < 4:
        return False
    lnm = nm.lower()
    for bad in BAD_NAME_STARTS:
        if lnm == bad or lnm.startswith(bad + " "):
            return False
    for kw in BAD_NAME_KEYWORDS:
        if kw in lnm:
            return False
    if TIME_NAME_PAT.fullmatch(lnm):
        return False
    if not re.search(r"[a-zA-Z]", nm):
        return False
    if len(nm.split()) > 8:
        return False
    return True


def extract_net_name_candidates(text: str) -> List[str]:
    cands: List[str] = []
    for pat in PHRASE_NET_NAME_PATS:
        for m in pat.finditer(text):
            cands.append(m.group(1))
    for line in text.splitlines():
        if "net" not in line.lower():
            continue
        words = re.findall(r"[A-Za-z0-9&/'-]+", line)
        if not words:
            continue
        low = [w.lower() for w in words]
        for i, w in enumerate(low):
            if w == "net" and i > 0:
                start = max(0, i-6)
                cands.append(" ".join(words[start:i]))
    return cands


def enhance_with_context(raw_name: Optional[str], text: str) -> Optional[str]:
    if not raw_name:
        return None
    if PSRG_PAT.search(text):
        m = TIME_NAME_PAT.search(raw_name)
        if m:
            slot = m.group(0)
            slot_norm = "9 O'Clock" if "9" in slot else ("Noon" if "noon" in slot.lower() else "9PM")
            return f"PSRG {slot_norm}"
    return raw_name


def choose_best_name(cands: List[str], text: str) -> Optional[str]:
    if not cands:
        return None
    votes: Dict[str, int] = {}
    best_map: Dict[str, str] = {}
    for raw in cands:
        clipped = clip_net_name(raw)
        clipped = enhance_with_context(clipped, text)
        if not looks_like_good_name(clipped):
            continue
        norm = clipped.lower()
        votes[norm] = votes.get(norm, 0) + 1
        best_map.setdefault(norm, clipped)
    if not votes:
        return None
    norm_best = sorted(votes.items(), key=lambda kv: (-kv[1], len(best_map[kv[0]])))[0][0]
    return best_map[norm_best]


def extract_net_name(text: str) -> Optional[str]:
    if not re.search(r"\bnet\b", text, re.I):
        return None
    name = choose_best_name(extract_net_name_candidates(text), text)
    if name:
        return limit_str(name.title(), NET_NAME_MAX)
    return None

# --------------- DB access ---------------
def fetch_transcripts_for_analysis(cur, limit: int) -> List[Transcript]:
    """Fetch new items + re-scan candidates (is_net=1 but missing name/net_id)."""
    sql = (
        "SELECT t.id, t.timestamp, t.transcription "
        "FROM transcriptions t "
        "LEFT JOIN transcription_analysis ta ON ta.transcription_id = t.id "
        "WHERE (ta.transcription_id IS NULL) "
        "   OR (ta.is_net = 1 AND ta.net_id IS NULL AND (ta.detected_net_name IS NULL OR ta.detected_net_name = '') "
        "       AND t.timestamp < (NOW() - INTERVAL %s MINUTE)) "
        "ORDER BY t.timestamp ASC LIMIT %s"
    )
    cur.execute(sql, (RESCAN_MINUTES, limit))
    rows = cur.fetchall()
    out: List[Transcript] = []
    for rid, ts, txt in rows:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        out.append(Transcript(id=rid, timestamp=ts, text=txt or ""))
    logger.info(f"Fetched {len(out)} transcripts (incl. rescans)")
    return out


def upsert_transcription_analysis(cur, t: Transcript, is_net: int, net_id: Optional[int],
                                  detected_net_name: Optional[str], detected_club_name: Optional[str],
                                  ncs_candidate: int, keyword_hits: Dict[str, int],
                                  callsigns: List[str], topics: List[str], confidence: float):
    detected_net_name = limit_str(clip_net_name(detected_net_name), NET_NAME_MAX)
    detected_club_name = limit_str(clean_text(detected_club_name), CLUB_NAME_MAX)
    sql = (
        "INSERT INTO transcription_analysis (transcription_id, is_net, net_id, ncs_candidate, "
        "detected_net_name, detected_club_name, keyword_hits, callsigns_json, topic_labels, confidence_score) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE is_net=VALUES(is_net), net_id=VALUES(net_id), ncs_candidate=VALUES(ncs_candidate), "
        "detected_net_name=VALUES(detected_net_name), detected_club_name=VALUES(detected_club_name), "
        "keyword_hits=VALUES(keyword_hits), callsigns_json=VALUES(callsigns_json), topic_labels=VALUES(topic_labels), "
        "confidence_score=VALUES(confidence_score)"
    )
    cur.execute(sql, (
        t.id, is_net, net_id, ncs_candidate,
        detected_net_name, detected_club_name,
        json.dumps(keyword_hits) if keyword_hits else None,
        json.dumps(callsigns) if callsigns else None,
        json.dumps(topics) if topics else None,
        confidence,
    ))


def insert_net_data(cur, net_name: Optional[str], club_name: Optional[str], ncs_callsign: Optional[str],
                    start_tid: int, end_tid: int, start_time: datetime, end_time: datetime,
                    duration_sec: int, confidence: float, summary: Optional[str]) -> int:
    net_name = limit_str(clip_net_name(net_name), NET_NAME_MAX)
    club_name = limit_str(clean_text(club_name), CLUB_NAME_MAX)
    # ncs callsign already normalized upstream; clamp length defensively
    if ncs_callsign:
        ncs_callsign = clean_text(ncs_callsign.upper())
        ncs_callsign = limit_str(ncs_callsign, 16)  # typical callsigns <= 10, safety buffer
    sql = (
        "INSERT INTO net_data (net_name, club_name, ncs_callsign, start_transcription_id, end_transcription_id, "
        "start_time, end_time, duration_sec, confidence_score, summary) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    )
    cur.execute(sql, (net_name, club_name, ncs_callsign, start_tid, end_tid,
                      start_time, end_time, duration_sec, confidence, summary))
    return cur.lastrowid


def link_session_transcripts(cur, net_id: int, tids: List[int]):
    if not tids:
        return
    values = ",".join(["(%s,%s)"] * len(tids))
    params: List[int] = []
    for tid in tids:
        params.extend([net_id, tid])
    sql = f"INSERT IGNORE INTO net_session_transcripts (net_id, transcription_id) VALUES {values}"
    cur.execute(sql, params)


def ensure_callsign(cur, callsign: str) -> Optional[int]:
    cur.execute("SELECT ID FROM callsigns WHERE callsign = %s", (callsign.upper(),))
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute("INSERT INTO callsigns (callsign, validated) VALUES (%s, 0)", (callsign.upper(),))
    return cur.lastrowid


def upsert_participation(cur, net_id: int, callsign: str, first_time: datetime, last_time: datetime,
                         tx_count: int, talk_seconds: int, checkin_type: str = "unknown"):
    callsign_id = ensure_callsign(cur, callsign)
    sql = (
        "INSERT INTO net_participation (net_id, callsign_id, callsign, first_seen_time, last_seen_time, "
        "transmissions_count, talk_seconds, checkin_type) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE last_seen_time=GREATEST(VALUES(last_seen_time), last_seen_time), "
        "transmissions_count=transmissions_count+VALUES(transmissions_count), "
        "talk_seconds=talk_seconds+VALUES(talk_seconds), checkin_type=IF(checkin_type='unknown', VALUES(checkin_type), checkin_type)"
    )
    cur.execute(sql, (net_id, callsign_id, callsign.upper(), first_time, last_time, tx_count, talk_seconds, checkin_type))


def insert_callsign_topic(cur, net_id: int, callsign: str, description: str, corr: Dict[str, str]):
    """Insert a single operator topic description into callsign_topics (if callsign can be normalized)."""
    if not description:
        return
    cs_norm = normalize_callsign_or_phonetic(callsign, corr)
    if not cs_norm:
        return
    callsign_id = ensure_callsign(cur, cs_norm)
    cur.execute(
        "INSERT INTO callsign_topics (net_id, callsign_id, callsign, topic_description) VALUES (%s,%s,%s,%s)",
        (net_id, callsign_id, cs_norm, description[:4000])
    )

# --------------- Topic detection (simple heuristics) ---------------
def detect_topics(line: str) -> List[str]:
    low = line.lower()
    found: List[str] = []
    topics = {
        "Antennas": ["antenna", "yagi", "dipole", "vertical", "swr", "tuner", "feedline", "balun"],
        "Digital":  ["dmr", "d-star", "fusion", "p25", "vara", "winlink", "packet"],
        "HF":       ["hf", "20m", "40m", "80m", "ssb", "cw", "ft8", "contest"],
        "Service":  ["ares", "races", "skywarn", "parade", "marathon", "event support"],
        "Swap":     ["wtb", "wts", "for", "sale", "swap", "sked"],
        "Weather":  ["storm", "outage", "wildfire", "earthquake", "evacuation"],
    }
    for topic, kws in topics.items():
        for kw in kws:
            if kw in low:
                found.append(topic)
                break
    return found

# --------------- NCS extraction (regex) ---------------
def extract_club_name(text: str) -> Optional[str]:
    m = re.search(r"\b(?:hosted|presented|brought to you) by ([\w .\-]+)", text, re.I)
    if m:
        name = clean_text(m.group(1))
        return limit_str(name.title(), CLUB_NAME_MAX)
    return None


def extract_ncs(text: str) -> Optional[str]:
    # If we see "this is <callsign>" *without* NCS language, skip (to avoid false positives).
    if THIS_IS_CALLSIGN_RE.search(text) and not re.search(r"\b(net control|ncs)\b", text, re.I):
        return None
    if THIS_IS_PHONETIC_RE.search(text) and not re.search(r"\b(net control|ncs)\b", text, re.I):
        return None
    for pat in [
        re.compile(r"\bthis is\s+([A-Z0-9/]+)\b.*\b(net control|NCS)\b", re.I),
        re.compile(r"\b([A-Z0-9/]+)\b.*\b(your|the)\s+(?:net control|NCS)\b", re.I),
    ]:
        m = pat.search(text)
        if m:
            cs = m.group(1).upper().replace("/", "")
            if CALLSIGN_RE.match(cs):
                return cs
    return None

# --------------- Sessionization & Scoring ---------------
def make_sessions(transcripts: List[Transcript], gap_minutes: int) -> List[Session]:
    if not transcripts:
        return []
    transcripts = sorted(transcripts, key=lambda t: t.timestamp)
    sessions: List[Session] = []
    cur_sess = Session()
    cur_sess.add(transcripts[0])

    for prev, cur in zip(transcripts, transcripts[1:]):
        gap = (cur.timestamp - prev.timestamp).total_seconds() / 60.0
        if gap >= gap_minutes:
            sessions.append(cur_sess)
            cur_sess = Session()
        cur_sess.add(cur)
    sessions.append(cur_sess)
    return sessions


def score_session_for_net(sess: Session) -> Tuple[float, Dict[str,int]]:
    text = sess.text_blob.lower()
    score = 0.0
    hits: Dict[str,int] = {}

    def add_hits(patterns: List[str], weight: float):
        nonlocal score
        for p in patterns:
            c = len(re.findall(p, text))
            if c:
                hits[p] = hits.get(p, 0) + c
                score += weight * c

    add_hits(NET_STRONG_PHRASES, 0.6)
    add_hits(NET_WEAK_PHRASES, 0.3)

    simple_this_is = len(THIS_IS_CALLSIGN_RE.findall(text)) + len(THIS_IS_PHONETIC_RE.findall(text))
    has_net_token = bool(re.search(r"\bnet\b", text))
    if simple_this_is >= 3 and not has_net_token:
        score -= 0.6

    uniq_calls = set()
    for t in sess.transcripts:
        for m in CALLSIGN_RE.findall(t.text):
            uniq_calls.add(m.upper())
    if len(uniq_calls) >= 12:
        score += 0.2

    dur = sess.duration_sec
    if 20*60 <= dur <= 120*60:
        score += 0.2

    if sess.start_time and sess.start_time.minute in (0, 30) and sess.start_time.second < 30:
        score += 0.1

    # If no "net" token and no hits, cap below 1.0 so it's not a "net" by score alone.
    if not has_net_token and not any(h for h in hits.values()):
        score = min(score, 0.9)

    return score, hits

# --------------- Main ---------------
def main():
    if not cpu_ok():
        logger.info("CPU too high; exiting without processing.")
        return

    cnx = get_db()
    cur = cnx.cursor()
    try:
        tx = fetch_transcripts_for_analysis(cur, BATCH_LIMIT)
        if not tx:
            logger.info("No transcripts to analyze.")
            cnx.rollback()
            return
        sessions = make_sessions(tx, SESSION_GAP_MIN)
        logger.info(f"Built {len(sessions)} sessions (gap >= {SESSION_GAP_MIN} min)")

        # Load phonetic corrections once
        corr_map = load_corrections_map(cur)

        for sess in sessions:
            score, hits = score_session_for_net(sess)
            text_blob = sess.text_blob
            is_net = 1 if score >= 1.0 else 0

            net_id: Optional[int] = None
            net_name = extract_net_name(text_blob)
            club_name = extract_club_name(text_blob)
            ncs = extract_ncs(text_blob)
            summary_text: Optional[str] = None

            # --- Optional AI refinement ---
            if is_net and (AI_FORCE or should_call_ai(score, net_name)):
                if AI_LOG:
                    logger.info(
                        "AI decision → is_net=%s score=%.2f regex_name=%r force=%s",
                        is_net, score, net_name, int(AI_FORCE),
                    )
                    logger.info("AI_ENABLE=%s | API_KEY len=%d | MODEL=%s",
                                True, len(os.getenv("AI_API_KEY","")), os.getenv("AI_MODEL",""))
                ai_payload = [
                    {
                        "id": t.id,
                        "timestamp": t.timestamp.isoformat() if hasattr(t.timestamp, "isoformat") else str(t.timestamp),
                        "text": t.text,
                    }
                    for t in sess.transcripts
                ]
                ai = ai_infer_session(ai_payload, hints={
                    "club_hint": club_name,
                    "psrg": bool(PSRG_PAT.search(text_blob)),
                })
                accepted = bool(ai and getattr(ai, "is_net", 0) and float(getattr(ai, "confidence", 0.0)) >= AI_MIN_CONF)
                if accepted:
                    if getattr(ai, "net_name", None) and looks_like_good_name(ai.net_name):
                        net_name = ai.net_name
                    if getattr(ai, "club_name", None):
                        club_name = ai.club_name
                    if getattr(ai, "summary", None):
                        summary_text = ai.summary
                    # normalize NCS callsign using phonetics map
                    ncs_raw = getattr(ai, "ncs_callsign", None)
                    ncs_norm = normalize_callsign_or_phonetic(ncs_raw, corr_map)
                    if ncs_norm:
                        ncs = ncs_norm
                    if AI_LOG:
                        logger.info(
                            "AI accepted: conf=%.2f name=%r club=%r ncs=%r participants=%d",
                            float(getattr(ai,"confidence",0.0)),
                            net_name, club_name, ncs, len(getattr(ai, "participants", []) or []),
                        )
                else:
                    if AI_LOG:
                        logger.info(
                            "AI skipped (accepted=%s, ai_present=%s, is_net=%s, conf=%s)",
                            accepted, bool(ai), getattr(ai, "is_net", None), getattr(ai, "confidence", None)
                        )

            # Only create a net if we have a good name
            create_net = bool(is_net and looks_like_good_name(net_name))

            if create_net and sess.start_time and sess.end_time and sess.ids:
                if not DRY_RUN:
                    net_id = insert_net_data(cur, net_name, club_name, ncs,
                                             sess.ids[0], sess.ids[-1],
                                             sess.start_time, sess.end_time,
                                             sess.duration_sec, score, summary_text)
                    link_session_transcripts(cur, net_id, sess.ids)
                    logger.info(
                        "Created net_data id=%s name=%r len=%d score=%.2f summary_len=%d",
                        net_id, net_name, len(sess.ids), score, len(summary_text or "")
                    )

                    # Persist AI operator topic descriptions, if provided by ai_backend
                    try:
                        if 'ai' in locals() and ai:
                            op_map = getattr(ai, "operator_topics_desc", {}) or {}
                            # If model returned array form only, synthesize map from topics
                            if not op_map and getattr(ai, "operator_topics", None):
                                for item in (ai.operator_topics or []):
                                    cs = (getattr(item, "callsign", None)
                                          or (isinstance(item, dict) and item.get("callsign")) or "")
                                    topics = (getattr(item, "topics", None)
                                              or (isinstance(item, dict) and item.get("topics")) or []) or []
                                    if cs and topics:
                                        op_map[str(cs).upper()] = "Topics: " + "; ".join(
                                            [str(t).strip() for t in topics if str(t).strip()][:6]
                                        )
                            inserted = 0
                            for raw_cs, desc in op_map.items():
                                insert_callsign_topic(cur, net_id, str(raw_cs), str(desc).strip(), corr_map)
                                inserted += 1
                            if inserted and AI_LOG:
                                logger.info("Stored %d operator topic descriptions into callsign_topics", inserted)
                    except Exception as e:
                        logger.warning("Failed inserting callsign_topics rows: %s", e)

                else:
                    logger.info(
                        "[DRY-RUN] Would create net %r (len=%d, score=%.2f, summary_len=%d)",
                        net_name, len(sess.ids), score, len(summary_text or "")
                    )
            elif is_net and not create_net:
                logger.info("Detected a net-like session but NO valid name yet — will rescan later.")

            # Roster & topics if we have an actual net row
            if net_id is not None:
                roster = {}
                for t in sess.transcripts:
                    calls_this_line = set(m.upper() for m in CALLSIGN_RE.findall(t.text))
                    if not calls_this_line:
                        continue
                    stripped = re.sub(r"[^A-Za-z0-9/ ]", "", t.text).strip()
                    checkin_type = "unknown"
                    low = stripped.lower()
                    if "late" in low:
                        checkin_type = "late"
                    elif "recheck" in low:
                        checkin_type = "recheck"
                    elif "proxy" in low:
                        checkin_type = "proxy"
                    elif "echolink" in low:
                        checkin_type = "echolink"
                    elif "allstar" in low:
                        checkin_type = "allstar"
                    elif IO_CHECKIN_RE.search(t.text):
                        checkin_type = "io"

                    for cs in calls_this_line:
                        ent = roster.setdefault(cs, {"first": t.timestamp, "last": t.timestamp,
                                                     "tx_count": 0, "talk_seconds": 0, "type": checkin_type})
                        ent["first"] = min(ent["first"], t.timestamp)
                        ent["last"] = max(ent["last"], t.timestamp)
                        ent["tx_count"] = int(ent["tx_count"]) + 1
                        ent["talk_seconds"] = int(ent["talk_seconds"]) + 8
                        if ent.get("type") == "unknown" and checkin_type != "unknown":
                            ent["type"] = checkin_type

                for cs, ent in roster.items():
                    if not DRY_RUN:
                        upsert_participation(cur, net_id, cs, ent["first"], ent["last"],
                                             ent["tx_count"], ent["talk_seconds"], ent["type"])

            # Per-transcript analysis (even if name missing, net_id stays NULL)
            for t in sess.transcripts:
                calls = [m.upper() for m in CALLSIGN_RE.findall(t.text)]
                topics = detect_topics(t.text)
                ncs_cand = 1 if (ncs and ncs in calls) else 0
                detected_name_for_row = net_name if create_net else None
                if not DRY_RUN:
                    upsert_transcription_analysis(cur, t, is_net, net_id,
                                                  detected_name_for_row, club_name,
                                                  ncs_cand, hits, calls, topics,
                                                  score if is_net else max(0.0, score - 0.6))

        if not DRY_RUN:
            cnx.commit()
            logger.info("Committed analysis updates.")
        else:
            logger.info("DRY-RUN complete; no DB changes made.")

    except Exception:
        logger.exception("Analyzer failed; rolling back.")
        try:
            cnx.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
            cnx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
