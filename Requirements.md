# ⚙️ System Requirements & Dependencies

This document outlines the dependencies and minimum hardware recommendations for running the SDR Repeater Logger system.

---

## 📋 Required System Packages

Install these using your system package manager (`apt`, `dnf`, `pacman`, etc.):

```bash
sudo apt update
sudo apt install rtl-sdr sox python3 python3-pip git
```

---

## 🐍 Required Python Modules

Install with pip:

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install flask requests pydub
```

**Whisper model requirements:**
> ⚠️ Transcription uses OpenAI Whisper or Whisper.cpp. Torch is required.

```bash
pip install git+https://github.com/openai/whisper.git
pip install torch
```

Whisper also benefits from:
- FFmpeg (`sudo apt install ffmpeg`)
- 16kHz mono WAV input files

---

## 🧊 Suggested Hardware

| Component       | Recommended Specs                          |
|----------------|---------------------------------------------|
| CPU            | Quad-core (e.g., Intel N100, Pi 4, i3+)     |
| RAM            | 4 GB minimum (8 GB+ preferred for Whisper)  |
| Storage        | 32 GB SSD minimum (logs + audio grow fast)  |
| OS             | Linux (Debian, Ubuntu, Raspberry Pi OS)     |
| SDR Receiver   | RTL-SDR v3 or compatible USB dongle         |
| Cooling        | Passive or active cooling for 24/7 uptime   |
| Audio Format   | Mono, 16-bit, 16 kHz WAV                    |

> Whisper performance will vary by CPU. Faster CPUs = faster transcription.
> Raspberry Pi 4 is *usable*, but may fall behind in real-time nets.

---

## 🔐 External Services

### QRZ XML API Key
Required for `CallSignValidator.py`:
- [QRZ XML API](https://www.qrz.com/page/xml_data.html)
- Free tier available with registered account

Add your key to the config or script directly.

---

## 🧪 Optional Tools

These are useful for debugging or expansion:

| Tool           | Purpose                                       |
|----------------|-----------------------------------------------|
| `rtl_test`     | Verify SDR dongle functionality               |
| `rtl_fm`       | Live FM decoding (used in audio capture)      |
| `rtl_power`    | Frequency sweep / waterfall testing           |
| `htop`         | Monitor CPU/memory usage                      |
| `ngrok`        | Securely tunnel Flask dashboard to the web    |

---

## ✅ Final Checklist

- [x] RTL-SDR dongle connected and detected (`rtl_test`)
- [x] AudioCaptureLoop.sh configured with correct frequency
- [x] Python scripts working with correct dependencies
- [x] Whisper transcription tested manually
- [x] QRZ key added (for call sign validation)
- [x] Flask servers reachable on LAN or local device

---