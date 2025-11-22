#!/usr/bin/env python3
"""
repo_inspector 새로운 기능을 실제 GitHub 리포지토리로 테스트하는 스크립트
"""
import json
import sys
import os

# Lambda 코드 경로 추가
sys.path.append('/Users/gimdonghyeon/Desktop/softbank/lambda/repo_inspector')
sys.path.append('/Users/gimdonghyeon/Desktop/softbank/lambda/layers/github_utils/python')

from handler import (
    explore_repository_structure,
    find_gradle_projects, 
    verify_spring_boot_project,
    find_dockerfile_candidates,
    analyze_spring_gradle_project
)

def test_repository_analysis(repo_name, branch='main', token=None):
    """
    실제 GitHub 리포지토리를 분석하여 새로운 함수들을 테스트합니다.
    """
    if not token:
        print("GitHub 토큰이 필요합니다. GITHUB_TOKEN 환경변수를 설정해주세요.")
        return
    
    print(f"\n{'='*60}")
    print(f"Testing repository: {repo_name}:{branch}")
    print(f"{'='*60}")
    
    # 1. 저장소 구조 탐색 테스트
    print("\n1. Repository Structure Exploration")
    print("-" * 40)
    repo_structure = explore_repository_structure(repo_name, branch, token)
    
    if repo_structure.get('files'):
        print(f"✅ Found {len(repo_structure['files'])} files, {len(repo_structure['directories'])} directories")
        
        # 흥미로운 파일들 출력
        interesting_files = []
        for file_path in list(repo_structure['files'].keys())[:20]:  # 처음 20개만
            if any(pattern in file_path for pattern in ['gradle', 'Dockerfile', 'package.json', '.env']):
                interesting_files.append(file_path)
        
        if interesting_files:
            print("🔍 Interesting files found:")
            for file in interesting_files:
                print(f"   - {file}")
    else:
        print("❌ Failed to explore repository structure")
        return
    
    # 2. Gradle 프로젝트 탐색 테스트
    print("\n2. Gradle Project Detection")
    print("-" * 40)
    gradle_projects = find_gradle_projects(repo_structure)
    
    if gradle_projects:
        print(f"✅ Found {len(gradle_projects)} Gradle project(s):")
        for i, project in enumerate(gradle_projects):
            print(f"   {i+1}. Directory: {project['gradle_dir']}")
            print(f"      Gradle file: {project['gradle_file']}")
            print(f"      Has wrapper: {project['has_wrapper']}")
    else:
        print("❌ No Gradle projects found")
        return
    
    # 3. Spring Boot 검증 테스트
    print("\n3. Spring Boot Verification")
    print("-" * 40)
    spring_boot_projects = []
    
    for project in gradle_projects:
        is_spring_boot = verify_spring_boot_project(
            project['gradle_file'], 
            repo_name, 
            branch, 
            token
        )
        if is_spring_boot:
            project['is_spring_boot'] = True
            spring_boot_projects.append(project)
            print(f"✅ Spring Boot project confirmed: {project['gradle_dir']}")
        else:
            print(f"❌ Not a Spring Boot project: {project['gradle_dir']}")
    
    if not spring_boot_projects:
        print("❌ No Spring Boot projects found")
        return
    
    # 4. Dockerfile 후보 탐색 테스트
    print("\n4. Dockerfile Discovery")
    print("-" * 40)
    
    for project in spring_boot_projects:
        gradle_dir = project['gradle_dir']
        candidates = find_dockerfile_candidates(gradle_dir, repo_structure)
        
        print(f"📁 Gradle project: {gradle_dir}")
        if candidates:
            print(f"   ✅ Found {len(candidates)} Dockerfile candidate(s):")
            for candidate in candidates:
                print(f"      Priority {candidate['priority']}: {candidate['dockerfile_path']}")
                print(f"         Build context: {candidate['build_context']}")
        else:
            print(f"   ❌ No Dockerfile candidates found")
    
    # 5. 통합 분석 테스트
    print("\n5. Complete Analysis Test")
    print("-" * 40)
    
    analysis_result = analyze_spring_gradle_project(repo_name, branch, token)
    
    if analysis_result:
        print("✅ Complete analysis successful!")
        print("📊 Analysis Result:")
        for key, value in analysis_result.items():
            print(f"   {key}: {value}")
    else:
        print("❌ Complete analysis failed")
    
    return analysis_result


def main():
    """
    메인 테스트 함수
    """
    # GitHub 토큰 확인
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        print("Please set GITHUB_TOKEN environment variable")
        print("Example: export GITHUB_TOKEN='your_github_token'")
        return
    
    # 테스트할 리포지토리들 (다양한 패턴)
    test_repositories = [
        # 일반적인 Spring Boot 프로젝트들
        "spring-projects/spring-boot",
        "spring-guides/gs-spring-boot", 
        "spring-guides/gs-rest-service",
        
        # 서브디렉토리 구조를 가진 프로젝트들
        # "microsoft/vscode",  # 복잡한 구조 (Node.js 포함)
        # "apache/kafka",      # Gradle 멀티모듈
    ]
    
    print("🚀 Starting repo_inspector enhancement tests...")
    
    results = {}
    for repo in test_repositories:
        try:
            result = test_repository_analysis(repo, 'main', token)
            results[repo] = result
        except Exception as e:
            print(f"\n❌ Error testing {repo}: {str(e)}")
            results[repo] = None
    
    # 결과 요약
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    successful = 0
    for repo, result in results.items():
        if result:
            successful += 1
            print(f"✅ {repo} - SUCCESS")
            print(f"   Framework: {result.get('framework')}")
            print(f"   Source Dir: {result.get('source_directory')}")
            print(f"   Dockerfile: {result.get('dockerfile_path', 'Not found')}")
        else:
            print(f"❌ {repo} - FAILED")
    
    print(f"\nSuccess Rate: {successful}/{len(test_repositories)} ({successful/len(test_repositories)*100:.1f}%)")


if __name__ == "__main__":
    main()