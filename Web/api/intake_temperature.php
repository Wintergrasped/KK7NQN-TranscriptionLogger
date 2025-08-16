<?php
header('Content-Type: application/json');
include 'db.php';
$sql = "SELECT * FROM temperature_log WHERE sensor_id='28-510500879011' ORDER BY timestamp DESC LIMIT 25";
$result = $conn->query($sql);
$data = [];
while ($row = $result->fetch_assoc()) $data[] = $row;
echo json_encode($data);
?>