# KK7NQN Repeater Logger
# Copyright (C) 2025 Hunter Inman
#
# This file is part of the KK7NQN Repeater Logger project.
# It is licensed under the GNU General Public License v3.0.
# See the LICENSE file in the root of this repository for full terms.


from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
import os

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

db_config = {
    'host': 'localhost',
    'user': 'repeateruser',
    'password': 'changeme123',
    'database': 'repeater'
}

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

def query_db(query, args=()):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, args)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

@app.route('/api/stats')
def get_system_stats():
    return jsonify(query_db("SELECT * FROM system_stats WHERE device_name='RepeaterServer' ORDER BY timestamp DESC LIMIT 25"))
    
@app.route('/api/serverstats')
def get_server_stats():
    return jsonify(query_db("SELECT * FROM system_stats WHERE device_name='RepeaterServer' ORDER BY timestamp DESC LIMIT 25"))
    
@app.route('/api/repeaterstats')
def get_repeater_stats():
    return jsonify(query_db("SELECT * FROM system_stats WHERE device_name='OpenRepeater' ORDER BY timestamp DESC LIMIT 25"))

@app.route('/api/callsigns')
def get_callsigns():
    return jsonify(query_db("SELECT * FROM callsigns ORDER BY seen_count DESC"))

@app.route('/api/temperatures')
def get_temps():
    return jsonify(query_db("SELECT * FROM temperature_log ORDER BY timestamp DESC LIMIT 25"))

@app.route('/api/intake_temperature')
def get_intake_temps():
    return jsonify(query_db("SELECT * FROM temperature_log WHERE sensor_id='28-510500879011' ORDER BY timestamp DESC LIMIT 25"))

@app.route('/api/internal_temperature')
def get_internal_temps():
    return jsonify(query_db("SELECT * FROM temperature_log WHERE sensor_id='28-4f10d446d493' ORDER BY timestamp DESC LIMIT 25"))
    
@app.route('/api/amplifier_temperature')
def get_amplifier_temps():
    return jsonify(query_db("SELECT * FROM temperature_log WHERE sensor_id='28-2531d446d51e' ORDER BY timestamp DESC LIMIT 25"))
    
@app.route('/api/radio_temperature')
def get_radio_temps():
    return jsonify(query_db("SELECT * FROM temperature_log WHERE sensor_id='28-73e8d4464f3e' ORDER BY timestamp DESC LIMIT 25"))

@app.route('/api/transcriptions')
def get_transcriptions():
    return jsonify(query_db("SELECT * FROM transcriptions ORDER BY timestamp DESC LIMIT 50"))

@app.route('/api/system_status')
def get_system_status_alias():
    return get_system_stats()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
