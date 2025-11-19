import json
import os
import boto3
import time
from typing import Dict, Optional
import requests
from uuid import uuid4

codebuild = boto3.client('codebuild')
dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager') # Renamed to avoid conflict with `secrets` module

DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
USERS_TABLE = os.environ['USERS_TABLE']
GITHUB_APP_PRIVATE_KEY_ARN = os.environ.get('GITHUB_APP_PRIVATE_KEY_ARN')
GITHUB_APP_ID = os.environ.get('GITHUB_APP_ID')

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)
users_table = dynamodb.Table(USERS_TABLE)


def get_plain_item(dynamodb_image: Dict) -> Dict:
    """
    Converts a DynamoDB NewImage dictionary to a plain Python dictionary.
    Handles basic types: S, N, BOOL, L (list), M (map).
    """
    plain_item = {}
    for k, v in dynamodb_image.items():
        if 'S' in v:
            plain_item[k] = v['S']
        elif 'N' in v:
            plain_item[k] = int(v['N']) # Convert to int if numerical
        elif 'BOOL' in v:
            plain_item[k] = v['BOOL']
        elif 'L' in v:
            plain_item[k] = [get_plain_item({'_': item})['_'] for item in v['L']] # Recursive for lists
        elif 'M' in v:
            plain_item[k] = get_plain_item(v['M']) # Recursive for maps
        else:
            plain_item[k] = None # Handle other types or skip
    return plain_item


def handler(event, context):
    """
    DynamoDB Stream 이벤트에 반응하여 GitHub 레포지토리를 분석하고
    적절한 CodeBuild 프로젝트를 선택하여 배포를 시작하는 Lambda
    """
    print(f"Received event: {json.dumps(event, default=str)}")

    for record in event['Records']:
        if record['eventName'] != 'INSERT':
            print(f"Skipping non-INSERT event: {record['eventName']}")
            continue

        deployment_id = 'N/A' # Default for logging in case of early failure
        try:
            new_image = record['dynamodb']['NewImage']
            deployment = get_plain_item(new_image)

            deployment_id = deployment['deploymentId']
            user_id = deployment['userId']
            repository_full_name = deployment['repositoryFullName']
            branch = deployment.get('branch', 'main')

            print(f"Processing deployment {deployment_id} for user {user_id} with repo {repository_full_name}")

            # 'PENDING' 상태의 배포만 처리 (CREATED는 이제 deploy 람다에서 사용)
            if deployment.get('status') != 'PENDING':
                print(f"Deployment {deployment_id} status is {deployment.get('status')}, skipping.")
                continue

            # Deployment 상태를 PROCESSING으로 업데이트
            deployments_table.update_item(
                Key={'deploymentId': deployment_id},
                UpdateExpression='SET #status = :status, updatedAt = :updatedAt',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'PROCESSING',
                    ':updatedAt': int(time.time())
                }
            )

            # Users 테이블에서 GitHub 토큰 정보 조회 (installation token 발급에 필요)
            # user_response = users_table.get_item(Key={'userId': user_id})
            #
            # if 'Item' not in user_response:
            #     raise ValueError(f"User {user_id} not found. Cannot retrieve GitHub token.")
            #
            # user = user_response['Item']
            # installation_id = user.get('installationId')

            # installations_table에서 installationId 조회
            installation_response = installations_table.query(
                IndexName='userId-index',
                KeyConditionExpression='userId = :userId',
                ExpressionAttributeValues={
                    ':userId': user_id
                },
                Limit=1
            )

            installations = installation_response.get('Items', [])

            if not installations:
                raise ValueError(f"No GitHub App installation found for user {user_id}. Please install the app.")

            installation_id = installations[0]['installationId']

            if not installation_id:
                raise ValueError(f"GitHub App installation ID not found for user {user_id}. Please install the app.")

            # GitHub App installation access token 생성
            installation_access_token = get_installation_access_token(installation_id)

            # 레포 분석을 위한 repo_url 생성 (CodeBuild에서 사용)
            repo_url = f"https://github.com/{repository_full_name}.git"

            # 레포 분석 (프레임워크 감지)
            framework = detect_framework(repository_full_name, branch, installation_access_token)

            # CodeBuild 프로젝트 선택
            codebuild_project = select_codebuild_project(framework)

            if not codebuild_project:
                raise ValueError(f"Unsupported framework '{framework}' for repository {repository_full_name}. Deployment ID: {deployment_id}")

            # CodeBuild 빌드 시작
            build_response = codebuild.start_build(
                projectName=codebuild_project,
                sourceVersion=branch,
                sourceLocationOverride=repo_url,
                environmentVariablesOverride=[
                    {
                        'name': 'DEPLOYMENT_ID',
                        'value': deployment_id,
                        'type': 'PLAINTEXT'
                    },
                    {
                        'name': 'ECR_IMAGE_URI',
                        'value': f"{os.environ['ECR_REPOSITORY_URL']}:{deployment_id}",
                        'type': 'PLAINTEXT'
                    }
                ]
            )

            build_id = build_response['build']['id']
            # build_arn = build_response['build']['arn'] # Not directly used in subsequent updates

            # Deployment 정보 업데이트 (상태를 BUILDING으로 변경)
            deployments_table.update_item(
                Key={'deploymentId': deployment_id},
                UpdateExpression='SET #status = :status, framework = :framework, codebuildProject = :codebuildProject, codebuildBuildId = :buildId, codebuildLogGroup = :logGroup, updatedAt = :updatedAt',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'BUILDING',
                    ':framework': framework,
                    ':codebuildProject': codebuild_project,
                    ':buildId': build_id,
                    ':logGroup': f'/aws/codebuild/{codebuild_project}',
                    ':updatedAt': int(time.time())
                }
            )
            print(f"Successfully started CodeBuild for deployment {deployment_id}")

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


def detect_framework(repository_full_name: str, branch: str, github_token: Optional[str] = None) -> str:
    """
    GitHub 레포지토리에서 프레임워크 감지
    GitHub Content API를 사용하여 파일 존재 여부 확인
    """
    print(f"Detecting framework for {repository_full_name} on branch {branch}...")

    headers = {
        'Authorization': f'Bearer {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
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
    
    if check_file_exists('package.json'):
        # Check if it's a Next.js project
        if check_file_exists('next.config.js'):
            return 'nextjs'
        # Otherwise, assume it's a generic Node.js project
        return 'nodejs'
    
    if check_file_exists('requirements.txt'):
        # Further checks could be added for app.py or wsgi.py if needed
        return 'python'
    
    # Default to nodejs if no specific framework is detected
    print(f"No specific framework detected for {repository_full_name}. Defaulting to 'nodejs'.")
    return 'nodejs'


def select_codebuild_project(framework: str) -> Optional[str]:
    """
    프레임워크에 따라 CodeBuild 프로젝트 선택
    """
    project_name = os.environ.get('PROJECT_NAME', 'whaleray')

    mapping = {
        'spring-boot': f'{project_name}-spring-boot',
        'nodejs': f'{project_name}-nodejs',
        'nextjs': f'{project_name}-nextjs',
        'python': f'{project_name}-python'
    }

    return mapping.get(framework)


def get_secret(secret_id: str) -> str:
    """
    Secrets Manager에서 시크릿 가져오기
    """
    try:
        response = secrets_manager.get_secret_value(SecretId=secret_id)
        if 'SecretString' in response:
            return response['SecretString']
        else:
            # Handle binary secrets if needed
            raise ValueError(f"Secret {secret_id} does not contain SecretString")
    except Exception as e:
        print(f"Error retrieving secret {secret_id}: {e}")
        raise


def get_installation_access_token(installation_id: str) -> str:
    """
    GitHub App installation access token 생성

    1. GitHub App private key로 JWT 생성
    2. JWT를 사용하여 installation access token 요청
    """
    if not GITHUB_APP_PRIVATE_KEY_ARN or not GITHUB_APP_ID:
        raise ValueError("GitHub App private key ARN or App ID not configured in environment variables.")

    try:
        # Secrets Manager에서 GitHub App private key 가져오기
        private_key = get_secret(GITHUB_APP_PRIVATE_KEY_ARN)

        # PyJWT 라이브러리 동적 로드 (Lambda Layer로 제공될 것으로 예상)
        import jwt
        
        now = int(time.time())
        payload = {
            'iat': now - 60,  # 1분 전으로 설정 (clock skew 대응)
            'exp': now + 600, # 10분 후 만료
            'iss': GITHUB_APP_ID
        }

        app_jwt = jwt.encode(payload, private_key, algorithm='RS256')

        # Installation access token 요청
        token_response = requests.post(
            f'https://api.github.com/app/installations/{installation_id}/access_tokens',
            headers={
                'Authorization': f'Bearer {app_jwt}',
                'Accept': 'application/vnd.github+json'
            },
            timeout=10
        )

        if token_response.status_code != 201:
            raise Exception(
                f"Failed to create installation token for installation {installation_id}: "
                f"{token_response.status_code} {token_response.text}"
            )

        token_data = token_response.json()
        return token_data['token']

    except ImportError:
        raise ImportError("PyJWT library not found. Ensure it's available in the Lambda environment.")
    except Exception as e:
        print(f"Error generating installation access token for installation {installation_id}: {e}")
        raise