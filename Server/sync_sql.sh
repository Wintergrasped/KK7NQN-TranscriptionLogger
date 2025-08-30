#!/bin/bash

# Local DB config
LOCAL_HOST="127.0.0.1"
LOCAL_USER="USERNAME"
LOCAL_PASS="PASSWORD"
LOCAL_DB="DATABASE"
API_URL="https://YOURURL/sql_sync.php"
API_KEY="YOUR API KEY (Or Somthing matching sql_sync.php)"  # Authentication key
STATE_DIR="/var/tmp/sql_sync_state"
CHUNK_SIZE=500

mkdir -p "$STATE_DIR"

TABLES=("callsigns" "transcriptions" "callsign_log" "system_stats" "temperature_log")

for TABLE in "${TABLES[@]}"; do
    
    if [[ "$TABLE" == "callsigns" ]]; then
        # Special handling for callsigns table - use timestamp tracking
        STATE_FILE="$STATE_DIR/${TABLE}.last_sync"
        [ -f "$STATE_FILE" ] || echo "1970-01-01 00:00:00" > "$STATE_FILE"
        LAST_SYNC=$(cat "$STATE_FILE")
        
        echo "[$(date)] Starting sync for table: $TABLE from timestamp $LAST_SYNC"
        
        ROWS_PROCESSED=0
        MAX_ITERATIONS=100  # Safety limit to prevent infinite loops
        ITERATION=0
        
        while [ $ITERATION -lt $MAX_ITERATIONS ]; do
            ITERATION=$((ITERATION + 1))
            
            # Fetch next chunk based on last_modified timestamp
            echo "[$(date)] Querying $TABLE WHERE last_modified > '$LAST_SYNC' (iteration $ITERATION)"
            RESULT=$(mysql -h "$LOCAL_HOST" -u "$LOCAL_USER" -p"$LOCAL_PASS" "$LOCAL_DB" \
                --batch --skip-column-names \
                -e "SELECT * FROM $TABLE WHERE last_modified > '$LAST_SYNC' ORDER BY last_modified ASC LIMIT $CHUNK_SIZE;" 2>/dev/null || true)
            
            # Check if result is truly empty
            if [ -z "$RESULT" ] || [ "$RESULT" = "" ]; then
                echo "[$(date)] No more rows for $TABLE (processed $ROWS_PROCESSED total)"
                break
            fi
            
            ROW_COUNT=$(echo "$RESULT" | wc -l)
            ROWS_PROCESSED=$((ROWS_PROCESSED + ROW_COUNT))
            echo "[$(date)] Found $ROW_COUNT rows to sync"
            
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
            
            # Extract last timestamp - assuming it's the last two fields (date and time)
            # Combines the second-to-last field (date) with the last field (time)
            NEW_LAST_SYNC=$(echo "$RESULT" | tail -n 1 | awk '{print $(NF-1)" "$NF}')
            
            if [[ -z "$NEW_LAST_SYNC" ]] || [[ "$NEW_LAST_SYNC" == "$LAST_SYNC" ]]; then
                echo "[$(date)] WARNING: Could not extract new timestamp or timestamp unchanged. Breaking to prevent infinite loop."
                echo "[$(date)] Debug: NEW_LAST_SYNC='$NEW_LAST_SYNC', LAST_SYNC='$LAST_SYNC'"
                break
            fi
            
            echo "$NEW_LAST_SYNC" > "$STATE_FILE"
            LAST_SYNC="$NEW_LAST_SYNC"
            echo "[$(date)] Synced chunk for $TABLE up to timestamp $NEW_LAST_SYNC"
            
            # If we got less than CHUNK_SIZE rows, we're done
            if [ $ROW_COUNT -lt $CHUNK_SIZE ]; then
                echo "[$(date)] Last chunk was partial ($ROW_COUNT < $CHUNK_SIZE), sync complete for $TABLE"
                break
            fi
        done
        
        if [ $ITERATION -ge $MAX_ITERATIONS ]; then
            echo "[$(date)] WARNING: Hit max iterations limit for $TABLE"
        fi
        
    else
        # Standard ID-based sync for all other tables
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
            
            # ✅ Correct last ID tracking
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
    fi
done