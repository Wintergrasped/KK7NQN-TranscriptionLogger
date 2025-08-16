#!/usr/bin/env python3
import datetime
import socket
import time
import sys

# AMI connection details
AMI_HOST = "127.0.0.1"
AMI_PORT = 5038
AMI_USER = "USERNAME"
AMI_PASS = "PASSWORD"

LOG_FILE = "/var/log/allstar_cosptt.log"

# State tracking
cos_active = False
cos_start_time = None
ptt_active = False
ptt_start_time = None

def log(message):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{now} | {message}"
    print(entry)  # Debug output
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")

def debug(msg):
    print(f"[DEBUG] {msg}")
    sys.stdout.flush()

def main():
    global cos_active, cos_start_time, ptt_active, ptt_start_time

    debug("Connecting to Asterisk AMI...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((AMI_HOST, AMI_PORT))
    debug("Connected to AMI")

    # Login
    s.sendall(f"Action: Login\r\nUsername: {AMI_USER}\r\nSecret: {AMI_PASS}\r\n\r\n".encode())
    s.sendall(b"Action: Events\r\nEventMask: on\r\n\r\n")
    debug("Login and event subscription sent")

    buffer = ""
    while True:
        data = s.recv(4096).decode(errors="ignore")
        if not data:
            debug("No data received, connection might be closed")
            break

        buffer += data
        if "\r\n\r\n" not in buffer:
            continue

        # Split complete AMI event blocks
        events = buffer.split("\r\n\r\n")
        buffer = events.pop()  # Keep incomplete part in buffer

        for event in events:
            debug(f"Received event block:\n{event}\n---")
            lower_event = event.lower()

            # COS event detection
            if "rxkeyed" in lower_event:
                if "value: 1" in lower_event:
                    if not cos_active:
                        cos_active = True
                        cos_start_time = time.time()
                        log("COS ON (RF)")
                elif "value: 0" in lower_event:
                    if cos_active:
                        duration = int(time.time() - cos_start_time)
                        cos_active = False
                        log(f"COS OFF after {duration} seconds")

            # PTT event detection
            if "txkeyed" in lower_event:
                if "value: 1" in lower_event:
                    if not ptt_active:
                        ptt_active = True
                        ptt_start_time = time.time()
                        source = "RF" if "source: radio" in lower_event else "Network"
                        log(f"PTT ON ({source})")
                elif "value: 0" in lower_event:
                    if ptt_active:
                        duration = int(time.time() - ptt_start_time)
                        ptt_active = False
                        log(f"PTT OFF after {duration} seconds")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        debug("Exiting on Ctrl+C")
