<?php
header('Content-Type: application/json');
require __DIR__.'/db_transcriber.php';
if (!isset($pdo) || !($pdo instanceof PDO)) { http_response_code(500); echo json_encode(['ok'=>false,'error'=>'PDO not initialized']); exit; }

try {
  $since = $_GET['since'] ?? '';
  $until = $_GET['until'] ?? '';
  $limit = max(1, min(500, (int)($_GET['limit'] ?? 200)));

  $where=[]; $params=[];
  if ($since !== '') { $where[] = 't.timestamp >= :since'; $params[':since'] = $since; }
  if ($until !== '') { $where[] = 't.timestamp <= :until'; $params[':until'] = $until; }
  $wsql = $where ? 'WHERE '.implode(' AND ', $where) : '';

  // NOTE: inline LIMIT (integer) to avoid binding issues
  $sql = "
    SELECT t.id, t.filename, t.transcription, t.timestamp, t.created_at,
           GROUP_CONCAT(DISTINCT cl.callsign ORDER BY cl.callsign SEPARATOR ', ') AS callsigns
    FROM transcriptions t
    LEFT JOIN callsign_log cl ON cl.transcript_id = t.id
    $wsql
    GROUP BY t.id
    ORDER BY t.timestamp DESC, t.id DESC
    LIMIT $limit
  ";
  $st = $pdo->prepare($sql);
  $st->execute($params);
  echo json_encode($st->fetchAll(), JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['ok'=>false,'error'=>$e->getMessage()]);
}
