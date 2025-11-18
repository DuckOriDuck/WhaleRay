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
  return data.services || []
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
  return data.deployments || []
}