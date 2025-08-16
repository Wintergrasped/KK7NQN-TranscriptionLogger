<?php
// db_transcriber.php

$DB_HOST = 'IP/ HOST';
$DB_NAME = 'DATABSE NAME';
$DB_USER = 'USERNAME';
$DB_PASS = 'PASSWORD';

try {
    $pdo = new PDO(
        "mysql:host={$DB_HOST};dbname={$DB_NAME};charset=utf8mb4",
        $DB_USER,
        $DB_PASS,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false
        ]
    );
} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Database connection failed', 'details' => $e->getMessage()]);
    exit;
}
