# One-time setup for Windows (PowerShell). macOS/Linux users: run ./setup.sh instead.
#
# The only prerequisite is `uv` (https://docs.astral.sh/uv/). It downloads a
# Python interpreter and every dependency itself — no system Python needed.
#
# Run from the repository folder:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (Python package manager)..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # The installer puts uv in %USERPROFILE%\.local\bin; make it visible to this shell.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
Write-Host "uv $((uv --version) -replace '^uv ', '')"

# Icelandic characters (þ, ð, æ, ö) print correctly only when Python uses UTF-8
# for the console. Persist that for the current user.
Write-Host "Setting the user environment variable PYTHONUTF8=1 (affects every Python on this account; needed for Icelandic characters)."
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
$env:PYTHONUTF8 = "1"

Write-Host "Installing Python and project dependencies..."
uv sync

Write-Host "Checking the setup (this also repairs the .claude\skills link)..."
uv run python scripts/setup_check.py

Write-Host ""
Write-Host "Optional - only needed for browser-driven scrapers (Power BI, Tableau, skatturinn cart):"
Write-Host "  uv run playwright install chromium"
Write-Host ""
Write-Host "Now open this folder in Claude Code, Codex, Claude Desktop or ChatGPT Desktop and ask"
Write-Host "a question, e.g. 'What is the median price per m2 of apartments in Reykjavik since 2020?'"
