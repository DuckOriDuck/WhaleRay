import { config } from '../config'
import { getToken } from './auth'

const API_BASE_URL = config.apiEndpoint

/**
 * Authorization 헤더 생성
 */
function getAuthHeaders() {
  const token = getToken()

  if (!token) {
    throw new Error('No authentication token found')
  }

  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  }
}

/**
 * 서비스 배포
 */
export async function deployService(serviceData) {
  const headers = getAuthHeaders()

  const response = await fetch(`${API_BASE_URL}/deploy`, {
    method: 'POST',
    headers,
    body: JSON.stringify(serviceData)
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.message || 'Deployment failed')
  }

  return response.json()
}

/**
 * 서비스 목록 조회
 */
export async function getServices() {
  const headers = getAuthHeaders()

  const response = await fetch(`${API_BASE_URL}/services`, {
    method: 'GET',
    headers
  })

  if (!response.ok) {
    throw new Error('Failed to fetch services')
  }

  const data = await response.json()
  return data // 전체 응답 객체 반환 (data.services 포함)
}

/**
 * 특정 서비스 조회
 */
export async function getService(serviceId) {
  const headers = getAuthHeaders()

  const response = await fetch(`${API_BASE_URL}/services/${serviceId}`, {
    method: 'GET',
    headers
  })

  if (!response.ok) {
    throw new Error('Failed to fetch service')
  }

  return response.json()
}

/**
 * 배포 히스토리 조회
 */
export async function getDeployments() {
  const headers = getAuthHeaders()

  const response = await fetch(`${API_BASE_URL}/deployments`, {
    method: 'GET',
    headers
  })

  if (!response.ok) {
    throw new Error('Failed to fetch deployments')
  }

  const data = await response.json()
  return data // 전체 응답 객체 반환 (data.deployments 포함)
}

/**
 * GET /me - 사용자 정보 및 설치 상태 조회
 */
export async function getMe() {
  const headers = getAuthHeaders()

  const response = await fetch(`${API_BASE_URL}/me`, {
    method: 'GET',
    headers
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.error || 'Failed to fetch user info')
  }

  return response.json()
}

/**
 * GET /github/repositories - GitHub App installation을 사용하여 repositories 조회
 */
export async function getGitHubRepositories() {
  const headers = getAuthHeaders()

  const response = await fetch(`${API_BASE_URL}/github/repositories`, {
    method: 'GET',
    headers
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.error || 'Failed to fetch repositories')
  }

  return response.json()
}

/**
 * POST /deployments - 새 배포 시작
 */
export async function createDeployment(repositoryFullName, branch, envFileContent = '') {
  const headers = getAuthHeaders()
  
  const requestBody = {
    repositoryFullName,
    branch
  }
  
  // 환경변수 내용이 있으면 추가
  if (envFileContent.trim()) {
    requestBody.envFileContent = envFileContent
  }

  const response = await fetch(`${API_BASE_URL}/deployments`, {
    method: 'POST',
    headers,
    body: JSON.stringify(requestBody)
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.error || 'Failed to create deployment')
  }

  return response.json()
}

/**
 * 배포 로그 조회
 */
export async function getDeploymentLogs(deploymentId, options = {}) {
  const headers = getAuthHeaders()
  
  // Query parameters 생성
  const params = new URLSearchParams()
  if (options.type) params.append('type', options.type) // 'build', 'runtime', 'all'
  if (options.limit) params.append('limit', options.limit.toString())
  if (options.lastEventTime) params.append('lastEventTime', options.lastEventTime.toString())
  
  const url = `${API_BASE_URL}/deployments/${deploymentId}/logs${params.toString() ? '?' + params.toString() : ''}`
  
  const response = await fetch(url, {
    method: 'GET',
    headers
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.error || 'Failed to fetch logs')
  }

  return response.json()
}

/**
 * GitHub App 설치 상태 조회 (deprecated)
 */
export async function getGitHubInstallationStatus() {
  // 이제 getMe() 사용
  return getMe()
}
