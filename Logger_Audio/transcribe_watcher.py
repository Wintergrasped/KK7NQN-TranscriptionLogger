#!/usr/bin/env python3
import os
import time
# KK7NQN Repeater Logger
# Copyright (C) 2025 Hunter Inman
#
# This file is part of the KK7NQN Repeater Logger project.
# It is licensed under the GNU General Public License v3.0.
# See the LICENSE file in the root of this repository for full terms.

import subprocess

WATCH_DIR = "/Logger_Audio/incoming"
PROCESSED_DIR = "/Logger_Audio/processed"
ERROR_DIR = "/Logger_Audio/repeater_audio/failed"

# Ensure fallback dir exists
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(ERROR_DIR, exist_ok=True)

while True:
    files = [f for f in os.listdir(WATCH_DIR) if f.endswith(".wav")]
    for f in files:
        full_path = os.path.join(WATCH_DIR, f)

        # Skip zero-byte or unreadable files
        if not os.path.isfile(full_path) or os.path.getsize(full_path) < 1000:
            print(f"Skipping invalid or empty file: {f}")
            continue

        print(f"Processing {f}")
        try:
            subprocess.run(
                ["python3", "/Logger_Audio/transcribe_and_log.py", full_path],
                check=True,
                timeout=1500  # timeout to prevent Whisper hanging forever
            )
            os.rename(full_path, os.path.join(PROCESSED_DIR, f))
        except subprocess.TimeoutExpired:
            print(f"Timeout expired for {f}. Moving to failed directory.")
            os.rename(full_path, os.path.join(ERROR_DIR, f))
        except subprocess.CalledProcessError as e:
            print(f"Error processing {f}: {e}. Moving to failed directory.")
            os.rename(full_path, os.path.join(ERROR_DIR, f))
        except Exception as e:
            print(f"Unexpected error on {f}: {e}")
            os.rename(full_path, os.path.join(ERROR_DIR, f))

    time.sleep(5)
