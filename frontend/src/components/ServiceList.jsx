import { useEffect, useState } from 'react'
import { getServices } from '../lib/api'

export default function ServiceList() {
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadServices()
  }, [])

  async function loadServices() {
    try {
      setLoading(true)
      setError(null)
      const data = await getServices()
      setServices(data)
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

  if (services.length === 0) {
    return (
      <div className="card">
        <p style={{ textAlign: 'center', color: '#666' }}>
          배포된 서비스가 없습니다. 새 배포를 시작해보세요!
        </p>
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
