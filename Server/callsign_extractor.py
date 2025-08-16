#!/usr/bin/env python3

import re
import mysql.connector
import requests
from datetime import datetime
import time
import string

# ----------------------------
# Config
# ----------------------------

DB_CONFIG = {
    'host': 'HOSTNAME / IP',
    'user': 'USER',
    'password': 'PASSWORD',
    'database': 'DATABASE'
}

USE_QRZ_VALIDATION = False #Use QRZ XML API to validate Callsigns?
QRZ_USERNAME = 'USERNAME'
QRZ_PASSWORD = 'PASSWORD'
QRZ_SESSION_KEY = None  # will be dynamically set
currentID = 0

# ----------------------------
# Database Helpers
# ----------------------------

def get_mysql_connection():
    return mysql.connector.connect(**DB_CONFIG)

def load_corrections():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT `detect`, `correct` FROM corrections")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {d.strip().lower(): c.strip().lower() for d, c in rows}

def get_recent_transcripts(limit=900):
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
    SELECT * FROM transcriptions
    WHERE processed = 0
    ORDER BY id ASC
""")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

# ----------------------------
# Callsign Insert/Update Logic
# ----------------------------

def insert_or_update_callsign(callsign, validated):
    now = datetime.now()
    conn = get_mysql_connection()
    cursor = conn.cursor()

    # Check for existing entry
    cursor.execute("SELECT id FROM callsigns WHERE callsign = %s", (callsign,))
    result = cursor.fetchone()
    log_callsign_sighting(callsign, currentID)

    if result:
        # Update last_seen
        cursor.execute(
            """
            UPDATE callsigns
            SET last_seen = %s,
                seen_count = seen_count + 1
            WHERE callsign = %s
            """,
            (now, callsign)
        )
    else:
        # Insert new
        cursor.execute(
            """
            INSERT INTO callsigns (callsign, validated, first_seen, last_seen)
            VALUES (%s, %s, %s, %s)
            """,
            (callsign, int(validated), now, now)
        )

    conn.commit()
    cursor.close()
    conn.close()

# ----------------------------
# QRZ Session Management
# ----------------------------

def get_qrz_session_key():
    """
    Log in to QRZ and return a valid session key.
    """
    url = f"https://xmldata.qrz.com/xml/current/?username={QRZ_USERNAME}&password={QRZ_PASSWORD}"
    try:
        response = requests.get(url, timeout=5)
        if '<Session>' in response.text:
            match = re.search(r'<Key>(.*?)</Key>', response.text)
            if match:
                print("[QRZ] New session key acquired.")
                return match.group(1)
        print("[QRZ] Failed to get session key. Response:", response.text)
    except Exception as e:
        print(f"[QRZ] Exception while getting session key: {e}")
    return None

def check_callsign_qrz(callsign, max_retries=2):
    """
    Validate a callsign via QRZ lookup with limited retries.
    """
    global QRZ_SESSION_KEY

    for attempt in range(max_retries):
        if not QRZ_SESSION_KEY:
            QRZ_SESSION_KEY = get_qrz_session_key()
            if not QRZ_SESSION_KEY:
                print("[QRZ] Could not obtain session key.")
                return False

        url = f"https://xmldata.qrz.com/xml/current/?s={QRZ_SESSION_KEY}&callsign={callsign}"
        try:
            r = requests.get(url, timeout=5)
            if "<Session>" in r.text and "<Error>" in r.text:
                print(f"[QRZ] Session expired. Attempt {attempt+1}/{max_retries}. Renewing...")
                QRZ_SESSION_KEY = None  # force new session
                continue
            return callsign in r.text
        except Exception as e:
            print(f"[QRZ] Lookup error for {callsign}: {e}")
            return False

    print(f"[QRZ] Failed after {max_retries} retries for {callsign}.")
    return False



def is_callsign_validated_locally(callsign):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT validated FROM callsigns WHERE callsign = %s", (callsign,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result and result[0] == 1:
        return True
    return False
# ----------------------------
# Text & Callsign Processing
# ----------------------------

def apply_corrections(transcript, correction_map):
    words = transcript.lower().split()
    corrected = []
    for word in words:
        cleaned = word.translate(str.maketrans('', '', string.punctuation))
        corrected.append(correction_map.get(cleaned, cleaned))
    return ' '.join(corrected)

def rejoin_potential_callsigns(corrected_text):
    words = corrected_text.split()
    rejoined = []
    buffer = []

    def flush_buffer():
        if buffer:
            rejoined.append(''.join(buffer))
            buffer.clear()

    for word in words:
        if len(word) == 1 or (len(word) == 2 and word.isdigit()):
            buffer.append(word)
        else:
            flush_buffer()
            rejoined.append(word)
    flush_buffer()

    return ' '.join(rejoined)

def extract_callsigns_smart(text):
    words = text.lower().translate(str.maketrans('', '', string.punctuation)).split()
    candidates = set()
    #pattern = r'^[A-Z]{1,2}\d{1,2}[A-Z]{1,4}$'
    pattern = r'^[A-Z]{1,2}\d[A-Z]{1,4}$'

    for i in range(len(words)):
    
        if re.fullmatch(pattern, words[i]):
            candidates.add(words[i])
    
        for window in range(2, 7):
            chunk = words[i:i+window]
            joined = ''.join(chunk).upper()
            if re.fullmatch(pattern, joined):
                candidates.add(joined)
                
        for size in range(2, 7):
            chunk = ''.join(words[i:i+size])
            if any(c.isdigit() for c in chunk) and re.fullmatch(pattern, chunk):
                candidates.add(chunk)

    for word in words:
        joined = word.upper()
        if re.fullmatch(pattern, joined):
            candidates.add(joined)

    for i in range(len(words)-1):
        joined = (words[i] + words[i+1]).upper()
        if re.fullmatch(pattern, joined):
            candidates.add(joined)

    return list(candidates)

def mark_transcript_processed(transcript_id):
    global currentID
    currentID = transcript_id
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE transcriptions SET processed = 1 WHERE id = %s", (transcript_id,))
    conn.commit()
    cursor.close()
    conn.close()

def process_transcript_entry(entry, correction_map):
    corrected = apply_corrections(entry['transcription'], correction_map)
    rejoined = rejoin_potential_callsigns(corrected)
    raw_callsigns = extract_callsigns_smart(rejoined)

    results = []
    for cs in raw_callsigns:
        cs_upper = cs.upper()

        if is_callsign_validated_locally(cs_upper):
            validated = 1
            print(f"[CACHE HIT] {cs_upper} already validated in DB, skipping QRZ")
        elif USE_QRZ_VALIDATION:
            validated = 1 if check_callsign_qrz(cs_upper) else 0
            print(f"[QRZ LOOKUP] {cs_upper} → {'VALID' if validated else 'NOT FOUND'}")
        else:
            validated = 0

        insert_or_update_callsign(cs_upper, validated)
        results.append((cs_upper, validated))

    return {
        'id': entry['id'],
        'filename': entry['filename'],
        'corrected_text': corrected,
        'rejoined_text': rejoined,
        'callsigns': results
    }

def log_callsign_sighting(callsign, transcript_id):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO callsign_log (callsign, transcript_id) VALUES (%s, %s)",
        (callsign, transcript_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

# ----------------------------
# Batch Runner
# ----------------------------

def run_batch():
    print("\n[🔎] Callsign Extractor + Logger\n")
    corrections = load_corrections()
    transcripts = get_recent_transcripts(limit=900)

    for row in transcripts:
        result = process_transcript_entry(row, corrections)
        mark_transcript_processed(row['id'])
        print(f" File: {result['filename']} (ID: {result['id']})")
        print(f" Corrected: {result['corrected_text']}")
        for cs, valid in result['callsigns']:
            print(f" {cs} → {'VALID' if valid else 'UNVERIFIED'}")
        print("-" * 50)

# ----------------------------
# Run Once
# ----------------------------

if __name__ == '__main__':
    run_batch()
    # For looped use:
    # while True:
    #     run_batch()
    #     time.sleep(60)
