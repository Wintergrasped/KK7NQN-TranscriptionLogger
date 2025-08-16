<?php
header('Content-Type: application/json');
include 'db.php';

// Set default, min, and max limits
$defaultLimit = 25;


// Get the 'limit' parameter from the URL query string
$limit = isset($_GET['limit']) ? intval($_GET['limit']) : $defaultLimit;


$sql = "SELECT * FROM callsigns ORDER BY seen_count DESC LIMIT $limit";
$result = $conn->query($sql);
$data = [];
while ($row = $result->fetch_assoc()) $data[] = $row;
echo json_encode($data);
?>