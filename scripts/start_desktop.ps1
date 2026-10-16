param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$qpgRoot = Split-Path -Parent $PSScriptRoot
$qpgPython = Join-Path $qpgRoot '.venv\Scripts\python.exe'
$qpgInstance = Join-Path $qpgRoot 'instance'
$qpgStatePath = Join-Path $qpgInstance 'running_processes.json'
$qpgUrl = 'http://127.0.0.1:8080'

function Test-QpgProcess($processId, [string]$commandPattern) {
    if (-not $processId) { return $false }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process -or $process.Path -ne $qpgPython) { return $false }
    $details = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
    return $details.CommandLine -match $commandPattern
}

function Test-QpgWeb {
    try {
        $response = Invoke-WebRequest -Uri $qpgUrl -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content.Contains('hero-section')
    } catch { return $false }
}

try {
    if (-not (Test-Path -LiteralPath $qpgPython)) { throw 'Install the project dependencies in .venv first. See README.md.' }
    if (-not (Test-Path -LiteralPath (Join-Path $qpgRoot '.env'))) { throw 'Configure .env and PostgreSQL first. See README.md.' }
    $qpgEdge = @(
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $CheckOnly -and -not $qpgEdge) { throw 'Microsoft Edge is required for the desktop window. Install Edge or use the web interface.' }

    $qpgMutex = New-Object System.Threading.Mutex($false, 'Local\AshokaQPGDesktopStartup')
    $qpgHasLock = $qpgMutex.WaitOne(30000)
    if (-not $qpgHasLock) { throw 'Another QPG window is starting. Try again shortly.' }
    Set-Location -LiteralPath $qpgRoot
    $null = New-Item -ItemType Directory -Force -Path $qpgInstance
    $qpgState = @{ web_pid = $null; worker_pid = $null; url = $qpgUrl }
    if (Test-Path -LiteralPath $qpgStatePath) {
        $saved = Get-Content -LiteralPath $qpgStatePath | ConvertFrom-Json
        $qpgState.web_pid = $saved.web_pid
        $qpgState.worker_pid = $saved.worker_pid
    }
    $qpgWebRunning = Test-QpgProcess $qpgState.web_pid 'serve\.py.*--host\s+127\.0\.0\.1.*--port\s+8080'
    $qpgWorkerRunning = Test-QpgProcess $qpgState.worker_pid 'flask.*school_platform:create_app.*worker'
    if (-not $qpgWebRunning -or -not $qpgWorkerRunning) {
        # Check the configured database and migrated tables without displaying credentials.
        @'
import sys
try:
    from school_platform import create_app, db
    from sqlalchemy import text
    with create_app().app_context():
        db.session.execute(text('SELECT id FROM users LIMIT 1'))
        db.session.remove()
except Exception as exc:
    print('Database startup check failed: ' + type(exc).__name__, file=sys.stderr)
    sys.exit(1)
'@ | & $qpgPython -B - 2> (Join-Path $qpgInstance 'desktop-startup.stderr.log')
        if ($LASTEXITCODE -ne 0) { throw 'Cannot connect to the configured platform database. Check PostgreSQL, .env and migrations. Details: instance/desktop-startup.stderr.log.' }
    }
    if (-not $qpgWebRunning) {
        $portListener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
        if ($portListener) { throw 'Port 8080 is already in use by an untracked server. Close it or use that server in your browser.' }
        $web = Start-Process -FilePath $qpgPython -ArgumentList @('serve.py','--host','127.0.0.1','--port','8080') -WorkingDirectory $qpgRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $qpgInstance 'web.stdout.log') -RedirectStandardError (Join-Path $qpgInstance 'web.stderr.log') -PassThru
        $qpgState.web_pid = $web.Id
        $qpgState | ConvertTo-Json | Set-Content -LiteralPath $qpgStatePath
    }
    $qpgReady = $false
    $qpgDeadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        if (Test-QpgWeb) { $qpgReady = $true; break }
        if (-not (Test-QpgProcess $qpgState.web_pid 'serve\.py')) { break }
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $qpgDeadline)
    if (-not $qpgReady) { throw 'The web server did not become ready. Check instance/web.stderr.log.' }
    if (-not $qpgWorkerRunning) {
        $worker = Start-Process -FilePath $qpgPython -ArgumentList @('-m','flask','--app','school_platform:create_app','worker') -WorkingDirectory $qpgRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $qpgInstance 'worker.stdout.log') -RedirectStandardError (Join-Path $qpgInstance 'worker.stderr.log') -PassThru
        $qpgState.worker_pid = $worker.Id
        $qpgState | ConvertTo-Json | Set-Content -LiteralPath $qpgStatePath
        Start-Sleep -Seconds 2
        if (-not (Test-QpgProcess $qpgState.worker_pid 'flask.*school_platform:create_app.*worker')) { throw 'The generation worker could not start. Check instance/worker.stderr.log.' }
    }
    if (-not $CheckOnly) {
        $qpgProfile = Join-Path $qpgInstance 'desktop-profile'
        Start-Process -FilePath $qpgEdge -ArgumentList @("--app=$qpgUrl", "--user-data-dir=`"$qpgProfile`"", '--no-first-run', '--no-default-browser-check') -WorkingDirectory $qpgRoot -WindowStyle Normal
        Write-Output 'QPG opened in a Windows application window.'
    } else { Write-Output 'QPG web server and generation worker are ready.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    if ($qpgHasLock) { $qpgMutex.ReleaseMutex() }
    if ($qpgMutex) { $qpgMutex.Dispose() }
}
