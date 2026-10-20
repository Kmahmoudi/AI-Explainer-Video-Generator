$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$runtimeDir = Join-Path $PSScriptRoot '.runtime'
$uvPath = Join-Path $runtimeDir 'uv.exe'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtimeDir 'python'
$env:UV_CACHE_DIR = Join-Path $runtimeDir 'uv-cache'
$env:PYTHONUTF8 = '1'
try {
    if (-not (Test-Path -LiteralPath $uvPath)) {
        Write-Host 'Downloading uv from the official Astral GitHub release...'
        $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/astral-sh/uv/releases/latest' -Headers @{ 'User-Agent'='ExplainerStudio-Setup' }
        $asset = $release.assets | Where-Object { $_.name -eq 'uv-x86_64-pc-windows-msvc.zip' } | Select-Object -First 1
        if (-not $asset) { throw 'Official Windows x64 uv archive was not found.' }
        $archive = Join-Path $runtimeDir 'uv.zip'
        Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $archive
        if ($asset.digest -and $asset.digest.StartsWith('sha256:')) {
            $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower()
            if ($actual -ne $asset.digest.Substring(7)) { throw 'uv archive checksum mismatch.' }
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $runtimeDir -Force
        if (-not (Test-Path -LiteralPath $uvPath)) {
            $found = Get-ChildItem -LiteralPath $runtimeDir -Filter uv.exe -Recurse | Select-Object -First 1
            if (-not $found) { throw 'uv.exe missing from archive.' }
            Copy-Item -LiteralPath $found.FullName -Destination $uvPath
        }
    }
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        Write-Host 'Creating a private Python 3.11 environment (no administrator rights needed)...'
        & $uvPath venv --python 3.11 --managed-python (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
    }
    $requirements = Join-Path $PSScriptRoot 'requirements.txt'
    $hash = (Get-FileHash -LiteralPath $requirements).Hash
    $marker = Join-Path $runtimeDir 'requirements.sha256'
    if (-not (Test-Path -LiteralPath $marker) -or (Get-Content -LiteralPath $marker -Raw).Trim() -ne $hash) {
        Write-Host 'Installing slide, speech and video libraries...'
        & $uvPath pip install --python $pythonPath --only-binary :all: -r $requirements
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network connection and retry.' }
        Set-Content -LiteralPath $marker -Value $hash
    }
    Write-Host 'Preparing local models. First setup downloads several GB; subsequent launches reuse them.'
    & $pythonPath (Join-Path $PSScriptRoot 'studio.py') --setup
    if ($LASTEXITCODE -ne 0) { throw 'Model setup failed. Your completed downloads are retained; run this launcher again to retry.' }
    & $pythonPath (Join-Path $PSScriptRoot 'studio.py')
    if ($LASTEXITCODE -ne 0) { throw 'Studio exited with an error. See the message above.' }
} catch {
    Write-Host "Setup stopped: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'No system Python or existing Ollama installation was modified.'
    exit 1
}
