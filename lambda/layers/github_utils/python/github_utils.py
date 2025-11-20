import os
import time
import boto3
import requests

secrets_manager = boto3.client('secretsmanager')

def get_secret(secret_id: str) -> str:
    """
    Secrets Manager에서 시크릿 가져오기
    """
    try:
        response = secrets_manager.get_secret_value(SecretId=secret_id)
        return response['SecretString']
    except Exception as e:
        print(f"Error retrieving secret {secret_id}: {e}")
        raise


def get_installation_access_token(installation_id: str, github_app_id: str, private_key_secret_arn: str) -> str:
    """
    GitHub App installation access token 생성
    """
    if not private_key_secret_arn or not github_app_id:
        raise ValueError("GitHub App private key ARN or App ID not provided.")
    try:
        private_key = get_secret(private_key_secret_arn)
        import jwt
        
        now = int(time.time())
        payload = {
            'iat': now - 60,
            'exp': now + 600,
            'iss': github_app_id
        }
        app_jwt = jwt.encode(payload, private_key, algorithm='RS256')

        token_response = requests.post(
            f'https://api.github.com/app/installations/{installation_id}/access_tokens',
            headers={'Authorization': f'Bearer {app_jwt}', 'Accept': 'application/vnd.github+json'},
            timeout=10
        )
        token_response.raise_for_status()
        return token_response.json()['token']
    except ImportError:
        # 이 에러는 레이어에 PyJWT가 포함되어야 함을 의미합니다.
        raise ImportError("PyJWT library not found. Ensure it's included in the Lambda Layer.")
    except Exception as e:
        print(f"Error generating installation access token for installation {installation_id}: {e}")
        raise