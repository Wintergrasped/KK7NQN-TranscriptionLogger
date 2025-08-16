<?php
// /api/health.php

// --- CORS & JSON headers ---
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// --- Handle CORS preflight ---
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// --- Build response ---
$response = [
    'ok'    => true,
    'time'  => gmdate('c'),
    'ip'    => $_SERVER['REMOTE_ADDR'] ?? null,
    'ua'    => $_SERVER['HTTP_USER_AGENT'] ?? null,
    'proto' => $_SERVER['SERVER_PROTOCOL'] ?? null,
    'method'=> $_SERVER['REQUEST_METHOD'] ?? null,
    'query' => $_GET ?? [],
    'headers' => getallheaders(), // shows exactly what the client sent
];

// --- Output JSON safely ---
echo json_encode($response, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
?>