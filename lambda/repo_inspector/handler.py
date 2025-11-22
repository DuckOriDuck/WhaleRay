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
            
            build_response = codebuild.start_build(
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
                environmentVariablesOverride=env_vars
            )
            
            build_id = build_response['build']['id']
            print(f"Successfully started CodeBuild for deployment {deployment_id}, build ID: {build_id}")

            # 6. 배포 상태를 'BUILDING'으로 업데이트 (CodeBuild 로그 정보 포함)
            print(f"Updating status to BUILDING for deployment {deployment_id}.")
            
            # Spring Boot 프로젝트일 때 포트 8080 설정
            extra_attrs = {
                'framework': framework,
                'codebuild_project': codebuild_project,
                'codebuildLogGroup': f'/aws/codebuild/{codebuild_project}',
                'codebuildLogStream': f'{deployment_id}/{build_id.split(":")[-1]}',
                'buildId': build_id
            }
            
            if framework and framework.startswith('spring-boot'):
                extra_attrs['port'] = 8080
                print(f"Detected Spring Boot project - setting port to 8080")
            
            update_deployment_status(
                DEPLOYMENTS_TABLE,
                deployment_id, 'BUILDING',
                **extra_attrs
            )
            print(f"Successfully updated deployment status to BUILDING for deployment {deployment_id}")

        except Exception as e:
            error_message = f"Error processing deployment {deployment_id}: {str(e)}"
            print(error_message)
            update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=framework, errorMessage=error_message)
            continue
        
        return {'status': 'BUILDING'}



def detect_framework(repository_full_name: str, branch: str, github_token: str) -> Optional[str]:
    """
    GitHub 저장소를 분석하여 프레임워크를 감지합니다.
    우선순위: package.json (Next.js 확인) -> package.json (일반 Node.js) -> build.gradle (Spring Boot) -> .NET
    """
    
    base_url = f"https://api.github.com/repos/{repository_full_name}/contents"
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3.raw'
    }

    def check_file_exists(file_path):
        """파일이 존재하는지 확인"""
        response = requests.get(f"{base_url}/{file_path}?ref={branch}", headers=headers)
        return response.status_code == 200

    def get_file_content(file_path):
        """파일 내용을 가져옴"""
        response = requests.get(f"{base_url}/{file_path}?ref={branch}", headers=headers)
        if response.status_code == 200:
            return response.text
        return None

    print(f"Starting framework detection for {repository_full_name} on branch {branch}")

    # 1. Node.js 프로젝트 확인 (package.json)
    if check_file_exists("package.json"):
        print("Found package.json - analyzing Node.js project type")
        package_json_content = get_file_content("package.json")
        if package_json_content:
            try:
                package_data = json.loads(package_json_content)
                dependencies = package_data.get('dependencies', {})
                dev_dependencies = package_data.get('devDependencies', {})
                all_deps = {**dependencies, **dev_dependencies}
                
                # Next.js 확인
                if 'next' in all_deps:
                    print("Next.js framework detected")
                    return "nextjs"
                
                # 일반 Node.js
                print("Node.js framework detected")
                return "nodejs"
            except json.JSONDecodeError:
                print("Failed to parse package.json")

    # 2. Spring Boot 확인 (build.gradle)
    if check_file_exists("build.gradle"):
        print("Found build.gradle - analyzing Spring Boot project")
        gradle_content = get_file_content("build.gradle")
        if gradle_content and 'org.springframework.boot' in gradle_content:
            print("Spring Boot framework detected")
            return "spring-boot"
        elif gradle_content:
            print("Gradle project found but not Spring Boot")

    # 3. .NET 확인
    for csproj_pattern in ["*.csproj", "*.sln"]:
        # 간단한 체크: API 호출로 .csproj나 .sln 파일 존재 여부만 확인
        response = requests.get(f"{base_url}?ref={branch}", headers=headers)
        if response.status_code == 200:
            files = response.json()
            if any(file['name'].endswith('.csproj') or file['name'].endswith('.sln') for file in files if file['type'] == 'file'):
                print(".NET framework detected")
                return "dotnet"

    print("No supported framework detected")
    return None


def select_codebuild_project(framework: str) -> str:
    """감지된 프레임워크에 따라 적절한 CodeBuild 프로젝트를 반환"""
    project_mapping = {
        'nodejs': f"{PROJECT_NAME}-nodejs",
        'nextjs': f"{PROJECT_NAME}-nextjs", 
        'spring-boot': f"{PROJECT_NAME}-spring-boot",
        'dotnet': f"{PROJECT_NAME}-dotnet"
    }
    
    return project_mapping.get(framework)