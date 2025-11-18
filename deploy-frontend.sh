#!/bin/bash
# WhaleRay Frontend 배포 스크립트 (Linux/Mac)
# terraform apply 완료 후 실행하세요

set -e

echo "=== WhaleRay Frontend 배포 ==="

# Terraform 출력에서 값 가져오기
cd terraform
REGION="ap-northeast-2"
API_ENDPOINT=$(terraform output -raw api_endpoint)
ECR_URL=$(terraform output -raw ecr_repository_url)
ALB_DNS=$(terraform output -raw alb_dns)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FRONTEND_BUCKET="whaleray-frontend-${ACCOUNT_ID}"
cd ..

# config.js 생성
echo -e "\n[1/4] config.js 생성 중..."
cat > frontend/src/config.js <<EOF
export const config = {
  region: '${REGION}',
  apiEndpoint: '${API_ENDPOINT}',
  ecrRepositoryUrl: '${ECR_URL}',
  albDns: '${ALB_DNS}'
}
EOF
echo "✓ config.js 생성 완료"

# 의존성 설치
echo -e "\n[2/4] npm 의존성 설치 중..."
cd frontend
npm install
echo "✓ npm install 완료"

# 빌드
echo -e "\n[3/4] 프론트엔드 빌드 중..."
npm run build
echo "✓ 빌드 완료"

# S3 업로드
echo -e "\n[4/4] S3에 업로드 중..."
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
