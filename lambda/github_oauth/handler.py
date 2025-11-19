import json
import os
import boto3
import requests
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')
users_table = dynamodb.Table(os.environ['USERS_TABLE'])

def handler(event, context):
    """
    GitHub OAuth callback handler

    Flow:
    1. User clicks "Connect GitHub" in frontend
    2. Redirects to GitHub OAuth authorize URL
    3. GitHub redirects back to this Lambda with code
    4. Exchange code for access token
    5. Store token in DynamoDB
    6. Redirect back to frontend
    """

    try:
        # Get query parameters
        params = event.get('queryStringParameters', {})
        code = params.get('code')
        state = params.get('state')  # Contains userId

        if not code or not state:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing code or state parameter'})
            }

        # Get GitHub OAuth credentials from Secrets Manager
        secret = secrets_manager.get_secret_value(SecretId='whaleray/github-oauth')
        github_creds = json.loads(secret['SecretString'])
        client_id = github_creds['client_id']
        client_secret = github_creds['client_secret']

        # Exchange code for access token
        token_response = requests.post(
            'https://github.com/login/oauth/access_token',
            headers={'Accept': 'application/json'},
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code
            }
        )

        token_data = token_response.json()
        access_token = token_data.get('access_token')

        if not access_token:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Failed to get access token'})
            }

        # Get GitHub user info
        user_response = requests.get(
            'https://api.github.com/user',
            headers={
                'Authorization': f'token {access_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
        )

        github_user = user_response.json()

        # Update user record in DynamoDB
        users_table.update_item(
            Key={'userId': state},  # state contains the userId
            UpdateExpression='SET githubAccessToken = :token, githubUsername = :username, githubUserId = :userId, updatedAt = :updatedAt',
            ExpressionAttributeValues={
                ':token': access_token,
                ':username': github_user['login'],
                ':userId': str(github_user['id']),
                ':updatedAt': datetime.utcnow().isoformat()
            }
        )

        # Redirect back to frontend with success
        frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

        return {
            'statusCode': 302,
            'headers': {
                'Location': f'{frontend_url}?github=connected'
            }
        }

    except Exception as e:
        print(f'Error: {str(e)}')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def get_authorize_url(event, context):
    """
    Generate GitHub OAuth authorize URL
    """
    try:
        # Get userId from request
        user_id = event['requestContext']['authorizer']['claims']['sub']

        # Get GitHub OAuth client ID from Secrets Manager
        secret = secrets_manager.get_secret_value(SecretId='whaleray/github-oauth')
        github_creds = json.loads(secret['SecretString'])
        client_id = github_creds['client_id']

        # Callback URL is this Lambda's API Gateway URL
        callback_url = f"https://{event['requestContext']['domainName']}{event['requestContext']['path'].replace('/authorize', '/callback')}"

        # Generate authorize URL
        authorize_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={callback_url}"
            f"&scope=repo,read:user,user:email"
            f"&state={user_id}"
        )

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'authorizeUrl': authorize_url
            })
        }

    except Exception as e:
        print(f'Error: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': str(e)})
        }


def disconnect_github(event, context):
    """
    Disconnect GitHub account
    """
    try:
        user_id = event['requestContext']['authorizer']['claims']['sub']

        # Remove GitHub credentials from DynamoDB
        users_table.update_item(
            Key={'userId': user_id},
            UpdateExpression='REMOVE githubAccessToken, githubUsername, githubUserId SET updatedAt = :updatedAt',
            ExpressionAttributeValues={
                ':updatedAt': datetime.utcnow().isoformat()
            }
        )

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'message': 'GitHub disconnected successfully'})
        }

    except Exception as e:
        print(f'Error: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': str(e)})
        }
