import { useEffect, useState } from 'react'
import { getDeployments } from '../lib/api'

export default function DeploymentHistory({ onRefreshReady }) {
  const [deployments, setDeployments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadDeployments()
    // Pass refresh function to parent
    if (onRefreshReady) {
      onRefreshReady(loadDeployments)
    }
  }, [])

  async function loadDeployments() {
    try {
      setLoading(true)
      setError(null)
      const response = await getDeployments()
      setDeployments(response.deployments || []) // 응답 객체에서 deployments 배열을 추출
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
    return (
      <div className="card">
        <div className="error">{error}</div>
      </div>
    )
  }

  return (
    <div>
      {deployments.length === 0 ? (
        <div className="card">
          <p style={{ textAlign: 'center', color: '#666' }}>
            배포 기록이 없습니다.
          </p>
        </div>
      ) : (
        <div className="service-list">
          {deployments.map((deployment) => (
            <div key={deployment.deploymentId} className="service-item">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
                <div style={{ flex: 1 }}>
                  <div className="service-name">{deployment.serviceName || `Deployment ID :  ${deployment.deploymentId}`}</div>
                  <div style={{ fontSize: '13px', color: '#666', marginTop: '6px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    {deployment.repositoryFullName && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <strong>📦 Repository:</strong> {deployment.repositoryFullName}
                      </span>
                    )}
                    {deployment.branch && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <strong>🌿 Branch:</strong> {deployment.branch}
                      </span>
                    )}
                  </div>
                  {deployment.imageUri && (
                    <div style={{ fontSize: '12px', color: '#999', marginTop: '6px', fontFamily: 'monospace' }}>
                      {deployment.imageUri}
                    </div>
                  )}
                  <div style={{ fontSize: '12px', color: '#999', marginTop: '6px' }}>
                    ⏰ {new Date(deployment.createdAt * 1000).toLocaleString('ko-KR')}
                  </div>
                </div>
                <span className={`service-status ${deployment.status.toLowerCase()}`}>
                  {deployment.status}
                </span>
              </div>
              {deployment.errorMessage && (
                <div style={{ marginTop: '8px', padding: '10px', background: '#ffebee', borderRadius: '4px', fontSize: '13px', color: '#c62828', borderLeft: '3px solid #c62828' }}>
                  <strong>⚠️ Error:</strong> {deployment.errorMessage}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}