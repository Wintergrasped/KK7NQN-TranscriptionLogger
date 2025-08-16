<?php
header('Content-Type: application/json');
include 'db.php';
$callsign = $_GET['cs'] ?? '';
if (!$callsign) {
    echo json_encode(["summary" => null]);
    exit;
}
$stmt = $conn->prepare("SELECT * FROM callsigns WHERE callsign = ?");
$stmt->bind_param("s", $callsign);
$stmt->execute();
$res = $stmt->get_result();
if ($res->num_rows === 0) {
    echo json_encode(["summary" => null]);
	
    exit;
}
$summary = $res->fetch_assoc();

// Logs
$logs_stmt = $conn->prepare("SELECT cs_log.timestamp, t.transcription FROM callsign_log cs_log JOIN transcriptions t ON cs_log.transcript_id = t.id WHERE cs_log.callsign = ? ORDER BY cs_log.timestamp DESC LIMIT 25");
$logs_stmt->bind_param("s", $callsign);
$logs_stmt->execute();
$logs_res = $logs_stmt->get_result();
$logs = [];
while ($row = $logs_res->fetch_assoc()) $logs[] = $row;

// Activity
$act_stmt = $conn->prepare("SELECT DATE(timestamp) as date, COUNT(*) as count FROM callsign_log WHERE callsign = ? GROUP BY DATE(timestamp) ORDER BY date");
$act_stmt->bind_param("s", $callsign);
$act_stmt->execute();
$act_res = $act_stmt->get_result();
$activity = [];
while ($row = $act_res->fetch_assoc()) $activity[] = $row;

echo json_encode(["summary" => $summary, "logs" => $logs, "activity" => $activity]);
?>