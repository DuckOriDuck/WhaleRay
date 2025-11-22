#!/usr/bin/env python3
"""
repo_inspector 로직을 모킹 데이터로 테스트하는 스크립트
"""

def find_gradle_projects(repo_structure: dict) -> list:
    """저장소 구조에서 build.gradle 파일이 있는 모든 디렉토리를 찾습니다."""
    files = repo_structure.get('files', {})
    gradle_projects = []
    
    for file_path in files.keys():
        if file_path.endswith('build.gradle'):
            gradle_dir = file_path.rsplit('/', 1)[0] if '/' in file_path else '.'
            wrapper_file = f"{gradle_dir}/gradlew" if gradle_dir != '.' else "gradlew"
            has_wrapper = wrapper_file in files
            
            gradle_projects.append({
                'gradle_dir': gradle_dir,
                'gradle_file': file_path,
                'has_wrapper': has_wrapper,
                'is_spring_boot': False
            })
    
    return gradle_projects


def find_dockerfile_candidates(gradle_dir: str, repo_structure: dict) -> list:
    """특정 Gradle 프로젝트를 위한 Dockerfile 후보들을 우선순위별로 반환합니다."""
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
            (f"{gradle_dir}/Dockerfile", 1),
            (f"{gradle_dir}/docker/Dockerfile", 2),
            (f"{gradle_dir}/src/main/docker/Dockerfile", 3),
            (f"{gradle_dir}/.docker/Dockerfile", 4),
            ("Dockerfile", 5),  # 루트 폴백
            ("docker/Dockerfile", 6),
            ("deploy/Dockerfile", 7),
            (".docker/Dockerfile", 8),
        ]
    
    for dockerfile_path, priority in search_paths:
        if dockerfile_path and dockerfile_path in files:
            candidates.append({
                'dockerfile_path': dockerfile_path,
                'priority': priority,
                'build_context': determine_build_context(dockerfile_path, gradle_dir)
            })
    
    candidates.sort(key=lambda x: x['priority'])
    return candidates


def determine_build_context(dockerfile_path: str, gradle_dir: str) -> str:
    """Dockerfile 위치에 따른 최적의 Docker 빌드 컨텍스트를 결정합니다."""
    dockerfile_dir = dockerfile_path.rsplit('/', 1)[0] if '/' in dockerfile_path else '.'
    
    if dockerfile_dir == "":
        return "."
    elif dockerfile_path.startswith(gradle_dir + "/") and gradle_dir != ".":
        return dockerfile_dir
    elif dockerfile_dir == gradle_dir:
        return gradle_dir
    else:
        return dockerfile_dir


def test_case(name: str, repo_structure: dict, expected_gradle_dirs: list, expected_dockerfiles: dict):
    """테스트 케이스 실행"""
    print(f"\n{'='*50}")
    print(f"Test Case: {name}")
    print(f"{'='*50}")
    
    # 1. Gradle 프로젝트 찾기 테스트
    gradle_projects = find_gradle_projects(repo_structure)
    found_gradle_dirs = [p['gradle_dir'] for p in gradle_projects]
    
    print(f"📁 Files in repository: {len(repo_structure['files'])}")
    print(f"🔍 Expected Gradle dirs: {expected_gradle_dirs}")
    print(f"✅ Found Gradle dirs: {found_gradle_dirs}")
    
    gradle_success = set(found_gradle_dirs) == set(expected_gradle_dirs)
    print(f"📊 Gradle detection: {'✅ PASS' if gradle_success else '❌ FAIL'}")
    
    # 2. Dockerfile 후보 찾기 테스트
    dockerfile_results = {}
    for project in gradle_projects:
        gradle_dir = project['gradle_dir']
        candidates = find_dockerfile_candidates(gradle_dir, repo_structure)
        
        if candidates:
            best_candidate = candidates[0]
            dockerfile_results[gradle_dir] = {
                'path': best_candidate['dockerfile_path'],
                'context': best_candidate['build_context'],
                'priority': best_candidate['priority']
            }
            print(f"🐳 {gradle_dir} -> {best_candidate['dockerfile_path']} (context: {best_candidate['build_context']})")
        else:
            dockerfile_results[gradle_dir] = None
            print(f"🐳 {gradle_dir} -> No Dockerfile found")
    
    # 결과 검증
    dockerfile_success = True
    for gradle_dir, expected in expected_dockerfiles.items():
        found = dockerfile_results.get(gradle_dir)
        if expected is None and found is None:
            continue
        elif expected and found and found['path'] == expected:
            continue
        else:
            dockerfile_success = False
            break
    
    print(f"📊 Dockerfile detection: {'✅ PASS' if dockerfile_success else '❌ FAIL'}")
    
    overall_success = gradle_success and dockerfile_success
    print(f"🏆 Overall: {'✅ PASS' if overall_success else '❌ FAIL'}")
    
    return overall_success


def main():
    """메인 테스트 함수"""
    print("🧪 Testing repo_inspector logic with mock data...")
    
    test_results = []
    
    # Test Case 1: Backend 서브디렉토리 구조
    test_results.append(test_case(
        "Backend Subdirectory Structure",
        {
            'files': {
                'README.md': True,
                'frontend/package.json': True,
                'frontend/src/index.js': True,
                'backend/build.gradle': True,
                'backend/gradlew': True,
                'backend/gradle/wrapper/gradle-wrapper.properties': True,
                'backend/src/main/java/Application.java': True,
                'backend/Dockerfile': True,
                'backend/src/main/resources/application.yml': True
            },
            'directories': {
                'frontend': True,
                'frontend/src': True,
                'backend': True,
                'backend/gradle': True,
                'backend/gradle/wrapper': True,
                'backend/src': True,
                'backend/src/main': True,
                'backend/src/main/java': True,
                'backend/src/main/resources': True
            }
        },
        expected_gradle_dirs=['backend'],
        expected_dockerfiles={'backend': 'backend/Dockerfile'}
    ))
    
    # Test Case 2: Docker 서브디렉토리 구조
    test_results.append(test_case(
        "Docker Subdirectory Structure", 
        {
            'files': {
                'build.gradle': True,
                'gradlew': True,
                'gradle/wrapper/gradle-wrapper.properties': True,
                'src/main/java/Application.java': True,
                'docker/Dockerfile': True,
                'src/main/resources/application.yml': True
            },
            'directories': {
                'gradle': True,
                'gradle/wrapper': True,
                'src': True,
                'src/main': True,
                'src/main/java': True,
                'src/main/resources': True,
                'docker': True
            }
        },
        expected_gradle_dirs=['.'],
        expected_dockerfiles={'.': 'docker/Dockerfile'}
    ))
    
    # Test Case 3: 멀티모듈 프로젝트
    test_results.append(test_case(
        "Multi-module Project",
        {
            'files': {
                'build.gradle': True,
                'settings.gradle': True,
                'gradlew': True,
                'gradle/wrapper/gradle-wrapper.properties': True,
                'Dockerfile': True,
                'service-a/build.gradle': True,
                'service-a/src/main/java/ServiceA.java': True,
                'service-a/Dockerfile': True,
                'service-b/build.gradle': True,
                'service-b/src/main/java/ServiceB.java': True,
                'common/build.gradle': True,
                'common/src/main/java/Common.java': True
            },
            'directories': {
                'gradle': True,
                'gradle/wrapper': True,
                'service-a': True,
                'service-a/src': True,
                'service-a/src/main': True,
                'service-a/src/main/java': True,
                'service-b': True,
                'service-b/src': True,
                'service-b/src/main': True,
                'service-b/src/main/java': True,
                'common': True,
                'common/src': True,
                'common/src/main': True,
                'common/src/main/java': True
            }
        },
        expected_gradle_dirs=['.', 'service-a', 'service-b', 'common'],
        expected_dockerfiles={
            '.': 'Dockerfile',
            'service-a': 'service-a/Dockerfile', 
            'service-b': 'Dockerfile',  # 루트 Dockerfile로 폴백
            'common': 'Dockerfile'     # 루트 Dockerfile로 폴백
        }
    ))
    
    # Test Case 4: Maven 스타일 Docker 구조
    test_results.append(test_case(
        "Maven-style Docker Structure",
        {
            'files': {
                'backend/build.gradle': True,
                'backend/gradlew': True,
                'backend/gradle/wrapper/gradle-wrapper.properties': True,
                'backend/src/main/java/Application.java': True,
                'backend/src/main/docker/Dockerfile': True,
                'backend/src/main/resources/application.yml': True
            },
            'directories': {
                'backend': True,
                'backend/gradle': True,
                'backend/gradle/wrapper': True,
                'backend/src': True,
                'backend/src/main': True,
                'backend/src/main/java': True,
                'backend/src/main/docker': True,
                'backend/src/main/resources': True
            }
        },
        expected_gradle_dirs=['backend'],
        expected_dockerfiles={'backend': 'backend/src/main/docker/Dockerfile'}
    ))
    
    # 결과 요약
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(test_results)
    total = len(test_results)
    
    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total-passed}/{total}")
    print(f"📊 Success Rate: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n🎉 All tests passed! The logic is working correctly.")
    else:
        print(f"\n⚠️  {total-passed} test(s) failed. Please review the logic.")


if __name__ == "__main__":
    main()