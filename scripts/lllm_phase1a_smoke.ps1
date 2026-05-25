#!/usr/bin/env pwsh
# LLLM Phase 1a deterministic-soak smoke test.
#
# Run from your local machine AFTER PR #55 has merged and Render has
# finished deploying both the API and the static web service.  The
# only thing you need to provide is a SuperAdmin JWT — grab it from
# any logged-in browser tab via DevTools:
#
#   localStorage.getItem('t911_token')
#
# Then either set TRUE911_TOKEN in your env or pass it as -Token.
#
# What this verifies (covers smoke items 1, 4, 5, 6, 7 from the
# enable-Phase-1a instruction):
#   * /api/config/features surfaces lllm:true
#   * /api/llm/health-summary (fleet) succeeds for SuperAdmin
#   * Response has deterministic_fallback=true and source="fallback"
#     — confirming LLLM_ALLOW_EXTERNAL=false is honored
#   * Response model is "deterministic" (not a Claude model)
#   * Audit row is implied by every call — DB spot-check left to you
#
# Items 2 (UI visibility) and 3 (impersonation containment) are
# verified by structure (Layout.jsx NOC_NAV-only + backend
# _require_internal_context), not by this script.

[CmdletBinding()]
param(
  [string]$ApiHost = "https://true911-api.onrender.com",
  [string]$Token = $env:TRUE911_TOKEN
)

if ([string]::IsNullOrWhiteSpace($Token)) {
  Write-Host "ERROR: No JWT supplied." -ForegroundColor Red
  Write-Host "  Either set `$env:TRUE911_TOKEN or pass -Token <jwt>." -ForegroundColor Yellow
  Write-Host "  Grab one from a logged-in browser tab:" -ForegroundColor Yellow
  Write-Host "    localStorage.getItem('t911_token')" -ForegroundColor Yellow
  exit 1
}

$headers = @{ "Authorization" = "Bearer $Token" }
$results = @()

function Add-Result($name, $passed, $detail) {
  $script:results += [pscustomobject]@{
    Check  = $name
    Passed = $passed
    Detail = $detail
  }
  $color = if ($passed) { "Green" } else { "Red" }
  $mark  = if ($passed) { "PASS" } else { "FAIL" }
  Write-Host "[$mark] $name" -ForegroundColor $color
  if (-not [string]::IsNullOrWhiteSpace($detail)) {
    Write-Host "       $detail" -ForegroundColor DarkGray
  }
}

# ── 1. /api/config/features surfaces lllm:true ────────────────────
Write-Host "`n=== 1. /api/config/features ===" -ForegroundColor Cyan
try {
  $f = Invoke-RestMethod -Uri "$ApiHost/api/config/features" -Method Get -TimeoutSec 20
  Add-Result "features.lllm == true" ($f.lllm -eq $true) ("features=" + ($f | ConvertTo-Json -Compress))
} catch {
  Add-Result "features.lllm == true" $false "request failed: $($_.Exception.Message)"
}

# ── 2. Auth + permission + internal-only gate (unauth probe) ──────
Write-Host "`n=== 2. Route auth (no token expects 401, not 404) ===" -ForegroundColor Cyan
try {
  Invoke-WebRequest -Uri "$ApiHost/api/llm/health-summary?scope=fleet" -Method Get -TimeoutSec 20 -UseBasicParsing | Out-Null
  Add-Result "unauthenticated /api/llm/health-summary" $false "unexpected 200 without token"
} catch {
  $code = $_.Exception.Response.StatusCode.value__
  Add-Result "unauthenticated -> 401 (not 404, so feature flag is honored)" ($code -eq 401) "got HTTP $code"
}

# ── 3. SuperAdmin: GET /api/llm/health-summary?scope=fleet ────────
Write-Host "`n=== 3. SuperAdmin fleet summary ===" -ForegroundColor Cyan
try {
  $s = Invoke-RestMethod -Uri "$ApiHost/api/llm/health-summary?scope=fleet" -Method Get -Headers $headers -TimeoutSec 30
  Add-Result "GET fleet returns 200 with valid payload" ($null -ne $s.summary_id) ("summary_id=" + $s.summary_id)
  Add-Result "scope == 'fleet'" ($s.scope -eq "fleet") ("scope=" + $s.scope)
  Add-Result "deterministic_fallback == true (LLLM_ALLOW_EXTERNAL=false honored)" ($s.deterministic_fallback -eq $true) ("got " + $s.deterministic_fallback)
  Add-Result "source == 'fallback'" ($s.source -eq "fallback") ("got " + $s.source)
  Add-Result "model == 'deterministic' (no Claude call)" ($s.model -eq "deterministic") ("got " + $s.model)
  Add-Result "sources_used has at least one entry" ($s.sources_used.Count -gt 0) ("sources=" + ($s.sources_used -join ","))
  Add-Result "confidence in [0.0, 1.0]" ($s.confidence -ge 0.0 -and $s.confidence -le 1.0) ("confidence=" + $s.confidence)
  Add-Result "customer_safe_summary is null in Phase 1" ($null -eq $s.customer_safe_summary) ("got " + $s.customer_safe_summary)
  Write-Host "`n--- Sample fleet summary ---" -ForegroundColor DarkCyan
  Write-Host "  current_status:        $($s.current_status)"
  Write-Host "  likely_issue:          $($s.likely_issue)"
  Write-Host "  recommended_next_step: $($s.recommended_next_step)"
} catch {
  Add-Result "GET fleet" $false "request failed: $($_.Exception.Message)"
}

# ── 4. POST /api/llm/health-summary/refresh ───────────────────────
Write-Host "`n=== 4. SuperAdmin refresh (bypasses cache) ===" -ForegroundColor Cyan
try {
  $r = Invoke-RestMethod -Uri "$ApiHost/api/llm/health-summary/refresh?scope=fleet" -Method Post -Headers $headers -TimeoutSec 30
  Add-Result "POST refresh returns 200" ($null -ne $r.summary_id) ("summary_id=" + $r.summary_id)
  Add-Result "still deterministic_fallback after refresh" ($r.deterministic_fallback -eq $true) ("got " + $r.deterministic_fallback)
} catch {
  Add-Result "POST refresh" $false "request failed: $($_.Exception.Message)"
}

# ── 5. Invalid scope → 422 (validates parameter) ──────────────────
Write-Host "`n=== 5. Parameter validation ===" -ForegroundColor Cyan
try {
  Invoke-WebRequest -Uri "$ApiHost/api/llm/health-summary?scope=universe" -Method Get -Headers $headers -TimeoutSec 20 -UseBasicParsing | Out-Null
  Add-Result "scope=universe rejected" $false "unexpected 200 with bad scope"
} catch {
  $code = $_.Exception.Response.StatusCode.value__
  Add-Result "scope=universe -> 422" ($code -eq 422) "got HTTP $code"
}

# ── 6. site scope without scope_id → 422 ──────────────────────────
try {
  Invoke-WebRequest -Uri "$ApiHost/api/llm/health-summary?scope=site" -Method Get -Headers $headers -TimeoutSec 20 -UseBasicParsing | Out-Null
  Add-Result "scope=site without scope_id rejected" $false "unexpected 200"
} catch {
  $code = $_.Exception.Response.StatusCode.value__
  Add-Result "scope=site without scope_id -> 422" ($code -eq 422) "got HTTP $code"
}

# ── Summary ────────────────────────────────────────────────────────
$passed = ($results | Where-Object Passed).Count
$total  = $results.Count
$failed = $total - $passed
Write-Host "`n========================================================" -ForegroundColor White
Write-Host " LLLM Phase 1a smoke results: $passed / $total passed" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Yellow" })
Write-Host "========================================================" -ForegroundColor White

if ($failed -gt 0) {
  Write-Host "`nFailures:" -ForegroundColor Red
  $results | Where-Object { -not $_.Passed } | Format-Table Check, Detail -AutoSize
  exit 1
}

Write-Host "`nAll passed.  Manual checks still required:" -ForegroundColor Yellow
Write-Host "  * Open the portal, log in as SuperAdmin, look for 'AI Health'"
Write-Host "    in the NOC nav.  Click it, run a Fleet summary.  Confirm the"
Write-Host "    response card shows the 'rules-based' source pill."
Write-Host "  * In Render dashboard or psql, run:"
Write-Host "      SELECT created_at, scope, status, error_summary"
Write-Host "        FROM llm_audit_log ORDER BY created_at DESC LIMIT 5;"
Write-Host "    Expect rows from your smoke run with status='fallback' and"
Write-Host "    error_summary='egress disabled'."
Write-Host "  * Check Anthropic console: zero requests today."
exit 0
