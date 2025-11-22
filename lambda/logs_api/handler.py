import json
import os
import boto3
import time

logs = boto3.client('logs')
dynamodb = boto3.resource('dynamodb')

DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)


def handler(event, context):
    """
    배포 로그를 CloudWatch Logs에서 가져오는 Lambda 함수
    """
    try:
        # JWT authorizer에서 userId 추출
        user_id = event['requestContext']['authorizer']['jwt']['claims']['sub']

        # Path parameter에서 deploymentId 추출
        deployment_id = event['pathParameters']['deploymentId']

        # Query parameter에서 옵션 추출
        query_params = event.get('queryStringParameters', {}) or {}
        log_type = query_params.get('type', 'all')  # 'build', 'runtime', 'all'
        limit = int(query_params.get('limit', 100))
        next_token = query_params.get('nextToken')
        last_event_time = query_params.get('lastEventTime')  # 증분 업데이트용

        # Deployments 테이블에서 배포 정보 조회
        response = deployments_table.get_item(Key={'deploymentId': deployment_id})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Deployment not found'})
            }

        deployment = response['Item']

        # 소유권 확인
        if deployment.get('userId') != user_id:
            return {
                'statusCode': 403,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Forbidden'})
            }

        # 배포 상태에 따라 로그 소스 결정
        status = deployment.get('status')
        log_events = []

        # 로그 타입별 제한 설정 (성능 최적화)
        build_limit = limit // 2 if log_type == 'all' else limit
        runtime_limit = limit // 2 if log_type == 'all' else limit

        # CodeBuild 로그 (빌드 중이거나 빌드 로그가 요청된 경우)
        if log_type in ['build', 'all'] and 'codebuildLogGroup' in deployment:
            try:
                print(f"Fetching CodeBuild logs from {deployment['codebuildLogGroup']}")
                build_logs = get_cloudwatch_logs(
                    log_group=deployment['codebuildLogGroup'],
                    log_stream=deployment.get('codebuildLogStream'),
                    limit=build_limit,
                    next_token=next_token,
                    start_time=int(last_event_time) if last_event_time else None
                )
                build_events = [{
                    'timestamp': event['timestamp'],
                    'message': event['message'],
                    'source': 'build'
                } for event in build_logs.get('events', [])]
                log_events.extend(build_events)
                print(f"Fetched {len(build_events)} build log events")
            except Exception as e:
                print(f"Failed to fetch build logs: {e}")

        # ECS 로그 (실행 중이거나 런타임 로그가 요청된 경우)
        if log_type in ['runtime', 'all'] and 'ecsLogGroup' in deployment:
            try:
                # ECS 로그 스트림 prefix는 deployment_id
                log_stream_prefix = deployment_id
                print(f"Fetching ECS logs from {deployment['ecsLogGroup']} with prefix {log_stream_prefix}")
                
                ecs_logs = get_cloudwatch_logs(
                    log_group=deployment['ecsLogGroup'],
                    log_stream_prefix=log_stream_prefix,
                    limit=runtime_limit,
                    next_token=next_token,
                    start_time=int(last_event_time) if last_event_time else None
                )
                runtime_events = [{
                    'timestamp': event['timestamp'],
                    'message': event['message'],
                    'source': 'runtime'
                } for event in ecs_logs.get('events', [])]
                log_events.extend(runtime_events)
                print(f"Fetched {len(runtime_events)} runtime log events")
            except Exception as e:
                print(f"Failed to fetch ECS logs: {e}")

        # 시간순 정렬
        log_events.sort(key=lambda x: x['timestamp'])

        # 응답할 로그 (최신 순으로 제한)
        response_logs = log_events[-limit:] if len(log_events) > limit else log_events
        
        # 가장 최근 로그의 timestamp (다음 요청의 lastEventTime으로 사용)
        latest_event_time = response_logs[-1]['timestamp'] if response_logs else None

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'deploymentId': deployment_id,
                'status': status,
                'logs': response_logs,
                'hasMore': len(log_events) > limit,
                'latestEventTime': latest_event_time  # 프론트엔드가 다음 요청에 사용
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


def get_cloudwatch_logs(log_group, log_stream=None, log_stream_prefix=None, limit=100, next_token=None, start_time=None):
    """
    CloudWatch Logs에서 로그 가져오기
    """
    try:
        if log_stream:
            # 특정 로그 스트림에서 가져오기
            params = {
                'logGroupName': log_group,
                'logStreamName': log_stream,
                'limit': limit,
                'startFromHead': False
            }
            if next_token:
                params['nextToken'] = next_token
            if start_time:
                params['startTime'] = start_time

            response = logs.get_log_events(**params)
            return response

        elif log_stream_prefix:
            # 로그 스트림 목록 조회 (최신 스트림만)
            streams_response = logs.describe_log_streams(
                logGroupName=log_group,
                logStreamNamePrefix=log_stream_prefix,
                orderBy='LastEventTime',
                descending=True,
                limit=3  # 최근 3개 스트림만 조회하여 성능 향상
            )

            all_events = []
            total_fetched = 0
            
            for stream in streams_response.get('logStreams', []):
                if total_fetched >= limit:
                    break  # 이미 충분한 로그를 가져왔으면 중단
                    
                stream_params = {
                    'logGroupName': log_group,
                    'logStreamName': stream['logStreamName'],
                    'limit': min(limit - total_fetched, 50),  # 스트림당 최대 50개로 제한
                    'startFromHead': False
                }
                if start_time:
                    stream_params['startTime'] = start_time
                
                try:
                    stream_response = logs.get_log_events(**stream_params)
                    events = stream_response.get('events', [])
                    all_events.extend(events)
                    total_fetched += len(events)
                except Exception as stream_error:
                    print(f"Failed to fetch from stream {stream['logStreamName']}: {stream_error}")
                    continue

            return {'events': all_events}

        else:
            # filter_log_events로 전체 조회
            params = {
                'logGroupName': log_group,
                'limit': limit
            }
            if next_token:
                params['nextToken'] = next_token
            if start_time:
                params['startTime'] = start_time

            response = logs.filter_log_events(**params)
            return response

    except logs.exceptions.ResourceNotFoundException:
        print(f"Log group {log_group} not found")
        return {'events': []}
    except Exception as e:
        print(f"Error fetching logs: {e}")
        raise
