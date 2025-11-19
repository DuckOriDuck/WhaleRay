import json
import os
import boto3
import time
from typing import Dict, Optional
import requests

# Boto3 클라이언트 초기화
codebuild = boto3.client('codebuild')
dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')

# 환경 변수
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
GITHUB_APP_PRIVATE_KEY_ARN = os.environ.get('GITHUB_APP_PRIVATE_KEY_ARN')
GITHUB_APP_ID = os.environ.get('GITHUB_APP_ID')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'whaleray')
ECR_REPOSITORY_URL = os.environ.get('ECR_REPOSITORY_URL')


deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)


def handler(event, context):
    """
    deploy 람다로부터 직접 호출되어 GitHub 레포지토리를 분석하고
    적절한 CodeBuild 프로젝트를 선택하여 배포를 시작하는 Lambda
    """
    print(f"Received event: {json.dumps(event, default=str)}")
    
    # deploy 람다로부터 전달받은 정보
    deployment_id = event['deploymentId']
    repository_full_name = event['repositoryFullName']
    branch = event.get('branch', 'main')
    installation_id = event['installationId']
    
    try:
        # 1. GitHub App 설치 액세스 토큰 생성
        installation_access_token = get_installation_access_token(installation_id)

        # 2. 레포지토리 분석 (프레임워크 감지)
        framework = detect_framework(repository_full_name, branch, installation_access_token)
        
        if not framework:
            raise ValueError(f"Could not detect a supported framework for repository {repository_full_name}.")

        # 3. 프레임워크에 맞는 CodeBuild 프로젝트 선택
        codebuild_project = select_codebuild_project(framework)

        if not codebuild_project:
            print(f"Unsupported framework '{framework}' for repository {repository_full_name}. Setting status to NOT_SUPPORTED.")
            deployments_table.update_item(
                Key={'deploymentId': deployment_id},
                UpdateExpression='SET #status = :status, updatedAt = :updatedAt, framework = :framework',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'NOT_SUPPORTED',
                    ':updatedAt': int(time.time()),
                    ':framework': framework
                }
            )
            return {'status': 'NOT_SUPPORTED'}

        # 4. 배포 상태를 'BUILDING'으로 업데이트 (피드백 반영)
        # 실제 CodeBuild 실행 로직은 생략하고 상태만 업데이트합니다.
        print(f"Framework '{framework}' detected. Updating status to BUILDING for deployment {deployment_id}.")
        deployments_table.update_item(
            Key={'deploymentId': deployment_id},
            UpdateExpression='SET #status = :status, framework = :framework, codebuildProject = :codebuildProject, updatedAt = :updatedAt',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'BUILDING',
                ':framework': framework,
                ':codebuildProject': codebuild_project,
                ':updatedAt': int(time.time())
            }
        )
        print(f"Successfully updated status to BUILDING for deployment {deployment_id}")
        
        # TODO: 이후 단계에서 CodeBuild 실행 로직 추가
        # codebuild.start_build(...)

        return {'status': 'BUILDING'}

    except Exception as e:
        print(f"Error processing deployment {deployment_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        # 오류 발생 시 Deployment 상태를 FAILED로 업데이트
        try:
            deployments_table.update_item(
                Key={'deploymentId': deployment_id},
                UpdateExpression='SET #status = :status, errorMessage = :errorMessage, updatedAt = :updatedAt',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'FAILED',
                    ':errorMessage': str(e),
                    ':updatedAt': int(time.time())
                }
            )
        except Exception as update_e:
            print(f"Failed to update deployment {deployment_id} status to FAILED: {str(update_e)}")
        
        # 에러를 발생시켜 호출 측에서 인지할 수 있도록 함
        raise e


def detect_framework(repository_full_name: str, branch: str, github_token: str) -> Optional[str]:
    """
    GitHub 레포지토리에서 프레임워크 감지
    """
    print(f"Detecting framework for {repository_full_name} on branch {branch}...")
    headers = {'Authorization': f'Bearer {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    base_url = f"https://api.github.com/repos/{repository_full_name}/contents/"

    def check_file_exists(file_path: str) -> bool:
        url = f"{base_url}{file_path}?ref={branch}"
        try:
            response = requests.head(url, headers=headers, timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            print(f"Error checking file {file_path}: {e}")
            return False

    if check_file_exists('pom.xml') or check_file_exists('build.gradle'):
        return 'spring-boot'
    if check_file_exists('next.config.js'):
        return 'nextjs'
    if check_file_exists('package.json'):
        return 'nodejs'
    if check_file_exists('requirements.txt'):
        return 'python'
    
    return None


def select_codebuild_project(framework: str) -> Optional[str]:
    """
    프레임워크에 따라 CodeBuild 프로젝트 선택
    """
    mapping = {
        'spring-boot': f'{PROJECT_NAME}-spring-boot',
        'nodejs': f'{PROJECT_NAME}-nodejs',
        'nextjs': f'{PROJECT_NAME}-nextjs',
        'python': f'{PROJECT_NAME}-python'
    }
    return mapping.get(framework)


def get_secret(secret_id: str) -> str:
    """
    Secrets Manager에서 시크릿 가져오기
    """
    try:
        response = secrets_manager.get_secret_value(SecretId=secret_id)
        return response['SecretString']
    except Exception as e:
        print(f"Error retrieving secret {secret_id}: {e}")
        raise


def get_installation_access_token(installation_id: str) -> str:
    """
    GitHub App installation access token 생성
    """
    if not GITHUB_APP_PRIVATE_KEY_ARN or not GITHUB_APP_ID:
        raise ValueError("GitHub App private key ARN or App ID not configured in environment variables.")
    try:
        private_key = get_secret(GITHUB_APP_PRIVATE_KEY_ARN)
        import jwt
        
        now = int(time.time())
        payload = {
            'iat': now - 60,
            'exp': now + 600,
            'iss': GITHUB_APP_ID
        }
        app_jwt = jwt.encode(payload, private_key, algorithm='RS256')

        token_response = requests.post(
            f'https://api.github.com/app/installations/{installation_id}/access_tokens',
            headers={'Authorization': f'Bearer {app_jwt}', 'Accept': 'application/vnd.github+json'},
            timeout=10
        )
        token_response.raise_for_status()
        return token_response.json()['token']
    except ImportError:
        raise ImportError("PyJWT library not found. Ensure it's available in the Lambda environment.")
    except Exception as e:
        print(f"Error generating installation access token for installation {installation_id}: {e}")
        raise

