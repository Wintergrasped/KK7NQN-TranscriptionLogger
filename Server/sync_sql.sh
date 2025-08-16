#!/bin/bash

# Local DB config
LOCAL_HOST="IP / HOSTNAME"
LOCAL_USER="USERNAME"
LOCAL_PASS="PASSWORD"
LOCAL_DB="DATABASE"
API_URL="YOUR_URL/sql_sync.php"
API_KEY="YOUR GENERATED API KEY (Or any long random string of numbers as long as it matches the PHP setting)"  # Authentication key
STATE_DIR="/var/tmp/sql_sync_state"
CHUNK_SIZE=500

mkdir -p "$STATE_DIR"

TABLES=("callsigns" "transcriptions" "callsign_log" "system_stats" "temperature_log")

for TABLE in "${TABLES[@]}"; do
    STATE_FILE="$STATE_DIR/${TABLE}.lastid"
    [ -f "$STATE_FILE" ] || echo 0 > "$STATE_FILE"
    LAST_ID=$(cat "$STATE_FILE")

    echo "[$(date)] Starting sync for table: $TABLE from ID $LAST_ID"

    while true; do
        # Fetch next chunk
        RESULT=$(mysql -h "$LOCAL_HOST" -u "$LOCAL_USER" -p"$LOCAL_PASS" "$LOCAL_DB" \
            --batch --skip-column-names \
            -e "SELECT * FROM $TABLE WHERE id > $LAST_ID ORDER BY id ASC LIMIT $CHUNK_SIZE;")

        if [ -z "$RESULT" ]; then
            echo "[$(date)] No more rows for $TABLE"
            break
        fi

        # Convert chunk to JSON
        JSON=$(echo "$RESULT" | jq -Rsn '
            {
              "'$TABLE'": [
                inputs
                | split("\n")
                | map(select(length > 0))
                | map(split("\t"))
              ]
            }'
        )

        TMP_FILE="/tmp/${TABLE}_payload.json"
        echo "$JSON" > "$TMP_FILE"

        # Send chunk to PHP API and capture response
		
		echo "[$(date)] Sending payload for $TABLE (size: $(stat -c%s "$TMP_FILE") bytes)"
head -c 200 "$TMP_FILE" | tr -d '\n' && echo "..."
		
        RESPONSE=$(curl -v -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -H "X-API-KEY: $API_KEY" \
    --data-binary @"$TMP_FILE" 2>&1)

echo "[$(date)] Response from PHP for $TABLE: $RESPONSE"

        # Correct last ID tracking
        NEW_LAST_ID=$(echo "$RESULT" | tail -n 1 | awk '{print $1}')
        if [[ -n "$NEW_LAST_ID" ]]; then
            echo "$NEW_LAST_ID" > "$STATE_FILE"
            LAST_ID=$NEW_LAST_ID
            echo "[$(date)] Synced chunk for $TABLE up to ID $NEW_LAST_ID"
        else
            echo "[$(date)] ERROR: Could not extract last ID for $TABLE"
            break
        fi
    done
done
