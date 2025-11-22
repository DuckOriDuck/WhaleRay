import json
import os
import boto3
import time
from typing import Dict, Optional
import requests

# Lambda Layer에서 공통 유틸리티 함수 가져오기
from github_utils import get_installation_access_token, update_deployment_status

# Boto3 클라이언트 초기화
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')

# 환경 변수
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
GITHUB_APP_PRIVATE_KEY_ARN = os.environ.get('GITHUB_APP_PRIVATE_KEY_ARN')
GITHUB_APP_ID = os.environ.get('GITHUB_APP_ID')
ENV_BUILDER_FUNCTION_NAME = os.environ.get('ENV_BUILDER_FUNCTION_NAME')

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)


def handler(event, context):
    """
    DynamoDB Stream 이벤트(deployments 테이블 INSERT)를 받아
    GitHub 분석 후 env_builder Lambda를 비동기 호출(Invoke)하는 탐정 Lambda
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
        
        # envFileContent와 isReset은 env_builder로 그대로 전달
        env_file_content = new_image.get('envFileContent', {}).get('S', '')
        is_reset = new_image.get('isReset', {}).get('BOOL', False)

        framework = None
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
                error_message = f"Could not detect a supported framework for repository {repository_full_name}."
                print(error_message)
                update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=None, errorMessage=error_message)
                continue

            # 3. env_builder 호출 (비동기)
            payload = {
                'deploymentId': deployment_id,
                'userId': user_id,
                'serviceId': service_id,
                'repositoryFullName': repository_full_name,
                'branch': branch,
                'envFileContent': env_file_content,
                'isReset': is_reset,
                'detectedFramework': framework
            }
            
            print(f"Invoking env_builder for deployment {deployment_id} with payload: {json.dumps(payload)}")
            
            lambda_client.invoke(
                FunctionName=ENV_BUILDER_FUNCTION_NAME,
                InvocationType='Event', # 비동기 호출
                Payload=json.dumps(payload)
            )
            
            print(f"Successfully invoked env_builder for deployment {deployment_id}")
            
        except Exception as e:
            print(f"Error processing deployment {deployment_id}: {str(e)}")
            import traceback
            error_message = traceback.format_exc()
            print(error_message)
            update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=framework, errorMessage=str(e))


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