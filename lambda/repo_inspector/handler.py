import json
import os
import boto3
import time
from typing import Dict, Optional

codebuild = boto3.client('codebuild')
dynamodb = boto3.resource('dynamodb')

DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
USERS_TABLE = os.environ['USERS_TABLE']

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)
users_table = dynamodb.Table(USERS_TABLE)


def handler(event, context):
    """
    GitHub 레포지토리를 분석하고 적절한 CodeBuild 프로젝트를 선택하는 Lambda
    """
    try:
        # Cognito authorizer에서 userId 추출
        user_id = event['requestContext']['authorizer']['jwt']['claims']['sub']

        # 요청 본문 파싱
        body = json.loads(event['body'])

        repo_url = body.get('repoUrl')
        branch = body.get('branch', 'main')
        env_vars = body.get('envVars', {})

        if not repo_url:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'repoUrl is required'})
            }

        # Users 테이블에서 GitHub 토큰 정보 조회
        user_response = users_table.get_item(Key={'userId': user_id})

        if 'Item' not in user_response:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'User not found. Please link your GitHub account first.'})
            }

        user = user_response['Item']
        github_token_ref = user.get('githubTokenRef')

        if not github_token_ref:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'GitHub token not configured'})
            }

        # TODO: Secrets Manager에서 GitHub 토큰 가져오기
        # github_token = get_secret(github_token_ref)

        # 레포 분석
        framework = detect_framework(repo_url, branch, github_token=None)  # TODO: token 전달

        # CodeBuild 프로젝트 선택
        codebuild_project = select_codebuild_project(framework)

        if not codebuild_project:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Unsupported framework',
                    'detected': framework
                })
            }

        # Deployment ID 생성
        deployment_id = str(uuid4())
        timestamp = int(time.time())

        # Deployment 정보 저장
        deployments_table.put_item(Item={
            'deploymentId': deployment_id,
            'userId': user_id,
            'repoUrl': repo_url,
            'branch': branch,
            'framework': framework,
            'status': 'CREATED',
            'codebuildProject': codebuild_project,
            'createdAt': timestamp,
            'updatedAt': timestamp
        })

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
            ] + [
                {
                    'name': k,
                    'value': str(v),
                    'type': 'PLAINTEXT'
                } for k, v in env_vars.items()
            ]
        )

        build_id = build_response['build']['id']
        build_arn = build_response['build']['arn']

        # Deployment 정보 업데이트
        deployments_table.update_item(
            Key={'deploymentId': deployment_id},
            UpdateExpression='SET #status = :status, codebuildBuildId = :buildId, codebuildLogGroup = :logGroup, updatedAt = :updatedAt',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'BUILDING',
                ':buildId': build_id,
                ':logGroup': f'/aws/codebuild/{codebuild_project}',
                ':updatedAt': int(time.time())
            }
        )

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'deploymentId': deployment_id,
                'framework': framework,
                'codebuildProject': codebuild_project,
                'buildId': build_id,
                'status': 'BUILDING'
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }


def detect_framework(repo_url: str, branch: str, github_token: Optional[str] = None) -> str:
    """
    GitHub 레포지토리에서 프레임워크 감지

    TODO: GitHub API를 사용하여 파일 존재 여부 확인
    - pom.xml or build.gradle -> spring-boot
    - package.json + next.config.js -> nextjs
    - package.json (without next) -> nodejs
    - requirements.txt + (app.py or wsgi.py) -> python
    """
    # 임시 구현 - 실제로는 GitHub API 호출
    # 예시:
    # if check_file_exists(repo_url, branch, 'pom.xml', github_token):
    #     return 'spring-boot'
    # elif check_file_exists(repo_url, branch, 'build.gradle', github_token):
    #     return 'spring-boot'
    # ...

    return 'nodejs'  # 기본값


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


def get_secret(secret_ref: str) -> str:
    """
    Secrets Manager에서 시크릿 가져오기

    TODO: 구현
    """
    import boto3
    secrets = boto3.client('secretsmanager')
    response = secrets.get_secret_value(SecretId=secret_ref)
    return response['SecretString']


from uuid import uuid4
