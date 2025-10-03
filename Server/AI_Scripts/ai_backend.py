# ===============================
# File: /home/wintergrasped/repeater_audio/ai_backend.py
# ===============================
"""
OpenAI backend for Transcript Analyzer
- Handles HTTPError with Retry-After and backoff
- Aggressively compacts prompt to reduce token count
- Accepts BOTH operator_topics styles:
    * dict {callsign: "freeform description"}
    * array [{callsign, topics: [...]}, ...]
  and always returns operator_topics_desc: Dict[callsign, description]
"""
from __future__ import annotations
import os, json, logging, time, random, re
from typing import Optional, List, Dict, Any, Union
import urllib.request, urllib.error

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:  # minimal fallback
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
        def model_dump(self):
            return self.__dict__
    def Field(*a, **k):
        return None

# --------- Config ---------
AI_ENABLE = os.getenv("AI_ENABLE", "1") == "1"
AI_MODEL = os.getenv("AI_MODEL", "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4")
AI_BACKUP_MODEL = os.getenv("AI_BACKUP_MODEL", "gpt-4o-mini")
AI_API_KEY = os.getenv("AI_API_KEY", "sk-Not-Used-For-Local")
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://192.168.0.104:8001/v1").rstrip("/")
AI_BACKUP_BASE_URL = os.getenv("AI_BACKUP_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "60"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "900"))
AI_MAX_PROMPT_CHARS = 62000
AI_LOG = os.getenv("AI_LOG", "1") == "1"
AI_BACKUP = 0  # (currently unused, kept for compatibility)

_logger = logging.getLogger("ai_backend")
if not _logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --------- Schema ---------
class OperatorTopics(BaseModel):
    callsign: str = Field(description="Ham callsign")
    topics: List[str] = Field(default_factory=list)

class AiNetInference(BaseModel):
    net_name: Optional[str] = Field(default=None)
    club_name: Optional[str] = Field(default=None)
    ncs_callsign: Optional[str] = Field(default=None)
    participants: List[str] = Field(default_factory=list)
    net_topics: List[str] = Field(default_factory=list)
    operator_topics: List[OperatorTopics] = Field(default_factory=list)
    summary: Optional[str] = Field(default=None)
    is_net: int = Field(default=0)
    confidence: float = Field(default=0.0)
    reasons: List[str] = Field(default_factory=list)
    # Always present: callsign -> one-line description
    operator_topics_desc: Dict[str, str] = Field(default_factory=dict)

CALLSIGN_RE = re.compile(r"\b([A-KN-PR-Z]{1,2}\d{1,4}[A-Z]{1,3})(?:\/[A-Z0-9]+)?\b", re.I)

# --------- Prompting ---------
SYSTEM_PROMPT = (
    "You are a ham radio net analyzer. Analyze the provided ham-radio transcript(s) and return JSON with: "
    "net_name, club_name, ncs_callsign, participants (callsigns only), net_topics (short list), "
    "operator_topics (either an object mapping callsign->description OR an array of {callsign, topics[]} "
    "with 1–5 concise topics per operator), summary (2–3 sentences), is_net (0/1), confidence (0..1), reasons."
)

USER_TEMPLATE = (
    "TRANSCRIPTS (JSON lines):\n{lines}\n\n"
    "HINTS(JSON): {hints}\n\n"
    "Return ONLY JSON with keys: net_name, club_name, ncs_callsign, participants, net_topics, operator_topics, "
    "summary, is_net, confidence, reasons."
)

# --------- Normalization & Compaction ---------
KEEP_PATTERNS = [
    r"\bnet\b", r"\bnet control\b", r"\bcheck[- ]?ins?\b", r"\blate check[- ]?ins?\b",
    r"\broll call\b", r"\bclosing\b", r"\bdirected net\b"
]
_KEEP_RE = re.compile("|".join(KEEP_PATTERNS), re.I)

def _normalize_rows(transcripts: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if isinstance(transcripts, str):
        return [{"id": None, "ts": None, "text": transcripts[:20000]}]
    out: List[Dict[str, Any]] = []
    for t in transcripts[:6000]:
        out.append({
            "id": t.get("id"),
            "ts": t.get("timestamp"),
            "text": (t.get("text") or "")[:1000],
        })
    return out

def _compact_rows(rows: List[Dict[str, Any]]) -> str:
    kept: List[str] = []
    for row in rows:
        txt = (row.get("text") or "").strip()
        if not txt:
            continue
        if _KEEP_RE.search(txt) or CALLSIGN_RE.search(txt):
            kept.append(json.dumps({"id": row.get("id"), "ts": row.get("ts"), "text": txt[:400]}, ensure_ascii=False))
    if not kept:
        for row in rows[:200]:
            txt = (row.get("text") or "").strip()
            if txt:
                kept.append(json.dumps({"id": row.get("id"), "ts": row.get("ts"), "text": txt[:300]}, ensure_ascii=False))
    blob = "\n".join(kept)
    if len(blob) > AI_MAX_PROMPT_CHARS:
        blob = blob[:AI_MAX_PROMPT_CHARS]
    if AI_LOG:
        _logger.info("AI payload compacted to %d chars (%d kept lines)", len(blob), len(kept))
    return blob

# --------- HTTP layer ---------
def _http_post_chat(body: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{AI_BASE_URL}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_API_KEY}" if AI_API_KEY else "",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            retry_after_hdr = e.headers.get("Retry-After") if hasattr(e, "headers") else None
            setattr(e, "retry_after", float(retry_after_hdr) if retry_after_hdr and str(retry_after_hdr).isdigit() else None)
        except Exception:
            setattr(e, "retry_after", None)
        try:
            snippet = e.read().decode("utf-8", errors="ignore")[:400]
        except Exception:
            snippet = ""
        setattr(e, "body_snippet", snippet)
        raise

def _http_post_chat_backup(body: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{AI_BACKUP_BASE_URL}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_API_KEY}" if AI_API_KEY else "",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            retry_after_hdr = e.headers.get("Retry-After") if hasattr(e, "headers") else None
            setattr(e, "retry_after", float(retry_after_hdr) if retry_after_hdr and str(retry_after_hdr).isdigit() else None)
        except Exception:
            setattr(e, "retry_after", None)
        try:
            snippet = e.read().decode("utf-8", errors="ignore")[:400]
        except Exception:
            snippet = ""
        setattr(e, "body_snippet", snippet)
        raise

def _call_openai_chat(messages: List[Dict[str, str]]) -> Optional[str]:
    body = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": AI_MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            data = _http_post_chat(body)
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            code = getattr(e, 'code', None)
            ra = getattr(e, 'retry_after', None)
            if AI_LOG:
                _logger.error("OpenAI HTTPError %s (attempt %d): %s", code, attempt, getattr(e, 'body_snippet', '') )
            if attempt >= max_attempts:
                return None
            if code == 429 and ra:
                time.sleep(ra)
            else:
                time.sleep((1.5 ** attempt) + random.uniform(0, 0.6))
            continue
        except Exception as e:
            if AI_LOG:
                _logger.error("OpenAI call error (attempt %d): %s", attempt, e)
            if attempt >= max_attempts:
                return None
            time.sleep((1.5 ** attempt) + random.uniform(0, 0.6))
            continue

def _call_openai_chat_backup(messages: List[Dict[str, str]]) -> Optional[str]:
    body = {
        "model": AI_BACKUP_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": AI_MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            data = _http_post_chat_backup(body)
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            code = getattr(e, 'code', None)
            ra = getattr(e, 'retry_after', None)
            if AI_LOG:
                _logger.error("OpenAI HTTPError %s (attempt %d): %s", code, attempt, getattr(e, 'body_snippet', '') )
            if attempt >= max_attempts:
                return None
            if code == 429 and ra:
                time.sleep(ra)
            else:
                time.sleep((1.5 ** attempt) + random.uniform(0, 0.6))
            continue
        except Exception as e:
            if AI_LOG:
                _logger.error("OpenAI call error (attempt %d): %s", attempt, e)
            if attempt >= max_attempts:
                return None
            time.sleep((1.5 ** attempt) + random.uniform(0, 0.6))
            continue

# --------- Public API ---------
def ai_infer_session(transcripts: Union[str, List[Dict[str, Any]]], hints: Optional[Dict[str, Any]] = None) -> Optional[AiNetInference]:
    if AI_LOG:
        _logger.info("AI_ENABLE=%s AI_API_KEY len=%d", AI_ENABLE, len(AI_API_KEY or ""))
    if not AI_ENABLE or not AI_API_KEY:
        if AI_LOG:
            _logger.info("AI disabled or missing API key; skipping AI inference.")
        return None

    rows = _normalize_rows(transcripts)
    compact = _compact_rows(rows)
    hints = hints or {}
    user = USER_TEMPLATE.format(lines=compact, hints=json.dumps(hints))

    if AI_LOG:
        _logger.info("AI call → model=%s, len(payload)=%d", AI_MODEL, len(compact))

    content = _call_openai_chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ])
    if not content:
        if AI_LOG:
            _logger.warning("AI returned no content (Trying Backup).")
        return ai_infer_session_backup(transcripts, hints)

    raw = content.strip()
    if raw.startswith("```"):
        start = raw.find("{"); end = raw.rfind("}")
        raw = raw[start:end+1] if start != -1 and end != -1 else raw

    # Parse JSON
    try:
        obj = json.loads(raw)
    except Exception:
        start = raw.find("{"); end = raw.rfind("}")
        try:
            obj = json.loads(raw[start:end+1]) if start != -1 and end != -1 else None
        except Exception:
            obj = None
    if not obj:
        if AI_LOG:
            _logger.warning("AI response could not be parsed as JSON (Trying Backup). Raw head: %r", raw[:200])
        return ai_infer_session_backup(transcripts, hints)

    # Defaults
    obj.setdefault("participants", [])
    obj.setdefault("net_topics", [])
    obj.setdefault("operator_topics", [])
    obj.setdefault("reasons", [])
    obj.setdefault("is_net", 0)
    obj.setdefault("confidence", 0.0)

    # participants → valid callsigns only
    participants: List[str] = []
    for cs in obj.get("participants", [])[:200]:
        m = CALLSIGN_RE.match(str(cs).upper().strip())
        if m:
            participants.append(m.group(1).upper())
    seen: set = set()
    obj["participants"] = [x for x in participants if not (x in seen or seen.add(x))][:150]

    # Build operator_topics_desc (works for both styles)
    op_desc: Dict[str, str] = {}
    raw_ops = obj.get("operator_topics")

    if isinstance(raw_ops, dict):
        # direct map {callsign: "desc"}
        for k, v in list(raw_ops.items())[:200]:
            ks = str(k).upper().strip()
            vs = str(v).strip()
            if ks and vs:
                op_desc[ks] = vs

    elif isinstance(raw_ops, list):
        # array form [{callsign, topics: [...]}, ...]
        for item in raw_ops:
            try:
                cs = str(item.get("callsign", "")).upper().strip()
                if not CALLSIGN_RE.match(cs):
                    continue
                topics = [str(t).strip() for t in (item.get("topics") or []) if str(t).strip()]
                desc = (item.get("description") or item.get("summary") or "").strip()
                if not desc and topics:
                    desc = "Topics: " + "; ".join(topics[:6])
                if desc:
                    op_desc[cs] = desc
            except Exception:
                continue

    # Keep also the normalized list form for completeness
    norm_ops: List[OperatorTopics] = []
    if isinstance(raw_ops, list):
        for item in raw_ops:
            try:
                cs = str(item.get("callsign", "")).upper().strip()
                if not CALLSIGN_RE.match(cs):
                    continue
                topics = [str(t).strip() for t in (item.get("topics") or []) if str(t).strip()]
                if topics:
                    norm_ops.append(OperatorTopics(callsign=cs, topics=topics[:8]))
            except Exception:
                continue

    def _to_dict(m):
        md = getattr(m, "model_dump", None)
        if callable(md):
            return md()
        dd = getattr(m, "dict", None)
        if callable(dd):
            return dd()
        return {"callsign": getattr(m, "callsign", None), "topics": getattr(m, "topics", [])}

    obj["operator_topics"] = [_to_dict(x) for x in norm_ops][:80]
    obj["operator_topics_desc"] = op_desc

    # Build pydantic (or fallback)
    try:
        res = AiNetInference(**obj)
        if AI_LOG:
            _logger.info("AI parsed ok: name=%r club=%r ncs=%r conf=%.2f participants=%d op_desc=%d",
                         res.net_name, res.club_name, res.ncs_callsign, res.confidence,
                         len(res.participants or []), len(op_desc))
        return res
    except Exception as e:
        if AI_LOG:
            _logger.error("AI response final parsing failed after normalization: %s | keys=%s", e, list(obj.keys()))
        class _Simple: pass
        simple = _Simple()
        for k in ["net_name","club_name","ncs_callsign","participants","net_topics",
                  "operator_topics","summary","is_net","confidence","reasons","operator_topics_desc"]:
            setattr(simple, k, obj.get(k, None))
        if not isinstance(getattr(simple,"participants",[]), list): simple.participants = []
        if not isinstance(getattr(simple,"operator_topics",[]), list): simple.operator_topics = []
        if not isinstance(getattr(simple,"operator_topics_desc",{}), dict): simple.operator_topics_desc = op_desc
        try: simple.is_net = int(bool(simple.is_net))
        except Exception: simple.is_net = 0
        try: simple.confidence = float(simple.confidence)
        except Exception: simple.confidence = 0.0
        return simple

def ai_infer_session_backup(transcripts: Union[str, List[Dict[str, Any]]], hints: Optional[Dict[str, Any]] = None) -> Optional[AiNetInference]:
    if AI_LOG:
        _logger.info("AI_ENABLE=%s AI_API_KEY len=%d", AI_ENABLE, len(AI_API_KEY or ""))
    if not AI_ENABLE or not AI_API_KEY:
        if AI_LOG:
            _logger.info("AI disabled or missing API key; skipping AI inference.")
        return None

    rows = _normalize_rows(transcripts)
    compact = _compact_rows(rows)
    hints = hints or {}
    user = USER_TEMPLATE.format(lines=compact, hints=json.dumps(hints))

    if AI_LOG:
        _logger.info("AI call (backup) → model=%s, len(payload)=%d", AI_BACKUP_MODEL, len(compact))

    content = _call_openai_chat_backup([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ])
    if not content:
        if AI_LOG:
            _logger.warning("Backup AI returned no content.")
        return None

    raw = content.strip()
    if raw.startswith("```"):
        start = raw.find("{"); end = raw.rfind("}")
        raw = raw[start:end+1] if start != -1 and end != -1 else raw

    # Parse JSON
    try:
        obj = json.loads(raw)
    except Exception:
        start = raw.find("{"); end = raw.rfind("}")
        try:
            obj = json.loads(raw[start:end+1]) if start != -1 and end != -1 else None
        except Exception:
            obj = None
    if not obj:
        if AI_LOG:
            _logger.warning("Backup AI response could not be parsed as JSON. Raw head: %r", raw[:200])
        return None

    # Defaults
    obj.setdefault("participants", [])
    obj.setdefault("net_topics", [])
    obj.setdefault("operator_topics", [])
    obj.setdefault("reasons", [])
    obj.setdefault("is_net", 0)
    obj.setdefault("confidence", 0.0)

    # participants → valid callsigns only
    participants: List[str] = []
    for cs in obj.get("participants", [])[:200]:
        m = CALLSIGN_RE.match(str(cs).upper().strip())
        if m:
            participants.append(m.group(1).upper())
    seen: set = set()
    obj["participants"] = [x for x in participants if not (x in seen or seen.add(x))][:150]

    # Build operator_topics_desc (works for both styles)
    op_desc: Dict[str, str] = {}
    raw_ops = obj.get("operator_topics")

    if isinstance(raw_ops, dict):
        for k, v in list(raw_ops.items())[:200]:
            ks = str(k).upper().strip()
            vs = str(v).strip()
            if ks and vs:
                op_desc[ks] = vs
    elif isinstance(raw_ops, list):
        for item in raw_ops:
            try:
                cs = str(item.get("callsign", "")).upper().strip()
                if not CALLSIGN_RE.match(cs):
                    continue
                topics = [str(t).strip() for t in (item.get("topics") or []) if str(t).strip()]
                desc = (item.get("description") or item.get("summary") or "").strip()
                if not desc and topics:
                    desc = "Topics: " + "; ".join(topics[:6])
                if desc:
                    op_desc[cs] = desc
            except Exception:
                continue

    norm_ops: List[OperatorTopics] = []
    if isinstance(raw_ops, list):
        for item in raw_ops:
            try:
                cs = str(item.get("callsign", "")).upper().strip()
                if not CALLSIGN_RE.match(cs):
                    continue
                topics = [str(t).strip() for t in (item.get("topics") or []) if str(t).strip()]
                if topics:
                    norm_ops.append(OperatorTopics(callsign=cs, topics=topics[:8]))
            except Exception:
                continue

    def _to_dict(m):
        md = getattr(m, "model_dump", None)
        if callable(md):
            return md()
        dd = getattr(m, "dict", None)
        if callable(dd):
            return dd()
        return {"callsign": getattr(m, "callsign", None), "topics": getattr(m, "topics", [])}

    obj["operator_topics"] = [_to_dict(x) for x in norm_ops][:80]
    obj["operator_topics_desc"] = op_desc

    try:
        res = AiNetInference(**obj)
        if AI_LOG:
            _logger.info("Backup AI parsed ok: name=%r club=%r ncs=%r conf=%.2f participants=%d op_desc=%d",
                         res.net_name, res.club_name, res.ncs_callsign, res.confidence,
                         len(res.participants or []), len(op_desc))
        return res
    except Exception as e:
        if AI_LOG:
            _logger.error("Backup AI response final parsing failed after normalization: %s | keys=%s", e, list(obj.keys()))
        class _Simple: pass
        simple = _Simple()
        for k in ["net_name","club_name","ncs_callsign","participants","net_topics",
                  "operator_topics","summary","is_net","confidence","reasons","operator_topics_desc"]:
            setattr(simple, k, obj.get(k, None))
        if not isinstance(getattr(simple,"participants",[]), list): simple.participants = []
        if not isinstance(getattr(simple,"operator_topics",[]), list): simple.operator_topics = []
        if not isinstance(getattr(simple,"operator_topics_desc",{}), dict): simple.operator_topics_desc = op_desc
        try: simple.is_net = int(bool(simple.is_net))
        except Exception: simple.is_net = 0
        try: simple.confidence = float(simple.confidence)
        except Exception: simple.confidence = 0.0
        return simple

def should_call_ai(is_net_score: float, regex_name: Optional[str]) -> bool:
    if is_net_score >= 1.0 and not regex_name:
        return True
    if is_net_score >= 0.8 and (not regex_name or len(regex_name) < 5):
        return True
    return False
