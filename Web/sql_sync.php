<?php
header('Content-Type: application/json');
mysqli_report(MYSQLI_REPORT_OFF);

// ✅ API Key Authentication
$api_key = "YOUR API KEY (Or same long random string as set in .sh script)";
if (!isset($_SERVER['HTTP_X_API_KEY']) || $_SERVER['HTTP_X_API_KEY'] !== $api_key) {
    echo json_encode(["error" => "Unauthorized"]);
    exit;
}

// ✅ DB Connection
$mysqli = new mysqli("HOSTNAME", "USERNAME", "PASSWORD", "DATABASE");
if ($mysqli->connect_errno) {
    echo json_encode(["error" => "DB connection failed", "details" => $mysqli->connect_error]);
    exit;
}
$mysqli->set_charset("utf8mb4");

// ✅ Read JSON input
$raw = file_get_contents('php://input');
$data = json_decode($raw, true);
if (!$data) {
    echo json_encode(["error" => "Invalid JSON", "json_error" => json_last_error_msg()]);
    exit;
}

$response = [
    "status" => "ok",
    "rows_inserted" => 0,
    "rows_failed" => 0,
    "errors" => []
];

foreach ($data as $table => $rows) {
    if (!is_array($rows)) continue;

    // ✅ Get column names dynamically
    $colsResult = $mysqli->query("SHOW COLUMNS FROM `$table`");
    if (!$colsResult) {
        $response["errors"][] = ["table" => $table, "error" => $mysqli->error];
        continue;
    }

    $columns = [];
    while ($col = $colsResult->fetch_assoc()) {
        $columns[] = $col['Field'];
    }

    foreach ($rows as $rowSet) {
        // ✅ Handle nested array [[...],[...]]
        if (is_array($rowSet) && isset($rowSet[0]) && is_array($rowSet[0])) {
            foreach ($rowSet as $row) {
                processRow($mysqli, $table, $columns, $row, $response);
            }
        } else {
            processRow($mysqli, $table, $columns, $rowSet, $response);
        }
    }
}

echo json_encode($response);

// ✅ Function to insert row safely
function processRow($mysqli, $table, $columns, $row, &$response) {
    if (!is_array($row)) return;

    $insertCols = array_slice($columns, 0, count($row));
    $placeholders = implode(",", array_fill(0, count($row), '?'));
    $sql = "REPLACE INTO `$table` (`" . implode("`,`", $insertCols) . "`) VALUES ($placeholders)";
    
    $stmt = $mysqli->prepare($sql);
    if (!$stmt) {
        $response["rows_failed"]++;
        $response["errors"][] = ["table" => $table, "sql" => $sql, "error" => $mysqli->error];
        return;
    }

    // ✅ Bind all as strings
    $types = str_repeat('s', count($row));
    $stmt->bind_param($types, ...$row);

    if ($stmt->execute()) {
        $response["rows_inserted"]++;
    } else {
        $response["rows_failed"]++;
        $response["errors"][] = ["table" => $table, "sql" => $sql, "error" => $stmt->error];
    }

    $stmt->close();
}
?>
