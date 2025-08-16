<?php
header('Content-Type: application/json');
include 'db.php';
$start = $_GET['start'] ?? '';
$end = $_GET['end'] ?? '';
if (!$start || !$end) {
    echo json_encode(["error" => "Missing start or end"]);
    exit;
}
$stmt = $conn->prepare("SELECT * FROM transcriptions WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp");
$stmt->bind_param("ss", $start, $end);
$stmt->execute();
$res = $stmt->get_result();
$transcripts = [];
while ($row = $res->fetch_assoc()) $transcripts[] = $row;

$stmt2 = $conn->prepare("SELECT callsign, COUNT(*) as mentions FROM callsign_log WHERE timestamp BETWEEN ? AND ? GROUP BY callsign ORDER BY mentions DESC");
$stmt2->bind_param("ss", $start, $end);
$stmt2->execute();
$res2 = $stmt2->get_result();
$call_signs = [];
while ($row = $res2->fetch_assoc()) $call_signs[] = $row;

echo json_encode(["transcripts" => $transcripts, "call_signs" => $call_signs]);
?>