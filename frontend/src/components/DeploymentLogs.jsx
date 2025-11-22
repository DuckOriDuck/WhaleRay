import React, { useEffect, useRef } from 'react'
import { useBuildLogs } from '../hooks/useBuildLogs'

/**
 * 실시간 배포 로그 컴포넌트
 */
export function DeploymentLogs({ deploymentId, logType = 'all' }) {
  const { logs, status, isLoading, error, isPolling, refresh, stopPolling } = useBuildLogs(deploymentId, {
    type: logType,
    pollingInterval: 2000,
    enabled: Boolean(deploymentId)
  })

  const logContainerRef = useRef(null)
  const shouldAutoScroll = useRef(true)

  // 새 로그가 추가될 때 자동 스크롤
  useEffect(() => {
    if (shouldAutoScroll.current && logContainerRef.current && logs.length > 0) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs.length])

  // 사용자가 스크롤했는지 감지
  const handleScroll = () => {
    if (!logContainerRef.current) return
    
    const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current
    // 하단에 가까우면 자동 스크롤 활성화 (20px 여유)
    shouldAutoScroll.current = scrollTop + clientHeight >= scrollHeight - 20
  }

  // 로그 메시지 포맷팅
  const formatLogMessage = (log) => {
    const date = new Date(log.timestamp)
    const timeStr = date.toLocaleTimeString()
    return `[${timeStr}] [${log.source}] ${log.message}`
  }

  // 상태에 따른 색상 클래스
  const getStatusColor = (status) => {
    switch (status) {
      case 'QUEUED': return 'text-gray-600'
      case 'INSPECTING': return 'text-blue-600'
      case 'BUILDING': return 'text-yellow-600'
      case 'DEPLOYING': return 'text-orange-600'
      case 'RUNNING': return 'text-green-600'
      case 'FAILED':
      case 'BUILDING_FAIL':
      case 'DEPLOYING_FAIL':
        return 'text-red-600'
      default: return 'text-gray-600'
    }
  }

  // 상태 표시 텍스트
  const getStatusText = (status) => {
    switch (status) {
      case 'QUEUED': return '대기 중'
      case 'INSPECTING': return '분석 중'
      case 'BUILDING': return '빌드 중'
      case 'DEPLOYING': return '배포 중'
      case 'RUNNING': return '실행 중'
      case 'BUILDING_FAIL': return '빌드 실패'
      case 'DEPLOYING_FAIL': return '배포 실패'
      case 'FAILED': return '실패'
      default: return status
    }
  }

  if (!deploymentId) {
    return (
      <div className="p-4 text-center text-gray-500">
        배포를 선택하여 로그를 확인하세요.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-white border rounded-lg shadow">
      {/* 헤더 */}
      <div className="flex items-center justify-between p-4 border-b bg-gray-50">
        <div className="flex items-center space-x-3">
          <h3 className="font-semibold text-gray-900">배포 로그</h3>
          <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusColor(status)} bg-gray-100`}>
            {getStatusText(status)}
          </span>
          {isPolling && (
            <div className="flex items-center space-x-1 text-xs text-blue-600">
              <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse"></div>
              <span>실시간 업데이트 중</span>
            </div>
          )}
        </div>
        
        <div className="flex items-center space-x-2">
          <button
            onClick={refresh}
            disabled={isLoading}
            className="px-3 py-1 text-xs text-gray-600 bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
          >
            {isLoading ? '로딩...' : '새로고침'}
          </button>
          
          {isPolling && (
            <button
              onClick={stopPolling}
              className="px-3 py-1 text-xs text-red-600 bg-white border border-red-300 rounded hover:bg-red-50"
            >
              중단
            </button>
          )}
        </div>
      </div>

      {/* 로그 컨테이너 */}
      <div 
        ref={logContainerRef}
        onScroll={handleScroll}
        className="flex-1 p-4 overflow-auto bg-black text-green-400 font-mono text-sm"
        style={{ minHeight: '300px', maxHeight: '500px' }}
      >
        {error && (
          <div className="mb-4 p-3 bg-red-900 text-red-200 rounded">
            오류: {error}
          </div>
        )}
        
        {isLoading && logs.length === 0 && (
          <div className="text-center text-gray-400 py-8">
            로그를 불러오는 중...
          </div>
        )}
        
        {logs.length === 0 && !isLoading && !error && (
          <div className="text-center text-gray-400 py-8">
            아직 로그가 없습니다.
          </div>
        )}
        
        {logs.map((log, index) => (
          <div key={`${log.timestamp}-${index}`} className="mb-1 leading-relaxed">
            <span className={log.source === 'build' ? 'text-blue-400' : 'text-green-400'}>
              {formatLogMessage(log)}
            </span>
          </div>
        ))}
        
        {logs.length > 0 && (
          <div className="mt-4 text-xs text-gray-500 text-center">
            총 {logs.length}개의 로그
          </div>
        )}
      </div>
      
      {/* 하단 정보 */}
      <div className="px-4 py-2 text-xs text-gray-500 border-t bg-gray-50">
        배포 ID: {deploymentId} | 로그 타입: {logType}
      </div>
    </div>
  )
}