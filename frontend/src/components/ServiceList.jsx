import { useEffect, useState } from 'react'
import { getServices, getGitHubInstallationStatus } from '../lib/api'
import { config } from '../config'

export default function ServiceList({ onStartDeployment, onRefreshReady }) {
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [installStatus, setInstallStatus] = useState(null)
  const [checkingInstall, setCheckingInstall] = useState(false)

  useEffect(() => {
    loadServices()
    // Pass refresh function to parent
    if (onRefreshReady) {
      onRefreshReady(loadServices)
    }
  }, [])

  async function loadServices() {
    try {
      setLoading(true)
      setError(null)
      const data = await getServices()
      setServices(data)
    } catch (err) {
      setError(err.message)
      // trigger install check only when service load fails
      checkInstallationStatus()
    } finally {
      setLoading(false)
    }
  }

  async function checkInstallationStatus() {
    setCheckingInstall(true)
    try {
      const status = await getGitHubInstallationStatus()
      setInstallStatus(status)
    } catch (e) {
      // best-effort; keep previous
    } finally {
      setCheckingInstall(false)
    }
  }

  if (loading) {
    return <div className="loading">로딩 중...</div>
  }

  const githubAppInstallUrl = config.githubAppInstallUrl || 'https://github.com/apps/whaleray/installations/select_target'

  if (error) {
    const installLink = githubAppInstallUrl
    const isInstalled = installStatus?.installed

    return (
      <div className="card" style={{ textAlign: 'center', padding: '40px 20px' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>⚠️</div>
        <h3 style={{ color: '#333', marginBottom: '8px' }}>GitHub 리포지토리에 접근할 수 없습니다</h3>
        <p style={{ color: '#666', marginBottom: '16px' }}>
          WhaleRay가 리포지토리에 접근할 수 있도록 권한을 부여해주세요.
        </p>

        {checkingInstall && (
          <p style={{ color: '#2563eb', marginBottom: '16px' }}>
            GitHub App 설치 상태를 확인 중...
          </p>
        )}

        {isInstalled ? (
          <button
            onClick={loadServices}
            style={{
              padding: '12px 24px',
              backgroundColor: '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '16px',
              cursor: 'pointer',
              fontWeight: '500'
            }}
            onMouseOver={(e) => (e.target.style.backgroundColor = '#1d4ed8')}
            onMouseOut={(e) => (e.target.style.backgroundColor = '#2563eb')}
          >
            다시 시도
          </button>
        ) : (
          <button
            onClick={() => {
              window.location.href = installLink
            }}
            style={{
              padding: '12px 24px',
              backgroundColor: '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '16px',
              cursor: 'pointer',
              fontWeight: '500'
            }}
            onMouseOver={(e) => (e.target.style.backgroundColor = '#1d4ed8')}
            onMouseOut={(e) => (e.target.style.backgroundColor = '#2563eb')}
          >
            Configure GitHub App
          </button>
        )}
      </div>
    )
  }

  if (services.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '40px 20px' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>🚀</div>
        <h3 style={{ color: '#333', marginBottom: '8px' }}>배포된 서비스가 없습니다</h3>
        <p style={{ color: '#666', marginBottom: '24px' }}>
          첫 배포를 시작해보세요!
        </p>
        <button
          onClick={onStartDeployment}
          style={{
            padding: '12px 24px',
            backgroundColor: '#2563eb',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            fontSize: '16px',
            cursor: 'pointer',
            fontWeight: '500'
          }}
          onMouseOver={(e) => (e.target.style.backgroundColor = '#1d4ed8')}
          onMouseOut={(e) => (e.target.style.backgroundColor = '#2563eb')}
        >
          Start Deployment
        </button>
      </div>
    )
  }

  return (
    <div className="service-list">
      {services.map((service) => (
        <div key={service.serviceId} className="service-item">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
            <div>
              <div className="service-name">{service.serviceName}</div>
              <div style={{ fontSize: '14px', color: '#666', marginBottom: '8px' }}>
                {service.imageUri}
              </div>
              <div style={{ fontSize: '12px', color: '#999' }}>
                포트: {service.port}
              </div>
            </div>
            <span className={`service-status ${service.status.toLowerCase()}`}>
              {service.status}
            </span>
          </div>
          {service.taskDefinitionArn && (
            <div style={{ marginTop: '12px', fontSize: '12px', color: '#999' }}>
              Task: {service.taskDefinitionArn.split('/').pop()}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}