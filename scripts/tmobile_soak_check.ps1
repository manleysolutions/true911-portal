#!/usr/bin/env pwsh
# T-Mobile Callback Ingest -- Phase 1a Soak daily check.
#
# Read-only. Connects to the production database only if $env:DATABASE_URL
# is set, wraps every query in BEGIN TRANSACTION READ ONLY ... ROLLBACK,
# runs a fixed SELECT-only query set, prints a PASS / WARN summary, exits
# 0 on all PASS or 1 on any WARN.
#
# This script does NOT:
#   * write to the database
#   * call the API, Render dashboard, T-Mobile, Cloudflare, or any other
#     external service
#   * replay or re-enqueue any callback
#   * touch any feature flag or env var
#
# Full runbook (red flags, manual SQL, success criteria, escalation):
#   docs/TMOBILE_CALLBACK_SOAK_RUNBOOK.md
#
# Prerequisites:
#   * psql on PATH
#   * Render dashboard → true911-prod-db → "External Database URL"
#     copied into $env:DATABASE_URL (or passed via -DatabaseUrl)
#
# Usage:
#   $env:DATABASE_URL = "postgres://USER:PASS@HOST.render.com/DBNAME"
#   ./scripts/tmobile_soak_check.ps1
#   Remove-Item Env:DATABASE_URL   # clear after to avoid lingering creds

[CmdletBinding()]
param(
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [int]$HoursWindow = 24,
  [int]$QueuedStuckMinutes = 5
)

$ErrorActionPreference = 'Stop'
$results = @()

function Add-Result {
  param(
    [Parameter(Mandatory)][string]$Check,
    [Parameter(Mandatory)][ValidateSet('PASS', 'WARN', 'INFO')][string]$Status,
    [string]$Detail = ''
  )
  $script:results += [pscustomobject]@{
    Check  = $Check
    Status = $Status
    Detail = $Detail
  }
  $color = switch ($Status) {
    'PASS' { 'Green' }
    'WARN' { 'Yellow' }
    'INFO' { 'DarkGray' }
  }
  Write-Host ("[{0}] {1}" -f $Status, $Check) -ForegroundColor $color
  if (-not [string]::IsNullOrWhiteSpace($Detail)) {
    Write-Host ("       {0}" -f $Detail) -ForegroundColor DarkGray
  }
}

function Invoke-ReadOnlySql {
  # Executes a SELECT inside an explicit READ-ONLY transaction.  Any
  # accidental DML in the script would be rejected by Postgres itself,
  # giving us a second layer of safety beyond "we only wrote SELECTs".
  param([Parameter(Mandatory)][string]$Sql)
  $wrapped = @"
BEGIN TRANSACTION READ ONLY;
$Sql
ROLLBACK;
"@
  # -t: tuples only; -A: unaligned; -X: no psqlrc; -q: quiet;
  # -v ON_ERROR_STOP=on: stop on any SQL error.
  $out = $wrapped | & psql `
    --no-password `
    -X -q -t -A `
    -v ON_ERROR_STOP=on `
    -F '|' `
    "$DatabaseUrl" 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "psql failed (exit $LASTEXITCODE): $out"
  }
  return ($out | Where-Object { $_ -ne '' })
}

# ── 1. Sanity ──────────────────────────────────────────────────────

Write-Host '=== T-Mobile callback soak check ===' -ForegroundColor Cyan
Write-Host ("    window: last {0} hours" -f $HoursWindow) -ForegroundColor DarkGray
Write-Host ''

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
  Write-Host 'ERROR: DATABASE_URL not set.' -ForegroundColor Red
  Write-Host '  Either set $env:DATABASE_URL or pass -DatabaseUrl.' -ForegroundColor Yellow
  Write-Host '  Get it from Render dashboard -> true911-prod-db -> External Database URL.' -ForegroundColor Yellow
  exit 1
}

$psql = Get-Command psql -ErrorAction SilentlyContinue
if ($null -eq $psql) {
  Write-Host 'ERROR: psql not found on PATH.' -ForegroundColor Red
  Write-Host '  Install the PostgreSQL client and retry.' -ForegroundColor Yellow
  exit 1
}

try {
  $version = Invoke-ReadOnlySql -Sql 'SELECT version();'
  Add-Result -Check 'database reachable (read-only transaction OK)' -Status 'PASS' `
    -Detail ("server: " + ($version -split ' ')[1])
} catch {
  Add-Result -Check 'database reachable' -Status 'WARN' `
    -Detail ("connection failed: " + $_.Exception.Message)
  Write-Host ''
  Write-Host 'Cannot continue without DB connectivity.' -ForegroundColor Red
  exit 1
}

# ── Q1. Recent webhook.tmobile jobs by status ──────────────────────

try {
  $rows = Invoke-ReadOnlySql -Sql @"
SELECT status, count(*)
FROM jobs
WHERE job_type = 'webhook.tmobile'
  AND created_at > now() - interval '$HoursWindow hours'
GROUP BY status
ORDER BY status;
"@
  $counts = @{}
  foreach ($r in $rows) {
    $parts = $r -split '\|'
    if ($parts.Count -ge 2) { $counts[$parts[0]] = [int]$parts[1] }
  }
  $completed = if ($counts.ContainsKey('completed')) { $counts['completed'] } else { 0 }
  $failed = if ($counts.ContainsKey('failed')) { $counts['failed'] } else { 0 }
  $queued = if ($counts.ContainsKey('queued')) { $counts['queued'] } else { 0 }
  $running = if ($counts.ContainsKey('running')) { $counts['running'] } else { 0 }
  $total = $completed + $failed + $queued + $running

  $detail = "completed=$completed failed=$failed queued=$queued running=$running"
  if ($total -eq 0) {
    Add-Result -Check 'Q1 recent webhook.tmobile jobs' -Status 'INFO' `
      -Detail 'zero callbacks in window -- T-Mobile may be quiet, or our endpoint unreachable (check Q5 + Cloudflare)'
  } elseif ($failed -gt 0) {
    Add-Result -Check 'Q1 webhook.tmobile failed jobs' -Status 'WARN' `
      -Detail "$failed failed in window (see Q3 for rows); $detail"
  } else {
    Add-Result -Check 'Q1 webhook.tmobile jobs healthy' -Status 'PASS' -Detail $detail
  }
} catch {
  Add-Result -Check 'Q1' -Status 'WARN' -Detail ("query failed: " + $_.Exception.Message)
}

# ── Q2. Status distribution from jobs.result ───────────────────────

try {
  $rows = Invoke-ReadOnlySql -Sql @"
SELECT COALESCE(result->>'tmobile_status', '(none)'), count(*)
FROM jobs
WHERE job_type = 'webhook.tmobile'
  AND created_at > now() - interval '$HoursWindow hours'
GROUP BY 1
ORDER BY 2 DESC;
"@
  $promoted = 0
  $promotedFb = 0
  $flagOff = 0
  $ambig = 0
  $detail = @()
  foreach ($r in $rows) {
    $parts = $r -split '\|'
    if ($parts.Count -lt 2) { continue }
    $detail += "{0}={1}" -f $parts[0], $parts[1]
    switch ($parts[0]) {
      'promoted'                       { $promoted   = [int]$parts[1] }
      'promoted:device_fallback'       { $promotedFb = [int]$parts[1] }
      'skipped:flag_off'               { $flagOff    = [int]$parts[1] }
      'skipped:ambiguous_match'        { $ambig     += [int]$parts[1] }
      'skipped:ambiguous_device_match' { $ambig     += [int]$parts[1] }
    }
  }
  $detailStr = ($detail -join ' ')
  if ($flagOff -gt 0) {
    Add-Result -Check 'Q2 skipped:flag_off present' -Status 'WARN' `
      -Detail "$flagOff job(s) -- worker missing FEATURE_TMOBILE_CALLBACK_INGEST=true (see render-env-vars-per-service-pitfall). full: $detailStr"
  } elseif ($ambig -gt 0) {
    Add-Result -Check 'Q2 ambiguous matches present' -Status 'WARN' `
      -Detail "$ambig ambiguous job(s) -- duplicate ICCID/MSISDN somewhere. full: $detailStr"
  } elseif (($promoted + $promotedFb) -gt 0) {
    Add-Result -Check 'Q2 status distribution healthy' -Status 'PASS' -Detail $detailStr
  } else {
    Add-Result -Check 'Q2 no promotions in window' -Status 'INFO' `
      -Detail "no promoted/promoted:device_fallback rows. could be zero callbacks or all callbacks were CIM/static-ip. full: $detailStr"
  }
} catch {
  Add-Result -Check 'Q2' -Status 'WARN' -Detail ("query failed: " + $_.Exception.Message)
}

# ── Q3. Failed webhook.tmobile jobs (sample) ───────────────────────

try {
  $rows = Invoke-ReadOnlySql -Sql @"
SELECT id, attempt, COALESCE(substring(error from 1 for 80), '(no error)')
FROM jobs
WHERE job_type = 'webhook.tmobile'
  AND status = 'failed'
  AND created_at > now() - interval '7 days'
ORDER BY id DESC
LIMIT 5;
"@
  if ($rows.Count -eq 0) {
    Add-Result -Check 'Q3 no failed webhook.tmobile jobs (last 7d)' -Status 'PASS'
  } else {
    Add-Result -Check 'Q3 FAILED webhook.tmobile jobs detected' -Status 'WARN' `
      -Detail ("first 5: " + ($rows -join ' || '))
  }
} catch {
  Add-Result -Check 'Q3' -Status 'WARN' -Detail ("query failed: " + $_.Exception.Message)
}

# ── Q4. Stuck queued jobs ──────────────────────────────────────────

try {
  $rows = Invoke-ReadOnlySql -Sql @"
SELECT id, job_type, attempt
FROM jobs
WHERE status = 'queued'
  AND created_at < now() - interval '$QueuedStuckMinutes minutes'
ORDER BY id
LIMIT 10;
"@
  if ($rows.Count -eq 0) {
    Add-Result -Check ("Q4 no jobs stuck queued > {0}m" -f $QueuedStuckMinutes) -Status 'PASS'
  } else {
    Add-Result -Check 'Q4 STUCK queued jobs detected' -Status 'WARN' `
      -Detail ("first 10: " + ($rows -join ' || '))
  }
} catch {
  Add-Result -Check 'Q4' -Status 'WARN' -Detail ("query failed: " + $_.Exception.Message)
}

# ── Q5. IntegrationPayload tmobile archive vs processed ────────────

try {
  $rows = Invoke-ReadOnlySql -Sql @"
SELECT count(*),
       sum(case when processed then 1 else 0 end)
FROM integration_payloads
WHERE source = 'tmobile'
  AND created_at > now() - interval '$HoursWindow hours';
"@
  if ($rows.Count -eq 0) {
    Add-Result -Check 'Q5 IntegrationPayload archive' -Status 'INFO' -Detail 'no rows in window'
  } else {
    $parts = ($rows[0]) -split '\|'
    $total = [int]$parts[0]
    $proc = [int]$parts[1]
    if ($total -eq 0) {
      Add-Result -Check 'Q5 IntegrationPayload tmobile rows' -Status 'INFO' `
        -Detail 'zero in window (matches Q1 zero-callbacks scenario)'
    } elseif ($total -eq $proc) {
      Add-Result -Check 'Q5 IntegrationPayload archived AND processed' -Status 'PASS' `
        -Detail ("total={0} processed={1}" -f $total, $proc)
    } else {
      Add-Result -Check 'Q5 IntegrationPayload archive vs processed DELTA' -Status 'WARN' `
        -Detail ("total={0} processed={1} -- worker not reaching some rows" -f $total, $proc)
    }
  }
} catch {
  Add-Result -Check 'Q5' -Status 'WARN' -Detail ("query failed: " + $_.Exception.Message)
}

# ── Q6. Recent device promotions via t-mobile carrier ──────────────

try {
  $rows = Invoke-ReadOnlySql -Sql @"
SELECT count(*)
FROM devices
WHERE telemetry_source = 't-mobile_carrier'
  AND last_network_event > now() - interval '$HoursWindow hours';
"@
  $count = if ($rows.Count -gt 0) { [int]$rows[0] } else { 0 }
  if ($count -gt 0) {
    Add-Result -Check 'Q6 devices promoted via t-mobile_carrier' -Status 'PASS' `
      -Detail ("{0} device(s) updated in window" -f $count)
  } else {
    Add-Result -Check 'Q6 no device promotions in window' -Status 'INFO' `
      -Detail 'expected if zero callbacks, otherwise cross-check Q2 + Q5'
  }
} catch {
  Add-Result -Check 'Q6' -Status 'WARN' -Detail ("query failed: " + $_.Exception.Message)
}

# ── Q7. command_telemetry rows for t-mobile ────────────────────────

try {
  $rows = Invoke-ReadOnlySql -Sql @"
SELECT count(*)
FROM command_telemetry
WHERE metadata_json LIKE '%"source": "t-mobile_carrier"%'
  AND created_at > now() - interval '$HoursWindow hours';
"@
  $count = if ($rows.Count -gt 0) { [int]$rows[0] } else { 0 }
  if ($count -gt 0) {
    Add-Result -Check 'Q7 command_telemetry t-mobile rows present' -Status 'PASS' `
      -Detail ("{0} row(s) in window" -f $count)
  } else {
    Add-Result -Check 'Q7 no command_telemetry t-mobile rows in window' -Status 'INFO' `
      -Detail 'expected if zero promotions; if promotions > 0 (Q2), this is a WARN'
  }
} catch {
  Add-Result -Check 'Q7' -Status 'WARN' -Detail ("query failed: " + $_.Exception.Message)
}

# ── Q9. Cross-tenant sanity (top 5 tenants with t-mobile evidence) ─

try {
  $rows = Invoke-ReadOnlySql -Sql @"
SELECT tenant_id, count(*)
FROM devices
WHERE telemetry_source = 't-mobile_carrier'
  AND last_network_event > now() - interval '7 days'
GROUP BY tenant_id
ORDER BY 2 DESC
LIMIT 5;
"@
  if ($rows.Count -eq 0) {
    Add-Result -Check 'Q9 tenant distribution (last 7d)' -Status 'INFO' `
      -Detail 'no promotions in 7d window'
  } else {
    Add-Result -Check 'Q9 tenant distribution (last 7d)' -Status 'INFO' `
      -Detail ("review manually for unexpected tenants: " + ($rows -join '; '))
  }
} catch {
  Add-Result -Check 'Q9' -Status 'WARN' -Detail ("query failed: " + $_.Exception.Message)
}

# ── Summary ────────────────────────────────────────────────────────

$pass = ($results | Where-Object { $_.Status -eq 'PASS' }).Count
$warn = ($results | Where-Object { $_.Status -eq 'WARN' }).Count
$info = ($results | Where-Object { $_.Status -eq 'INFO' }).Count

Write-Host ''
Write-Host '=======================================================' -ForegroundColor White
Write-Host (" T-Mobile soak: PASS={0}  WARN={1}  INFO={2}" -f $pass, $warn, $info) `
  -ForegroundColor $(if ($warn -gt 0) { 'Yellow' } else { 'Green' })
Write-Host '=======================================================' -ForegroundColor White

if ($warn -gt 0) {
  Write-Host ''
  Write-Host 'WARN items -- drill into the specific check using the matching' -ForegroundColor Yellow
  Write-Host 'SQL block in docs/TMOBILE_CALLBACK_SOAK_RUNBOOK.md, then' -ForegroundColor Yellow
  Write-Host 'consult the Red flags table for the first-action step.' -ForegroundColor Yellow
  $results | Where-Object { $_.Status -eq 'WARN' } | Format-Table Check, Detail -Wrap
  exit 1
}

Write-Host ''
Write-Host 'All checks PASS or INFO. Repeat daily during soak window.' -ForegroundColor Green
Write-Host 'Manual checks still required (script cannot reach these):' -ForegroundColor DarkGray
Write-Host '  * Cloudflare dashboard -> Security -> Events for pit-api.manleysolutions.com' -ForegroundColor DarkGray
Write-Host '  * T-Mobile PIT validator dashboard (operator confirms with T-Mobile engineering)' -ForegroundColor DarkGray
exit 0
