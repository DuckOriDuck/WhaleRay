# Build script for Auth Lambda (Windows PowerShell)

Write-Host "Building Auth Lambda package..." -ForegroundColor Green

# 현재 디렉토리
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# build 디렉토리 생성
$buildDir = "build"
if (Test-Path $buildDir) {
    Remove-Item $buildDir -Recurse -Force
}
New-Item -ItemType Directory -Path $buildDir | Out-Null

# Python 코드 복사
Write-Host "Copying Python files..." -ForegroundColor Yellow
Copy-Item "authorize.py" $buildDir
Copy-Item "callback.py" $buildDir
Copy-Item "verify.py" $buildDir

# 의존성 설치
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt -t $buildDir --quiet

Write-Host "Build complete! Package is in $buildDir" -ForegroundColor Green
Write-Host "Terraform will zip this directory automatically." -ForegroundColor Cyan
