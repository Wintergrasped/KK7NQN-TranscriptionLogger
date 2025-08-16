<?php
// /api/callsign_transcriptions.php
// Callsign + mentions + date range + proper LIMIT handling + debug helper.

// --- headers ---
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=60');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

// --- timezone ---
date_default_timezone_set('America/Los_Angeles');

// --- params ---
$defaultLimit = 25;
$minLimit     = 1;          // was 10; make testing sane
$maxLimit     = 100000;

$limitParam   = isset($_GET['limit']) ? (int)$_GET['limit'] : $defaultLimit;
$limit        = max($minLimit, min($limitParam, $maxLimit)); // clamp hard

$callsign     = isset($_GET['callsign']) ? strtoupper(trim($_GET['callsign'])) : '';
$mentionsMode = (isset($_GET['mentions']) && $_GET['mentions'] === '1');
$sinceRaw     = isset($_GET['since']) ? trim($_GET['since']) : '';
$untilRaw     = isset($_GET['until']) ? trim($_GET['until']) : '';
$debug        = isset($_GET['debug']) && $_GET['debug'] === '1';

// --- helpers ---
function is_date_only_str($s) { return (bool)preg_match('/^\d{4}-\d{2}-\d{2}$/', $s); }
function parse_local_dt($raw) {
    if ($raw === '' || $raw === null) return null;
    try {
        $hasOffset = (bool)preg_match('/[zZ]|[\+\-]\d{2}:?\d{2}$/', $raw);
        if ($hasOffset) {
            $dt = new DateTime($raw);
            $dt->setTimezone(new DateTimeZone('America/Los_Angeles'));
        } else {
            $dt = new DateTime($raw, new DateTimeZone('America/Los_Angeles'));
        }
        return $dt;
    } catch (Exception $e) { return null; }
}
function stmt_bind_params($stmt, $types, array $params) {
    if ($types === '' || empty($params)) return true;
    $a = array($types);
    foreach ($params as $k => $v) { $a[] = &$params[$k]; } // by reference
    return call_user_func_array(array($stmt, 'bind_param'), $a);
}
function stmt_fetch_all_assoc($stmt) {
    $meta = $stmt->result_metadata();
    if (!$meta) return array();
    $row = array(); $bind = array(); $fields = array();
    while ($f = $meta->fetch_field()) {
        $fields[] = $f->name;
        $row[$f->name] = null;
        $bind[] = &$row[$f->name];
    }
    call_user_func_array(array($stmt, 'bind_result'), $bind);
    $out = array();
    while ($stmt->fetch()) {
        $copy = array();
        foreach ($fields as $name) { $copy[$name] = $row[$name]; }
        $out[] = $copy;
    }
    return $out;
}

// --- include DB ---
include 'db.php'; // must define $conn (MySQLi)
if (!isset($conn) || !($conn instanceof mysqli)) {
    http_response_code(500);
    echo json_encode(['error'=>'DB not initialized']);
    exit;
}

// --- parse times (local) ---
$sinceDT = $sinceRaw ? parse_local_dt($sinceRaw) : null;
$untilDT = $untilRaw ? parse_local_dt($untilRaw) : null;
if ($sinceDT && is_date_only_str($sinceRaw)) $sinceDT->setTime(0,0,0);
if ($untilDT && is_date_only_str($untilRaw)) $untilDT->setTime(23,59,59);

// --- run ---
try {
    $meta = ['branch'=>null,'effective_limit'=>$limit];

    if ($callsign !== '') {
        // Build WHERE for callsign_log (unaliased for reuse)
        $conds = array('callsign = ?');
        $types = 's';
        $binds = array($callsign);

        if ($sinceDT) { $conds[] = '`timestamp` >= ?'; $types .= 's'; $binds[] = $sinceDT->format('Y-m-d H:i:s'); }
        if ($untilDT) { $conds[] = '`timestamp` <= ?'; $types .= 's'; $binds[] = $untilDT->format('Y-m-d H:i:s'); }

        $cslParts = array();
        foreach ($conds as $c) $cslParts[] = 'csl.' . $c;
        $where_csl      = implode(' AND ', $cslParts);
        $where_no_alias = implode(' AND ', $conds);

        if ($mentionsMode) {
            $meta['branch'] = 'callsign_mentions';
            $sql = "
                SELECT
                    t.id            AS transcript_id,
                    t.filename,
                    t.transcription,
                    t.`timestamp`   AS transcript_timestamp,
                    csl.`timestamp` AS mentioned_at
                FROM callsign_log csl
                JOIN transcriptions t ON t.id = csl.transcript_id
                WHERE $where_csl
                ORDER BY csl.`timestamp` DESC
                LIMIT ".(int)$limit."
            ";
            $stmt = $conn->prepare($sql);
            if (!$stmt) throw new Exception('prepare failed (mentions): ' . $conn->error);
            if (!stmt_bind_params($stmt, $types, $binds)) throw new Exception('bind_param failed (mentions)');
            if (!$stmt->execute()) throw new Exception('execute failed (mentions): ' . $stmt->error);

        } else {
            $meta['branch'] = 'callsign_dedup';
            // LIMIT is on the OUTER query (after the join) — fixes N-1 and honors exact limit.
            $sql = "
                SELECT
                    t.id          AS transcript_id,
                    t.filename,
                    t.transcription,
                    t.`timestamp` AS transcript_timestamp,
                    x.last_mentioned_at
                FROM (
                    SELECT
                        transcript_id,
                        MAX(`timestamp`) AS last_mentioned_at
                    FROM callsign_log
                    WHERE $where_no_alias
                    GROUP BY transcript_id
                ) x
                JOIN transcriptions t ON t.id = x.transcript_id
                ORDER BY x.last_mentioned_at DESC
                LIMIT ".(int)$limit."
            ";
            $stmt = $conn->prepare($sql);
            if (!$stmt) throw new Exception('prepare failed (dedup): ' . $conn->error);
            if (!stmt_bind_params($stmt, $types, $binds)) throw new Exception('bind_param failed (dedup)');
            if (!$stmt->execute()) throw new Exception('execute failed (dedup): ' . $stmt->error);
        }

    } else {
        $meta['branch'] = 'fallback_transcriptions';
        $where = array(); $types = ''; $binds = array();
        if ($sinceDT) { $where[] = "t.`timestamp` >= ?"; $types .= 's'; $binds[] = $sinceDT->format('Y-m-d H:i:s'); }
        if ($untilDT) { $where[] = "t.`timestamp` <= ?"; $types .= 's'; $binds[] = $untilDT->format('Y-m-d H:i:s'); }
        $whereSql = $where ? ('WHERE ' . implode(' AND ', $where)) : '';

        $sql = "
            SELECT
                t.id AS transcript_id,
                t.filename,
                t.transcription,
                t.`timestamp` AS transcript_timestamp
            FROM transcriptions t
            $whereSql
            ORDER BY t.`timestamp` DESC
            LIMIT ".(int)$limit."
        ";
        $stmt = $conn->prepare($sql);
        if (!$stmt) throw new Exception('prepare failed (fallback): ' . $conn->error);
        if ($types !== '') {
            if (!stmt_bind_params($stmt, $types, $binds)) throw new Exception('bind_param failed (fallback)');
        }
        if (!$stmt->execute()) throw new Exception('execute failed (fallback): ' . $stmt->error);
    }

    // fetch rows
    if (method_exists($stmt, 'get_result')) {
        $res = $stmt->get_result();
        $rows = $res ? $res->fetch_all(MYSQLI_ASSOC) : array();
    } else {
        $stmt->store_result();
        $rows = stmt_fetch_all_assoc($stmt);
    }
    $stmt->close();

    // Optional debug metadata (non-breaking): append as a trailing object
    if ($debug) {
        // return `{ data: [...], _meta: {...} }` instead of raw array
        echo json_encode(['data'=>$rows, '_meta'=>$meta], JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    } else {
        echo json_encode($rows, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    }
    exit;

} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['error'=>'Server error','message'=>$e->getMessage()]);
    exit;
}
