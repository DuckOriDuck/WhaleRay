import json
import os
import boto3
import time
from typing import Dict, Optional
import requests

# Lambda Layer에서 공통 유틸리티 함수 가져오기
from github_utils import get_installation_access_token, update_deployment_status

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
    
    framework = None # 오류 로깅을 위해 프레임워크 변수 미리 선언
    try:
        # 1. GitHub App 설치 액세스 토큰 생성
        installation_access_token = get_installation_access_token(
            installation_id=installation_id,
            github_app_id=GITHUB_APP_ID,
            private_key_secret_arn=GITHUB_APP_PRIVATE_KEY_ARN
        )

        # 2. 레포지토리 분석 (프레임워크 감지)
        framework = detect_framework(repository_full_name, branch, installation_access_token)
        
        if not framework:
            # 지원하지 않는 프레임워크는 INSPECTING_FAIL로 처리
            error_message = f"Could not detect a supported framework for repository {repository_full_name}. Supported frameworks are Spring Boot, Node.js, and Next.js."
            print(error_message)
            update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=None)
            # 람다를 성공적으로 종료하여 재시도를 방지
            return {'status': 'INSPECTING_FAIL'}

        # 3. 프레임워크에 맞는 CodeBuild 프로젝트 선택
        codebuild_project = select_codebuild_project(framework)

        if not codebuild_project:
            # 이 경우는 발생할 가능성이 낮지만, 방어 코드로 남겨둡니다.
            error_message = f"Framework '{framework}' was detected, but no corresponding CodeBuild project is defined."
            print(error_message)
            update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=framework)
            # 람다를 성공적으로 종료하여 재시도를 방지
            return {'status': 'INSPECTING_FAIL'}

        # 4. CodeBuild 프로젝트 실행
        print(f"Starting CodeBuild project '{codebuild_project}' for deployment {deployment_id}")
        codebuild.start_build(
            projectName=codebuild_project,
            sourceVersion=branch,  # 빌드할 브랜치 지정
            sourceLocationOverride=f"https://github.com/{repository_full_name}.git", # 동적으로 소스 저장소 위치 지정
            logsConfigOverride={
                'cloudWatchLogs': {
                    'status': 'ENABLED',
                    # 로그 스트림 이름을 deploymentId로 고정하여 빌드 로그를 격리합니다.
                    'streamName': deployment_id
                }
            },
            environmentVariablesOverride=[
                {'name': 'DEPLOYMENT_ID', 'value': deployment_id, 'type': 'PLAINTEXT'},
                {'name': 'REPOSITORY_FULL_NAME', 'value': repository_full_name, 'type': 'PLAINTEXT'},
                {'name': 'INSTALLATION_ID', 'value': str(installation_id), 'type': 'PLAINTEXT'},
                {'name': 'ECR_IMAGE_URI', 'value': f"{ECR_REPOSITORY_URL}:{deployment_id}", 'type': 'PLAINTEXT'}
            ]
        )
        print(f"Successfully started CodeBuild for deployment {deployment_id}")

        # 5. 배포 상태를 'BUILDING'으로 업데이트
        print(f"Updating status to BUILDING for deployment {deployment_id}.")
        update_deployment_status(
            DEPLOYMENTS_TABLE,
            deployment_id, 'BUILDING',
            framework=framework,
            codebuild_project=codebuild_project
        )
        print(f"Successfully updated deployment status to BUILDING for deployment {deployment_id}")
        
        return {'status': 'BUILDING'}

    except Exception as e:
        print(f"Error processing deployment {deployment_id}: {str(e)}")
        import traceback
        error_message = traceback.format_exc()
        print(error_message)
        # 오류 발생 시 Deployment 상태를 FAILED로 업데이트
        update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=framework)
        raise # 람다 재시도를 위해 에러를 다시 발생시킴


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
    
    return None


def select_codebuild_project(framework: str) -> Optional[str]:
    """
    프레임워크에 따라 CodeBuild 프로젝트 선택
    """
    mapping = {
        'spring-boot': f'{PROJECT_NAME}-spring-boot',
        'nodejs': f'{PROJECT_NAME}-nodejs',
        'nextjs': f'{PROJECT_NAME}-nextjs'
    }
    return mapping.get(framework)
