"""
GitHub App installation helpers
- Check whether the WhaleRay GitHub App is installed for the user
- Redirect to the GitHub App installation target picker
"""
import base64
import json
import os

import boto3
import requests

dynamodb = boto3.resource('dynamodb')
kms = boto3.client('kms')

users_table = dynamodb.Table(os.environ['USERS_TABLE'])

APP_SLUG = os.environ.get('GITHUB_APP_SLUG', '').strip()
APP_ID = os.environ.get('GITHUB_APP_ID')


def check_installation(event, context):
    """
    GET /auth/github/installations
    Requires Lambda authorizer (JWT).

    Returns:
    - installed: bool
    - installationId, accountLogin, targetType (when installed)
    - installUrl: GitHub App installation target picker URL
    """
    user_id = event['requestContext']['authorizer']['userId']
    install_url = _build_install_url()

    try:
        user_response = users_table.get_item(Key={'userId': user_id})
        user = user_response.get('Item')
    except Exception as e:
        print(f"Failed to load user {user_id}: {str(e)}")
        return _response(500, {'error': 'Failed to load user profile', 'installUrl': install_url})

    if not user:
        return _response(404, {'error': 'User not found', 'installUrl': install_url})

    encrypted_token = user.get('githubToken')
    if not encrypted_token:
        return _response(
            400,
            {
                'error': 'GitHub account not connected',
                'installed': False,
                'installUrl': install_url,
                'action': 'connect_github'
            }
        )

    try:
        access_token = _decrypt_token(encrypted_token)
    except Exception as e:
        print(f"KMS decrypt failed for user {user_id}: {str(e)}")
        return _response(
            500,
            {'error': 'Failed to decrypt GitHub token', 'installed': False, 'installUrl': install_url}
        )

    try:
        gh_response = requests.get(
            'https://api.github.com/user/installations',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/vnd.github+json'
            },
            timeout=10
        )
    except requests.exceptions.Timeout:
        return _response(504, {'error': 'GitHub API timeout', 'installed': False, 'installUrl': install_url})
    except Exception as e:
        print(f"GitHub API request failed: {str(e)}")
        return _response(502, {'error': 'Failed to query GitHub installations', 'installed': False, 'installUrl': install_url})

    if gh_response.status_code == 401:
        return _response(
            401,
            {
                'error': 'GitHub token expired or revoked',
                'installed': False,
                'installUrl': install_url,
                'action': 'reconnect_github'
            }
        )

    if gh_response.status_code >= 400:
        print(f"GitHub API error: {gh_response.status_code} {gh_response.text}")
        return _response(
            502,
            {'error': 'Unexpected response from GitHub', 'installed': False, 'installUrl': install_url}
        )

    installations = gh_response.json().get('installations', [])

    matched_installation = None
    for installation in installations:
        if APP_ID and str(installation.get('app_id')) == str(APP_ID):
            matched_installation = installation
            break
        if APP_SLUG and installation.get('app_slug') == APP_SLUG:
            matched_installation = installation
            break

    if not matched_installation:
        return _response(
            200,
            {
                'installed': False,
                'installUrl': install_url,
                'reason': 'not_installed'
            }
        )

    account = matched_installation.get('account', {}) or {}
    return _response(
        200,
        {
            'installed': True,
            'installationId': matched_installation.get('id'),
            'targetType': matched_installation.get('target_type'),
            'accountLogin': account.get('login'),
            'installUrl': install_url
        }
    )


def redirect_to_install(event, context):
    """
    GET /auth/github/install
    Redirects to the GitHub App installation target picker.
    """
    install_url = _build_install_url()
    return {
        'statusCode': 302,
        'headers': {
            'Location': install_url,
            'Cache-Control': 'no-store'
        },
        'body': ''
    }


def _build_install_url():
    if not APP_SLUG:
        # Fallback to a safe placeholder to avoid empty redirects
        return "https://github.com/apps/github/installations/select_target"
    return f"https://github.com/apps/{APP_SLUG}/installations/select_target"


def _decrypt_token(encrypted_token: str) -> str:
    ciphertext = base64.b64decode(encrypted_token)
    result = kms.decrypt(
        CiphertextBlob=ciphertext,
        KeyId=os.environ['KMS_KEY_ID']
    )
    return result['Plaintext'].decode()


def _response(status_code: int, body: dict):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }
