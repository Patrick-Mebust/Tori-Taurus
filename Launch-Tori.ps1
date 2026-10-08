$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Install Python 3.11 or newer, then launch again.' }
    & $pythonCommand.Source -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 or newer required'"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
    & $pythonCommand.Source -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
}
Write-Host 'Preparing Tori Taurus beta. The first launch may take a minute.'
& $pythonPath -m pip install -e '.[calendar]'
if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Check your Internet connection and Python installation.' }
& $pythonPath -m tori_taurus.beta
if ($LASTEXITCODE -ne 0) { throw 'Tori could not start. See the message above; another copy may already be running.' }
