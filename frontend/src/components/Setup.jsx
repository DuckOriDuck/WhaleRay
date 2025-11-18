import { config } from '../config'

export default function Setup({ installUrl, installed, checkingInstall }) {
  const githubAppInstallUrl = 'https://github.com/apps/whaleray/installations/select_target'
  const installLink = githubAppInstallUrl

  return (
    <div style={{
      maxWidth: '600px',
      margin: '80px auto',
      padding: '40px',
      textAlign: 'center'
    }}>
      <div style={{ fontSize: '64px', marginBottom: '24px' }}>🚀</div>

      <h1 style={{
        fontSize: '32px',
        fontWeight: '700',
        color: '#333',
        marginBottom: '16px'
      }}>
        Welcome to WhaleRay!
      </h1>

      <p style={{
        fontSize: '18px',
        color: '#666',
        marginBottom: '12px',
        lineHeight: '1.6'
      }}>
        GitHub 리포지토리에 접근할 수 없습니다.
      </p>
      <p style={{
        fontSize: '18px',
        color: '#666',
        marginBottom: '32px',
        lineHeight: '1.6'
      }}>
        WhaleRay가 리포지토리에 접근할 수 있도록 권한을 부여해주세요.
      </p>

      <div className="card" style={{
        textAlign: 'left',
        marginBottom: '32px',
        padding: '24px'
      }}>
        <h3 style={{ marginBottom: '16px', color: '#333' }}>설치 단계:</h3>
        <ol style={{ paddingLeft: '20px', lineHeight: '2', color: '#666' }}>
          <li>“GitHub App 설치하기” 버튼 클릭</li>
          <li>어떤 계정/조직에 설치할지 선택</li>
          <li>접근 가능한 리포지토리를 선택하고 권한을 승인</li>
          <li>설치 완료 후 자동으로 돌아오기—or 아래 “완료” 버튼</li>
        </ol>

        {checkingInstall && (
          <div style={{ marginTop: '12px', color: '#2563eb' }}>
            GitHub App 설치 상태 확인 중...
          </div>
        )}

        {installed && (
          <div style={{
            marginTop: '16px',
            padding: '12px',
            borderRadius: '8px',
            background: '#ecfdf3',
            color: '#166534',
            fontWeight: 600
          }}>
            GitHub App 설치가 확인되었습니다.
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
        <button
          onClick={() => {
            window.location.href = installLink
          }}
          style={{
            padding: '14px 28px',
            backgroundColor: '#24292e',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            fontSize: '16px',
            cursor: 'pointer',
            fontWeight: '600',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
          onMouseOver={(e) => e.target.style.backgroundColor = '#1b1f23'}
          onMouseOut={(e) => e.target.style.backgroundColor = '#24292e'}
        >
          <svg height="20" width="20" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
          </svg>
          Configure GitHub App
        </button>

        <button
          onClick={() => {
            window.location.href = '/'
          }}
          style={{
            padding: '14px 28px',
            backgroundColor: '#2563eb',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            fontSize: '16px',
            cursor: 'pointer',
            fontWeight: '600'
          }}
          onMouseOver={(e) => e.target.style.backgroundColor = '#1d4ed8'}
          onMouseOut={(e) => e.target.style.backgroundColor = '#2563eb'}
        >
          완료
        </button>
      </div>

      <p style={{
        marginTop: '24px',
        fontSize: '14px',
        color: '#999'
      }}>
        GitHub App 설치를 완료한 후 "완료" 버튼을 클릭하세요.
      </p>
    </div>
  )
}
