import { useState, useEffect } from 'react'
import { getGitHubRepositories, createDeployment } from '../lib/api'
import { getUser } from '../lib/auth'

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

    const handleMessage = (event) => {
      // 보안을 위해 origin 체크 (동일 출처만 허용)
      if (event.origin !== window.location.origin) return

      if (event.data === 'github-app-config-complete') {
        console.log('GitHub App 설정 완료 신호 수신 - 리포지토리 목록 갱신')
        loadRepositories()
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ margin: 0 }}>새 배포</h2>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={loadRepositories}
            title="리포지토리 목록 새로고침"
            style={{
              background: 'none',
              border: '1px solid #ddd',
              borderRadius: '4px',
              cursor: 'pointer',
              padding: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#666'
            }}
            onMouseOver={(e) => e.currentTarget.style.background = '#f5f5f5'}
            onMouseOut={(e) => e.currentTarget.style.background = 'none'}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 4v6h-6"></path>
              <path d="M1 20v-6h6"></path>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
          </button>
          <button
            onClick={() => {
              const user = getUser()
              const userId = user ? user.username : 'unknown' // Using username as ID for now, or fetch real ID if available

              const width = 900
              const height = 700
              const left = (window.screen.width - width) / 2
              const top = (window.screen.height - height) / 2
              window.open(
                `https://github.com/apps/whaleray/installations/new?state=${userId}`,
                'github_app_install',
                `width=${width},height=${height},left=${left},top=${top},scrollbars=yes`
              )
            }}
            style={{
              background: 'none',
              cursor: 'pointer',
              textDecoration: 'none',
              padding: '8px 16px',
              fontSize: '14px',
              fontWeight: '500',
              color: '#1a73e8',
              border: '1px solid #1a73e8',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.2s'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = '#e8f0fe'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = 'transparent'
            }}
          >
            <svg height="16" width="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
            </svg>
            GitHub App 설정
          </button>
        </div>
      </div>

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
      </form >
    </div >
  )
}
