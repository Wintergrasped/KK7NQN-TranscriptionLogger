import os
import subprocess
import datetime
import schedule
import time
import shutil

# Paths
processed_dir = "DIRECTORY_PATH/processed"
archive_dir = "DIRECTORY_PATH/archive"

# Ensure archive directory exists
os.makedirs(archive_dir, exist_ok=True)

def convert_and_move():
    today_folder = os.path.join(archive_dir, datetime.date.today().strftime("%Y-%m-%d"))
    os.makedirs(today_folder, exist_ok=True)

    for filename in os.listdir(processed_dir):
        if filename.lower().endswith(".wav"):
            wav_path = os.path.join(processed_dir, filename)
            mp3_filename = os.path.splitext(filename)[0] + ".mp3"
            mp3_path = os.path.join(today_folder, mp3_filename)

            # Convert to MP3 at 32 kbps mono
            subprocess.run([
                "ffmpeg", "-y", "-i", wav_path,
                "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "32k", mp3_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Remove original WAV after conversion
            os.remove(wav_path)
            print(f"Converted and moved: {filename} -> {mp3_path}")

def compress_yesterday():
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    folder_to_compress = os.path.join(archive_dir, yesterday.strftime("%Y-%m-%d"))

    if os.path.exists(folder_to_compress):
        archive_path = folder_to_compress + ".7z"
        # Compress with 7z for max compression
        subprocess.run([
            "7z", "a", "-t7z", "-mx=9", archive_path, folder_to_compress
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Remove original folder after compression
        shutil.rmtree(folder_to_compress)
        print(f"Compressed and removed: {folder_to_compress}")

# Schedule tasks
schedule.every(1).minutes.do(convert_and_move)  # Check for WAVs every minute
schedule.every().day.at("23:59").do(compress_yesterday)  # Compress yesterday at midnight

print("Audio compression and archiving service started...")

while True:
    schedule.run_pending()
    time.sleep(10)
