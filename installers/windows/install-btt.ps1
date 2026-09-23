param(
    [switch]$SkipUi
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step([string]$Message) {
    Write-Host "[BTT Installer] $Message" -ForegroundColor Cyan
}

function Resolve-Python {
    $candidates = @(
        "py -3.14",
        "py -3.13",
        "py -3.12",
        "py -3.11",
        "python"
    )

    foreach ($candidate in $candidates) {
        try {
            if ($candidate -eq "python") {
                $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            }
            else {
                $parts = $candidate.Split(" ")
                $version = & $parts[0] $parts[1] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            }

            $majorMinor = $version.Trim()
            if ($majorMinor -match "^3\.(11|12|13|14)$") {
                return $candidate
            }
        }
        catch {
            continue
        }
    }

    throw "No supported Python interpreter found (requires Python 3.11-3.14)."
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Write-Step "Repository root: $RepoRoot"
$pythonLauncher = Resolve-Python
Write-Step "Using Python launcher: $pythonLauncher"

$venvDir = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $venvDir)) {
    Write-Step "Creating virtual environment..."
    if ($pythonLauncher -eq "python") {
        & python -m venv .venv
    }
    else {
        $parts = $pythonLauncher.Split(" ")
        & $parts[0] $parts[1] -m venv .venv
    }
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment Python not found at $venvPython"
}

Write-Step "Installing dependencies..."
& $venvPython -m pip install --upgrade pip wheel setuptools
& $venvPython -m pip install -r requirements-dev.txt
& $venvPython -m pip install -e .

if (-not $SkipUi) {
    Write-Step "Installing FreqUI..."
    & $venvPython -m freqtrade install-ui
}

Write-Step "Generating helper launcher..."
$launcherPath = Join-Path $RepoRoot "run-backtest.ps1"
@"
`$ErrorActionPreference = "Stop"
Set-Location "$RepoRoot"
& "$venvPython" -m freqtrade backtesting --help
Write-Host ""
Write-Host "Example:"
Write-Host "& `"$venvPython`" -m freqtrade backtesting --config tests/testdata/config.tests.json --strategy SampleStrategy --strategy-path tests/strategy/strats --datadir tests/testdata --timerange 20180110-20180130 -i 5m --cache none"
"@ | Out-File -FilePath $launcherPath -Encoding utf8

Write-Step "Done."
Write-Host ""
Write-Host "Next:"
Write-Host "1) Activate: .\.venv\Scripts\Activate.ps1"
Write-Host "2) Backtesting help: python -m freqtrade backtesting --help"
Write-Host "3) Or run helper: .\run-backtest.ps1"
