import { useEffect, useState } from 'react'
import { getDeployments } from '../lib/api'

export default function DeploymentHistory() {
  const [deployments, setDeployments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadDeployments()
  }, [])

  async function loadDeployments() {
    try {
      setLoading(true)
      setError(null)
      const data = await getDeployments()
      setDeployments(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="loading">로딩 중...</div>
  }

  if (error) {
    return <div className="error">{error}</div>
  }

  if (deployments.length === 0) {
    return (
      <div className="card">
        <p style={{ textAlign: 'center', color: '#666' }}>
          배포 기록이 없습니다.
        </p>
      </div>
    )
  }

  return (
    <div className="service-list">
      {deployments.map((deployment) => (
        <div key={deployment.deploymentId} className="service-item">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
            <div style={{ flex: 1 }}>
              <div className="service-name">{deployment.serviceName}</div>
              <div style={{ fontSize: '14px', color: '#666', marginTop: '4px' }}>
                {deployment.imageUri}
              </div>
              <div style={{ fontSize: '12px', color: '#999', marginTop: '8px' }}>
                {new Date(deployment.createdAt * 1000).toLocaleString('ko-KR')}
              </div>
            </div>
            <span className={`service-status ${deployment.status.toLowerCase()}`}>
              {deployment.status}
            </span>
          </div>
          {deployment.errorMessage && (
            <div style={{ marginTop: '12px', padding: '8px', background: '#ffebee', borderRadius: '4px', fontSize: '12px', color: '#c62828' }}>
              {deployment.errorMessage}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
