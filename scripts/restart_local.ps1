$ErrorActionPreference = 'Stop'
$qpgRoot = Split-Path -Parent $PSScriptRoot
$qpgPython = Join-Path $qpgRoot '.venv\Scripts\python.exe'
$qpgInstance = Join-Path $qpgRoot 'instance'
$qpgStatePath = Join-Path $qpgInstance 'running_processes.json'
Set-Location -LiteralPath $qpgRoot
@'
from school_platform import create_app, db
from school_platform.models import GenerationJob
app = create_app()
with app.app_context():
    if db.session.query(GenerationJob).filter_by(status='running').count():
        print('A generation job is active. Restart after it finishes.')
        raise SystemExit(2)
'@ | & $qpgPython
if ($LASTEXITCODE -ne 0) { throw 'Restart deferred: check the database and active jobs.' }
if (Test-Path -LiteralPath $qpgStatePath) {
    $qpgState = Get-Content -LiteralPath $qpgStatePath | ConvertFrom-Json
    foreach ($qpgProcessId in @($qpgState.web_pid, $qpgState.worker_pid)) {
        $qpgProcess = Get-Process -Id $qpgProcessId -ErrorAction SilentlyContinue
        if ($qpgProcess -and $qpgProcess.Path -eq $qpgPython) { Stop-Process -Id $qpgProcessId }
    }
}
$qpgWeb = Start-Process -FilePath $qpgPython -ArgumentList @('serve.py','--host','127.0.0.1','--port','8080') -WorkingDirectory $qpgRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $qpgInstance 'web.stdout.log') -RedirectStandardError (Join-Path $qpgInstance 'web.stderr.log') -PassThru
$qpgWorker = Start-Process -FilePath $qpgPython -ArgumentList @('-m','flask','--app','school_platform:create_app','worker') -WorkingDirectory $qpgRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $qpgInstance 'worker.stdout.log') -RedirectStandardError (Join-Path $qpgInstance 'worker.stderr.log') -PassThru
@{web_pid=$qpgWeb.Id;worker_pid=$qpgWorker.Id;url='http://127.0.0.1:8080'} | ConvertTo-Json | Set-Content -LiteralPath $qpgStatePath
Write-Output 'Web server and worker started at http://127.0.0.1:8080'
