Live Example setup at https://kk7nqn.net
---
# 📻 SDR Repeater Logger & Transcription System

This project is a modular SDR-based system for capturing, transcribing, logging, and monitoring amateur radio repeater activity. It uses an RTL-SDR receiver, Whisper for transcription, Flask for web/API serving, and QRZ for call sign validation.

## 🎯 System Overview

### 🔊 `LoggerAudio/`

#### `Audio_Capture_Loop.sh`
- **Role**: Core audio capture loop using `rtl_fm` or `sox`.
- **Function**: Records repeater audio via RTL-SDR and saves `.wav` files into the `incoming/` directory.
- **Configuration**: Set **frequency** and **file output paths** via variables at the top of the script.

#### `Transcribe_Watcher.py`
- **Role**: Watches for new audio files and transcribes them.
- **Function**: Auto-runs `Transcribe_And_Log.py` on new `.wav` files.
- **Behavior**:
  - Moves bad or empty files to `failed/`
  - Processes valid ones and moves them to `processed/`

---

### 🧠 `Logger/`

#### `CallSign_Extractor.py`
- **Role**: Searches transcriptions for amateur call signs.
- **Function**: Pulls from the transcription log and applies phonetic and fuzzy matching to extract likely call signs.

#### `CallSign_Validator.py`
- **Role**: Verifies callsigns with [QRZ XML API](https://www.qrz.com/docs/xml).
- **Function**: Validates all unconfirmed call signs and removes invalid ones from the database.
- **Requires**: A QRZ API key.

#### `System_Status.py`
- **Role**: Displays real-time system health.
- **Function**: Flask app that shows CPU usage, temperature, RAM, etc.

#### `Temp_Receiver.py`
- **Role**: Accepts temperature sensor data via POST.
- **Function**: Flask app listening for temperature updates from remote sensors or repeater hosts.

---

### 🌐 `Web/`

#### `Dashboard_API.py`
- **Role**: Main Flask backend.
- **Function**: Exposes REST API endpoints to serve:
  - Temperature data
  - System stats
  - Transcriptions and call logs
- **Default Port**: 80

#### `index.html`
- **Role**: Frontend dashboard.
- **Function**: Visual interface to view all system activity:
  - Real-time logs
  - Graphs (e.g., temperature history)
  - Call sign log & verification status

---

## 🛠️ Setup Instructions

> ⚠️ This is an early development version. Automation and packaging are coming soon.

# KK7NQN Transcription Service Node (TSN) – Install & Setup Guide

This guide explains how to set up a **basic Transcription Node (TSN)** for AllStarLink. The TSN captures audio from AllStar hub connections, transcribes it using Whisper, and logs results into a MySQL database. Optional support is included for callsign extraction with QRZ XML API validation.

> ⚠️ This guide assumes a Linux system (such as a Raspberry Pi or mini-PC) with AllStarLink and Python installed.

---

## 📦 System Overview

| Component             | Purpose                              |
|----------------------|--------------------------------------|
| AllStarLink Hub Node | Receives remote audio (no RF/COS)    |
| Whisper              | Transcribes WAVs to text             |
| MySQL                | Stores transcripts and metadata      |
| Python Scripts       | Handles file watch, transcription    |
| QRZ Integration      | (Optional) Validates callsigns       |

---

## 🛠️ Installation Steps

### 1. Install AllStarLink and Set Up as Hub

Install using the official installer:

```bash
curl -fsSL https://raw.githubusercontent.com/AllStarLink/installer/master/install-allstar.sh | sh
```

Configure the system as a **hub node only** — do not set up a radio interface.

---

### 2. Enable PTT-Based Recording in Asterisk

Edit the following files:

- `rpt.conf`: Enable recording and set the archive directory.
- `extensions.conf`: Modify recording logic to trigger on **PTT start/end**, not COS.

> 🧪 Example files can be found in the `TSN/AllStar-CONF/` directory of this repository.

---

### 3. Edit `push-taas-wavs.sh`

Set the following variables:

```bash
WATCH_DIR="/var/log/asterisk/transcripts"
REMOTE_HOST="192.168.1.100"
REMOTE_USER="tsnuser"
REMOTE_DIR="/home/tsnuser/incoming"
```

This script monitors for `.wav` files and pushes them to your transcription server over SFTP.

---

### 4. Autostart `push-taas-wavs.sh` (Optional)

You can launch this script on boot using:

- `systemd`
- `cron @reboot`
- Or manually (for testing)

---

### 5. Copy Scripts to Transcription Server

On your transcription server, place the following Python scripts:

- `transcribe_watcher.py`
- `transcribe_and_log.py`

---

### 6. Configure `transcribe_watcher.py`

Edit:

```python
WATCH_DIR = "/home/tsnuser/incoming"
```

Also edit **line 28** to set the path to `transcribe_and_log.py`:
```python
subprocess.call(["python3", "/path/to/transcribe_and_log.py", new_file])
```

---

### 7. Configure `transcribe_and_log.py`

Set your MySQL connection credentials:

```python
host = "localhost"
user = "tsnuser"
password = "your_password"
database = "repeater"
```

---

### 8. Place `callsign_extractor.py` (Optional)

Copy `callsign_extractor.py` to the machine that will handle callsign detection.

---

### 9. Configure `callsign_extractor.py`

Edit connection and QRZ credentials:

```python
use_qrz = True
qrz_username = "your_qrz_username"
qrz_password = "your_qrz_password"
```

---

### 10. Autostart `transcribe_watcher.py` on Boot

Use one of:

- `systemd` service file (recommended)
- `cron @reboot`
- Manual launch with `screen` or `tmux`

---

### 11. Test the Full Flow

- Trigger a test PTT on your AllStar hub node
- Confirm `.wav` files are sent to the transcription server
- Verify the file is transcribed and logged into the MySQL database

---

### 12. (Optional) Setup Public Web Dashboard

Follow the upcoming **Dashboard Setup Guide** (Coming Soon) to expose data and statistics via a public website or API.

---

## 🗂️ Example Project Structure

```
TSN/
├── push-taas-wavs.sh
├── transcribe_watcher.py
├── transcribe_and_log.py
├── callsign_extractor.py
├── AllStar-CONF/
│   ├── rpt.conf
│   └── extensions.conf
```

---

## 🧠 MySQL Schema Summary

Ensure these tables exist:

```sql
CREATE TABLE transcriptions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    filename VARCHAR(255) NOT NULL,
    transcription TEXT,
    timestamp DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed TINYINT DEFAULT 0
);

CREATE TABLE callsigns (
    ID INT PRIMARY KEY AUTO_INCREMENT,
    callsign VARCHAR(16) UNIQUE NOT NULL,
    validated TINYINT DEFAULT 0,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    seen_count INT DEFAULT 1,
    original_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE callsign_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    callsign VARCHAR(16) NOT NULL,
    transcript_id INT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 📬 Contact

Created by [Hunter Inman (KK7NQN)](https://www.qrz.com/db/KK7NQN)  
Project Website: [https://kk7nqn.net](https://kk7nqn.net)

### 1. Clone the Repository

```bash
git clone https://github.com/yourname/sdr-repeater-logger.git
cd sdr-repeater-logger
