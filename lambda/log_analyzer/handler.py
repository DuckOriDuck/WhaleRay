import json
import boto3
import re
import time
from typing import Dict, List, Optional
from datetime import datetime

# Bedrock 클라이언트 초기화
bedrock_runtime = boto3.client('bedrock-runtime')

# CORS 헤더
cors_headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
}

def handler(event, context):
    """
    배포 로그를 Claude 3 Haiku로 분석하여 사용자 친화적 요약 제공
    """
    try:
        print(f"Received event: {json.dumps(event, default=str)}")
        
        # OPTIONS 요청 처리 (CORS)
        if event.get('httpMethod') == 'OPTIONS' or event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': ''
            }
        
        # JWT authorizer에서 userId 추출
        auth_ctx = event.get('requestContext', {}).get('authorizer', {}) or {}
        user_id = extract_user_id(auth_ctx)
        
        if not user_id:
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Unauthorized: No user ID found'})
            }
        
        # 요청 파라미터 추출
        deployment_id = event.get('pathParameters', {}).get('deploymentId')
        if not deployment_id:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Missing deploymentId parameter'})
            }
        
        # 요청 본문에서 로그 데이터 추출
        try:
            body = json.loads(event.get('body', '{}'))
            logs = body.get('logs', [])
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Invalid JSON in request body'})
            }
        
        if not logs:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No logs provided for analysis'})
            }
        
        print(f"Analyzing {len(logs)} log entries for deployment {deployment_id}")
        
        # 로그 분석 실행
        analysis_result = analyze_logs_with_claude(logs, deployment_id)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'deploymentId': deployment_id,
                'analysis': analysis_result,
                'analyzedAt': int(time.time()),
                'logCount': len(logs)
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }


def extract_user_id(auth_ctx: Dict) -> Optional[str]:
    """JWT authorizer에서 userId 추출"""
    # 방법 1: claims.sub (github_oauth 방식)
    if 'claims' in auth_ctx and auth_ctx['claims']:
        user_id = auth_ctx['claims'].get('sub')
        if user_id:
            return user_id
    
    # 방법 2: lambda.userId (deployments_api 방식)
    lambda_ctx = auth_ctx.get('lambda', {}) or {}
    user_id = lambda_ctx.get('userId') or lambda_ctx.get('sub')
    if user_id:
        return user_id
    
    # 방법 3: 직접 userId
    return auth_ctx.get('userId')


def preprocess_logs(logs: List[Dict]) -> str:
    """
    로그 데이터를 Claude 분석에 적합한 형태로 전처리
    """
    processed_lines = []
    
    # 로그를 시간순으로 정렬
    sorted_logs = sorted(logs, key=lambda x: x.get('timestamp', 0))
    
    # 최대 50개 로그만 분석 (토큰 제한 및 비용 절약)
    limited_logs = sorted_logs[-50:] if len(sorted_logs) > 50 else sorted_logs
    
    for log in limited_logs:
        timestamp = log.get('timestamp', 0)
        message = log.get('message', '').strip()
        source = log.get('source', 'unknown')
        
        # 시간 포맷팅
        try:
            dt = datetime.fromtimestamp(timestamp / 1000)
            time_str = dt.strftime('%H:%M:%S')
        except:
            time_str = 'unknown'
        
        # 중요하지 않은 로그 필터링
        if should_skip_log(message):
            continue
            
        processed_lines.append(f"[{time_str}][{source}] {message}")
    
    return '\n'.join(processed_lines)


def should_skip_log(message: str) -> bool:
    """분석에서 제외할 로그인지 판단"""
    skip_patterns = [
        r'^START RequestId:',
        r'^END RequestId:',
        r'^REPORT RequestId:',
        r'^\s*$',  # 빈 줄
        r'Cleanup complete',
        r'Executing: \["/bin/sh"',
        r'^\d+% \[\d+:\d+',  # 진행률 표시
    ]
    
    for pattern in skip_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            return True
    
    return False


def analyze_logs_with_claude(logs: List[Dict], deployment_id: str) -> Dict:
    """
    Amazon Nova Micro로 로그 분석 수행 (비용 효율적)
    """
    # 로그 전처리
    processed_logs = preprocess_logs(logs)
    
    if not processed_logs:
        return {
            'summary': '분석할 의미있는 로그가 없습니다.',
            'status': 'no_data',
            'issues': [],
            'recommendations': []
        }
    
    # Claude 프롬프트 구성
    prompt = f"""다음은 WhaleRay 배포 플랫폼에서 발생한 배포 로그입니다. 
이 로그를 분석하여 한국어로 사용자 친화적인 요약을 제공해주세요.

배포 ID: {deployment_id}

로그:
{processed_logs}

다음 JSON 형식으로 응답해주세요:
{{
    "summary": "배포 과정의 전반적인 요약 (2-3문장)",
    "status": "success|warning|error|in_progress",
    "issues": [
        {{
            "level": "error|warning|info",
            "title": "이슈 제목",
            "description": "상세 설명",
            "suggestion": "해결 방안"
        }}
    ],
    "recommendations": [
        "개선 제안사항 1",
        "개선 제안사항 2"
    ],
    "keyMetrics": {{
        "buildTime": "예상 빌드 시간",
        "framework": "감지된 프레임워크",
        "progress": "진행률 (%)"
    }}
}}

분석 기준:
1. 에러 메시지가 있으면 원인과 해결방안 제시
2. 경고가 있으면 잠재적 문제점 설명
3. 성공적인 단계들은 긍정적으로 요약
4. 개발자가 이해하기 쉬운 용어로 설명
5. 구체적이고 실용적인 조치사항 제안"""

    try:
        # Claude 3.5 Sonnet 모델 호출 (안정적이고 성능 좋음)
        response = bedrock_runtime.invoke_model(
            modelId='anthropic.claude-3-haiku-20240307-v1:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 1000,  # 비용 절약을 위해 제한
                'temperature': 0.1,  # 일관된 분석을 위해 낮게 설정
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ]
            })
        )
        
        # 응답 파싱 (Claude 모델 형식)
        response_body = json.loads(response['body'].read())
        claude_response = response_body['content'][0]['text']
        
        print(f"Claude response: {claude_response}")
        
        # JSON 응답 파싱
        try:
            analysis_result = json.loads(claude_response)
            return analysis_result
        except json.JSONDecodeError:
            # JSON 파싱 실패시 기본 응답
            return {
                'summary': claude_response[:200] + '...' if len(claude_response) > 200 else claude_response,
                'status': 'analysis_completed',
                'issues': [],
                'recommendations': ['Claude 응답을 JSON으로 파싱하는데 실패했습니다.'],
                'keyMetrics': {}
            }
            
    except Exception as e:
        print(f"Claude analysis failed: {str(e)}")
        return {
            'summary': f'로그 분석 중 오류가 발생했습니다: {str(e)}',
            'status': 'analysis_failed',
            'issues': [
                {
                    'level': 'error',
                    'title': 'AI 분석 실패',
                    'description': f'Bedrock Claude 호출 중 오류: {str(e)}',
                    'suggestion': '잠시 후 다시 시도해주세요.'
                }
            ],
            'recommendations': ['로그를 수동으로 확인해주세요.'],
            'keyMetrics': {}
        }