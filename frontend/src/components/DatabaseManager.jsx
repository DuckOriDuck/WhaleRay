import { useState, useEffect, forwardRef, useImperativeHandle } from 'react'
import { getDatabase, createDatabase, deleteDatabase, resetDatabasePassword } from '../lib/api'

const DatabaseManager = forwardRef((props, ref) => {
    const [dbInfo, setDbInfo] = useState(null)
    const [loading, setLoading] = useState(true)
    const [creating, setCreating] = useState(false)
    const [deleting, setDeleting] = useState(false)
    const [error, setError] = useState(null)

    useEffect(() => {
        loadDatabase()
    }, [])

    // Expose loadDatabase to parent via ref
    useImperativeHandle(ref, () => loadDatabase)

    async function loadDatabase() {
        try {
            setLoading(true)
            const data = await getDatabase()
            setDbInfo(data)
            setError(null)
        } catch (err) {
            console.error(err)
            setError('데이터베이스 정보를 불러오는데 실패했습니다.')
        } finally {
            setLoading(false)
        }
    }

    async function handleCreate() {
        try {
            setCreating(true)
            setError(null)
            await createDatabase()
            // 생성 시작 후 잠시 대기 후 새로고침
            setTimeout(loadDatabase, 2000)
        } catch (err) {
            console.error(err)
            setError(err.message || '데이터베이스 생성에 실패했습니다.')
        } finally {
            setCreating(false)
        }
    }

    async function handleDelete() {
        if (!confirm('정말로 데이터베이스를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) return

        try {
            setDeleting(true)
            setError(null)
            await deleteDatabase()
            setDbInfo(null)
        } catch (err) {
            console.error(err)
            setError(err.message || '데이터베이스 삭제에 실패했습니다.')
        } finally {
            setDeleting(false)
        }
    }

    async function handleResetPassword() {
        if (!confirm('비밀번호를 재설정하시겠습니까?')) return
        try {
            await resetDatabasePassword()
            alert('비밀번호 재설정 요청이 전송되었습니다.')
        } catch (err) {
            setError(err.message)
        }
    }

    if (loading) {
        return <div className="p-4 text-center">로딩 중...</div>
    }

    if (!dbInfo) {
        return (
            <div style={{
                background: 'white',
                borderRadius: '8px',
                padding: '32px',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                textAlign: 'center'
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <h2 style={{ fontSize: '24px', margin: 0, color: '#333', flex: 1, textAlign: 'center' }}>데이터베이스가 없습니다</h2>
                    <button
                        onClick={loadDatabase}
                        disabled={loading}
                        style={{
                            background: 'none',
                            border: '1px solid #ddd',
                            padding: '4px 8px',
                            borderRadius: '4px',
                            cursor: loading ? 'not-allowed' : 'pointer',
                            opacity: loading ? 0.5 : 1
                        }}
                    >
                        {loading ? '...' : '새로고침'}
                    </button>
                </div>
                <p style={{ color: '#666', marginBottom: '24px' }}>
                    PostgreSQL 데이터베이스를 생성하여 프로젝트에 연결하세요.
                </p>
                {error && <div style={{ color: 'red', marginBottom: '16px' }}>{error}</div>}
                <button
                    onClick={handleCreate}
                    disabled={creating}
                    style={{
                        padding: '12px 24px',
                        background: '#10B981',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        fontSize: '16px',
                        cursor: creating ? 'not-allowed' : 'pointer',
                        opacity: creating ? 0.7 : 1
                    }}
                >
                    {creating ? '생성 중...' : '데이터베이스 생성'}
                </button>
            </div>
        )
    }

    const isRunning = dbInfo.dbState === 'RUNNING'
    const isProvisioning = dbInfo.dbState === 'PROVISIONING' || dbInfo.dbState === 'CREATING'

    return (
        <div style={{
            background: 'white',
            borderRadius: '8px',
            padding: '24px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#333', margin: 0 }}>내 데이터베이스</h2>
                <button
                    onClick={loadDatabase}
                    style={{ background: 'none', border: '1px solid #ddd', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer' }}
                >
                    새로고침
                </button>
            </div>

            {error && <div style={{ color: 'red', marginBottom: '16px', padding: '8px', background: '#ffebee', borderRadius: '4px' }}>{error}</div>}

            <div style={{ display: 'grid', gap: '16px' }}>
                <div style={{ padding: '16px', background: '#f8f9fa', borderRadius: '6px' }}>
                    <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>상태</div>
                    <div style={{
                        fontSize: '16px',
                        fontWeight: '600',
                        color: isRunning ? '#34a853' : (isProvisioning ? '#fbbc05' : '#ea4335'),
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                    }}>
                        <span style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            background: isRunning ? '#34a853' : (isProvisioning ? '#fbbc05' : '#ea4335')
                        }}></span>
                        {dbInfo.dbState}
                    </div>
                </div>

                <div style={{ padding: '16px', background: '#f8f9fa', borderRadius: '6px' }}>
                    <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>내부 엔드포인트 (VPC 내)</div>
                    <div style={{ fontSize: '14px', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                        {dbInfo.dbInternalEndpoint}:5432
                    </div>
                </div>

                <div style={{ padding: '16px', background: '#f8f9fa', borderRadius: '6px' }}>
                    <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>외부 접속 (pgAdmin)</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <a
                            href={`https://${dbInfo.dbExternalEndpoint}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: '#10B981', textDecoration: 'none', fontSize: '14px' }}
                        >
                            https://{dbInfo.dbExternalEndpoint}
                        </a>
                        <span style={{ fontSize: '12px', color: '#999' }}>(로그인 필요)</span>
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                    <div style={{ padding: '16px', background: '#f8f9fa', borderRadius: '6px' }}>
                        <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>사용자명</div>
                        <div style={{ fontSize: '14px', fontFamily: 'monospace' }}>{dbInfo.username}</div>
                    </div>

                    <div style={{ padding: '16px', background: '#f8f9fa', borderRadius: '6px' }}>
                        <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>비밀번호</div>
                        <div style={{ fontSize: '14px', color: '#666', fontStyle: 'italic' }}>
                            (생성 시 1회만 표시됨, 분실 시 재설정 필요)
                        </div>
                    </div>
                </div>

                <div style={{ marginTop: '24px', borderTop: '1px solid #eee', paddingTop: '24px' }}>
                    <h3 style={{ fontSize: '16px', marginBottom: '16px', color: '#d93025' }}>위험 구역</h3>
                    <div style={{ display: 'flex', gap: '12px' }}>
                        <button
                            onClick={handleResetPassword}
                            style={{
                                padding: '8px 16px',
                                background: 'white',
                                color: '#d93025',
                                border: '1px solid #d93025',
                                borderRadius: '4px',
                                cursor: 'pointer'
                            }}
                        >
                            비밀번호 재설정
                        </button>
                        <button
                            onClick={handleDelete}
                            disabled={deleting}
                            style={{
                                padding: '8px 16px',
                                background: '#d93025',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: deleting ? 'not-allowed' : 'pointer',
                                opacity: deleting ? 0.7 : 1
                            }}
                        >
                            {deleting ? '삭제 중...' : '데이터베이스 삭제'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
})

DatabaseManager.displayName = 'DatabaseManager'

export default DatabaseManager
