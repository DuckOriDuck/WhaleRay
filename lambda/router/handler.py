import json
import os
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
SERVICES_TABLE = os.environ.get('SERVICES_TABLE', 'whaleray-services')

services_table = dynamodb.Table(SERVICES_TABLE)


def handler(event, context):
    """
    동적 라우팅을 위한 Lambda@Edge 함수
    (선택 사항 - CloudFront와 함께 사용)
    """
    try:
        # CloudFront request 이벤트
        request = event['Records'][0]['cf']['request']

        # 호스트 헤더에서 서비스 식별
        host = request['headers'].get('host', [{}])[0].get('value', '')

        # 서브도메인에서 서비스 이름 추출 (예: myapp.whaleray.io -> myapp)
        parts = host.split('.')
        if len(parts) > 2:
            service_name = parts[0]

            # 서비스 정보 조회 (간단한 캐싱 로직 추가 가능)
            # 실제로는 CloudFront 오리진을 동적으로 변경하거나
            # ALB의 타겟 그룹으로 라우팅

            # 여기서는 간단히 요청을 그대로 통과
            return request

        return request

    except Exception as e:
        print(f"Error: {str(e)}")
        return request
