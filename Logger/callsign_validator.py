#!/usr/bin/env python3

import mysql.connector
import requests
import re
import xml.etree.ElementTree as ET

# ----------------------------
# Config
# ----------------------------

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'repeateruser',
    'password': 'changeme123',
    'database': 'repeater'
}

QRZ_USERNAME = 'YOUR_QRZ_USERNAME'
QRZ_PASSWORD = 'YOUR_QRZ_PASSWORD'
QRZ_SESSION_KEY = None

# ----------------------------
# Database Helpers
# ----------------------------

def get_mysql_connection():
    return mysql.connector.connect(**DB_CONFIG)

def get_unvalidated_callsigns():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT callsign FROM callsigns WHERE validated = 0")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r[0] for r in rows]

def update_callsign_validated(callsign):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE callsigns SET validated = 1 WHERE callsign = %s", (callsign,))
    conn.commit()
    cursor.close()
    conn.close()

def delete_callsign(callsign):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM callsigns WHERE callsign = %s", (callsign,))
    conn.commit()
    cursor.close()
    conn.close()

# ----------------------------
# QRZ API Session Handling
# ----------------------------

def get_qrz_session_key():
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

def check_callsign_qrz(callsign, retries=1):
    """
    Validates a callsign using QRZ API. Only retries if the session key is explicitly invalid.
    """
    global QRZ_SESSION_KEY

    for attempt in range(retries + 3):
        if not QRZ_SESSION_KEY:
            QRZ_SESSION_KEY = get_qrz_session_key()
            if not QRZ_SESSION_KEY:
                print(f"[QRZ] Could not get session key.")
                return False

        url = f"https://xmldata.qrz.com/xml/current/?s={QRZ_SESSION_KEY}&callsign={callsign}"
        try:
            r = requests.get(url, timeout=5)
            root = ET.fromstring(r.text)

            # Check for error
            session = root.find('{http://xmldata.qrz.com}Session')
            error = session.find('{http://xmldata.qrz.com}Error') if session is not None else None

            if error is not None:
                error_msg = error.text.strip()
                print(f"[QRZ] Error from QRZ: {error_msg}")

                if 'Invalid session key' in error_msg:
                    QRZ_SESSION_KEY = None  # Trigger re-login
                    continue  # Retry
                else:
                    return False  # Actual callsign or account error

            # If we got this far and there's no <Error>, it's a valid call
            return True

        except Exception as e:
            print(f"[QRZ] Exception checking {callsign}: {e}")
            return False

    print(f"[QRZ] Max retries exceeded for {callsign}")
    return False

# ----------------------------
# Main Runner
# ----------------------------

def run_validation_cleanup():
    callsigns = get_unvalidated_callsigns()
    print(f"[🧹] Found {len(callsigns)} unvalidated callsigns")

    for cs in callsigns:
        print(f"[...] Checking {cs}")
        if check_callsign_qrz(cs):
            print(f"[] {cs} validated!")
            update_callsign_validated(cs)
        else:
            print(f"[] {cs} is invalid, removing...")
            delete_callsign(cs)

# ----------------------------
# Entry Point
# ----------------------------

if __name__ == '__main__':
    run_validation_cleanup()
