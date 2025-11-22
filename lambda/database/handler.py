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
SERVICE_DISCOVERY_ID = os.environ['SERVICE_DISCOVERY_ID']
DOMAIN_NAME = os.environ['DOMAIN_NAME']

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
                        current_state = 'RUNNING'
                    elif running_count < desired_count:
                        current_state = 'PROVISIONING' # or STARTING
                    elif desired_count == 0:
                        current_state = 'STOPPED'
                else:
                     # Service might be deleted manually or not found
                     current_state = 'UNKNOWN'
                     
            except ClientError as e:
                print(f"Error checking ECS service state: {e}")
                # Keep existing state or set to UNKNOWN
        
        return {
            'databaseId': db['databaseId'],
            'dbInternalEndpoint': db.get('dbInternalEndpoint', f"db-{db['databaseId']}.whaleray.local"),
            'dbExternalEndpoint': db.get('dbExternalEndpoint', f"db.{DOMAIN_NAME}/{db['databaseId']}"),
            'dbState': current_state,
            'username': db['username'],
            'createdAt': int(db['createdAt'])
        }
        
    except ClientError as e:
        print(f"Error querying database information: {e}")
        raise

def create_database(user_id):
    # 1. Check Limit
    existing_db = get_database(user_id)
    if existing_db:
        return {
            'statusCode': 409,
            'body': json.dumps({'message': 'Database already exists for this user'})
        }

    database_id = str(uuid.uuid4())
    username = f"user_{database_id[:8]}"
    password = generate_password()
    print(f"Generated password for {username}")
    
    # 1.5. Select Subnet and AZ
    # We need to pick a subnet and create the volume in its AZ
    # Then force the task to run in that subnet
    selected_subnet_id = SUBNETS[0] # Simple selection for now
    try:
        subnet_info = ec2.describe_subnets(SubnetIds=[selected_subnet_id])['Subnets'][0]
        availability_zone = subnet_info['AvailabilityZone']
    except ClientError as e:
        print(f"Error describing subnet: {e}")
        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to determine availability zone'})}

    # 2. Create EBS Volume
    volume_id = None
    try:
        vol_resp = ec2.create_volume(
            AvailabilityZone=availability_zone,
            Size=1, # 1GB
            VolumeType='gp3',
            TagSpecifications=[{
                'ResourceType': 'volume',
                'Tags': [
                    {'Key': 'Name', 'Value': f"whaleray-db-{database_id}"},
                    {'Key': 'databaseId', 'Value': database_id},
                    {'Key': 'userId', 'Value': user_id}
                ]
            }]
        )
        volume_id = vol_resp['VolumeId']
        print(f"Created volume {volume_id} in {availability_zone}")
        
        # Wait for volume to be available
        waiter = ec2.get_waiter('volume_available')
        waiter.wait(VolumeIds=[volume_id])
        
    except ClientError as e:
        print(f"Error creating volume: {e}")
        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to create storage volume'})}

    # 3. Save Credentials to SSM
    ssm_param_name = f"/whaleray/db/{database_id}/password"
    try:
        ssm.put_parameter(
            Name=ssm_param_name,
            Value=password,
            Type='SecureString',
            Overwrite=True
        )
        print(f"Saved password to SSM: {ssm_param_name}")
    except ClientError as e:
        print(f"Error saving to SSM: {e}")
        # Rollback volume
        if volume_id:
             ec2.delete_volume(VolumeId=volume_id)
        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to generate credentials'})}

    # 4. Save Metadata to DynamoDB
    timestamp = int(time.time())
    item = {
        'databaseId': database_id,
        'userId': user_id,
        'dbState': 'CREATING',
        'username': username,
        'passwordParam': ssm_param_name,
        'volumeId': volume_id,
        'availabilityZone': availability_zone,
        'subnetId': selected_subnet_id,
        'createdAt': timestamp
    }
    table.put_item(Item=item)

    # 5. Register Task Definition
    try:
        # Get base TD
        base_td = ecs.describe_task_definition(taskDefinition=TASK_DEFINITION_ARN)['taskDefinition']
        
        # Update Env Vars
        container_defs = base_td['containerDefinitions']
        for container in container_defs:
            if container['name'] == 'postgres':
                # Remove existing envs if any to avoid dupes, or just append/overwrite
                # Simpler: Just filter out old ones and add new ones
                new_env = [e for e in container.get('environment', []) if e['name'] not in ['POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB']]
                new_env.extend([
                    {'name': 'POSTGRES_USER', 'value': username},
                    {'name': 'POSTGRES_PASSWORD', 'value': password},
                    {'name': 'POSTGRES_DB', 'value': 'whaleray'}
                ])
                container['environment'] = new_env
                
                # Add Mount Point
                container['mountPoints'] = [{
                    'sourceVolume': 'db-storage',
                    'containerPath': '/var/lib/postgresql/data',
                    'readOnly': False
                }]
                
            elif container['name'] == 'pgadmin':
                new_env = [e for e in container.get('environment', []) if e['name'] not in ['PGADMIN_DEFAULT_EMAIL', 'PGADMIN_DEFAULT_PASSWORD']]
                new_env.extend([
                    {'name': 'PGADMIN_DEFAULT_EMAIL', 'value': f"{username}@whaleray.local"},
                    {'name': 'PGADMIN_DEFAULT_PASSWORD', 'value': password}
                ])
                container['environment'] = new_env
        
        # Register new TD
        # Add Volume Definition for EBS
        volumes = base_td.get('volumes', [])
        # Check if volume already exists (it shouldn't in base, but good to be safe)
        if not any(v['name'] == 'db-storage' for v in volumes):
            volumes.append({
                'name': 'db-storage'
                # For Fargate EBS, we don't specify host/dockerVolumeConfiguration here usually?
                # Actually, for Fargate EBS attachment at Service level, the TD volume is just a name.
                # "You specify the volume name in the task definition and then configure the volume details when you run the task or create the service."
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
        
    except ClientError as e:
        print(f"Error registering TD: {e}")
        # Rollback
        if volume_id: ec2.delete_volume(VolumeId=volume_id)
        ssm.delete_parameter(Name=ssm_param_name)
        table.delete_item(Key={'databaseId': database_id})
        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to register task definition'})}

    # 6. Create Cloud Map Service
    try:
        sd_response = servicediscovery.create_service(
            Name=f"db-{database_id}",
            NamespaceId=os.environ['NAMESPACE_ID'],
            DnsConfig={
                'DnsRecords': [{'Type': 'A', 'TTL': 10}],
                'RoutingPolicy': 'MULTIVALUE'
            },
            HealthCheckCustomConfig={'FailureThreshold': 1}
        )
        service_registry_arn = sd_response['Service']['Arn']
        service_registry_id = sd_response['Service']['Id']
    except ClientError as e:
        print(f"Error creating Cloud Map service: {e}")
        # Rollback
        if volume_id: ec2.delete_volume(VolumeId=volume_id)
        ssm.delete_parameter(Name=ssm_param_name)
        table.delete_item(Key={'databaseId': database_id})
        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to create service discovery'})}

    # 7. Create ECS Service
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
                    'assignPublicIp': 'ENABLED'
                }
            },
            serviceRegistries=[
                {'registryArn': service_registry_arn}
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
                    'roleArn': os.environ['ECS_TASK_ROLE_ARN'], # Need to pass this env var
                    'volumeId': volume_id,
                    'volumeType': 'gp3',
                    'size': 1,
                    'encrypted': True
                    # 'filesystemType': 'ext4' # Default
                }
            }]

        )
        
        # Update DynamoDB
        table.update_item(
            Key={'databaseId': database_id},
            UpdateExpression="set serviceArn = :s, serviceRegistryId = :r, taskDefinitionArn = :t",
            ExpressionAttributeValues={
                ':s': f"db-{database_id}",
                ':r': service_registry_id,
                ':t': new_td_arn
            }
        )

    except ClientError as e:
        print(f"Error creating service: {e}")
        # Rollback
        table.delete_item(Key={'databaseId': database_id})
        ssm.delete_parameter(Name=ssm_param_name)

        if volume_id: ec2.delete_volume(VolumeId=volume_id)
        # Clean up Cloud Map?

        return {'statusCode': 500, 'body': json.dumps({'message': 'Failed to start database service'})}

    return {
        'statusCode': 201,
        'body': json.dumps({
            'message': 'Database creation started',
            'databaseId': database_id,
            'username': username,
            'password': password,
            'endpoints': {
                'internal': f"db-{database_id}.whaleray.local",
                'external': f"db.{DOMAIN_NAME}/{database_id}"
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

    # 2. Delete Cloud Map Service
    if 'serviceRegistryId' in db_item:
        try:
            servicediscovery.delete_service(Id=db_item['serviceRegistryId'])
        except ClientError as e:
            print(f"Error deleting Cloud Map service: {e}")

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

    # 6. Delete EBS Volume (if recorded)

    # Note: ECS Service deletion might detach it, but we need to delete it explicitly
    # unless we set deleteOnTermination (which we didn't/couldn't easily for dynamic volumes)
    if 'volumeId' in db_item:
        try:
            # Wait for volume to be available (detached) before deleting?
            # Service deletion takes time. We might need to wait or retry.
            # For now, just try to delete. If attached, it will fail.
            # Ideally, we should poll.
            
            print(f"Attempting to delete volume {db_item['volumeId']}")
            # Simple retry loop
            for i in range(5):
                try:
                    ec2.delete_volume(VolumeId=db_item['volumeId'])
                    print(f"Volume {db_item['volumeId']} deleted")
                    break
                except ClientError as e:
                    if 'VolumeInUse' in str(e):
                        print("Volume in use, waiting...")
                        time.sleep(5)
                    else:
                        raise e

        except ClientError as e:
            print(f"Error deleting volume: {e}")

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
