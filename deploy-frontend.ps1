# WhaleRay Frontend 배포 스크립트 (Windows PowerShell)
# terraform apply 완료 후 실행하세요

Write-Host "=== WhaleRay Frontend 배포 ===" -ForegroundColor Cyan

# Terraform 출력에서 값 가져오기
Write-Host "`n[단계 1/5] Terraform 출력 가져오기..." -ForegroundColor Yellow
Push-Location terraform

$userPoolId = terraform output -raw cognito_user_pool_id
$userPoolClientId = terraform output -raw cognito_client_id
$cognitoDomain = terraform output -raw cognito_domain
$apiEndpoint = terraform output -raw api_endpoint
$ecrUrl = terraform output -raw ecr_repository_url
$albDns = terraform output -raw alb_dns

Pop-Location

$accountId = aws sts get-caller-identity --query Account --output text
$frontendBucket = "whaleray-frontend-$accountId"

Write-Host "✓ Terraform 출력 가져오기 완료" -ForegroundColor Green

# config.js 생성
Write-Host "`n[단계 2/5] config.js 생성 중..." -ForegroundColor Yellow

$configContent = @"
export const config = {
  region: 'ap-northeast-2',
  cognito: {
    userPoolId: '$userPoolId',
    userPoolClientId: '$userPoolClientId',
    domain: '$cognitoDomain'
  },
  apiEndpoint: '$apiEndpoint',
  ecrRepositoryUrl: '$ecrUrl',
  albDns: '$albDns'
}
"@

Set-Content -Path "frontend\src\config.js" -Value $configContent -Encoding UTF8
Write-Host "✓ config.js 생성 완료" -ForegroundColor Green

# 의존성 설치
Write-Host "`n[단계 3/5] npm 의존성 설치 중..." -ForegroundColor Yellow
Push-Location frontend
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ npm install 실패" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "✓ npm install 완료" -ForegroundColor Green

# 빌드
Write-Host "`n[단계 4/5] 프론트엔드 빌드 중..." -ForegroundColor Yellow
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ 빌드 실패" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "✓ 빌드 완료" -ForegroundColor Green

# S3 업로드
Write-Host "`n[단계 5/5] S3에 업로드 중..." -ForegroundColor Yellow
aws s3 sync dist/ "s3://$frontendBucket/" --delete
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ S3 업로드 실패" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "✓ S3 업로드 완료" -ForegroundColor Green

Pop-Location

# CloudFront URL 가져오기
Write-Host "`n[추가] CloudFront 캐시 무효화 시도..." -ForegroundColor Yellow
$distributions = aws cloudfront list-distributions --output json | ConvertFrom-Json
$distribution = $distributions.DistributionList.Items | Where-Object {
    $_.Origins.Items.Id -match "S3-$frontendBucket"
} | Select-Object -First 1

if ($distribution) {
    $cloudfrontId = $distribution.Id
    $cloudfrontDomain = $distribution.DomainName

    aws cloudfront create-invalidation --distribution-id $cloudfrontId --paths "/*" | Out-Null
    Write-Host "✓ CloudFront 캐시 무효화 완료" -ForegroundColor Green

    Write-Host "`n=== 배포 완료! ===" -ForegroundColor Green
    Write-Host "Frontend URL: https://$cloudfrontDomain" -ForegroundColor Cyan
} else {
    Write-Host "⚠ CloudFront 배포를 찾을 수 없습니다" -ForegroundColor Yellow
    Write-Host "`n=== 배포 완료! ===" -ForegroundColor Green
    Write-Host "S3 Bucket: $frontendBucket" -ForegroundColor Cyan
}
