import json
import os
import boto3
import uuid
import time
import secrets
import string
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
ecs = boto3.client('ecs')
ssm = boto3.client('ssm')
ec2 = boto3.client('ec2')
servicediscovery = boto3.client('servicediscovery')

DATABASE_TABLE = os.environ['DATABASE_TABLE']
CLUSTER_NAME = os.environ['CLUSTER_NAME']
TASK_DEFINITION_ARN = os.environ['TASK_DEFINITION_ARN']
SUBNETS = os.environ['SUBNETS'].split(',')
SECURITY_GROUPS = [os.environ['SECURITY_GROUPS']]
NAMESPACE_ID = os.environ['NAMESPACE_ID']
DB_SERVICE_ARN = os.environ['DB_SERVICE_ARN']
DOMAIN_NAME = os.environ['DOMAIN_NAME']
ECS_INFRA_ROLE_ARN = os.environ['ECS_INFRA_ROLE_ARN']

PROJECT_NAME = CLUSTER_NAME.replace('-cluster', '')
AWS_REGION = os.environ.get('AWS_REGION', boto3.Session().region_name)
LOG_GROUP_NAME = f"/ecs/{PROJECT_NAME}-database"

table = dynamodb.Table(DATABASE_TABLE)

def generate_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()_+"
    while True:
        password = ''.join(secrets.choice(alphabet) for i in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and sum(c.isdigit() for c in password) >= 3):
            return password

def get_user_id(event):
    # Assuming Authorizer passes userId in requestContext
    try:
        return event['requestContext']['authorizer']['lambda']['userId']
    except KeyError:
        # Fallback for testing or if structure differs
        return "test-user"

    except ClientError as e:
        print(f"Error querying database information: {e}")
        raise

def get_database(user_id):
    try:
        response = table.query(
            IndexName='userId-index',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('userId').eq(user_id)
        )
        items = response.get('Items', [])
        if not items:
            return None
        
        db = items[0]
        
        # On-demand state check
        current_state = db['dbState']
        service_arn = db.get('serviceArn')
        
        if service_arn:
            try:
                # Describe Service to get running count
                srv_resp = ecs.describe_services(
                    cluster=CLUSTER_NAME,
                    services=[service_arn]
                )
                services = srv_resp.get('services', [])
                if services:
                    service = services[0]
                    running_count = service['runningCount']
                    desired_count = service['desiredCount']
                    
                    if running_count == desired_count and running_count > 0:
                        current_state = 'AVAILABLE'
                    elif running_count < desired_count:
                        current_state = 'CREATING' # Was PROVISIONING
                    elif desired_count == 0:
                        current_state = 'STOPPED'
                else:
                     # Service might be deleted manually or not found
                     current_state = 'UNKNOWN'
                     
            except ClientError as e:
                print(f"Error checking ECS service state: {e}")
                # Keep existing state or set to UNKNOWN

        # Update DynamoDB if state changed
        if current_state != db['dbState']:
            print(f"Updating dbState from {db['dbState']} to {current_state}")
            try:
                table.update_item(
                    Key={'databaseId': db['databaseId']},
                    UpdateExpression="set dbState = :s",
                    ExpressionAttributeValues={':s': current_state}
                )
                db['dbState'] = current_state
            except ClientError as e:
                print(f"Error updating DynamoDB state: {e}")
        
        return {
            'databaseId': db['databaseId'],
            'dbInternalEndpoint': db.get('dbInternalEndpoint', f"db-{db['databaseId']}.db.whaleray.local"),
            'dbExternalEndpoint': db.get('dbExternalEndpoint', f"https://db.whaleray.oriduckduck.site/{db['databaseId']}/pgadmin/"), # pgAdmin 접속 경로 예시
            'dbState': current_state,
            'username': db['username'],
            'createdAt': int(db['createdAt'])
        }
        
    except ClientError as e:
        print(f"Error querying database information: {e}")
        raise

def create_database(user_id):
    print("Starting database creation process...")
    # 1. 사용자당 데이터베이스 수 제한 확인 (1개)
    print("Step 1: Checking for existing database for the user.")
    existing_db = get_database(user_id)
    if existing_db:
        print("Step 1 FAILED: Database already exists for this user.")
        return {
            'statusCode': 409,
            'body': json.dumps({'message': 'Database already exists for this user'})
        }
    print("Step 1 PASSED: No existing database found.")

    # 2. 데이터베이스 ID 및 자격 증명 생성
    print("Step 2: Generating new database ID and credentials.")
    database_id = str(uuid.uuid4())
    username = f"user_{database_id[:8]}"
    password = generate_password()
    print(f"Step 2 PASSED: Generated credentials for username '{username}'.")
    
    # 3. 서브넷 및 가용 영역 선택
    print("Step 3: Selecting subnet and Availability Zone.")
    selected_subnet_id = SUBNETS[0] # Simple selection for now
    try:
        subnet_info = ec2.describe_subnets(SubnetIds=[selected_subnet_id])['Subnets'][0]
        availability_zone = subnet_info['AvailabilityZone']
        print(f"Step 3 PASSED: Selected subnet {selected_subnet_id} in AZ {availability_zone}.")
    except ClientError as e:
        print(f"Error describing subnet: {e}")
        print(f"Step 3 FAILED: Could not determine Availability Zone.")
        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to determine availability zone'})}

    # 4. SSM 파라미터 스토어에 암호 저장
    print("Step 4: Saving generated password to SSM Parameter Store.")
    ssm_param_name = f"/whaleray/db/{database_id}/password"
    try:
        ssm.put_parameter(
            Name=ssm_param_name,
            Value=password,
            Type='SecureString',
            Overwrite=True
        )
        print(f"Step 4 PASSED: Saved password to SSM parameter '{ssm_param_name}'.")
    except ClientError as e:
        print(f"Error saving to SSM: {e}")
        print(f"Step 4 FAILED: Could not save password to SSM.")
        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to generate credentials'})}

    # 5. DynamoDB에 메타데이터 저장
    timestamp = int(time.time())
    print(f"Step 5: Saving initial metadata to DynamoDB for databaseId '{database_id}'.")
    item = {
        'databaseId': database_id,
        'userId': user_id,
        'dbState': 'CREATING',
        'username': username,
        'passwordParam': ssm_param_name,
        'availabilityZone': availability_zone,
        'subnetId': selected_subnet_id,
        'createdAt': timestamp
    }
    table.put_item(Item=item)
    print("Step 5 PASSED: Metadata saved to DynamoDB.")

    # 6. ECS 작업 정의 등록
    print("Step 6: Registering a new ECS Task Definition.")
    try:
        # Get base TD
        base_td = ecs.describe_task_definition(taskDefinition=TASK_DEFINITION_ARN)['taskDefinition']
        
        # Update Env Vars
        container_defs = base_td['containerDefinitions']
        for container in container_defs:
            if container['name'] == 'postgres':
                # Remove existing envs if any to avoid dupes, or just append/overwrite
                # Simpler: Just filter out old ones and add new ones
                # [FIX] Set PGDATA to a directory that the entrypoint can create.
                new_env = [e for e in container.get('environment', []) if e['name'] not in ['POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'PGDATA']]
                new_env.extend([
                    {'name': 'POSTGRES_USER', 'value': username},
                    {'name': 'POSTGRES_PASSWORD', 'value': password},
                    {'name': 'POSTGRES_DB', 'value': 'whaleray'},
                    {'name': 'PGDATA', 'value': '/var/lib/postgresql/data'}
                ])
                container['environment'] = new_env
                
                # Add Mount Point
                # [FIX] Mount one level up, so the entrypoint can create the data directory.
                container['mountPoints'] = [{
                    'sourceVolume': 'db-storage',
                    'containerPath': '/var/lib/postgresql',
                    'readOnly': False
                }]

                # [FIX] Update health check to use the correct username
                container['healthCheck'] = {
                    'command': ["CMD-SHELL", f"pg_isready -U {username} -d whaleray"],
                    'interval': 30,
                    'timeout': 5,
                    'retries': 3,
                    'startPeriod': 60
                }

                # [FIX] Forcefully add logConfiguration
                container['logConfiguration'] = {
                    'logDriver': 'awslogs',
                    'options': {
                        'awslogs-group': LOG_GROUP_NAME,
                        'awslogs-region': AWS_REGION,
                        'awslogs-stream-prefix': 'postgres',
                        'awslogs-create-group': 'true'
                    }
                }

                
            elif container['name'] == 'pgadmin':
                # [FIX] pgadmin v8+ no longer supports PGADMIN_DEFAULT_PASSWORD.
                # Use PGADMIN_SETUP_EMAIL and PGADMIN_SETUP_PASSWORD instead.
                # The password will be logged to container logs on first run.
                # [FIX] Use a valid email domain to pass validation.
                new_env = [e for e in container.get('environment', []) if e['name'] not in ['PGADMIN_DEFAULT_EMAIL', 'PGADMIN_DEFAULT_PASSWORD', 'PGADMIN_SETUP_EMAIL', 'PGADMIN_SETUP_PASSWORD', 'PGADMIN_CONFIG_ALLOW_SPECIAL_EMAIL_DOMAINS']]
                new_env.extend([
                    {'name': 'PGADMIN_DEFAULT_EMAIL', 'value': f"{username}@whaleray.com"},
                    {'name': 'PGADMIN_DEFAULT_PASSWORD', 'value': password},
                ])
                container['environment'] = new_env

                # [FIX] Forcefully add logConfiguration
                container['logConfiguration'] = {
                    'logDriver': 'awslogs',
                    'options': {
                        'awslogs-group': LOG_GROUP_NAME,
                        'awslogs-region': AWS_REGION,
                        'awslogs-stream-prefix': 'pgadmin',
                        'awslogs-create-group': 'true'
                    }
                }
        
        # Register new TD
        # Add Volume Definition for EBS
        volumes = base_td.get('volumes', [])
        # Check if volume already exists (it shouldn't in base, but good to be safe)
        if not any(v['name'] == 'db-storage' for v in volumes):
            volumes.append({
                'name': 'db-storage',
                'configuredAtLaunch': True  # Required for Fargate EBS volumes
            })

        new_td_resp = ecs.register_task_definition(
            family=f"whaleray-db-{database_id}",
            taskRoleArn=base_td['taskRoleArn'],
            executionRoleArn=base_td['executionRoleArn'],
            networkMode=base_td['networkMode'],
            containerDefinitions=container_defs,
            volumes=volumes,
            requiresCompatibilities=base_td.get('requiresCompatibilities', []),
            cpu=base_td['cpu'],
            memory=base_td['memory']
        )
        new_td_arn = new_td_resp['taskDefinition']['taskDefinitionArn']
        print(f"Step 6 PASSED: Registered new task definition '{new_td_arn}'.")
        
    except ClientError as e:
        print(f"Error registering TD: {e}")
        print("Step 6 FAILED: Could not register task definition. Rolling back...")
        # Rollback
        ssm.delete_parameter(Name=ssm_param_name)
        table.delete_item(Key={'databaseId': database_id})
        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to register task definition'})}

    # 7. ECS 서비스 생성
    print("Step 7: Creating ECS service to launch the database task.")
    try:
        ecs.create_service(
            cluster=CLUSTER_NAME,
            serviceName=f"db-{database_id}",
            taskDefinition=new_td_arn,
            launchType='FARGATE',
            desiredCount=1,
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': [selected_subnet_id], # Force specific subnet
                    'securityGroups': SECURITY_GROUPS,
                    'assignPublicIp': 'DISABLED'
                }
            },
            serviceRegistries=[
                {
                    'registryArn': DB_SERVICE_ARN,  # Use shared 'db' service
                    'containerName': 'postgres'  # Required for awsvpc network mode
                }
            ],
            tags=[
                {'key': 'databaseId', 'value': database_id},
                {'key': 'userId', 'value': user_id}
            ],
            propagateTags='SERVICE',
            enableECSManagedTags=True,
            volumeConfigurations=[{
                'name': 'db-storage',
                'managedEBSVolume': {
                    'roleArn': ECS_INFRA_ROLE_ARN,
                    'volumeType': 'gp3',
                    'sizeInGiB': 1,
                    'encrypted': True,
                    'filesystemType': 'ext4'
                }
            }]

        )
        print(f"Step 7 PASSED: ECS service 'db-{database_id}' creation initiated.")

        # 8. DynamoDB에 서비스 정보 업데이트
        table.update_item(
            Key={'databaseId': database_id},
            UpdateExpression="set serviceArn = :s, taskDefinitionArn = :t",
            ExpressionAttributeValues={
                ':s': f"db-{database_id}",
                ':t': new_td_arn
            }
        )
        print("Step 8 PASSED: Updated DynamoDB item with service and task definition ARN.")

    except ClientError as e:
        print(f"Error creating service: {e}")
        print("Step 7 FAILED: Could not create ECS service. Rolling back...")
        # Rollback
        table.delete_item(Key={'databaseId': database_id})
        ssm.delete_parameter(Name=ssm_param_name)
        # Clean up Cloud Map?

        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to start database service'})}
    
    print("Database creation process completed successfully.")
    return {
        'statusCode': 201,
        'body': json.dumps({
            'message': 'Database creation started',
            'databaseId': database_id,
            'username': username,
            'password': password,
            'endpoints': {
                'internal': f"db-{database_id}.db.whaleray.local",
                'external': f"https://db.whaleray.oriduckduck.site/{database_id}/pgadmin/"
            }
        })
    }

def delete_database(user_id):
    db = get_database(user_id)
    if not db:
        return {'statusCode': 404, 'body': json.dumps({'message': 'Database not found'})}
    
    database_id = db['databaseId']
    
    # Fetch full item for IDs
    db_item = table.get_item(Key={'databaseId': database_id}).get('Item', {})
    
    # 1. Delete ECS Service
    service_name = db_item.get('serviceArn', f"db-{database_id}")
    try:
        ecs.delete_service(
            cluster=CLUSTER_NAME,
            service=service_name,
            force=True
        )
    except ClientError as e:
        print(f"Error deleting service: {e}")

    # 2. Cloud Map Service - No need to delete (shared 'db' service)
    # When ECS service is deleted, the instance is automatically deregistered from Cloud Map

    # 3. Deregister Task Definition
    if 'taskDefinitionArn' in db_item:
        try:
            ecs.deregister_task_definition(taskDefinition=db_item['taskDefinitionArn'])
        except ClientError as e:
            print(f"Error deregistering TD: {e}")

    # 4. Delete SSM Parameter
    try:
        ssm.delete_parameter(Name=f"/whaleray/db/{database_id}/password")
    except ClientError:
        pass

    # 5. Delete DynamoDB Item
    table.delete_item(Key={'databaseId': database_id})

    # Note: EBS volumes are automatically deleted by Fargate when the service is deleted
    

    return {'statusCode': 200, 'body': json.dumps({'message': 'Database deleted'})}

def reset_password(user_id):
    # Placeholder for reset password logic
    # Requires connecting to DB which is complex from Lambda without VPC access/libraries
    # For MVP, we might just update SSM and restart the task with new env vars?
    # But requirements say "ALTER USER".
    # Assuming this Lambda is in VPC and has 'pg' lib (psycopg2-binary layer needed).
    
    return {
        'statusCode': 501, 
        'body': json.dumps({'message': 'Not implemented yet - requires psycopg2 layer'})
    }

def handler(event, context):
    print(json.dumps(event))
    
    try:
        user_id = get_user_id(event)
        method = event['requestContext']['http']['method']
        path = event['requestContext']['http']['path']
        
        if method == 'GET' and path == '/db':
            db = get_database(user_id)
            if db:
                return {'statusCode': 200, 'body': json.dumps(db)}
            else:
                return {'statusCode': 404, 'body': json.dumps({'message': 'No database found'})}
        
        elif method == 'POST' and path == '/db/createdb':
            return create_database(user_id)
            
        elif method == 'DELETE' and path == '/db':
            return delete_database(user_id)
            
        elif method == 'POST' and path == '/db/reset-password':
            return reset_password(user_id)
            
        else:
            return {'statusCode': 400, 'body': json.dumps({'message': 'Invalid request'})}
            
    except Exception as e:
        print(e)
        return {'statusCode': 500, 'body': json.dumps({'message': 'Internal server error'})}
