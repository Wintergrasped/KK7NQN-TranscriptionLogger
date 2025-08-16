#!/usr/bin/env python3
import os
import time
import subprocess

WATCH_DIR = "DIRECTORY_PATH/incoming"
PROCESSED_DIR = "DIRECTORY_PATH/processed"
ERROR_DIR = "DIRECTORY_PATH/failed"
TRANSCRIBE_SCRIPT = "DIRECTORY_PATH/transcribe_and_log.py"

# Ensure output directories exist
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(ERROR_DIR, exist_ok=True)

def is_valid_audio(file_path):
    return os.path.isfile(file_path) and os.path.getsize(file_path) > 1000

while True:
    files = [f for f in os.listdir(WATCH_DIR) if f.lower().endswith(".wav")]
    for f in files:
        full_path = os.path.join(WATCH_DIR, f)

        if not is_valid_audio(full_path):
            print(f"[SKIP] {f} is invalid or empty.")
            continue

        print(f"[INFO] Processing {f}")
        try:
            result = subprocess.run(
                ["python3", TRANSCRIBE_SCRIPT, full_path],
                check=True,
                timeout=1500,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            print(f"[SUCCESS] {f} processed.")
            os.rename(full_path, os.path.join(PROCESSED_DIR, f))

        except subprocess.TimeoutExpired:
            print(f"[TIMEOUT] {f} took too long, moving to failed.")
            os.rename(full_path, os.path.join(ERROR_DIR, f))

        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to process {f}")
            print("  STDOUT:", e.stdout.decode(errors='ignore') if e.stdout else "(empty)")
            print("  STDERR:", e.stderr.decode(errors='ignore') if e.stderr else "(empty)")
            os.rename(full_path, os.path.join(ERROR_DIR, f))

        except Exception as e:
            print(f"[UNEXPECTED] Error with {f}: {e}")
            os.rename(full_path, os.path.join(ERROR_DIR, f))

    time.sleep(5)
