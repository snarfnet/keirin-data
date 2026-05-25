# Remote data updater

Use this when GitHub Actions cannot scrape keirin data reliably. The updater runs on a VPS or always-on PC, writes JSON files, commits them, and pushes to GitHub. GitHub Pages then serves the new JSON to the app.

## GitHub token

Create a fine-grained GitHub token with write access to the `snarfnet/keirin-data` repository contents.

Set it as an environment variable by embedding it in the remote URL. Do not commit the token.

```bash
export KEIRIN_GIT_REMOTE_URL="https://x-access-token:YOUR_TOKEN@github.com/snarfnet/keirin-data.git"
```

PowerShell:

```powershell
$env:KEIRIN_GIT_REMOTE_URL = "https://x-access-token:YOUR_TOKEN@github.com/snarfnet/keirin-data.git"
```

If the machine already has SSH deploy keys or GitHub CLI auth, you can skip `KEIRIN_GIT_REMOTE_URL`.

## Linux / VPS setup

```bash
git clone https://github.com/snarfnet/keirin-data.git
cd keirin-data
export KEIRIN_GIT_REMOTE_URL="https://x-access-token:YOUR_TOKEN@github.com/snarfnet/keirin-data.git"
bash scripts/run_remote_update.sh entries
```

Cron example, JST-friendly:

```cron
10 7 * * * cd /opt/keirin-data && mkdir -p logs && KEIRIN_GIT_REMOTE_URL='https://x-access-token:YOUR_TOKEN@github.com/snarfnet/keirin-data.git' bash scripts/run_remote_update.sh entries >> logs/entries.log 2>&1
10 21 * * * cd /opt/keirin-data && mkdir -p logs && KEIRIN_GIT_REMOTE_URL='https://x-access-token:YOUR_TOKEN@github.com/snarfnet/keirin-data.git' bash scripts/run_remote_update.sh all >> logs/all.log 2>&1
```

## Windows always-on PC setup

Run once:

```powershell
git clone https://github.com/snarfnet/keirin-data.git
cd keirin-data
$env:KEIRIN_GIT_REMOTE_URL = "https://x-access-token:YOUR_TOKEN@github.com/snarfnet/keirin-data.git"
powershell -ExecutionPolicy Bypass -File .\scripts\run_remote_update.ps1 entries
```

Task Scheduler action example:

```text
Program/script:
powershell.exe

Arguments:
-ExecutionPolicy Bypass -NoProfile -File "C:\path\to\keirin-data\scripts\run_remote_update.ps1" entries

Start in:
C:\path\to\keirin-data
```

Use `all` instead of `entries` for a night run that also tries odds and results.

## Environment variables

- `KEIRIN_GIT_REMOTE_URL`: optional authenticated remote URL.
- `KEIRIN_GIT_BRANCH`: branch to push. Default: `main`.
- `KEIRIN_DAYS_AHEAD`: days ahead for entries. Default: `1`.
- `PYTHON_BIN`: Python executable. Default: `python3` on Linux, `python` on Windows.
