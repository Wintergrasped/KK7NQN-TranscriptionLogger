<?php
header('Content-Type: application/json');

$API_KEY_EXPECTED = 'YOUR TRANSCRIBER API KEY (If Applicable) (MUST Match .sh script ran by Transcriber node)'; // must match the shell script
if (($_SERVER['HTTP_X_API_KEY'] ?? '') !== $API_KEY_EXPECTED) {
  http_response_code(401); echo json_encode(['ok'=>false,'error'=>'unauthorized']); exit;
}

require __DIR__.'/db_transcriber.php';
if (!isset($pdo) || !($pdo instanceof PDO)) {
  http_response_code(500); echo json_encode(['ok'=>false,'error'=>'PDO not initialized']); exit;
}

/* Ensure we write to the intended schema */
$pdo->exec("USE `DATABASE_NAME`");

$raw = file_get_contents('php://input');
if ($raw === '' || $raw === false) { http_response_code(400); echo json_encode(['ok'=>false,'error'=>'empty body']); exit; }

$j = json_decode($raw, true);
if (!is_array($j)) { http_response_code(400); echo json_encode(['ok'=>false,'error'=>'invalid json']); exit; }

/* Optional: flatten accidental extra wrapper like {"t":[[ [row] ]]} */
foreach ($j as $tname => $rows) {
  if (is_array($rows) && count($rows) === 1 && is_array($rows[0]) && is_array($rows[0][0] ?? null)) {
    $j[$tname] = $rows[0];
  }
}

$out = ['ok'=>true,'tables'=>[]];

try {
  $pdo->beginTransaction();

  foreach ($j as $table => $rows) {
    if (!is_array($rows) || !$rows) { $out['tables'][$table] = ['updated'=>0]; continue; }

    switch ($table) {
      case 'transcriptions': {
        // id, filename, transcription, timestamp, created_at, processed
        $sql = "INSERT INTO `transcriptions`
          (id, filename, transcription, timestamp, created_at, processed)
          VALUES (:id,:filename,:transcription,:timestamp,:created_at,:processed)
          ON DUPLICATE KEY UPDATE
            filename=VALUES(filename),
            transcription=VALUES(transcription),
            timestamp=VALUES(timestamp),
            created_at=VALUES(created_at),
            processed=VALUES(processed)";
        $bind = fn($r) => [
          ':id'            => $r[0] ?? null,
          ':filename'      => $r[1] ?? null,
          ':transcription' => $r[2] ?? null,
          ':timestamp'     => $r[3] ?? null,
          ':created_at'    => $r[4] ?? null,
          ':processed'     => $r[5] ?? 0,
        ];
        break;
      }
      case 'callsigns': {
        // ID, callsign, validated, first_seen, last_seen, seen_count, original_timestamp
        $sql = "INSERT INTO `callsigns`
          (ID, callsign, validated, first_seen, last_seen, seen_count, original_timestamp)
          VALUES (:ID,:callsign,:validated,:first_seen,:last_seen,:seen_count,:original_timestamp)
          ON DUPLICATE KEY UPDATE
            validated=VALUES(validated),
            first_seen=VALUES(first_seen),
            last_seen=VALUES(last_seen),
            seen_count=VALUES(seen_count),
            original_timestamp=VALUES(original_timestamp)";
        $bind = fn($r) => [
          ':ID'                 => $r[0] ?? null,
          ':callsign'           => $r[1] ?? null,
          ':validated'          => $r[2] ?? 0,
          ':first_seen'         => $r[3] ?? null,
          ':last_seen'          => $r[4] ?? null,
          ':seen_count'         => $r[5] ?? 1,
          ':original_timestamp' => $r[6] ?? null,
        ];
        break;
      }
      case 'callsign_log': {
        // id, callsign, transcript_id, timestamp
        $sql = "INSERT INTO `callsign_log`
          (id, callsign, transcript_id, timestamp)
          VALUES (:id,:callsign,:transcript_id,:timestamp)
          ON DUPLICATE KEY UPDATE
            callsign=VALUES(callsign),
            transcript_id=VALUES(transcript_id),
            timestamp=VALUES(timestamp)";
        $bind = fn($r) => [
          ':id'            => $r[0] ?? null,
          ':callsign'      => $r[1] ?? null,
          ':transcript_id' => $r[2] ?? null,
          ':timestamp'     => $r[3] ?? null,
        ];
        break;
      }
      case 'system_stats': {
        // id, device_name, timestamp, cpu_usage, memory_usage, cpu_temp
        $sql = "INSERT INTO `system_stats`
          (id, device_name, timestamp, cpu_usage, memory_usage, cpu_temp)
          VALUES (:id,:device_name,:timestamp,:cpu_usage,:memory_usage,:cpu_temp)
          ON DUPLICATE KEY UPDATE
            device_name=VALUES(device_name),
            timestamp=VALUES(timestamp),
            cpu_usage=VALUES(cpu_usage),
            memory_usage=VALUES(memory_usage),
            cpu_temp=VALUES(cpu_temp)";
        $bind = fn($r) => [
          ':id'           => $r[0] ?? null,
          ':device_name'  => $r[1] ?? null,
          ':timestamp'    => $r[2] ?? null,
          ':cpu_usage'    => $r[3] ?? null,
          ':memory_usage' => $r[4] ?? null,
          ':cpu_temp'     => $r[5] ?? null,
        ];
        break;
      }
      case 'temperature_log': {
        // id, sensor_id, temperature_c, temperature_f, timestamp
        $sql = "INSERT INTO `temperature_log`
          (id, sensor_id, temperature_c, temperature_f, timestamp)
          VALUES (:id,:sensor_id,:temperature_c,:temperature_f,:timestamp)
          ON DUPLICATE KEY UPDATE
            sensor_id=VALUES(sensor_id),
            temperature_c=VALUES(temperature_c),
            temperature_f=VALUES(temperature_f),
            timestamp=VALUES(timestamp)";
        $bind = fn($r) => [
          ':id'            => $r[0] ?? null,
          ':sensor_id'     => $r[1] ?? null,
          ':temperature_c' => $r[2] ?? null,
          ':temperature_f' => $r[3] ?? null,
          ':timestamp'     => $r[4] ?? null,
        ];
        break;
      }
      case 'transcriptions_large': {
        // if you plan to sync this table too
        $sql = "INSERT INTO `transcriptions_large`
          (id, filename, transcription, timestamp, created_at, processed)
          VALUES (:id,:filename,:transcription,:timestamp,:created_at,:processed)
          ON DUPLICATE KEY UPDATE
            filename=VALUES(filename),
            transcription=VALUES(transcription),
            timestamp=VALUES(timestamp),
            created_at=VALUES(created_at),
            processed=VALUES(processed)";
        $bind = fn($r) => [
          ':id'            => $r[0] ?? null,
          ':filename'      => $r[1] ?? null,
          ':transcription' => $r[2] ?? null,
          ':timestamp'     => $r[3] ?? null,
          ':created_at'    => $r[4] ?? null,
          ':processed'     => $r[5] ?? 0,
        ];
        break;
      }
      default:
        $out['tables'][$table] = ['skipped'=>'unknown table'];
        continue 2;
    }

    $stmt = $pdo->prepare($sql);
    $n = 0;
    foreach ($rows as $r) {
      if (!is_array($r)) continue;
      $stmt->execute($bind($r));
      $n++;
    }
    $out['tables'][$table] = ['updated'=>$n];
  }

  $pdo->commit();
  echo json_encode($out, JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
  if ($pdo->inTransaction()) $pdo->rollBack();
  http_response_code(500);
  echo json_encode(['ok'=>false,'error'=>$e->getMessage()]);
}
