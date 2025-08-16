<?php
header('Content-Type: application/json');
include 'db.php';

// Set default, min, and max limits
$defaultLimit = 25;
$minLimit = 10;
$maxLimit = 100000;

// Get the 'limit' parameter from the URL query string
$limit = isset($_GET['limit']) ? intval($_GET['limit']) : $defaultLimit;

// Clamp the limit to be between $minLimit and $maxLimit
$limit = max($minLimit, min($limit, $maxLimit));

// Example query using the sanitized $limit
$sql = "SELECT * FROM transcriptions ORDER BY timestamp DESC LIMIT $limit";
$result = $conn->query($sql);

// Continue processing $result as usual...


if (!$result) {
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

$data = [];
while ($row = $result->fetch_assoc()) {
    $data[] = $row;
}

if (json_encode($data) === false) {
    echo json_encode(["error" => "JSON encoding failed", "json_error" => json_last_error_msg()]);
    exit;
}

echo json_encode($data);
?>
