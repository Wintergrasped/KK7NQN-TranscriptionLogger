<?php
header('Content-Type: application/json');
require __DIR__.'/db_transcriber.php';
if (!isset($pdo) || !($pdo instanceof PDO)) { http_response_code(500); echo json_encode(['ok'=>false,'error'=>'PDO not initialized']); exit; }

try {
  $since = $_GET['since'] ?? '';
  $until = $_GET['until'] ?? '';
  $limit = max(1, min(500, (int)($_GET['limit'] ?? 100)));
  $order = $_GET['order'] ?? 'seen_count';
  $dir   = (strtolower($_GET['dir'] ?? 'desc') === 'asc') ? 'ASC' : 'DESC';

  $allowed = ['seen_count','callsign','last_seen','first_seen'];
  if (!in_array($order, $allowed, true)) $order = 'seen_count';

  if ($since !== '' || $until !== '') {
    $where=[]; $params=[];
    if ($since !== '') { $where[]='timestamp >= :since'; $params[':since']=$since; }
    if ($until !== '') { $where[]='timestamp <= :until'; $params[':until']=$until; }
    $wsql = $where ? 'WHERE '.implode(' AND ', $where) : '';

    $sql = "
      SELECT c.callsign,
             COALESCE(x.cnt,0) AS seen_count,
             c.first_seen, c.last_seen
      FROM callsigns c
      LEFT JOIN (
        SELECT callsign, COUNT(*) AS cnt
        FROM callsign_log
        $wsql
        GROUP BY callsign
      ) x ON x.callsign = c.callsign
      ORDER BY $order $dir
      LIMIT $limit
    ";
    $st = $pdo->prepare($sql);
    $st->execute($params);
    echo json_encode($st->fetchAll(), JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
    exit;
  }

  $sql = "SELECT callsign, seen_count, first_seen, last_seen
          FROM callsigns
          ORDER BY $order $dir
          LIMIT $limit";
  $st = $pdo->query($sql);
  echo json_encode($st->fetchAll(), JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['ok'=>false,'error'=>$e->getMessage()]);
}
