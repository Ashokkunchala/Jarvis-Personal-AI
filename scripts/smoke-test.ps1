$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"
if (-not (Test-Path ".env")) { throw "Run this from the repository root; .env was not found." }

function Read-DotEnvValue([string]$key) {
    $line = Get-Content ".env" | Where-Object { $_ -match "^\s*$([regex]::Escape($key))\s*=" } | Select-Object -Last 1
    if (-not $line) { return "" }
    return ($line -replace "^\s*$([regex]::Escape($key))\s*=\s*", "").Trim().Trim('"').Trim("'")
}

Write-Host "Checking local health endpoint..."
$health = Invoke-RestMethod -Uri "$base/health" -Method Get -TimeoutSec 5
if ($health.status -ne "ok") { throw "Health check did not return status=ok." }
Write-Host "Health check passed."

$token = Read-DotEnvValue "JARVIS_API_TOKEN"
$headers = @{}
if ($token -and $token.Length -ge 32 -and -not $token.StartsWith("replace_")) {
    $headers["Authorization"] = "Bearer $token"
}
Write-Host "Sending one short Gemini request. Provider usage/quota may apply..."
$body = @{ message = "Reply with exactly: JARVIS_SMOKE_TEST_OK"; language = "en"; history = @() } | ConvertTo-Json -Depth 5
try {
    $reply = Invoke-RestMethod -Uri "$base/api/chat" -Method Post -ContentType "application/json" -Headers $headers -Body $body -TimeoutSec 45
} catch {
    throw "Chat smoke test failed. Check .env, device token, model access, network, quota, and the server terminal. Do not share your API key. Details: $($_.Exception.Message)"
}
if (-not $reply.reply) { throw "Gemini returned no text." }
Write-Host "Gemini request succeeded. Model: $($reply.model)"
Write-Host "Reply: $($reply.reply)"
Write-Host "Smoke test complete."
