# KK7NQN Repeater Logger
# Copyright (C) 2025 Hunter Inman
#
# This file is part of the KK7NQN Repeater Logger project.
# It is licensed under the GNU General Public License v3.0.
# See the LICENSE file in the root of this repository for full terms.



from flask import Flask, request
import mysql.connector
from datetime import datetime

app = Flask(__name__)

@app.route('/temp', methods=['POST'])
def log_temp():
    data = request.json
    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='repeateruser',
            password='changeme123',  # <-- Replace this with your actual password
            database='repeater'
        )
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO temperature_log (sensor_id, temperature_c, temperature_f)
            VALUES (%s, %s, %s)
        """, (data['sensor_id'], data['temperature_c'], data['temperature_f']))
        conn.commit()
        cursor.close()
        conn.close()
        return 'Logged', 200
    except Exception as e:
        return f'Error: {e}', 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
