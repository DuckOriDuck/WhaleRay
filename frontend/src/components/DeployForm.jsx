import { useState, useEffect } from 'react'
import { createDeployment } from '../lib/api'
import { getUser } from '../lib/auth'

export default function DeployForm({ repositories, loading, error, onLoadRepositories }) {
  const [deploying, setDeploying] = useState(false)
  const [deployError, setDeployError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [selectedRepo, setSelectedRepo] = useState('')
  const [branch, setBranch] = useState('main')
  const [envContent, setEnvContent] = useState('')

  useEffect(() => {
    const handleMessage = (event) => {
      // 보안을 위해 origin 체크 (동일 출처만 허용)
      if (event.origin !== window.location.origin) return

      if (event.data === 'github-app-config-complete') {
        console.log('GitHub App 설정 완료 신호 수신 - 리포지토리 목록 갱신')
        onLoadRepositories()
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [onLoadRepositories])

  async function handleSubmit(e) {
    e.preventDefault()
    setDeploying(true)
    setDeployError(null)
    setSuccess(null)

    try {
      const result = await createDeployment(selectedRepo, branch, envContent)
      setSuccess(`배포가 시작되었습니다! Deployment ID: ${result.deploymentId}`)

      // 폼 리셋
      setSelectedRepo('')
      setBranch('main')
      setEnvContent('')
    } catch (err) {
      setDeployError(err.message)
    } finally {
      setDeploying(false)
    }
  }

  return (
    <div className="card">
      <h2 style={{ marginBottom: '24px' }}>새 배포</h2>

      {error && <div className="error">리포지토리 로드 실패: {error}</div>}
      {deployError && <div className="error">{deployError}</div>}
      {success && <div className="success">{success}</div>}

      {loading ? (
        <p>리포지토리 목록을 불러오는 중...</p>
      ) : repositories.length === 0 ? (
        <p style={{ color: '#666', marginBottom: '16px' }}>
          사용 가능한 리포지토리가 없습니다. GitHub App에 리포지토리 권한을 부여해주세요.
        </p>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="repository">리포지토리</label>
            <select
              id="repository"
              value={selectedRepo}
              onChange={(e) => {
                setSelectedRepo(e.target.value)
                const repo = repositories.find(r => r.fullName === e.target.value)
                if (repo && repo.defaultBranch) {
                  setBranch(repo.defaultBranch)
                }
              }}
              required
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #ddd',
                borderRadius: '4px',
                fontSize: '14px'
              }}
            >
              <option value="">리포지토리를 선택하세요</option>
              {repositories.map(repo => (
                <option key={repo.id} value={repo.fullName}>
                  {repo.fullName} {repo.private ? '🔒' : ''}
                  {repo.language ? ` - ${repo.language}` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="branch">브랜치</label>
            <input
              id="branch"
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="main"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="envContent">환경변수 (.env)</label>
            <div style={{ fontSize: '12px', color: '#666', marginBottom: '8px' }}>
              환경변수는 KMS로 암호화되어 안전하게 저장됩니다. 재배포시에는 이전 설정을 자동으로 사용하므로 비워두셔도 됩니다.
            </div>
            <textarea
              id="envContent"
              value={envContent}
              onChange={(e) => setEnvContent(e.target.value)}
              placeholder={`# 예시:\nDATABASE_URL=postgres://...\nAPI_KEY=your-secret-key\nPORT=3000\n\n# 주석도 지원됩니다\n# 재배포시에는 비워두면 이전 설정 사용`}
              rows={8}
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #ddd',
                borderRadius: '4px',
                fontSize: '13px',
                fontFamily: 'monospace',
                resize: 'vertical',
                backgroundColor: '#f8f9fa'
              }}
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={deploying || !selectedRepo}>
            {deploying ? '배포 중...' : '배포하기'}
          </button>
        </form>
      )}
    </div>
  )
}