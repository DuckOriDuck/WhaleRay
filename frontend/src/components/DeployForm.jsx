import { useState } from 'react'
import { deployService } from '../lib/api'

export default function DeployForm() {
  const [formData, setFormData] = useState({
    serviceName: '',
    imageUri: '',
    port: '3000',
    envVars: ''
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      // 환경 변수 파싱 (KEY=VALUE 형식)
      const envVars = {}
      if (formData.envVars.trim()) {
        formData.envVars.split('\n').forEach(line => {
          const [key, ...valueParts] = line.split('=')
          if (key && valueParts.length > 0) {
            envVars[key.trim()] = valueParts.join('=').trim()
          }
        })
      }

      const result = await deployService({
        serviceName: formData.serviceName,
        imageUri: formData.imageUri,
        port: parseInt(formData.port),
        envVars
      })

      setSuccess(`배포가 시작되었습니다! Deployment ID: ${result.deploymentId}`)

      // 폼 리셋
      setFormData({
        serviceName: '',
        imageUri: '',
        port: '3000',
        envVars: ''
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>새 서비스 배포</h2>

      {error && <div className="error">{error}</div>}
      {success && <div className="success">{success}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="serviceName">서비스 이름</label>
          <input
            id="serviceName"
            type="text"
            value={formData.serviceName}
            onChange={(e) => setFormData({ ...formData, serviceName: e.target.value })}
            placeholder="my-app"
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="imageUri">Docker 이미지 URI</label>
          <input
            id="imageUri"
            type="text"
            value={formData.imageUri}
            onChange={(e) => setFormData({ ...formData, imageUri: e.target.value })}
            placeholder="123456789.dkr.ecr.ap-northeast-2.amazonaws.com/my-app:latest"
            required
          />
          <small style={{ display: 'block', marginTop: '4px', color: '#666' }}>
            ECR 이미지 URI 또는 Docker Hub 이미지
          </small>
        </div>

        <div className="form-group">
          <label htmlFor="port">포트</label>
          <input
            id="port"
            type="number"
            value={formData.port}
            onChange={(e) => setFormData({ ...formData, port: e.target.value })}
            placeholder="3000"
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="envVars">환경 변수 (선택사항)</label>
          <textarea
            id="envVars"
            rows="5"
            value={formData.envVars}
            onChange={(e) => setFormData({ ...formData, envVars: e.target.value })}
            placeholder="NODE_ENV=production&#10;API_KEY=your-key&#10;DATABASE_URL=postgres://..."
          />
          <small style={{ display: 'block', marginTop: '4px', color: '#666' }}>
            한 줄에 하나씩 KEY=VALUE 형식으로 입력
          </small>
        </div>

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? '배포 중...' : '배포하기'}
        </button>
      </form>
    </div>
  )
}
