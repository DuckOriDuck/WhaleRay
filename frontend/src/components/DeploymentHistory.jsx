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
              
              {/* 로그 보기 버튼 - 심플하게 개선 */}
              <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', paddingTop: '12px', borderTop: '1px solid #e0e0e0' }}>
                <button
                  onClick={() => setSelectedDeploymentId(
                    selectedDeploymentId === deployment.deploymentId ? null : deployment.deploymentId
                  )}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '10px 18px',
                    fontSize: '13px',
                    fontWeight: '500',
                    backgroundColor: selectedDeploymentId === deployment.deploymentId ? '#10B981' : '#ffffff',
                    color: selectedDeploymentId === deployment.deploymentId ? '#ffffff' : '#10B981',
                    border: '1px solid #10B981',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    outline: 'none',
                    boxShadow: selectedDeploymentId === deployment.deploymentId ? '0 2px 8px rgba(16, 185, 129, 0.3)' : 'none'
                  }}
                  onMouseOver={(e) => {
                    if (selectedDeploymentId !== deployment.deploymentId) {
                      e.target.style.backgroundColor = '#ECFDF5'
                      e.target.style.transform = 'translateY(-1px)'
                      e.target.style.boxShadow = '0 2px 8px rgba(16, 185, 129, 0.15)'
                    }
                  }}
                  onMouseOut={(e) => {
                    if (selectedDeploymentId !== deployment.deploymentId) {
                      e.target.style.backgroundColor = '#ffffff'
                      e.target.style.transform = 'translateY(0)'
                      e.target.style.boxShadow = 'none'
                    }
                  }}
                >
                  {selectedDeploymentId === deployment.deploymentId ? 'Hide Logs' : 'View Logs'}
                </button>
              </div>
              
              {/* 로그 컴포넌트 */}
              {selectedDeploymentId === deployment.deploymentId && (
                <div style={{ 
                  marginTop: '20px',
                  border: '1px solid #e0e0e0',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  backgroundColor: '#fafafa'
                }}>
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
          background: '#ECFDF5', 
          borderRadius: '6px', 
          fontSize: '13px',
          color: '#059669'
        }}>
          💡 <strong>개선 예정:</strong> React Query 도입으로 실시간 업데이트 및 캐싱 성능을 개선할 예정입니다.
        </div>
      )}
    </div>
  )
}