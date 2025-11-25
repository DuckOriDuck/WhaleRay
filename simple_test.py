#!/usr/bin/env python3
"""
repo_inspector 새로운 기능을 실제 GitHub 리포지토리로 테스트하는 간단한 스크립트
"""
import requests
import json
import os

def explore_repository_structure(repository_full_name: str, branch: str, github_token: str) -> dict:
    """
    GitHub API를 활용하여 저장소 전체 구조를 효율적으로 탐색합니다.
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
                'is_spring_boot': False
            })
    
    print(f"Found {len(gradle_projects)} Gradle projects: {[p['gradle_dir'] for p in gradle_projects]}")
    return gradle_projects


def verify_spring_boot_project(gradle_file_path: str, repository_full_name: str, branch: str, github_token: str) -> bool:
    """
    build.gradle 파일 내용을 확인하여 Spring Boot 프로젝트인지 검증합니다.
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
                print(f"✅ Confirmed Spring Boot project: {gradle_file_path}")
            else:
                print(f"❌ Not Spring Boot: {gradle_file_path}")
            
            return is_spring_boot
    except Exception as e:
        print(f"Failed to verify Spring Boot project {gradle_file_path}: {str(e)}")
    
    return False


def find_dockerfile_candidates(gradle_dir: str, repo_structure: dict) -> list:
    """
    특정 Gradle 프로젝트를 위한 Dockerfile 후보들을 우선순위별로 반환합니다.
    """
    files = repo_structure.get('files', {})
    candidates = []
    
    # 우선순위별 Dockerfile 탐색 경로
    search_paths = [
        (f"{gradle_dir}/Dockerfile" if gradle_dir != "." else "Dockerfile", 1),
        (f"{gradle_dir}/docker/Dockerfile", 2),
        (f"{gradle_dir}/src/main/docker/Dockerfile", 3),
        (f"{gradle_dir}/.docker/Dockerfile", 4),
        ("Dockerfile" if gradle_dir != "." else None, 5),
        ("docker/Dockerfile", 6),
        ("deploy/Dockerfile", 7),
        (".docker/Dockerfile", 8),
    ]
    
    for dockerfile_path, priority in search_paths:
        if dockerfile_path and dockerfile_path in files:
            candidates.append({
                'dockerfile_path': dockerfile_path,
                'priority': priority,
                'build_context': dockerfile_path.rsplit('/', 1)[0] if '/' in dockerfile_path else '.'
            })
    
    candidates.sort(key=lambda x: x['priority'])
    
    if candidates:
        print(f"Found {len(candidates)} Dockerfile candidates for {gradle_dir}")
    
    return candidates


def test_repository(repo_name, branch='main', token=None):
    """
    실제 GitHub 리포지토리를 분석하여 새로운 함수들을 테스트합니다.
    """
    print(f"\n{'='*60}")
    print(f"Testing repository: {repo_name}:{branch}")
    print(f"{'='*60}")
    
    # 1. 저장소 구조 탐색
    repo_structure = explore_repository_structure(repo_name, branch, token)
    
    if not repo_structure.get('files'):
        print("❌ Failed to explore repository")
        return None
    
    # 2. Gradle 프로젝트 찾기
    gradle_projects = find_gradle_projects(repo_structure)
    
    if not gradle_projects:
        print("❌ No Gradle projects found")
        return None
    
    # 3. Spring Boot 검증
    spring_boot_projects = []
    for project in gradle_projects:
        if verify_spring_boot_project(project['gradle_file'], repo_name, branch, token):
            project['is_spring_boot'] = True
            spring_boot_projects.append(project)
    
    if not spring_boot_projects:
        print("❌ No Spring Boot projects found")
        return None
    
    # 4. 첫 번째 Spring Boot 프로젝트 분석
    selected_project = spring_boot_projects[0]
    gradle_dir = selected_project['gradle_dir']
    
    # 5. Dockerfile 후보 찾기
    dockerfile_candidates = find_dockerfile_candidates(gradle_dir, repo_structure)
    
    result = {
        'framework': 'spring-boot-gradle',
        'source_directory': gradle_dir,
        'gradle_wrapper': selected_project['has_wrapper'],
        'gradle_file': selected_project['gradle_file'],
        'dockerfile_candidates': len(dockerfile_candidates),
        'dockerfile_path': dockerfile_candidates[0]['dockerfile_path'] if dockerfile_candidates else None,
        'build_context': dockerfile_candidates[0]['build_context'] if dockerfile_candidates else gradle_dir
    }
    
    print("✅ Analysis successful!")
    for key, value in result.items():
        print(f"   {key}: {value}")
    
    return result


def main():
    """메인 테스트 함수"""
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        # Public 리포지토리만 테스트 (토큰 없이)
        print("⚠️  No GITHUB_TOKEN found, testing public repositories only (rate limited)")
        token = ""
    
    # 테스트할 리포지토리들
    test_repositories = [
        "spring-guides/gs-spring-boot",
        "spring-guides/gs-rest-service"
    ]
    
    print("🚀 Testing enhanced repo_inspector functions...")
    
    results = {}
    for repo in test_repositories:
        try:
            result = test_repository(repo, 'main', token)
            results[repo] = result
        except Exception as e:
            print(f"\n❌ Error testing {repo}: {str(e)}")
            results[repo] = None
    
    # 결과 요약
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    successful = sum(1 for result in results.values() if result)
    total = len(results)
    
    for repo, result in results.items():
        status = "✅ SUCCESS" if result else "❌ FAILED"
        print(f"{status}: {repo}")
        if result:
            print(f"   Source: {result['source_directory']}, Dockerfile: {result['dockerfile_path']}")
    
    print(f"\nSuccess Rate: {successful}/{total} ({successful/total*100:.1f}%)")


if __name__ == "__main__":
    main()