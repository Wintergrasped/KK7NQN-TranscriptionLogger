<?php
header('Content-Type: application/json');
require __DIR__.'/db_transcriber.php';
if (!isset($pdo) || !($pdo instanceof PDO)) { http_response_code(500); echo json_encode(['ok'=>false,'error'=>'PDO not initialized']); exit; }

try {
  $start = $_GET['start'] ?? '';
  $end   = $_GET['end'] ?? '';

  $where=[]; $params=[];
  if ($start !== '') { $where[]='timestamp >= :start'; $params[':start']=$start; }
  if ($end   !== '') { $where[]='timestamp <= :end';   $params[':end']=$end; }
  $wsql = $where ? 'WHERE '.implode(' AND ', $where) : '';

  // transcripts in range
  $st = $pdo->prepare("SELECT COUNT(*) FROM transcriptions $wsql");
  $st->execute($params);
  $tcount = (int)$st->fetchColumn();

  // callsigns in range
  $st2 = $pdo->prepare("
    SELECT callsign, COUNT(*) AS mentions, MAX(timestamp) AS last_seen
    FROM callsign_log
    $wsql
    GROUP BY callsign
    ORDER BY mentions DESC
    LIMIT 50
  ");
  $st2->execute($params);
  $top = $st2->fetchAll();

  echo json_encode(['ok'=>true,'count'=>$tcount,'calls'=>count($top),'call_signs'=>$top], JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['ok'=>false,'error'=>$e->getMessage()]);
}
