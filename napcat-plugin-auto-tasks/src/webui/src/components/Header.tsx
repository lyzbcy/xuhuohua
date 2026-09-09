import type { PluginStatus } from '../types'
import type { PageId } from '../App'

interface HeaderProps {
    title: string
    description: string
    isScrolled: boolean
    status: PluginStatus | null
    currentPage: PageId
}

export default function Header({ title, description, isScrolled }: HeaderProps) {
    return (
        <header className={`sticky top-0 z-20 transition-all duration-300 ${isScrolled ? 'bg-white/80 dark:bg-[#1F2024]/80 backdrop-blur-lg shadow-sm' : 'bg-transparent'}`}>
            <div className="px-4 md:px-8 py-6">
                <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">{title}</h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{description}</p>
            </div>
        </header>
    )
}
