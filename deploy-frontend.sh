#!/bin/bash
# WhaleRay Frontend 배포 스크립트 (Linux/Mac)
# terraform apply 완료 후 실행하세요

set -e

echo "=== WhaleRay Frontend 배포 ==="

# Terraform 출력에서 값 가져오기
cd terraform
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FRONTEND_BUCKET="whaleray-frontend-${ACCOUNT_ID}"
cd ..

# 의존성 설치
echo -e "\n[1/3] npm 의존성 설치 중..."
cd frontend
npm install
echo "✓ npm install 완료"

# 빌드
echo -e "\n[2/3] 프론트엔드 빌드 중..."
npm run build
echo "✓ 빌드 완료"

# S3 업로드
echo -e "\n[3/3] S3에 업로드 중..."
aws s3 sync dist/ "s3://${FRONTEND_BUCKET}/" --delete
echo "✓ S3 업로드 완료"

# CloudFront 캐시 무효화
CLOUDFRONT_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Origins.Items[?Id=='S3-${FRONTEND_BUCKET}']].Id" --output text)
if [ -n "$CLOUDFRONT_ID" ]; then
    echo -e "\n[추가] CloudFront 캐시 무효화 중..."
    aws cloudfront create-invalidation --distribution-id "$CLOUDFRONT_ID" --paths "/*"
    echo "✓ CloudFront 캐시 무효화 완료"
fi

CLOUDFRONT_DOMAIN=$(aws cloudfront list-distributions --query "DistributionList.Items[?Origins.Items[?Id=='S3-${FRONTEND_BUCKET}']].DomainName" --output text)

echo -e "\n=== 배포 완료! ==="
echo "Frontend URL: https://${CLOUDFRONT_DOMAIN}"

cd ..
