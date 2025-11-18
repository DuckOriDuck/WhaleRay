import { useState, useEffect } from 'react'
import { getGitHubRepositories, createDeployment } from '../lib/api'

export default function DeployForm() {
  const [repositories, setRepositories] = useState([])
  const [loading, setLoading] = useState(true)
  const [deploying, setDeploying] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [selectedRepo, setSelectedRepo] = useState('')
  const [branch, setBranch] = useState('main')

  useEffect(() => {
    loadRepositories()
  }, [])

  async function loadRepositories() {
    setLoading(true)
    setError(null)

    try {
      const data = await getGitHubRepositories()
      setRepositories(data.repositories || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setDeploying(true)
    setError(null)
    setSuccess(null)

    try {
      const result = await createDeployment(selectedRepo, branch)
      setSuccess(`배포가 시작되었습니다! Deployment ID: ${result.deploymentId}`)

      // 폼 리셋
      setSelectedRepo('')
      setBranch('main')
    } catch (err) {
      setError(err.message)
    } finally {
      setDeploying(false)
    }
  }

  if (loading) {
    return (
      <div className="card">
        <h2>새 배포</h2>
        <p>리포지토리 목록을 불러오는 중...</p>
      </div>
    )
  }

  if (repositories.length === 0) {
    return (
      <div className="card">
        <h2>새 배포</h2>
        <p style={{ color: '#666', marginBottom: '16px' }}>
          사용 가능한 리포지토리가 없습니다. GitHub App에 리포지토리 권한을 부여해주세요.
        </p>
        <button
          onClick={() => window.location.href = 'https://github.com/apps/whaleray/installations/select_target'}
          className="btn btn-primary"
        >
          GitHub App 설정
        </button>
      </div>
    )
  }

  return (
    <div className="card">
      <h2>새 배포</h2>

      {error && <div className="error">{error}</div>}
      {success && <div className="success">{success}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="repository">리포지토리</label>
          <select
            id="repository"
            value={selectedRepo}
            onChange={(e) => {
              setSelectedRepo(e.target.value)
              // 선택한 repo의 defaultBranch를 찾아서 설정
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

        <button type="submit" className="btn btn-primary" disabled={deploying || !selectedRepo}>
          {deploying ? '배포 중...' : '배포하기'}
        </button>
      </form>
    </div>
  )
}
