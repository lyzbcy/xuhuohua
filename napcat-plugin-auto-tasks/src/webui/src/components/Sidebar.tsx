import type { PageId } from '../App'
import { IconDashboard, IconTask, IconGroup } from './icons'

interface SidebarProps {
    currentPage: PageId
    onPageChange: (page: PageId) => void
}

const navItems: { id: PageId; label: string; icon: React.ReactNode }[] = [
    { id: 'status', label: '仪表盘', icon: <IconDashboard size={18} /> },
    { id: 'tasks', label: '任务管理', icon: <IconTask size={18} /> },
    { id: 'groups', label: '群管理', icon: <IconGroup size={18} /> },
]

export default function Sidebar({ currentPage, onPageChange }: SidebarProps) {
    return (
        <aside className="w-56 shrink-0 bg-white dark:bg-[#1F2024] border-r border-gray-100 dark:border-gray-800 flex flex-col">
            {/* Logo */}
            <div className="h-16 flex items-center px-5 border-b border-gray-100 dark:border-gray-800">
                <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white text-sm font-bold shadow-md">
                        ⏰
                    </div>
                    <div>
                        <div className="text-sm font-semibold text-gray-800 dark:text-gray-100 leading-tight">Auto Tasks</div>
                        <div className="text-[10px] text-gray-400 tracking-wider">NAPCAT PLUGIN</div>
                    </div>
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex-1 py-4 px-3 space-y-1">
                {navItems.map(item => (
                    <button
                        key={item.id}
                        onClick={() => onPageChange(item.id)}
                        className={`
                            w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
                            ${currentPage === item.id
                                ? 'bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400 shadow-sm'
                                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-300'
                            }
                        `}
                    >
                        {item.icon}
                        {item.label}
                    </button>
                ))}
            </nav>

            {/* Footer */}
            <div className="p-4 border-t border-gray-100 dark:border-gray-800">
                <div className="text-xs text-gray-400 text-center">v2.0.0</div>
            </div>
        </aside>
    )
}
