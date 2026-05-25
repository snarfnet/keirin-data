param(
    [ValidateSet("entries", "all")]
    [string]$Mode = "entries"
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
$Branch = if ($env:KEIRIN_GIT_BRANCH) { $env:KEIRIN_GIT_BRANCH } else { "main" }
$DaysAhead = if ($env:KEIRIN_DAYS_AHEAD) { $env:KEIRIN_DAYS_AHEAD } else { "1" }
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

function Write-Log {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

function Invoke-Step {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $RootDir
    )

    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -Wait -NoNewWindow -PassThru
    if ($process.ExitCode -ne 0) {
        throw "$FilePath exited with code $($process.ExitCode)"
    }
}

function Ensure-GitReady {
    if ($env:KEIRIN_GIT_REMOTE_URL) {
        Invoke-Step "git" @("remote", "set-url", "origin", $env:KEIRIN_GIT_REMOTE_URL)
    }

    Invoke-Step "git" @("fetch", "origin", $Branch)
    Invoke-Step "git" @("checkout", $Branch)
    Invoke-Step "git" @("pull", "--ff-only", "origin", $Branch)
}

function Ensure-PythonReady {
    $venvDir = Join-Path $RootDir ".venv"
    if (-not (Test-Path $venvDir)) {
        Invoke-Step $PythonBin @("-m", "venv", ".venv")
    }

    $python = Join-Path $venvDir "Scripts\python.exe"
    Invoke-Step $python @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Step $python @("-m", "pip", "install", "-r", "requirements.txt")

    $marker = Join-Path $venvDir ".playwright-chromium-installed"
    if (-not (Test-Path $marker)) {
        Invoke-Step $python @("-m", "playwright", "install", "chromium")
        New-Item -ItemType File -Path $marker -Force | Out-Null
    }
}

function Run-Entries {
    Write-Log "Scraping entries"
    $scriptsDir = Join-Path $RootDir "scripts"
    New-Item -ItemType Directory -Path (Join-Path $scriptsDir "data") -Force | Out-Null
    $python = Join-Path $RootDir ".venv\Scripts\python.exe"
    Invoke-Step $python @("-u", "scrape_entries.py", $DaysAhead) $scriptsDir
    Invoke-Step $python @("-u", "publish_if_valid.py", "entries") $scriptsDir
}

function Run-Odds {
    Write-Log "Scraping odds"
    $scriptsDir = Join-Path $RootDir "scripts"
    $python = Join-Path $RootDir ".venv\Scripts\python.exe"
    Invoke-Step $python @("-u", "scrape_odds.py") $scriptsDir
    Invoke-Step $python @("-u", "publish_if_valid.py", "odds") $scriptsDir
}

function Run-Results {
    Write-Log "Scraping results"
    $scriptsDir = Join-Path $RootDir "scripts"
    $python = Join-Path $RootDir ".venv\Scripts\python.exe"
    $resultDate = & $python -c "from datetime import datetime,timedelta; from zoneinfo import ZoneInfo; now=datetime.now(ZoneInfo('Asia/Tokyo')); target=now if now.hour>=21 else now-timedelta(days=1); print(target.strftime('%Y%m%d'))"
    Invoke-Step $python @("-u", "scraper.py", $resultDate, $resultDate) $scriptsDir
    Invoke-Step $python @("-u", "scrape_results.py", $resultDate) $scriptsDir
    Invoke-Step $python @("-u", "publish_if_valid.py", "results") $scriptsDir
}

function Commit-AndPush {
    Invoke-Step "git" @("add", "*.json")
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Log "No JSON changes to publish"
        return
    }

    Invoke-Step "git" @("config", "user.name", $(if ($env:GIT_AUTHOR_NAME) { $env:GIT_AUTHOR_NAME } else { "keirin-data-bot" }))
    Invoke-Step "git" @("config", "user.email", $(if ($env:GIT_AUTHOR_EMAIL) { $env:GIT_AUTHOR_EMAIL } else { "keirin-data-bot@example.local" }))
    Invoke-Step "git" @("commit", "-m", "Remote update: $((Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmm'))")
    Invoke-Step "git" @("push", "origin", $Branch)
}

Push-Location $RootDir
try {
    Ensure-GitReady
    Ensure-PythonReady

    if ($Mode -eq "entries") {
        Run-Entries
    } else {
        Run-Entries
        try { Run-Odds } catch { Write-Log "Odds update failed; keeping previous odds: $_" }
        try { Run-Results } catch { Write-Log "Results update failed; keeping previous results: $_" }
    }

    Commit-AndPush
    Write-Log "Done"
}
finally {
    Pop-Location
}
