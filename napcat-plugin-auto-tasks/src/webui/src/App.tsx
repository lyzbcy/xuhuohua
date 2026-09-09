import { useState, useEffect, useCallback } from 'react'
import { useTheme } from './hooks/useTheme'
import { useStatus } from './hooks/useStatus'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import ToastContainer from './components/ToastContainer'
import StatusPage from './pages/StatusPage'
import TasksPage from './pages/TasksPage'
import GroupsPage from './pages/GroupsPage'

export type PageId = 'status' | 'tasks' | 'groups'

interface PageMeta {
    title: string
    description: string
}

const pageMeta: Record<PageId, PageMeta> = {
    status: { title: '仪表盘', description: '查看插件运行状态和任务执行统计' },
    tasks: { title: '任务管理', description: '配置内置任务和自定义定时任务' },
    groups: { title: '群管理', description: '管理各群的插件功能启用状态' },
}

export default function App() {
    useTheme()

    const [currentPage, setCurrentPage] = useState<PageId>('status')
    const [isScrolled, setIsScrolled] = useState(false)
    const { status, fetchStatus } = useStatus()

    useEffect(() => {
        fetchStatus()
        const interval = setInterval(fetchStatus, 10000)
        return () => clearInterval(interval)
    }, [fetchStatus])

    const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
        setIsScrolled(e.currentTarget.scrollTop > 0)
    }, [])

    const meta = pageMeta[currentPage]

    return (
        <div className="flex h-screen bg-gray-50 dark:bg-[#18191C] text-gray-900 dark:text-gray-100">
            <Sidebar currentPage={currentPage} onPageChange={setCurrentPage} />
            <main className="flex-1 flex flex-col overflow-hidden">
                <Header
                    title={meta.title}
                    description={meta.description}
                    isScrolled={isScrolled}
                    status={status}
                    currentPage={currentPage}
                />
                <div className="flex-1 overflow-y-auto px-4 md:px-8 pb-8" onScroll={handleScroll}>
                    {currentPage === 'status' && <StatusPage status={status} onRefresh={fetchStatus} />}
                    {currentPage === 'tasks' && <TasksPage />}
                    {currentPage === 'groups' && <GroupsPage />}
                </div>
            </main>
            <ToastContainer />
        </div>
    )
}
