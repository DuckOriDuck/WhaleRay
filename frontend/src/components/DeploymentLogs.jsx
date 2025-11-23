import React, { useEffect, useRef, useState } from 'react'
import { useBuildLogs } from '../hooks/useBuildLogs'
import { getToken } from '../lib/auth'
import { config } from '../config'

/**
 * 실시간 배포 로그 컴포넌트
 */
export function DeploymentLogs({ deploymentId, logType = 'all' }) {
  const { logs, status, isLoading, error, isPolling, refresh, stopPolling } = useBuildLogs(deploymentId, {
    type: logType,
    pollingInterval: 2000,
    enabled: Boolean(deploymentId)
  })

  // AI 분석 상태
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState(null)
  const [analysisError, setAnalysisError] = useState(null)
  const [showAnalysis, setShowAnalysis] = useState(false)

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

  // AI 로그 분석 함수
  const analyzeLogsWithAI = async () => {
    if (!logs.length || !deploymentId) return
    
    setAnalyzing(true)
    setAnalysisError(null)
    
    try {
      const token = getToken()
      const response = await fetch(`${config.apiEndpoint}/deployments/${deploymentId}/analyze-logs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ logs })
      })
      
      if (!response.ok) {
        throw new Error(`분석 실패: ${response.status}`)
      }
      
      const result = await response.json()
      setAnalysisResult(result.analysis)
      setShowAnalysis(true)
      
    } catch (err) {
      setAnalysisError(err.message)
    } finally {
      setAnalyzing(false)
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
    <>
      {/* CSS 애니메이션 정의 */}
      <style>{`
        @keyframes shimmer {
          0% { left: -100%; }
          100% { left: 100%; }
        }
      `}</style>
      
    <div className="flex flex-col h-full bg-white">
      {/* 개선된 헤더 */}
      <div style={{
        background: 'linear-gradient(135deg, #0F0F23 0%, #1A1A2E 50%, #10B981 100%)',
        color: 'white',
        padding: '16px 20px',
        borderRadius: '8px 8px 0 0'
      }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: '600', margin: '0' }}>Deployment Logs</h3>
              <span style={{
                padding: '4px 12px',
                fontSize: '12px',
                fontWeight: '500',
                borderRadius: '6px',
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                border: '1px solid rgba(255, 255, 255, 0.2)'
              }}>
                {getStatusText(status)}
              </span>
            </div>
            {isPolling && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                <div style={{
                  width: '8px',
                  height: '8px',
                  backgroundColor: '#10b981',
                  borderRadius: '50%',
                  animation: 'pulse 2s infinite'
                }}></div>
                <span>Live</span>
              </div>
            )}
          </div>
          
          <div className="flex items-center space-x-2">
            {/* AI Analysis 버튼 - 개선된 디자인 */}
            <button
              onClick={analyzeLogsWithAI}
              disabled={analyzing || logs.length === 0}
              style={{
                padding: '8px 16px',
                fontSize: '13px',
                fontWeight: '600',
                background: analyzing 
                  ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.15) 100%)' 
                  : logs.length === 0 
                    ? 'rgba(16, 185, 129, 0.3)'
                    : 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
                color: 'white',
                border: analyzing 
                  ? '1px solid rgba(16, 185, 129, 0.4)' 
                  : logs.length === 0
                    ? '1px solid rgba(16, 185, 129, 0.3)'
                    : '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '8px',
                cursor: (analyzing || logs.length === 0) ? 'default' : 'pointer',
                opacity: (analyzing || logs.length === 0) ? '0.7' : '1',
                transition: 'all 0.3s ease',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                boxShadow: analyzing 
                  ? '0 2px 8px rgba(16, 185, 129, 0.15)' 
                  : logs.length === 0
                    ? 'none'
                    : '0 2px 12px rgba(16, 185, 129, 0.25)',
                transform: analyzing ? 'scale(0.98)' : 'scale(1)',
                position: 'relative',
                overflow: 'hidden'
              }}
              onMouseOver={(e) => {
                if (!analyzing && logs.length > 0) {
                  e.target.style.background = 'linear-gradient(135deg, #059669 0%, #047857 100%)'
                  e.target.style.transform = 'scale(1.05)'
                  e.target.style.boxShadow = '0 4px 16px rgba(16, 185, 129, 0.4)'
                }
              }}
              onMouseOut={(e) => {
                if (!analyzing && logs.length > 0) {
                  e.target.style.background = 'linear-gradient(135deg, #10B981 0%, #059669 100%)'
                  e.target.style.transform = 'scale(1)'
                  e.target.style.boxShadow = '0 2px 12px rgba(16, 185, 129, 0.25)'
                }
              }}
            >
              {/* 배경 애니메이션 효과 */}
              {analyzing && (
                <div style={{
                  position: 'absolute',
                  top: 0,
                  left: '-100%',
                  width: '100%',
                  height: '100%',
                  background: 'linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent)',
                  animation: 'shimmer 1.5s infinite'
                }}></div>
              )}
              
              {/* 아이콘 */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '16px',
                height: '16px'
              }}>
                {analyzing ? (
                  <div style={{
                    width: '14px',
                    height: '14px',
                    border: '2px solid rgba(255, 255, 255, 0.3)',
                    borderTop: '2px solid white',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite'
                  }}></div>
                ) : (
                  <span style={{ 
                    fontSize: '14px',
                    display: 'flex',
                    alignItems: 'center',
                    background: 'linear-gradient(45deg, #FFF, #E0F2FE)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    filter: 'drop-shadow(0 1px 2px rgba(0, 0, 0, 0.1))'
                  }}>
                    ✨
                  </span>
                )}
              </div>
              
              {/* 텍스트 */}
              <span style={{
                letterSpacing: '0.5px',
                textShadow: analyzing ? 'none' : '0 1px 2px rgba(0, 0, 0, 0.1)'
              }}>
                {analyzing ? 'Analyzing...' : 'AI Analysis'}
              </span>
            </button>
            
            <button
              onClick={refresh}
              disabled={isLoading}
              style={{
                padding: '6px 12px',
                fontSize: '12px',
                fontWeight: '500',
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                color: 'white',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '4px',
                cursor: isLoading ? 'default' : 'pointer',
                opacity: isLoading ? '0.6' : '1',
                transition: 'all 0.2s ease'
              }}
              onMouseOver={(e) => {
                if (!isLoading) {
                  e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.2)'
                }
              }}
              onMouseOut={(e) => {
                if (!isLoading) {
                  e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.1)'
                }
              }}
            >
              {isLoading ? 'Loading...' : 'Refresh'}
            </button>
            
            {isPolling && (
              <button
                onClick={stopPolling}
                style={{
                  padding: '6px 12px',
                  fontSize: '12px',
                  fontWeight: '500',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  color: 'white',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease'
                }}
                onMouseOver={(e) => e.target.style.backgroundColor = 'rgba(239, 68, 68, 0.25)'}
                onMouseOut={(e) => e.target.style.backgroundColor = 'rgba(239, 68, 68, 0.15)'}
              >
                Stop
              </button>
            )}
            
            <button
              onClick={() => {
                const logContent = logs.map(log => formatLogMessage(log)).join('\n')
                const blob = new Blob([logContent], { type: 'text/plain' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `deployment-${deploymentId}-logs.txt`
                a.click()
                URL.revokeObjectURL(url)
              }}
              disabled={logs.length === 0}
              style={{
                padding: '6px 12px',
                fontSize: '12px',
                fontWeight: '500',
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                color: 'white',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '4px',
                cursor: logs.length > 0 ? 'pointer' : 'default',
                opacity: logs.length === 0 ? '0.5' : '1',
                transition: 'all 0.2s ease'
              }}
              onMouseOver={(e) => {
                if (logs.length > 0) {
                  e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.2)'
                }
              }}
              onMouseOut={(e) => {
                if (logs.length > 0) {
                  e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.1)'
                }
              }}
            >
              Download
            </button>
          </div>
        </div>
      </div>

      {/* AI 분석 결과 모달 */}
      {showAnalysis && analysisResult && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px'
        }}>
          <div style={{
            backgroundColor: 'white',
            borderRadius: '12px',
            maxWidth: '600px',
            width: '100%',
            maxHeight: '80vh',
            overflow: 'auto',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)'
          }}>
            {/* 모달 헤더 */}
            <div style={{
              background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
              color: 'white',
              padding: '20px',
              borderRadius: '12px 12px 0 0',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '20px' }}>🤖</span>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: '600' }}>AI Log Analysis Results</h3>
              </div>
              <button
                onClick={() => setShowAnalysis(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'white',
                  fontSize: '24px',
                  cursor: 'pointer',
                  padding: '0',
                  width: '32px',
                  height: '32px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: '4px',
                  opacity: '0.8',
                  transition: 'all 0.2s ease'
                }}
                onMouseOver={(e) => {
                  e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.1)'
                  e.target.style.opacity = '1'
                }}
                onMouseOut={(e) => {
                  e.target.style.backgroundColor = 'transparent'
                  e.target.style.opacity = '0.8'
                }}
              >
                ×
              </button>
            </div>
            
            {/* 모달 내용 */}
            <div style={{ padding: '24px' }}>
              {/* 요약 */}
              <div style={{ marginBottom: '24px' }}>
                <h4 style={{
                  margin: '0 0 12px 0',
                  fontSize: '16px',
                  fontWeight: '600',
                  color: '#1f2937',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  <span style={{
                    width: '20px',
                    height: '20px',
                    backgroundColor: '#10B981',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '12px',
                    color: 'white',
                    fontWeight: '700'
                  }}>📋</span>
                  Deployment Summary
                </h4>
                <p style={{ 
                  margin: 0, 
                  color: '#4b5563', 
                  lineHeight: '1.6',
                  backgroundColor: '#f9fafb',
                  padding: '16px',
                  borderRadius: '8px',
                  border: '1px solid #e5e7eb'
                }}>
                  {analysisResult.summary}
                </p>
              </div>
              
              {/* 상태 */}
              <div style={{ marginBottom: '24px' }}>
                <h4 style={{ margin: '0 0 12px 0', fontSize: '16px', fontWeight: '600', color: '#1f2937' }}>
                  Deployment Status
                </h4>
                <span style={{
                  padding: '8px 16px',
                  borderRadius: '20px',
                  fontSize: '14px',
                  fontWeight: '500',
                  backgroundColor: analysisResult.status === 'success' ? '#d1fae5' :
                                  analysisResult.status === 'error' ? '#fee2e2' :
                                  analysisResult.status === 'warning' ? '#fef3c7' : '#e5e7eb',
                  color: analysisResult.status === 'success' ? '#065f46' :
                         analysisResult.status === 'error' ? '#991b1b' :
                         analysisResult.status === 'warning' ? '#92400e' : '#374151'
                }}>
                  {analysisResult.status === 'success' ? '✅ Success' :
                   analysisResult.status === 'error' ? '❌ Error' :
                   analysisResult.status === 'warning' ? '⚠️ Warning' : '🔄 In Progress'}
                </span>
              </div>
              
              {/* 이슈 목록 */}
              {analysisResult.issues && analysisResult.issues.length > 0 && (
                <div style={{ marginBottom: '24px' }}>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '16px', fontWeight: '600', color: '#1f2937' }}>
                    Issues Found
                  </h4>
                  {analysisResult.issues.map((issue, index) => (
                    <div key={index} style={{
                      marginBottom: '12px',
                      padding: '16px',
                      backgroundColor: issue.level === 'error' ? '#fef2f2' :
                                      issue.level === 'warning' ? '#fffbeb' : '#f0f9ff',
                      border: `1px solid ${issue.level === 'error' ? '#fecaca' :
                                           issue.level === 'warning' ? '#fed7aa' : '#bae6fd'}`,
                      borderRadius: '8px'
                    }}>
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        marginBottom: '8px'
                      }}>
                        <span style={{ fontSize: '16px' }}>
                          {issue.level === 'error' ? '🔴' : issue.level === 'warning' ? '🟡' : '🔵'}
                        </span>
                        <strong style={{ 
                          fontSize: '14px',
                          color: issue.level === 'error' ? '#dc2626' :
                                 issue.level === 'warning' ? '#d97706' : '#2563eb'
                        }}>
                          {issue.title}
                        </strong>
                      </div>
                      <p style={{ margin: '0 0 8px 24px', fontSize: '13px', color: '#6b7280' }}>
                        {issue.description}
                      </p>
                      {issue.suggestion && (
                        <p style={{ 
                          margin: '0 0 0 24px', 
                          fontSize: '13px', 
                          color: '#059669',
                          fontWeight: '500'
                        }}>
                          💡 {issue.suggestion}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
              
              {/* 권장사항 */}
              {analysisResult.recommendations && analysisResult.recommendations.length > 0 && (
                <div style={{ marginBottom: '24px' }}>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '16px', fontWeight: '600', color: '#1f2937' }}>
                    Recommendations
                  </h4>
                  <ul style={{ margin: 0, paddingLeft: '20px', color: '#4b5563' }}>
                    {analysisResult.recommendations.map((rec, index) => (
                      <li key={index} style={{ marginBottom: '8px', fontSize: '14px' }}>
                        {rec}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              
              {/* 주요 지표 */}
              {analysisResult.keyMetrics && (
                <div>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '16px', fontWeight: '600', color: '#1f2937' }}>
                    Key Metrics
                  </h4>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                    gap: '12px'
                  }}>
                    {Object.entries(analysisResult.keyMetrics).map(([key, value]) => (
                      value && (
                        <div key={key} style={{
                          padding: '12px',
                          backgroundColor: '#f9fafb',
                          borderRadius: '8px',
                          border: '1px solid #e5e7eb',
                          textAlign: 'center'
                        }}>
                          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>
                            {key === 'buildTime' ? 'Build Time' :
                             key === 'framework' ? 'Framework' :
                             key === 'progress' ? 'Progress' : key}
                          </div>
                          <div style={{ fontSize: '14px', fontWeight: '600', color: '#1f2937' }}>
                            {value}
                          </div>
                        </div>
                      )
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* AI 분석 에러 토스트 */}
      {analysisError && (
        <div style={{
          position: 'fixed',
          top: '20px',
          right: '20px',
          backgroundColor: '#fee2e2',
          color: '#991b1b',
          padding: '12px 16px',
          borderRadius: '8px',
          border: '1px solid #fecaca',
          zIndex: 1001,
          boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1)',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          maxWidth: '400px'
        }}>
          <span>❌</span>
          <span style={{ fontSize: '14px' }}>AI Analysis Failed: {analysisError}</span>
          <button
            onClick={() => setAnalysisError(null)}
            style={{
              background: 'none',
              border: 'none',
              color: '#991b1b',
              fontSize: '16px',
              cursor: 'pointer',
              marginLeft: '8px',
              padding: '0',
              width: '20px',
              height: '20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            ×
          </button>
        </div>
      )}

      {/* 로그 컨테이너 - 개선된 스타일 */}
      <div 
        ref={logContainerRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          padding: '16px',
          overflowY: 'auto',
          background: 'linear-gradient(135deg, #0d1421 0%, #1a1a2e 50%, #16213e 100%)',
          color: '#e2e8f0',
          fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
          fontSize: '13px',
          lineHeight: '1.5',
          minHeight: '400px',
          maxHeight: '600px',
          position: 'relative'
        }}
      >
        {error && (
          <div style={{
            marginBottom: '16px',
            padding: '12px 16px',
            background: 'linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)',
            color: 'white',
            borderRadius: '6px',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            fontSize: '14px',
            fontWeight: '500'
          }}>
            Error: {error}
          </div>
        )}
        
        {isLoading && logs.length === 0 && (
          <div style={{
            textAlign: 'center',
            color: '#94a3b8',
            padding: '40px 0',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px'
          }}>
            <div style={{
              width: '24px',
              height: '24px',
              border: '2px solid rgba(148, 163, 184, 0.3)',
              borderTop: '2px solid #94a3b8',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite'
            }}></div>
            <span>Loading deployment logs...</span>
          </div>
        )}
        
        {logs.length === 0 && !isLoading && !error && (
          <div style={{
            textAlign: 'center',
            color: '#94a3b8',
            padding: '40px 0',
            fontSize: '14px'
          }}>
            <div style={{ marginBottom: '8px', fontWeight: '500' }}>No logs available</div>
            <div style={{ opacity: '0.7' }}>Logs will appear here when deployment starts</div>
          </div>
        )}
        
        {logs.map((log, index) => {
          const isError = log.message.toLowerCase().includes('error') || log.message.toLowerCase().includes('오류')
          const isWarning = log.message.toLowerCase().includes('warn') || log.message.toLowerCase().includes('경고')
          const isSuccess = log.message.toLowerCase().includes('success') || log.message.toLowerCase().includes('성공') || log.message.toLowerCase().includes('completed')
          
          return (
            <div 
              key={`${log.timestamp}-${index}`} 
              style={{
                marginBottom: '4px',
                padding: '8px 12px',
                borderRadius: '4px',
                backgroundColor: isError ? 'rgba(239, 68, 68, 0.1)' : 
                                 isWarning ? 'rgba(245, 158, 11, 0.1)' : 
                                 isSuccess ? 'rgba(34, 197, 94, 0.1)' : 
                                 'rgba(51, 65, 85, 0.3)',
                borderLeft: `3px solid ${
                  isError ? '#ef4444' : 
                  isWarning ? '#f59e0b' : 
                  isSuccess ? '#22c55e' : 
                  log.source === 'build' ? '#3b82f6' : '#10b981'
                }`,
                fontSize: '13px',
                lineHeight: '1.4',
                transition: 'all 0.2s ease'
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.backgroundColor = isError ? 'rgba(239, 68, 68, 0.15)' : 
                                                        isWarning ? 'rgba(245, 158, 11, 0.15)' : 
                                                        isSuccess ? 'rgba(34, 197, 94, 0.15)' : 
                                                        'rgba(51, 65, 85, 0.4)'
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.backgroundColor = isError ? 'rgba(239, 68, 68, 0.1)' : 
                                                        isWarning ? 'rgba(245, 158, 11, 0.1)' : 
                                                        isSuccess ? 'rgba(34, 197, 94, 0.1)' : 
                                                        'rgba(51, 65, 85, 0.3)'
              }}
            >
              <span style={{
                color: isError ? '#fca5a5' : 
                       isWarning ? '#fbbf24' : 
                       isSuccess ? '#86efac' : 
                       log.source === 'build' ? '#93c5fd' : '#6ee7b7'
              }}>
                {formatLogMessage(log)}
              </span>
            </div>
          )
        })}
        
        {logs.length > 0 && (
          <div style={{
            marginTop: '20px',
            padding: '12px',
            textAlign: 'center',
            fontSize: '12px',
            color: '#94a3b8',
            backgroundColor: 'rgba(51, 65, 85, 0.2)',
            borderRadius: '6px',
            border: '1px solid rgba(51, 65, 85, 0.3)'
          }}>
            <span style={{ fontWeight: '500' }}>{logs.length} log entries</span>
            <span style={{ marginLeft: '12px', opacity: '0.7' }}>• Last updated: {new Date().toLocaleTimeString()}</span>
          </div>
        )}
      </div>
      
      {/* 하단 정보 - 개선된 스타일 */}
      <div style={{
        padding: '12px 20px',
        fontSize: '12px',
        color: '#64748b',
        backgroundColor: '#f1f5f9',
        borderTop: '1px solid #e2e8f0',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderRadius: '0 0 8px 8px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span><strong>Deployment ID:</strong> {deploymentId}</span>
          <span><strong>Log Type:</strong> {logType}</span>
        </div>
        <div style={{ fontSize: '11px', opacity: '0.7' }}>
          Updated: {new Date().toLocaleString()}
        </div>
      </div>
    </div>
    </>
  )
}