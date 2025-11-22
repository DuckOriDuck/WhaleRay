import json
import os
import boto3
import time
from typing import Dict, Optional
import requests
from io import StringIO
# from dotenv import dotenv_values # No longer needed for parsing

# Lambda Layer에서 공통 유틸리티 함수 가져오기
from github_utils import get_installation_access_token, update_deployment_status

# Boto3 클라이언트 초기화
codebuild = boto3.client('codebuild')
dynamodb = boto3.resource('dynamodb')
ssm_client = boto3.client('ssm')
secrets_manager = boto3.client('secretsmanager')

# 환경 변수
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
GITHUB_APP_PRIVATE_KEY_ARN = os.environ.get('GITHUB_APP_PRIVATE_KEY_ARN')
GITHUB_APP_ID = os.environ.get('GITHUB_APP_ID')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'whaleray')
ECR_REPOSITORY_URL = os.environ.get('ECR_REPOSITORY_URL')
SSM_KMS_KEY_ARN = os.environ.get('SSM_KMS_KEY_ARN')

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)


def handler(event, context):
    """
    DynamoDB Stream 이벤트(deployments 테이블 INSERT)를 받아
    .env 내용을 Blob으로 SSM에 저장하고, 레포지토리를 분석한 후,
    적절한 CodeBuild 프로젝트를 선택하여 배포를 시작하는 Lambda
    """
    print(f"Received event: {json.dumps(event, default=str)}")

    for record in event['Records']:
        if record['eventName'] != 'INSERT':
            continue

        # DynamoDB Stream에서 새 배포 정보 추출
        new_image = record['dynamodb']['NewImage']
        deployment_id = new_image['deploymentId']['S']
        user_id = new_image['userId']['S']
        service_id = new_image['serviceId']['S']
        repository_full_name = new_image['repositoryFullName']['S']
        branch = new_image['branch']['S']
        installation_id = int(new_image['installationId']['N'])
        env_file_content = new_image.get('envFileContent', {}).get('S', '')

        framework = None
        try:
            # 1. .env Blob 처리 (point.txt 3단 논리)
            env_blob_ssm_path = f"/{PROJECT_NAME}/{user_id}/{service_id}/DOTENV_BLOB"
            

            if env_file_content:
                # 1.1. 입력이 있으면 SSM에 덮어쓰기
                print(f"envFileContent provided. Storing/Updating DOTENV_BLOB for service {service_id}")
                try:
                    ssm_client.put_parameter(
                        Name=env_blob_ssm_path,
                        Value=env_file_content,
                        Type='SecureString',
                        KeyId=SSM_KMS_KEY_ARN,
                        Overwrite=True,
                        Tags=[{'Key': 'serviceId', 'Value': service_id}]
                    )
                    print(f"Stored DOTENV_BLOB to SSM: {env_blob_ssm_path}")
                except Exception as e:
                    error_message = f"Failed to store .env blob to SSM: {str(e)}"
                    print(error_message)
                    update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', errorMessage=error_message)
                    continue
            else:
                # 1.2. 입력이 없으면 기존 설정 확인
                print(f"No envFileContent. Checking for existing DOTENV_BLOB for service {service_id}.")
                try:
                    ssm_client.get_parameter(Name=env_blob_ssm_path, WithDecryption=False)
                    print(f"Existing DOTENV_BLOB found. Skipping update.")
                except ssm_client.exceptions.ParameterNotFound:
                    # 1.3. 초기 배포인데 입력이 없으면 에러
                    error_message = "Initial deployment requires .env content, but none was provided."
                    print(error_message)
                    update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', errorMessage=error_message)
                    continue
                except Exception as e:
                    error_message = f"Failed to check existing .env blob in SSM: {str(e)}"
                    print(error_message)
                    update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', errorMessage=error_message)
                    continue

            # 2. GitHub App 설치 액세스 토큰 생성
            installation_access_token = get_installation_access_token(
                installation_id=installation_id,
                github_app_id=GITHUB_APP_ID,
                private_key_secret_arn=GITHUB_APP_PRIVATE_KEY_ARN
            )
            
            # 3. 레포지토리 분석 (프레임워크 감지)
            framework = detect_framework(repository_full_name, branch, installation_access_token)
            
            if not framework:
                error_message = f"Could not detect a supported framework for repository {repository_full_name}."
                print(error_message)
                update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=None, errorMessage=error_message)
                continue

            # 4. 프레임워크에 맞는 CodeBuild 프로젝트 선택
            codebuild_project = select_codebuild_project(framework)
            if not codebuild_project:
                error_message = f"Framework '{framework}' was detected, but no corresponding CodeBuild project is defined."
                print(error_message)
                update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=framework, errorMessage=error_message)
                continue

            # 5. CodeBuild 프로젝트 실행
            env_vars = [
                {'name': 'DEPLOYMENT_ID', 'value': deployment_id, 'type': 'PLAINTEXT'},
                {'name': 'ECR_IMAGE_URI', 'value': f"{ECR_REPOSITORY_URL}:{deployment_id}", 'type': 'PLAINTEXT'},
                {'name': 'DOTENV_BLOB_SSM_PATH', 'value': env_blob_ssm_path, 'type': 'PLAINTEXT'} # DOTENV_BLOB 경로 추가
            ]
            
            codebuild.start_build(
                projectName=codebuild_project,
                sourceVersion=branch,
                sourceLocationOverride=f"https://github.com/{repository_full_name}.git",
                logsConfigOverride={'cloudWatchLogs': {'status': 'ENABLED', 'streamName': deployment_id}},
                environmentVariablesOverride=env_vars
            )
            print(f"Successfully started CodeBuild for deployment {deployment_id}")

            # 6. 배포 상태를 'BUILDING'으로 업데이트
            update_deployment_status(
                DEPLOYMENTS_TABLE,
                deployment_id, 'BUILDING',
                framework=framework,
                codebuild_project=codebuild_project
            )
            print(f"Successfully updated deployment status to BUILDING for deployment {deployment_id}")

        except Exception as e:
            print(f"Error processing deployment {deployment_id}: {str(e)}")
            import traceback
            error_message = traceback.format_exc()
            print(error_message)
            update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=framework, errorMessage=str(e))
            # Note: DynamoDB Stream Lambda retry policies should be configured.

def detect_framework(repository_full_name: str, branch: str, github_token: str) -> Optional[str]:
    """
    GitHub 레포지토리에서 프레임워크 감지 및 소스 디렉토리 탐지
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

    def get_directory_contents(path: str = "") -> list:
        """디렉토리 내용을 가져옴"""
        url = f"{base_url}{path}?ref={branch}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            return []
        except requests.exceptions.RequestException as e:
            print(f"Error getting directory contents {path}: {e}")
            return []

    def find_dockerfile_locations() -> Dict[str, str]:
        """Dockerfile의 위치를 탐색하고 반환"""
        dockerfile_map = {}
        
        if check_file_exists('Dockerfile'):
            dockerfile_map['root'] = '.'
            print("Found Dockerfile in root directory")
        
        root_contents = get_directory_contents()
        for item in root_contents:
            if item.get('type') == 'dir':
                dir_name = item.get('name', '')
                if check_file_exists(f'{dir_name}/Dockerfile'):
                    dockerfile_map[dir_name] = dir_name
                    print(f"Found Dockerfile in {dir_name}/ directory")
        
        return dockerfile_map

    # Dockerfile 위치 탐색
    dockerfile_locations = find_dockerfile_locations()
    
    # 프로젝트 루트에서 build.gradle 확인
    if check_file_exists('build.gradle'):
        if 'root' in dockerfile_locations:
            return 'spring-boot'
        else:
            print("Spring Boot project found in root but no Dockerfile - will auto-generate")
            return 'spring-boot'
    
    # 서브디렉토리 탐색
    root_contents = get_directory_contents()
    
    for item in root_contents:
        if item.get('type') == 'dir':
            dir_name = item.get('name', '')
            
            # 일반적인 소스 디렉토리명들 확인
            if dir_name.lower() in ['src', 'app', 'backend', 'frontend', 'server', 'api']:
                if check_file_exists(f'{dir_name}/build.gradle'):
                    print(f"Found Spring Boot project in {dir_name}/ directory")
                    
                    if dir_name in dockerfile_locations:
                        print(f"Dockerfile found in same directory: {dir_name}")
                    elif 'root' in dockerfile_locations:
                        print(f"Dockerfile found in root, will use for {dir_name}")
                    else:
                        print(f"No Dockerfile found for {dir_name} - will auto-generate")
                    
                    return f'spring-boot:{dir_name}'
    
    return None


def select_codebuild_project(framework: str) -> Optional[str]:
    base_framework = framework.split(':')[0]
    if base_framework == 'spring-boot':
        return f'{PROJECT_NAME}-spring-boot'
    return None
