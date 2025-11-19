import { config } from '../config'

const TOKEN_KEY = 'whaleray_jwt_token'
const USER_KEY = 'whaleray_user'

/**
 * JWT 토큰 저장
 */
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

/**
 * JWT 토큰 가져오기
 */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

/**
 * 사용자 정보 저장
 */
export function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

/**
 * 사용자 정보 가져오기
 */
export function getUser() {
  const user = localStorage.getItem(USER_KEY)
  return user ? JSON.parse(user) : null
}

/**
 * 로그아웃 (토큰과 사용자 정보 삭제)
 */
export function logout() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

/**
 * 인증 여부 확인
 */
export function isAuthenticated() {
  const token = getToken()
  if (!token) return false

  try {
    // JWT 토큰 파싱 (payload 추출)
    const payload = JSON.parse(atob(token.split('.')[1]))

    // 만료 시간 확인
    const now = Math.floor(Date.now() / 1000)
    if (payload.exp && payload.exp < now) {
      logout()
      return false
    }

    return true
  } catch (error) {
    console.error('Invalid token:', error)
    logout()
    return false
  }
}

/**
 * GitHub App 로그인 시작
 */
export function loginWithGitHub() {
  const redirectUri = config.frontendUrl || window.location.origin
  const authBase = config.authEndpoint || `${config.apiEndpoint}/auth/github`
  window.location.href = `${authBase}/start?redirect_uri=${encodeURIComponent(redirectUri)}`
}

/**
 * OAuth 콜백 처리 (URL 파라미터에서 토큰 추출)
 */
export function handleAuthCallback() {
  const params = new URLSearchParams(window.location.search)
  const token = params.get('token')
  const username = params.get('username')

  if (token && username) {
    setToken(token)
    setUser({ username })

    // URL에서 파라미터 제거 (히스토리 정리)
    window.history.replaceState({}, document.title, window.location.pathname)

    return { token, username }
  }

  return null
}
