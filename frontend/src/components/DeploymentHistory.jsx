import { useEffect, useState } from 'react'
import { getDeployments } from '../lib/api'
import { DeploymentLogs } from './DeploymentLogs'

export default function DeploymentHistory({ onRefreshReady }) {
  const [deployments, setDeployments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedDeploymentId, setSelectedDeploymentId] = useState(null)

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
              
              {/* 로그 보기 버튼 */}
              <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => setSelectedDeploymentId(
                    selectedDeploymentId === deployment.deploymentId ? null : deployment.deploymentId
                  )}
                  style={{
                    padding: '6px 12px',
                    fontSize: '12px',
                    backgroundColor: selectedDeploymentId === deployment.deploymentId ? '#007bff' : '#f8f9fa',
                    color: selectedDeploymentId === deployment.deploymentId ? 'white' : '#007bff',
                    border: '1px solid #007bff',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  {selectedDeploymentId === deployment.deploymentId ? '로그 숨기기' : '로그 보기'}
                </button>
              </div>
              
              {/* 로그 컴포넌트 */}
              {selectedDeploymentId === deployment.deploymentId && (
                <div style={{ marginTop: '16px' }}>
                  <DeploymentLogs deploymentId={deployment.deploymentId} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      
      {/* React Query 도입 안내 */}
      {deployments.length > 0 && (
        <div style={{ 
          marginTop: '20px', 
          padding: '12px', 
          background: '#e3f2fd', 
          borderRadius: '6px', 
          fontSize: '13px',
          color: '#1565c0'
        }}>
          💡 <strong>개선 예정:</strong> React Query 도입으로 실시간 업데이트 및 캐싱 성능을 개선할 예정입니다.
        </div>
      )}
    </div>
  )
}