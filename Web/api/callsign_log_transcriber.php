<?php
// /api/callsign_log_transcriber.php (dual-driver: PDO or mysqli)
// Returns calls to callsign_log, supports limit/since/until/callsign

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=60');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

date_default_timezone_set('America/Los_Angeles');
$debug = isset($_GET['debug']) && $_GET['debug'] !== '0';

require_once __DIR__.'/db_transcriber.php'; // should define $pdo (PDO) OR $conn (mysqli)

$defaultLimit = 25; $minLimit = 1; $maxLimit = 100000;
$limit = isset($_GET['limit']) ? (int)$_GET['limit'] : $defaultLimit;
if ($limit < $minLimit) $limit = $minLimit;
if ($limit > $maxLimit) $limit = $maxLimit;

$sinceRaw = isset($_GET['since']) ? trim((string)$_GET['since']) : '';
$untilRaw = isset($_GET['until']) ? trim((string)$_GET['until']) : '';
$callsign = isset($_GET['callsign']) ? strtoupper(trim((string)$_GET['callsign'])) : '';
$transcriptId = isset($_GET['transcript_id']) ? (int)$_GET['transcript_id'] : 0;

function is_date_only(string $s): bool { return (bool)preg_match('/^\d{4}-\d{2}-\d{2}$/', $s); }
function parse_local_dt(string $raw): ?DateTime {
  try {
    if (is_date_only($raw)) { $dt = new DateTime($raw . ' 00:00:00', new DateTimeZone('America/Los_Angeles')); }
    else { $dt = new DateTime($raw, new DateTimeZone('America/Los_Angeles')); }
    return $dt;
  } catch (Throwable $e) { return null; }
}

$sinceDT = $sinceRaw ? parse_local_dt($sinceRaw) : null;
$untilDT = $untilRaw ? parse_local_dt($untilRaw) : null;
if ($sinceDT && is_date_only($sinceRaw)) $sinceDT->setTime(0,0,0);
if ($untilDT && is_date_only($untilRaw)) $untilDT->setTime(23,59,59);

// WHERE builder
$where = [];
$params = [];
if ($callsign !== '') { $where[] = "callsign = ?"; $params[] = $callsign; }
if ($transcriptId > 0) { $where[] = "transcript_id = ?"; $params[] = $transcriptId; }
if ($sinceDT) { $where[] = "timestamp >= ?"; $params[] = $sinceDT->format('Y-m-d H:i:s'); }
if ($untilDT) { $where[] = "timestamp <= ?"; $params[] = $untilDT->format('Y-m-d H:i:s'); }
$whereSql = $where ? ('WHERE ' . implode(' AND ', $where)) : '';

$sql = "SELECT id, callsign, transcript_id, timestamp
        FROM callsign_log
        $whereSql
        ORDER BY timestamp DESC
        LIMIT ?";

// Append limit param
$params_with_limit = $params;
$params_with_limit[] = $limit;

try {
  if (isset($pdo) && ($pdo instanceof PDO)) {
    // Use UTC offset instead of timezone name for MySQL compatibility
    // PST/PDT is UTC-8 or UTC-7 depending on DST
    // We'll use a safe SET command that works on most MySQL versions
    try {
      $pdo->exec("SET time_zone = '-08:00'");
    } catch (Exception $e) {
      // If setting timezone fails, continue without it
      // The dates will still work, just might be in server timezone
    }
    
    // Compose PDO SQL with placeholders
    $wherePieces = [];
    $pdoParams = [];
    if ($callsign !== '') { $wherePieces[] = "callsign = :callsign"; $pdoParams[':callsign'] = $callsign; }
    if ($transcriptId > 0) { $wherePieces[] = "transcript_id = :tid"; $pdoParams[':tid'] = $transcriptId; }
    if ($sinceDT) { $wherePieces[] = "timestamp >= :since"; $pdoParams[':since'] = $sinceDT->format('Y-m-d H:i:s'); }
    if ($untilDT) { $wherePieces[] = "timestamp <= :until"; $pdoParams[':until'] = $untilDT->format('Y-m-d H:i:s'); }
    $wsql = $wherePieces ? ('WHERE ' . implode(' AND ', $wherePieces)) : '';
    $sql = "SELECT id, callsign, transcript_id, timestamp FROM callsign_log $wsql ORDER BY timestamp DESC LIMIT :limit";
    $stmt = $pdo->prepare($sql);
    foreach ($pdoParams as $k => $v) $stmt->bindValue($k, $v);
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->execute();
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    if ($debug) {
      echo json_encode(['data'=>$rows, '_meta'=>['driver'=>'pdo','where'=>$wsql,'params'=>$pdoParams,'limit'=>$limit]], JSON_UNESCAPED_UNICODE);
    } else {
      echo json_encode($rows, JSON_UNESCAPED_UNICODE);
    }
    exit;
  }

  // Fallback to mysqli if provided
  if (isset($conn) && ($conn instanceof mysqli)) {
    // Use UTC offset for MySQL compatibility
    try {
      $conn->query("SET time_zone = '-08:00'");
    } catch (Exception $e) {
      // Continue without timezone setting if it fails
    }
    
    $types = '';
    foreach ($params as $p) $types .= is_int($p) ? 'i' : 's';
    $types .= 'i';
    $stmt = $conn->prepare($sql);
    if (!$stmt) throw new Exception('prepare failed: '.$conn->error);

    // bind params
    $bind = [$types];
    foreach ($params as $i => $v) { $bind[] = &$params[$i]; }
    $bind[] = &$params_with_limit[count($params_with_limit)-1];
    call_user_func_array([$stmt, 'bind_param'], $bind);

    if (!$stmt->execute()) throw new Exception('execute failed: '.$stmt->error);

    if (method_exists($stmt,'get_result')) {
      $res = $stmt->get_result();
      $rows = $res ? $res->fetch_all(MYSQLI_ASSOC) : [];
    } else {
      $stmt->store_result();
      $meta = $stmt->result_metadata();
      $rows = [];
      if ($meta) {
        $row = []; $bind = []; $fields = [];
        while ($f = $meta->fetch_field()) { $fields[] = $f->name; $row[$f->name] = null; $bind[] = &$row[$f->name]; }
        call_user_func_array([$stmt, 'bind_result'], $bind);
        while ($stmt->fetch()) { $copy = []; foreach ($fields as $n) { $copy[$n] = $row[$n]; } $rows[] = $copy; }
      }
    }
    $stmt->close();
    if ($debug) {
      echo json_encode(['data'=>$rows, '_meta'=>['driver'=>'mysqli','where'=>$whereSql,'params'=>$params_with_limit,'types'=>$types]], JSON_UNESCAPED_UNICODE);
    } else {
      echo json_encode($rows, JSON_UNESCAPED_UNICODE);
    }
    exit;
  }

  http_response_code(500);
  echo json_encode(['error'=>'DB not initialized','hint'=>'Ensure db_transcriber.php defines $pdo (PDO) or $conn (mysqli).']);

} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['error'=>'Server error','message'=>$e->getMessage()]);
}