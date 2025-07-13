
---
# 📻 SDR Repeater Logger & Transcription System

This project is a modular SDR-based system for capturing, transcribing, logging, and monitoring amateur radio repeater activity. It uses an RTL-SDR receiver, Whisper for transcription, Flask for web/API serving, and QRZ for call sign validation.

## 📁 Repository Structure

sdr-repeater-logger/
├── LoggerAudio/
│ ├── AudioCaptureLoop.sh # Main SDR recording loop
│ ├── TranscribeWatcher.py # Watches for WAV files and transcribes
│ └── TranscribeAndLog.py # Transcribes audio and logs it
│
├── Logger/
│ ├── CallSignExtractor.py # Pulls and corrects call signs from transcriptions
│ ├── CallSignValidator.py # Validates callsigns via QRZ API
│ ├── SystemStatus.py # Flask server for basic system metrics
│ └── TempReceiver.py # Flask server for temperature sensor updates
│
├── Web/
│ ├── DashboardAPI.py # Main Flask API for dashboard
│ └── index.html # Web-based dashboard interface
└── README.md

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

### 1. Clone the Repository

```bash
git clone https://github.com/yourname/sdr-repeater-logger.git
cd sdr-repeater-logger
