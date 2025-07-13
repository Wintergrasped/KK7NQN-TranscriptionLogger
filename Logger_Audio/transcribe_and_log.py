# KK7NQN Repeater Logger
# Copyright (C) 2025 Hunter Inman
#
# This file is part of the KK7NQN Repeater Logger project.
# It is licensed under the GNU General Public License v3.0.
# See the LICENSE file in the root of this repository for full terms.


import sys
import os
import whisper
import datetime
import mysql.connector

# Check if filename is passed
if len(sys.argv) < 2:
    print("Usage: python3 transcribe_and_log.py <filename>")
    sys.exit(1)

audio_file = sys.argv[1]
basename = os.path.basename(audio_file)
timestamp_str = os.path.splitext(basename)[0]  # Strip .wav
from datetime import datetime
timestamp2 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Load model
model = whisper.load_model("medium.en")
result = model.transcribe(audio_file)

# Extract transcript text
transcript = result["text"]

# Connect to DB (replace with your actual credentials)
db = mysql.connector.connect(
    host="localhost",
    user="repeateruser",
    password="changeme123",
    database="repeater"
)

cursor = db.cursor()

# Insert into database
cursor.execute("""
    INSERT INTO transcriptions (filename, timestamp, transcription)
    VALUES (%s, %s, %s)
""", (basename, timestamp2, transcript))

db.commit()
cursor.close()
db.close()

print(f"Transcribed and logged: {basename}")


