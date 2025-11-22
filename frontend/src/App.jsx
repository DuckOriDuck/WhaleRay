import { useState, useEffect, useRef } from 'react'
import { isAuthenticated, getUser, loginWithGitHub, logout, handleAuthCallback } from './lib/auth'
import { getMe, getGitHubRepositories } from './lib/api'
import ServiceList from './components/ServiceList'
import DeployForm from './components/DeployForm'
import DeploymentHistory from './components/DeploymentHistory'
import DatabaseManager from './components/DatabaseManager'

function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('services')

  // Repository state lifted from DeployForm
  const [repositories, setRepositories] = useState([])
  const [reposLoading, setReposLoading] = useState(false)
  const [reposError, setReposError] = useState(null)

  // Refresh state
  const [refreshing, setRefreshing] = useState(false)

  // Refs for child components refresh functions
  const serviceListRefreshRef = useRef(null)
  const deploymentHistoryRefreshRef = useRef(null)
  const databaseManagerRefreshRef = useRef(null)

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)

    // GitHub App 설정 완료 감지 (setup_action 또는 installation_id 파라미터 확인)
    const isGitHubAppCallback =
      urlParams.has('setup_action') ||
      urlParams.has('installation_id')

    // 에러 파라미터가 있고 팝업 창인 경우 (GitHub App callback 에러 포함)
    const hasErrorParam = urlParams.has('error')

    // 팝업 창이고 GitHub App 설정 콜백인 경우 또는 에러가 있는 경우
    if (window.opener && (isGitHubAppCallback || hasErrorParam)) {
      console.log('GitHub App 설정 완료/에러 감지 - 팝업 닫기', {
        isGitHubAppCallback,
        hasErrorParam,
        error: urlParams.get('error')
      })

      // 부모 창에 메시지 전송
      if (!window.opener.closed) {
        window.opener.postMessage('github-app-config-complete', window.location.origin)
      }

      // 짧은 지연 후 창 닫기 (메시지 전송 완료 보장)
      setTimeout(() => {
        window.close()
      }, 500)
      return
    }

    // OAuth 콜백 처리 (URL에 token 파라미터가 있으면)
    const authResult = handleAuthCallback()
    if (authResult) {
      setUser(authResult)
      setLoading(false)
      // 로그인 직후 리포지토리 로드
      loadRepositories()
      return
    }

    // 기존 인증 상태 확인
    if (isAuthenticated()) {
      const currentUser = getUser()
      setUser(currentUser)
      setLoading(false)
      // 초기 로드 시 리포지토리 로드
      loadRepositories()
    } else {
      setLoading(false)
    }
  }, [])

  async function loadRepositories() {
    setReposLoading(true)
    setReposError(null)

    try {
      const data = await getGitHubRepositories()
      setRepositories(data.repositories || [])
    } catch (err) {
      setReposError(err.message)
    } finally {
      setReposLoading(false)
    }
  }

  async function handleRefresh() {
    if (refreshing) return

    setRefreshing(true)
    try {
      if (activeTab === 'services' && serviceListRefreshRef.current) {
        await serviceListRefreshRef.current()
      } else if (activeTab === 'deploy') {
        await loadRepositories()
      } else if (activeTab === 'history' && deploymentHistoryRefreshRef.current) {
        await deploymentHistoryRefreshRef.current()
      } else if (activeTab === 'database' && databaseManagerRefreshRef.current) {
        await databaseManagerRefreshRef.current()
      }
    } finally {
      setRefreshing(false)
    }
  }

  function handleGitHubAppSettings() {
    const userId = user ? user.username : 'unknown'
    const width = 900
    const height = 700
    const left = (window.screen.width - width) / 2
    const top = (window.screen.height - height) / 2
    window.open(
      `https://github.com/apps/whaleray/installations/new?state=${userId}`,
      'github_app_install',
      `width=${width},height=${height},left=${left},top=${top},scrollbars=yes`
    )
  }

  const handleSignIn = () => {
    loginWithGitHub()
  }

  const handleSignOut = () => {
    logout()
    setUser(null)
    setRepositories([])
  }

  // Loading state
  if (loading) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        background: '#f5f5f5'
      }}>
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ color: '#1a73e8' }}>WhaleRay</h2>
          <p style={{ color: '#666' }}>로딩 중...</p>
        </div>
      </div>
    )
  }

  // Popup closing state (GitHub App installation callback)
  const urlParams = new URLSearchParams(window.location.search)
  if (window.opener && (
    urlParams.has('setup_action') ||
    urlParams.has('installation_id') ||
    urlParams.has('error')
  )) {
    const errorMessage = urlParams.get('error')
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        background: '#f5f5f5',
        flexDirection: 'column',
        gap: '16px'
      }}>
        {errorMessage ? (
          <>
            <p style={{ color: '#d32f2f', fontSize: '16px', maxWidth: '500px', textAlign: 'center' }}>
              {decodeURIComponent(errorMessage)}
            </p>
            <p style={{ color: '#666', fontSize: '14px' }}>창을 닫습니다...</p>
          </>
        ) : (
          <p style={{ color: '#666', fontSize: '16px' }}>설정이 완료되었습니다. 창을 닫습니다...</p>
        )}
        <button
          onClick={() => window.close()}
          style={{
            padding: '8px 16px',
            background: '#1a73e8',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px'
          }}
        >
          창이 자동으로 닫히지 않으면 여기를 클릭하세요
        </button>
      </div>
    )
  }

  // Login page
  if (!user) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        padding: '20px'
      }}>
        <div style={{
          background: 'white',
          borderRadius: '12px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
          padding: '48px',
          maxWidth: '400px',
          width: '100%',
          textAlign: 'center'
        }}>
          <h1 style={{
            fontSize: '42px',
            fontWeight: '700',
            color: '#1a73e8',
            marginBottom: '12px'
          }}>
            WhaleRay
          </h1>
          <p style={{
            color: '#666',
            fontSize: '16px',
            marginBottom: '48px'
          }}>
            Railway 스타일 배포 플랫폼
          </p>

          <button
            onClick={handleSignIn}
            style={{
              width: '100%',
              padding: '16px 24px',
              fontSize: '16px',
              fontWeight: '600',
              background: '#24292e',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '12px',
              transition: 'all 0.2s'
            }}
            onMouseOver={(e) => e.target.style.background = '#1b1f23'}
            onMouseOut={(e) => e.target.style.background = '#24292e'}
          >
            <svg height="24" width="24" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
            </svg>
            GitHub으로 로그인
          </button>

          <p style={{
            marginTop: '32px',
            fontSize: '14px',
            color: '#999'
          }}>
            GitHub 계정으로 간편하게 로그인하세요
          </p>
        </div>
      </div>
    )
  }

  // Main dashboard
  return (
    <div>
      <div className="header">
        <div className="container" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1>WhaleRay</h1>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <span style={{ color: '#666' }}>
              {user.username}
            </span>
            <button onClick={handleSignOut} className="btn btn-primary">
              로그아웃
            </button>
          </div>
        </div>
      </div>

      <div className="container">
        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e0e0e0' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => setActiveTab('services')}
                style={{
                  padding: '12px 24px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'services' ? '2px solid #1a73e8' : '2px solid transparent',
                  color: activeTab === 'services' ? '#1a73e8' : '#666',
                  fontWeight: activeTab === 'services' ? '600' : '400',
                  cursor: 'pointer'
                }}
              >
                서비스
              </button>
              <button
                onClick={() => setActiveTab('deploy')}
                style={{
                  padding: '12px 24px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'deploy' ? '2px solid #1a73e8' : '2px solid transparent',
                  color: activeTab === 'deploy' ? '#1a73e8' : '#666',
                  fontWeight: activeTab === 'deploy' ? '600' : '400',
                  cursor: 'pointer'
                }}
              >
                새 배포
              </button>
              <button
                onClick={() => setActiveTab('history')}
                style={{
                  padding: '12px 24px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'history' ? '2px solid #1a73e8' : '2px solid transparent',
                  color: activeTab === 'history' ? '#1a73e8' : '#666',
                  fontWeight: activeTab === 'history' ? '600' : '400',
                  cursor: 'pointer'
                }}
              >
                배포 히스토리
              </button>
              <button
                onClick={() => setActiveTab('database')}
                style={{
                  padding: '12px 24px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'database' ? '2px solid #1a73e8' : '2px solid transparent',
                  color: activeTab === 'database' ? '#1a73e8' : '#666',
                  fontWeight: activeTab === 'database' ? '600' : '400',
                  cursor: 'pointer'
                }}
              >
                데이터베이스
              </button>
            </div>

            {/* 공통 액션 버튼들 */}
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', paddingBottom: '2px' }}>
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                title="새로고침"
                style={{
                  background: 'none',
                  border: '1px solid #ddd',
                  borderRadius: '4px',
                  cursor: refreshing ? 'not-allowed' : 'pointer',
                  padding: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: refreshing ? '#999' : '#666',
                  opacity: refreshing ? 0.6 : 1
                }}
                onMouseOver={(e) => !refreshing && (e.currentTarget.style.background = '#f5f5f5')}
                onMouseOut={(e) => e.currentTarget.style.background = 'none'}
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ transform: refreshing ? 'rotate(180deg)' : 'none', transition: 'transform 0.3s' }}
                >
                  <path d="M23 4v6h-6"></path>
                  <path d="M1 20v-6h6"></path>
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                </svg>
              </button>
              <button
                onClick={handleGitHubAppSettings}
                style={{
                  background: 'none',
                  cursor: 'pointer',
                  textDecoration: 'none',
                  padding: '6px 14px',
                  fontSize: '13px',
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
                <svg height="14" width="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
                </svg>
                GitHub App 설정
              </button>
            </div>
          </div>
        </div>

        {activeTab === 'services' && (
          <ServiceList
            onStartDeployment={() => setActiveTab('deploy')}
            onRefreshReady={(refreshFn) => { serviceListRefreshRef.current = refreshFn }}
          />
        )}
        {activeTab === 'deploy' && (
          <DeployForm
            repositories={repositories}
            loading={reposLoading}
            error={reposError}
            onLoadRepositories={loadRepositories}
          />
        )}
        {activeTab === 'history' && (
          <DeploymentHistory
            onRefreshReady={(refreshFn) => { deploymentHistoryRefreshRef.current = refreshFn }}
          />
        )}
        {activeTab === 'database' && (
          <DatabaseManager ref={databaseManagerRefreshRef} />
        )}
      </div>
    </div>
  )
}

export default App
