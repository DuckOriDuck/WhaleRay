import json
import os
import boto3
from typing import Optional
import traceback

# Lambda Layer에서 공통 유틸리티 함수 가져오기
from github_utils import update_deployment_status

# Boto3 클라이언트 초기화
codebuild = boto3.client('codebuild')
ssm_client = boto3.client('ssm')

# 환경 변수
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'whaleray')
ECR_REPOSITORY_URL = os.environ.get('ECR_REPOSITORY_URL')
SSM_KMS_KEY_ARN = os.environ.get('SSM_KMS_KEY_ARN')


def handler(event, context):
    """
    repo_inspector로부터 분석된 정보를 받아
    SSM에 환경변수를 저장하고 CodeBuild를 트리거하는 건축가 Lambda
    """
    # 민감 정보 마스킹: envFileContent를 로그에 노출하지 않음
    safe_event = {k: ('***REDACTED***' if k == 'envFileContent' else v) for k, v in event.items()}
    print(f"Received event: {json.dumps(safe_event, default=str)}")

    # Event Payload 추출
    deployment_id = event.get('deploymentId')
    user_id = event.get('userId')
    service_id = event.get('serviceId')
    repository_full_name = event.get('repositoryFullName')
    branch = event.get('branch')
    env_file_content = event.get('envFileContent')
    is_reset = event.get('isReset', False)
    framework = event.get('detectedFramework')

    if not deployment_id or not service_id or not framework:
        print("Missing required fields in event")
        return

    try:
        # 0. isReset과 envFileContent 동시 제공 검증
        if is_reset and env_file_content:
            raise Exception("Cannot specify both 'isReset' and 'envFileContent'. Please choose one action: reset environment variables OR update them, not both.")
        
        # 1. .env Blob 처리 (point.txt 3단 논리)
        env_blob_ssm_path = f"/{PROJECT_NAME}/{user_id}/{service_id}/DOTENV_BLOB"
        
        # SSM Parameter Store 크기 제한 (SecureString: 4KB)
        MAX_SSM_SIZE = 4096
        
        # (1) 초기화 확인: isReset이 true 인가?
        if is_reset:
            print(f"isReset is True. Overwriting DOTENV_BLOB with empty space for service {service_id}")
            try:
                ssm_client.put_parameter(
                    Name=env_blob_ssm_path,
                    Value=" ", # 빈 공백으로 덮어쓰기 (삭제 효과)
                    Type='SecureString',
                    KeyId=SSM_KMS_KEY_ARN,
                    Overwrite=True
                )
                print(f"Reset DOTENV_BLOB in SSM: {env_blob_ssm_path}")
            except Exception as e:
                raise Exception(f"Failed to reset .env blob in SSM: {str(e)}")

        # (2) 입력 확인: envFileContent가 있는가?
        elif env_file_content:
            # SSM 크기 제한 검증
            content_size = len(env_file_content.encode('utf-8'))
            if content_size > MAX_SSM_SIZE:
                raise Exception(
                    f"Environment file size ({content_size} bytes) exceeds AWS SSM Parameter Store limit ({MAX_SSM_SIZE} bytes / 4KB). "
                    f"Please reduce the number of environment variables or consider using shorter variable names/values."
                )
            
            print(f"envFileContent provided ({content_size} bytes). Storing/Updating DOTENV_BLOB for service {service_id}")
            try:
                ssm_client.put_parameter(
                    Name=env_blob_ssm_path,
                    Value=env_file_content,
                    Type='SecureString',
                    KeyId=SSM_KMS_KEY_ARN,
                    Overwrite=True
                )
                print(f"Stored DOTENV_BLOB to SSM: {env_blob_ssm_path}")
            except Exception as e:
                raise Exception(f"Failed to store .env blob to SSM: {str(e)}")
        
        # (3) 기존 설정 확인: (입력 없음, Reset 아님)
        else:
            print(f"No envFileContent and not Reset. Checking for existing DOTENV_BLOB for service {service_id}.")
            try:
                ssm_client.get_parameter(Name=env_blob_ssm_path, WithDecryption=False)
                print(f"Existing DOTENV_BLOB found. Skipping update.")
            except ssm_client.exceptions.ParameterNotFound:
                # 이번이 첫 배포인데 환경변수를 안 줬음 -> 에러 반환
                raise Exception("Initial deployment requires .env content, but none was provided.")
            except Exception as e:
                raise Exception(f"Failed to check existing .env blob in SSM: {str(e)}")

        # 4. 프레임워크에 맞는 CodeBuild 프로젝트 선택
        codebuild_project = select_codebuild_project(framework)
        if not codebuild_project:
            raise Exception(f"Framework '{framework}' was detected, but no corresponding CodeBuild project is defined.")

        # 5. CodeBuild 프로젝트 실행
        env_vars = [
            {'name': 'DEPLOYMENT_ID', 'value': deployment_id, 'type': 'PLAINTEXT'},
            {'name': 'ECR_IMAGE_URI', 'value': f"{ECR_REPOSITORY_URL}:{deployment_id}", 'type': 'PLAINTEXT'},
            {'name': 'DOTENV_BLOB_SSM_PATH', 'value': env_blob_ssm_path, 'type': 'PLAINTEXT'}
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


def select_codebuild_project(framework: str) -> Optional[str]:
    base_framework = framework.split(':')[0]
    if base_framework == 'spring-boot':
        return f'{PROJECT_NAME}-spring-boot'
    return None