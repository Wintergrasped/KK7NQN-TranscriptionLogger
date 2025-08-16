#!/usr/bin/env python3

import psutil
import mysql.connector
from datetime import datetime
import socket
import os

DEVICE_NAME = 'DEVICE_NAME'  # or 'MiniPC' / 'RepeaterPi' hardcoded if you prefer

# MySQL config
DB_CONFIG = {
    'host': 'IP / HOSTNAME',
    'user': 'USERNAME',
    'password': 'PASSWORD',
    'database': 'DATABSE NAME'
}

def get_cpu_temp():
    # Works on most Linux SBCs like Pi
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read()) / 1000.0
    except:
        return None

def log_stats():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cpu_usage = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    mem_usage = memory.percent
    cpu_temp = get_cpu_temp()

    timestamp = datetime.utcnow()

    cursor.execute("""
        INSERT INTO system_stats (device_name, timestamp, cpu_usage, memory_usage, cpu_temp)
        VALUES (%s, %s, %s, %s, %s)
    """, (DEVICE_NAME, timestamp, cpu_usage, mem_usage, cpu_temp))

    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    log_stats()
