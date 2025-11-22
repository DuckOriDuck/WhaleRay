import { useState, useEffect, useRef } from 'react'
import { getDeploymentLogs } from '../lib/api'

/**
 * 실시간 배포 로그 폴링 Hook
 * @param {string} deploymentId - 배포 ID
 * @param {Object} options - 옵션
 * @param {string} options.type - 로그 타입 ('build', 'runtime', 'all')
 * @param {number} options.pollingInterval - 폴링 간격 (ms, 기본값: 2000)
 * @param {boolean} options.enabled - 폴링 활성화 여부 (기본값: true)
 */
export function useBuildLogs(deploymentId, options = {}) {
  const {
    type = 'all',
    pollingInterval = 2000,
    enabled = true
  } = options

  const [logs, setLogs] = useState([])
  const [status, setStatus] = useState('UNKNOWN')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [isPolling, setIsPolling] = useState(false)

  // 폴링 제어를 위한 ref
  const intervalRef = useRef(null)
  const lastEventTimeRef = useRef(null)
  const isMountedRef = useRef(true)

  // 컴포넌트 언마운트 시 정리
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])

  // 단일 로그 요청
  const fetchLogs = async (incremental = false) => {
    if (!deploymentId) return

    try {
      if (!incremental) setIsLoading(true)
      setError(null)

      const fetchOptions = {
        type,
        limit: 100
      }

      // 증분 업데이트인 경우 마지막 이벤트 시간 사용
      if (incremental && lastEventTimeRef.current) {
        fetchOptions.lastEventTime = lastEventTimeRef.current
      }

      const response = await getDeploymentLogs(deploymentId, fetchOptions)
      
      if (!isMountedRef.current) return

      // 상태 업데이트
      setStatus(response.status)

      if (incremental && response.logs.length > 0) {
        // 증분 업데이트: 새로운 로그만 추가
        setLogs(prevLogs => [...prevLogs, ...response.logs])
      } else if (!incremental) {
        // 전체 로드: 로그 교체
        setLogs(response.logs)
      }

      // 다음 증분 업데이트를 위해 마지막 이벤트 시간 저장
      if (response.latestEventTime) {
        lastEventTimeRef.current = response.latestEventTime
      }

      return response

    } catch (err) {
      console.error('Failed to fetch logs:', err)
      if (isMountedRef.current) {
        setError(err.message)
      }
      throw err
    } finally {
      if (isMountedRef.current && !incremental) {
        setIsLoading(false)
      }
    }
  }

  // 폴링 시작/중지 제어
  useEffect(() => {
    if (!enabled || !deploymentId) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        setIsPolling(false)
      }
      return
    }

    // 초기 로드
    fetchLogs(false)

    // 완료 상태가 아닌 경우에만 폴링 시작
    const startPolling = (currentStatus) => {
      if (['RUNNING', 'FAILED', 'BUILDING_FAIL', 'DEPLOYING_FAIL'].includes(currentStatus)) {
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
        }
        setIsPolling(false)
        return
      }

      if (!intervalRef.current) {
        setIsPolling(true)
        intervalRef.current = setInterval(async () => {
          try {
            const response = await fetchLogs(true)
            
            // 완료 상태면 폴링 중단
            if (response && ['RUNNING', 'FAILED', 'BUILDING_FAIL', 'DEPLOYING_FAIL'].includes(response.status)) {
              clearInterval(intervalRef.current)
              intervalRef.current = null
              setIsPolling(false)
            }
          } catch (err) {
            console.error('Polling error:', err)
            // 에러가 발생해도 폴링은 계속 (일시적 네트워크 오류일 수 있음)
          }
        }, pollingInterval)
      }
    }

    // status가 업데이트된 후 폴링 제어
    fetchLogs(false).then(response => {
      if (response) {
        startPolling(response.status)
      }
    })

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      setIsPolling(false)
    }
  }, [deploymentId, enabled, pollingInterval, type])

  // 수동 새로고침
  const refresh = () => {
    lastEventTimeRef.current = null // 전체 새로고침
    return fetchLogs(false)
  }

  // 폴링 중단
  const stopPolling = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
      setIsPolling(false)
    }
  }

  return {
    logs,
    status,
    isLoading,
    error,
    isPolling,
    refresh,
    stopPolling
  }
}