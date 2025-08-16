<?php
// /api/callsigns.php

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=60');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

date_default_timezone_set('America/Los_Angeles');

$defaultLimit = 25;
$minLimit     = 1;
$maxLimit     = 100000;

$limitParam = isset($_GET['limit']) ? (int)$_GET['limit'] : $defaultLimit;
$limit      = max($minLimit, min($limitParam, $maxLimit));

$q          = isset($_GET['q']) ? trim($_GET['q']) : '';
$qmode      = isset($_GET['qmode']) ? strtolower(trim($_GET['qmode'])) : 'contains'; // 'prefix'|'contains'
$validated  = isset($_GET['validated']) ? trim($_GET['validated']) : ''; // '', '0', '1'
$min_seen   = isset($_GET['min_seen']) ? (int)$_GET['min_seen'] : null;

$sinceRaw   = isset($_GET['since']) ? trim($_GET['since']) : '';
$untilRaw   = isset($_GET['until']) ? trim($_GET['until']) : '';
$order      = isset($_GET['order']) ? strtolower(trim($_GET['order'])) : 'last_seen';
$dir        = isset($_GET['dir']) ? strtolower(trim($_GET['dir'])) : 'desc';
$debug      = (isset($_GET['debug']) && $_GET['debug'] === '1');

function is_date_only($s){ return (bool)preg_match('/^\d{4}-\d{2}-\d{2}$/', $s); }
function parse_local_dt($raw){
    if ($raw === '' || $raw === null) return null;
    try {
        $hasOffset = (bool)preg_match('/[zZ]|[\+\-]\d{2}:?\d{2}$/', $raw);
        if ($hasOffset) { $dt = new DateTime($raw); $dt->setTimezone(new DateTimeZone('America/Los_Angeles')); }
        else { $dt = new DateTime($raw, new DateTimeZone('America/Los_Angeles')); }
        return $dt;
    } catch (Exception $e) { return null; }
}
function stmt_bind_params($stmt, $types, array $params) {
    if ($types === '' || empty($params)) return true;
    $a = array($types);
    foreach ($params as $k => $v) { $a[] = &$params[$k]; }
    return call_user_func_array(array($stmt,'bind_param'), $a);
}
function stmt_fetch_all_assoc($stmt) {
    $meta = $stmt->result_metadata();
    if (!$meta) return array();
    $row = array(); $bind = array(); $fields = array();
    while ($f = $meta->fetch_field()) { $fields[]=$f->name; $row[$f->name]=null; $bind[]=&$row[$f->name]; }
    call_user_func_array(array($stmt,'bind_result'), $bind);
    $out = array();
    while ($stmt->fetch()) { $copy=array(); foreach($fields as $n){ $copy[$n]=$row[$n]; } $out[]=$copy; }
    return $out;
}

include 'db.php';
if (!isset($conn) || !($conn instanceof mysqli)) { http_response_code(500); echo json_encode(['error'=>'DB not initialized']); exit; }

// parse dates (applied to last_seen)
$sinceDT = $sinceRaw ? parse_local_dt($sinceRaw) : null;
$untilDT = $untilRaw ? parse_local_dt($untilRaw) : null;
if ($sinceDT && is_date_only($sinceRaw)) $sinceDT->setTime(0,0,0);
if ($untilDT && is_date_only($untilRaw)) $untilDT->setTime(23,59,59);

// ORDER BY safety
$allowedOrder = array('last_seen'=>'last_seen','first_seen'=>'first_seen','seen_count'=>'seen_count','callsign'=>'callsign');
$orderCol = isset($allowedOrder[$order]) ? $allowedOrder[$order] : 'last_seen';
$dirSql   = ($dir === 'asc') ? 'ASC' : 'DESC';

// Build WHERE
$where = array();
$types = '';
$params = array();

if ($q !== '') {
    if ($qmode === 'prefix') { $where[] = "callsign LIKE ?"; $types .='s'; $params[] = strtoupper($q).'%'; }
    else { $where[] = "callsign LIKE ?"; $types .='s'; $params[] = '%'.strtoupper($q).'%'; }
}
if ($validated === '0' || $validated === '1') {
    $where[] = "validated = ?"; $types .='i'; $params[] = (int)$validated;
}
if ($min_seen !== null) {
    $where[] = "seen_count >= ?"; $types .='i'; $params[] = $min_seen;
}
if ($sinceDT) { $where[] = "last_seen >= ?"; $types .='s'; $params[] = $sinceDT->format('Y-m-d H:i:s'); }
if ($untilDT) { $where[] = "last_seen <= ?"; $types .='s'; $params[] = $untilDT->format('Y-m-d H:i:s'); }

$whereSql = $where ? ('WHERE '.implode(' AND ',$where)) : '';

$sql = "
    SELECT
        ID,
        callsign,
        validated,
        first_seen,
        last_seen,
        seen_count
    FROM callsigns
    $whereSql
    ORDER BY $orderCol $dirSql
    LIMIT ".(int)$limit."
";

try {
    $stmt = $conn->prepare($sql);
    if (!$stmt) throw new Exception('prepare failed: '.$conn->error);
    if ($types !== '') { if (!stmt_bind_params($stmt, $types, $params)) throw new Exception('bind_param failed'); }
    if (!$stmt->execute()) throw new Exception('execute failed: '.$stmt->error);

    if (method_exists($stmt,'get_result')) {
        $res  = $stmt->get_result();
        $rows = $res ? $res->fetch_all(MYSQLI_ASSOC) : array();
    } else {
        $stmt->store_result();
        $rows = stmt_fetch_all_assoc($stmt);
    }
    $stmt->close();

    if ($debug) echo json_encode(['data'=>$rows, '_meta'=>['effective_limit'=>$limit,'order'=>$orderCol,'dir'=>$dirSql]], JSON_UNESCAPED_UNICODE);
    else echo json_encode($rows, JSON_UNESCAPED_UNICODE);

} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['error'=>'Server error','message'=>$e->getMessage()]);
}
