import { fetchAuthSession } from 'aws-amplify/auth'
import { config } from '../config'

const API_BASE_URL = config.apiEndpoint

async function getAuthHeaders() {
  try {
    const session = await fetchAuthSession()
    const token = session.tokens?.idToken?.toString()

    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    }
  } catch (error) {
    console.error('Failed to get auth headers:', error)
    throw new Error('Authentication required')
  }
}

export async function deployService(serviceData) {
  const headers = await getAuthHeaders()

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

export async function getServices() {
  const headers = await getAuthHeaders()

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

export async function getService(serviceId) {
  const headers = await getAuthHeaders()

  const response = await fetch(`${API_BASE_URL}/services/${serviceId}`, {
    method: 'GET',
    headers
  })

  if (!response.ok) {
    throw new Error('Failed to fetch service')
  }

  return response.json()
}

export async function getDeployments() {
  const headers = await getAuthHeaders()

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
