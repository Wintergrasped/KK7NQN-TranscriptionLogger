#!/bin/bash

# KK7NQN Repeater Logger
# Copyright (C) 2025 Hunter Inman
#
# This file is part of the KK7NQN Repeater Logger project.
# It is licensed under the GNU General Public License v3.0.
# See the LICENSE file in the root of this repository for full terms.


mkdir -p ~/Logger_Audio/incoming
mkdir -p ~/Logger_Audio/recording

while true; do
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    RECORDING_FILE="/Logger_Audio/recording/${TIMESTAMP}.wav"
    FINAL_FILE="/Logger_Audio/incoming/${TIMESTAMP}.wav"
	FREQ=145.125M
	GAIN=0

    echo "[$(date)] Starting capture: $RECORDING_FILE"

    rtl_fm -M nfm -f "$freq" -s 48000 -g "$GAIN" -E deemp \
    | sox -t raw -r 48000 -e signed -b 16 -c 1 - -b 16 "$RECORDING_FILE" \
      silence 1 0.1 1% 1 2.0 1%

    if [[ -f "$RECORDING_FILE" && -s "$RECORDING_FILE" ]]; then
        mv "$RECORDING_FILE" "$FINAL_FILE"
        echo "[$(date)] Moved: $FINAL_FILE"
    else
        echo "[$(date)] Skipped empty file: $RECORDING_FILE"
        rm -f "$RECORDING_FILE"
    fi

    sleep 1
done
