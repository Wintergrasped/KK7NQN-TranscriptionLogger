<?php
$host = "IP / HOSTNAME";
$user = "USERNAME";
$pass = "PASSWORD";
$db = "DATABSE";

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    die(json_encode(["error" => "DB connection failed: " . $conn->connect_error]));
}

mysqli_set_charset($conn, "utf8mb4");
?>
