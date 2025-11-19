import { useState, useEffect } from 'react'
import { isAuthenticated, getUser, loginWithGitHub, logout, handleAuthCallback } from './lib/auth'
import { getMe } from './lib/api'
import ServiceList from './components/ServiceList'
import DeployForm from './components/DeployForm'
import DeploymentHistory from './components/DeploymentHistory'
import Setup from './components/Setup'

function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('services')
  const [needInstallation, setNeedInstallation] = useState(false)
  const [installUrl, setInstallUrl] = useState('')

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const pathname = window.location.pathname

    // GitHub App 설정 완료 감지 (setup_action 또는 installation_id 파라미터 확인)
    const isGitHubAppCallback =
      urlParams.has('setup_action') ||
      urlParams.has('installation_id') ||
      pathname === '/setup'

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
        // window.close()가 실패할 수 있으므로 사용자에게 안내
        setLoading(false)
      }, 500)
      return
    }

    // OAuth 콜백 처리 (URL에 token 파라미터가 있으면)
    const authResult = handleAuthCallback()
    if (authResult) {
      setUser(authResult)
      checkInstallation()
      return
    }

    // 기존 인증 상태 확인
    if (isAuthenticated()) {
      const currentUser = getUser()
      setUser(currentUser)
      checkInstallation()
    } else {
      setLoading(false)
    }
  }, [])

  async function checkInstallation() {
    try {
      const data = await getMe()
      setNeedInstallation(data.needInstallation || false)
      setInstallUrl(data.installUrl || '')
    } catch (err) {
      console.error('Failed to check installation:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleSignIn = () => {
    loginWithGitHub()
  }

  const handleSignOut = () => {
    logout()
    setUser(null)
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
    window.location.pathname === '/setup' ||
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

  // GitHub App 설치 필요
  if (needInstallation) {
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
        <Setup installUrl={installUrl} />
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
          <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #e0e0e0' }}>
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
          </div>
        </div>

        {activeTab === 'services' && <ServiceList />}
        {activeTab === 'deploy' && <DeployForm />}
        {activeTab === 'history' && <DeploymentHistory />}
      </div>
    </div>
  )
}

export default App
