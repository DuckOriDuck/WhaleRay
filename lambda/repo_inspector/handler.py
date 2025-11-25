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
    DynamoDB Stream 이벤트 또는 직접 호출을 받아
    .env 내용을 Blob으로 SSM에 저장하고, 레포지토리를 분석한 후,
    적절한 CodeBuild 프로젝트를 선택하여 배포를 시작하는 Lambda
    """
    print(f"Received event: {json.dumps(event, default=str)}")

    # 이벤트 형태 확인: DynamoDB Stream vs 직접 호출
    if 'Records' in event:
        # DynamoDB Stream 이벤트 처리
        records_to_process = []
        for record in event['Records']:
            if record['eventName'] == 'INSERT':
                new_image = record['dynamodb']['NewImage']
                records_to_process.append({
                    'deployment_id': new_image['deploymentId']['S'],
                    'user_id': new_image['userId']['S'], 
                    'service_id': new_image['serviceId']['S'],
                    'repository_full_name': new_image['repositoryFullName']['S'],
                    'branch': new_image['branch']['S'],
                    'installation_id': int(new_image['installationId']['N']),
                    'env_file_content': new_image.get('envFileContent', {}).get('S', '')
                })
    else:
        # 직접 호출 이벤트 처리
        records_to_process = [{
            'deployment_id': event['deploymentId'],
            'user_id': event['userId'],
            'service_id': event['serviceId'], 
            'repository_full_name': event['repositoryFullName'],
            'branch': event['branch'],
            'installation_id': int(event['installationId']),
            'env_file_content': event.get('envFileContent', '')
        }]

    for record_data in records_to_process:
        deployment_id = record_data['deployment_id']
        user_id = record_data['user_id']
        service_id = record_data['service_id']
        repository_full_name = record_data['repository_full_name']
        branch = record_data['branch']
        installation_id = record_data['installation_id']
        env_file_content = record_data['env_file_content']

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
                        Overwrite=True
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
                    # 1.3. 초기 배포인데 입력이 없으면 빈 환경변수로 진행
                    print("No existing .env found and no content provided. Creating empty DOTENV_BLOB.")
                    try:
                        ssm_client.put_parameter(
                            Name=env_blob_ssm_path,
                            Value="# No environment variables provided\n",
                            Type='SecureString',
                            KeyId=SSM_KMS_KEY_ARN,
                            Overwrite=True
                        )
                        print(f"Created empty DOTENV_BLOB at SSM: {env_blob_ssm_path}")
                    except Exception as e:
                        error_message = f"Failed to create empty .env blob in SSM: {str(e)}"
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

            # 3. 레포지토리 분석 - 새로운 향상된 분석 로직
            print("Starting enhanced repository analysis...")
            
            # 3.1. Spring Boot + Gradle 프로젝트 우선 분석
            spring_analysis = analyze_spring_gradle_project(repository_full_name, branch, installation_access_token)
            
            if spring_analysis:
                # Spring Boot 프로젝트 발견
                framework = f"spring-boot:{spring_analysis['source_directory']}" if spring_analysis['source_directory'] != '.' else 'spring-boot'
                source_dir = spring_analysis['source_directory']
                build_context = spring_analysis['build_context']
                dockerfile_path = spring_analysis.get('dockerfile_path')
                gradle_wrapper = spring_analysis.get('gradle_wrapper', False)
                
                print(f"Enhanced analysis result: framework={framework}, source_dir={source_dir}, build_context={build_context}")
                print(f"Dockerfile found: {dockerfile_path is not None}, Gradle wrapper: {gradle_wrapper}")
            else:
                # 기존 방식으로 폴백
                print("Spring Boot analysis failed, falling back to original detection...")
                framework = detect_framework(repository_full_name, branch, installation_access_token)
                
                if not framework:
                    error_message = f"Could not detect a supported framework for repository {repository_full_name}."
                    print(error_message)
                    update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=None, errorMessage=error_message)
                    continue
                
                # 기존 방식의 환경변수 설정
                source_dir = "."
                if ':' in framework:
                    source_dir = framework.split(':')[1]
                build_context = source_dir
                dockerfile_path = None
                gradle_wrapper = False

            # 4. 프레임워크에 맞는 CodeBuild 프로젝트 선택
            codebuild_project = select_codebuild_project(framework)
            if not codebuild_project:
                error_message = f"Framework '{framework}' was detected, but no corresponding CodeBuild project is defined."
                print(error_message)
                update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'INSPECTING_FAIL', framework=framework, errorMessage=error_message)
                continue

            # 5. CodeBuild 프로젝트 실행 - 향상된 환경변수 전달
            env_vars = [
                {'name': 'DEPLOYMENT_ID', 'value': deployment_id, 'type': 'PLAINTEXT'},
                {'name': 'ECR_IMAGE_URI', 'value': f"{ECR_REPOSITORY_URL}:{deployment_id}", 'type': 'PLAINTEXT'},
                {'name': 'DOTENV_BLOB_SSM_PATH', 'value': env_blob_ssm_path, 'type': 'PLAINTEXT'},
                {'name': 'SOURCE_DIR', 'value': source_dir, 'type': 'PLAINTEXT'},
                {'name': 'BUILD_CONTEXT', 'value': build_context, 'type': 'PLAINTEXT'},
                {'name': 'DOCKERFILE_PATH', 'value': dockerfile_path or '', 'type': 'PLAINTEXT'},
                {'name': 'HAS_GRADLE_WRAPPER', 'value': 'true' if gradle_wrapper else 'false', 'type': 'PLAINTEXT'}
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

    # 2. Spring Boot 확인 (build.gradle) - 서브디렉토리 지원
    gradle_locations = [
        "build.gradle",        # 루트
        "backend/build.gradle", # 백엔드 서브디렉토리
        "server/build.gradle",  # 서버 서브디렉토리
        "api/build.gradle"      # API 서브디렉토리
    ]
    
    for gradle_path in gradle_locations:
        if check_file_exists(gradle_path):
            print(f"Found {gradle_path} - analyzing Spring Boot project")
            gradle_content = get_file_content(gradle_path)
            if gradle_content and 'org.springframework.boot' in gradle_content:
                source_dir = "/".join(gradle_path.split("/")[:-1]) if "/" in gradle_path else "."
                print(f"Spring Boot framework detected in {source_dir}")
                return f"spring-boot:{source_dir}"
            elif gradle_content:
                print(f"Gradle project found in {gradle_path} but not Spring Boot")

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
    # Spring Boot 서브디렉토리 지원: spring-boot:backend → spring-boot
    base_framework = framework.split(':')[0] if ':' in framework else framework
    
    project_mapping = {
        'nodejs': f"{PROJECT_NAME}-nodejs",
        'nextjs': f"{PROJECT_NAME}-nextjs", 
        'spring-boot': f"{PROJECT_NAME}-spring-boot",
        'dotnet': f"{PROJECT_NAME}-dotnet"
    }
    
    return project_mapping.get(base_framework)


# =============================================================================
# 새로운 향상된 저장소 분석 함수들
# =============================================================================

def explore_repository_structure(repository_full_name: str, branch: str, github_token: str) -> dict:
    """
    GitHub API를 활용하여 저장소 전체 구조를 효율적으로 탐색합니다.
    
    Args:
        repository_full_name: 리포지토리 full name (예: "owner/repo")
        branch: 분석할 브랜치
        github_token: GitHub 액세스 토큰
        
    Returns:
        {
            'files': {'path/to/file': True, ...},
            'directories': {'path/to/dir': True, ...},
            'tree': {recursive git tree structure}
        }
    """
    print(f"Exploring repository structure for {repository_full_name}:{branch}")
    
    # GitHub Tree API를 사용하여 전체 구조를 한 번에 가져오기
    tree_url = f"https://api.github.com/repos/{repository_full_name}/git/trees/{branch}?recursive=1"
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    try:
        response = requests.get(tree_url, headers=headers)
        response.raise_for_status()
        
        tree_data = response.json()
        files = {}
        directories = {}
        
        # tree 데이터를 파싱하여 파일과 디렉토리 구조 생성
        for item in tree_data.get('tree', []):
            path = item['path']
            item_type = item['type']
            
            if item_type == 'blob':  # 파일
                files[path] = True
            elif item_type == 'tree':  # 디렉토리
                directories[path] = True
        
        print(f"Successfully explored repository: {len(files)} files, {len(directories)} directories")
        
        return {
            'files': files,
            'directories': directories,
            'tree': tree_data
        }
        
    except requests.RequestException as e:
        print(f"Failed to explore repository structure: {str(e)}")
        return {'files': {}, 'directories': {}, 'tree': {}}


def find_gradle_projects(repo_structure: dict) -> list:
    """
    저장소 구조에서 build.gradle 파일이 있는 모든 디렉토리를 찾습니다.
    
    Args:
        repo_structure: explore_repository_structure()의 결과
        
    Returns:
        [
            {
                'gradle_dir': 'backend',
                'gradle_file': 'backend/build.gradle',
                'has_wrapper': True,
                'is_spring_boot': False  # 추후 확인
            }
        ]
    """
    files = repo_structure.get('files', {})
    gradle_projects = []
    
    # build.gradle 파일들을 찾기
    for file_path in files.keys():
        if file_path.endswith('build.gradle'):
            # 디렉토리 경로 추출
            gradle_dir = file_path.rsplit('/', 1)[0] if '/' in file_path else '.'
            
            # Gradle Wrapper 존재 확인
            wrapper_file = f"{gradle_dir}/gradlew" if gradle_dir != '.' else "gradlew"
            has_wrapper = wrapper_file in files
            
            gradle_projects.append({
                'gradle_dir': gradle_dir,
                'gradle_file': file_path,
                'has_wrapper': has_wrapper,
                'is_spring_boot': False  # verify_spring_boot_project()에서 확인
            })
    
    print(f"Found {len(gradle_projects)} Gradle projects: {[p['gradle_dir'] for p in gradle_projects]}")
    return gradle_projects


def verify_spring_boot_project(gradle_file_path: str, repository_full_name: str, branch: str, github_token: str) -> bool:
    """
    build.gradle 파일 내용을 확인하여 Spring Boot 프로젝트인지 검증합니다.
    
    Args:
        gradle_file_path: build.gradle 파일 경로
        repository_full_name: 리포지토리 full name
        branch: 브랜치
        github_token: GitHub 토큰
        
    Returns:
        True if Spring Boot project, False otherwise
    """
    content_url = f"https://api.github.com/repos/{repository_full_name}/contents/{gradle_file_path}?ref={branch}"
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3.raw'
    }
    
    try:
        response = requests.get(content_url, headers=headers)
        if response.status_code == 200:
            content = response.text
            # Spring Boot 관련 의존성 확인
            spring_boot_indicators = [
                'org.springframework.boot',
                'spring-boot-starter',
                'org.springframework.boot:spring-boot-gradle-plugin',
                '@SpringBootApplication'
            ]
            
            is_spring_boot = any(indicator in content for indicator in spring_boot_indicators)
            if is_spring_boot:
                print(f"Confirmed Spring Boot project: {gradle_file_path}")
            
            return is_spring_boot
    except Exception as e:
        print(f"Failed to verify Spring Boot project {gradle_file_path}: {str(e)}")
    
    return False


def find_dockerfile_candidates(gradle_dir: str, repo_structure: dict) -> list:
    """
    특정 Gradle 프로젝트를 위한 Dockerfile 후보들을 우선순위별로 반환합니다.
    
    Args:
        gradle_dir: Gradle 프로젝트 디렉토리 (예: "backend", ".")
        repo_structure: 저장소 구조
        
    Returns:
        [
            {
                'dockerfile_path': 'backend/Dockerfile',
                'priority': 1,
                'build_context': 'backend'
            }
        ]
    """
    files = repo_structure.get('files', {})
    candidates = []
    
    # 우선순위별 Dockerfile 탐색 경로
    if gradle_dir == ".":
        # 루트 프로젝트의 경우
        search_paths = [
            ("Dockerfile", 1),
            ("docker/Dockerfile", 2),
            ("src/main/docker/Dockerfile", 3),
            (".docker/Dockerfile", 4),
            ("deploy/Dockerfile", 5)
        ]
    else:
        # 서브디렉토리 프로젝트의 경우
        search_paths = [
            # Priority 1: Same directory as build.gradle (40% frequency)
            (f"{gradle_dir}/Dockerfile", 1),
            
            # Priority 2: Docker subdirectory of project (25% frequency)  
            (f"{gradle_dir}/docker/Dockerfile", 2),
            
            # Priority 3: Maven-style convention (10% frequency)
            (f"{gradle_dir}/src/main/docker/Dockerfile", 3),
            
            # Priority 4: Hidden docker directory (5% frequency)
            (f"{gradle_dir}/.docker/Dockerfile", 4),
            
            # Priority 5: Repository root (fallback for multi-module, 15% frequency)
            ("Dockerfile", 5),
            
            # Priority 6: Root docker directories (fallback, 5% frequency)
            ("docker/Dockerfile", 6),
            ("deploy/Dockerfile", 7),
            (".docker/Dockerfile", 8),
            (f"deployment/{gradle_dir}/Dockerfile", 9)
        ]
    
    for dockerfile_path, priority in search_paths:
        if dockerfile_path and dockerfile_path in files:
            candidates.append({
                'dockerfile_path': dockerfile_path,
                'priority': priority,
                'build_context': determine_build_context(dockerfile_path, gradle_dir)
            })
    
    # 우선순위별 정렬
    candidates.sort(key=lambda x: x['priority'])
    
    if candidates:
        print(f"Found {len(candidates)} Dockerfile candidates for {gradle_dir}: {[c['dockerfile_path'] for c in candidates[:3]]}")
    
    return candidates


def determine_build_context(dockerfile_path: str, gradle_dir: str) -> str:
    """
    Dockerfile 위치에 따른 최적의 Docker 빌드 컨텍스트를 결정합니다.
    
    Args:
        dockerfile_path: Dockerfile 경로 (예: "backend/Dockerfile")
        gradle_dir: Gradle 프로젝트 디렉토리 (예: "backend")
        
    Returns:
        빌드 컨텍스트 디렉토리 (예: "backend", ".")
    """
    dockerfile_dir = dockerfile_path.rsplit('/', 1)[0] if '/' in dockerfile_path else '.'
    
    if dockerfile_dir == "":
        return "."  # Root level Dockerfile
    elif dockerfile_path.startswith(gradle_dir + "/") and gradle_dir != ".":
        return dockerfile_dir  # Dockerfile within gradle project
    elif dockerfile_dir == gradle_dir:
        return gradle_dir  # Same directory
    else:
        return dockerfile_dir  # Dockerfile outside gradle project


def analyze_spring_gradle_project(repository_full_name: str, branch: str, github_token: str) -> dict:
    """
    저장소를 분석하여 Spring Boot + Gradle 프로젝트 정보를 반환합니다.
    기존 detect_framework() 함수를 대체할 새로운 분석 함수입니다.
    
    Returns:
        {
            'framework': 'spring-boot-gradle',
            'source_directory': 'backend',
            'dockerfile_path': 'backend/Dockerfile', 
            'build_context': 'backend',
            'gradle_wrapper': True,
            'gradle_file': 'backend/build.gradle'
        }
        또는 None (Spring Boot 프로젝트가 아닌 경우)
    """
    print(f"Starting enhanced Spring Boot analysis for {repository_full_name}:{branch}")
    
    # 1. 저장소 구조 탐색
    repo_structure = explore_repository_structure(repository_full_name, branch, github_token)
    if not repo_structure.get('files'):
        print("Failed to explore repository structure")
        return None
    
    # 2. Gradle 프로젝트들 찾기
    gradle_projects = find_gradle_projects(repo_structure)
    if not gradle_projects:
        print("No Gradle projects found")
        return None
    
    # 3. Spring Boot 프로젝트 찾기
    spring_boot_projects = []
    for project in gradle_projects:
        if verify_spring_boot_project(
            project['gradle_file'], 
            repository_full_name, 
            branch, 
            github_token
        ):
            project['is_spring_boot'] = True
            spring_boot_projects.append(project)
    
    if not spring_boot_projects:
        print("No Spring Boot projects found")
        return None
    
    # 4. 첫 번째 Spring Boot 프로젝트 선택 (추후 멀티모듈 지원 시 개선)
    selected_project = spring_boot_projects[0]
    gradle_dir = selected_project['gradle_dir']
    
    print(f"Selected Spring Boot project: {gradle_dir}")
    
    # 5. Dockerfile 탐색
    dockerfile_candidates = find_dockerfile_candidates(gradle_dir, repo_structure)
    
    result = {
        'framework': 'spring-boot-gradle',
        'source_directory': gradle_dir,
        'gradle_wrapper': selected_project['has_wrapper'],
        'gradle_file': selected_project['gradle_file']
    }
    
    if dockerfile_candidates:
        best_dockerfile = dockerfile_candidates[0]  # 최고 우선순위
        result.update({
            'dockerfile_path': best_dockerfile['dockerfile_path'],
            'build_context': best_dockerfile['build_context'],
            'dockerfile_found': True
        })
        print(f"Found Dockerfile: {best_dockerfile['dockerfile_path']} (context: {best_dockerfile['build_context']})")
    else:
        result.update({
            'dockerfile_path': None,
            'build_context': gradle_dir,
            'dockerfile_found': False
        })
        print(f"No Dockerfile found, will auto-generate in build context: {gradle_dir}")
    
    return result