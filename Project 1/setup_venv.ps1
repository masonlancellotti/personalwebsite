# setup_venv.ps1 - Reliable venv setup script for Project 1
# Uses Python 3.12 for compatibility with pandas-ta/numba

Write-Host "Setting up virtual environment with Python 3.12..." -ForegroundColor Green

# Try to find Python 3.12
$python312 = $null

# First check if py launcher is available and has Python 3.12
if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
        $version = & py -V:3.12 -c "import sys; print(sys.version)" 2>&1
        if ($version -match "3\.12") {
            $python312 = "py -V:3.12"
            Write-Host "Found Python 3.12 via py launcher: py -V:3.12" -ForegroundColor Green
        }
    } catch {
        # py launcher might not have -V:3.12, try -3.12
        try {
            $version = & py -3.12 --version 2>&1
            if ($version -match "3\.12") {
                $python312 = "py -3.12"
                Write-Host "Found Python 3.12 via py launcher: py -3.12" -ForegroundColor Green
            }
        } catch {
            # Continue to other methods
        }
    }
}

# If py launcher didn't work, try direct python commands
if (-not $python312) {
    $pythonVersions = @("python3.12", "python")
    foreach ($pyCmd in $pythonVersions) {
        try {
            $version = & $pyCmd --version 2>&1
            if ($version -match "3\.12") {
                $python312 = $pyCmd
                Write-Host "Found Python 3.12: $pyCmd" -ForegroundColor Green
                break
            }
        } catch {
            continue
        }
    }
}

if (-not $python312) {
    Write-Host "ERROR: Python 3.12 not found!" -ForegroundColor Red
    Write-Host "Please install Python 3.12 or ensure it's available via 'py -V:3.12' launcher." -ForegroundColor Yellow
    Write-Host "Available Python versions:" -ForegroundColor Yellow
    python --version
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py --list
    }
    exit 1
}

# Check Python version
if ($python312 -match "^py ") {
    $pythonVersion = & py -V:3.12 -c "import sys; print(sys.version)" 2>&1
} else {
    $pythonVersion = & $python312 --version 2>&1
}
Write-Host "Using: $pythonVersion" -ForegroundColor Cyan

# Remove old venv if exists
if (Test-Path "venv") {
    Write-Host "Removing old venv..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force venv
}

# Create new venv with Python 3.12
Write-Host "Creating virtual environment with Python 3.12..." -ForegroundColor Green
if ($python312 -match "^py -V:3.12") {
    & py -V:3.12 -m venv venv
} elseif ($python312 -match "^py -3.12") {
    & py -3.12 -m venv venv
} else {
    & $python312 -m venv venv
}

# Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Green
& .\venv\Scripts\Activate.ps1

# Verify Python version in venv
$venvPythonVersion = python --version 2>&1
Write-Host "Virtual environment Python: $venvPythonVersion" -ForegroundColor Cyan

# Upgrade pip first (critical!)
Write-Host "Upgrading pip..." -ForegroundColor Green
python -m pip install --upgrade pip setuptools wheel

# Install core dependencies first (these are critical and must work)
Write-Host "`nInstalling core dependencies..." -ForegroundColor Green
python -m pip install "numpy>=1.24.0,<2.0.0"
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: numpy installation failed!" -ForegroundColor Red; exit 1 }

python -m pip install "pandas>=2.0.0,<2.4.0"
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: pandas installation failed!" -ForegroundColor Red; exit 1 }

python -m pip install "pyyaml>=6.0,<7.0"
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: pyyaml installation failed!" -ForegroundColor Red; exit 1 }

python -m pip install "python-dotenv>=1.0.0,<2.0.0"
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: python-dotenv installation failed!" -ForegroundColor Red; exit 1 }

python -m pip install "alpaca-py>=0.30.0,<0.44.0"
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: alpaca-py installation failed!" -ForegroundColor Red; exit 1 }

# Install pandas-ta (should work with Python 3.12)
Write-Host "`nInstalling pandas-ta..." -ForegroundColor Green
python -m pip install "pandas-ta>=0.3.14b,<0.5.0"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pandas-ta installation failed!" -ForegroundColor Red
    Write-Host "This may indicate a compatibility issue. Check error messages above." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "pandas-ta installed successfully" -ForegroundColor Green
}

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host "Activate with: .\venv\Scripts\Activate.ps1" -ForegroundColor Cyan
