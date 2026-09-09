import { useState, useEffect, useCallback } from 'react'
import { noAuthFetch } from '../utils/api'
import { showToast } from '../hooks/useToast'
import type { GroupInfo } from '../types'

export default function GroupsPage() {
    const [groups, setGroups] = useState<GroupInfo[]>([])
    const [search, setSearch] = useState('')
    const [loading, setLoading] = useState(true)

    const fetchGroups = useCallback(async () => {
        try {
            const res = await noAuthFetch<GroupInfo[]>('/groups')
            if (res.code === 0 && res.data) {
                setGroups(res.data)
            }
        } catch (e) {
            showToast('获取群列表失败', 'error')
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => { fetchGroups() }, [fetchGroups])

    const toggleGroup = async (groupId: number, enabled: boolean) => {
        try {
            await noAuthFetch(`/groups/${groupId}/config`, {
                method: 'POST',
                body: JSON.stringify({ enabled }),
            })
            setGroups(groups.map(g => g.group_id === groupId ? { ...g, enabled } : g))
            showToast(`群 ${groupId} 已${enabled ? '启用' : '禁用'}`, 'success')
        } catch (e) {
            showToast('操作失败', 'error')
        }
    }

    const toggleAll = async (enabled: boolean) => {
        try {
            const groupIds = filtered.map(g => g.group_id)
            await noAuthFetch('/groups/bulk-config', {
                method: 'POST',
                body: JSON.stringify({ enabled, groupIds }),
            })
            setGroups(groups.map(g => groupIds.includes(g.group_id) ? { ...g, enabled } : g))
            showToast(`已${enabled ? '全部启用' : '全部禁用'}`, 'success')
        } catch (e) {
            showToast('批量操作失败', 'error')
        }
    }

    const filtered = groups.filter(g =>
        !search || String(g.group_id).includes(search) || g.group_name?.includes(search)
    )

    if (loading) {
        return <div className="flex items-center justify-center h-64 text-gray-400">加载中...</div>
    }

    return (
        <div className="space-y-4 animate-fade-in-up">
            {/* 工具栏 */}
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
                <div className="text-sm text-gray-500 dark:text-gray-400">
                    共 {groups.length} 个群，{groups.filter(g => g.enabled).length} 个已启用
                    {search && `，搜索到 ${filtered.length} 个`}
                </div>
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="搜索群号或名称..."
                        className="px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#1A1B1E] text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-500/40 w-48"
                    />
                    <button onClick={() => toggleAll(true)} className="px-3 py-2 text-xs rounded-lg bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 transition-colors">
                        全部启用
                    </button>
                    <button onClick={() => toggleAll(false)} className="px-3 py-2 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 transition-colors">
                        全部禁用
                    </button>
                </div>
            </div>

            {/* 群列表 */}
            <div className="bg-white dark:bg-[#25262B] rounded-xl shadow-sm border border-gray-100 dark:border-gray-800 overflow-hidden">
                {filtered.length === 0 ? (
                    <div className="text-center py-12 text-gray-400">{search ? '没有匹配的群' : '暂无群数据'}</div>
                ) : (
                    <div className="divide-y divide-gray-100 dark:divide-gray-800">
                        {filtered.map((group) => (
                            <div key={group.group_id} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                                <div className="flex items-center gap-4">
                                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white text-sm font-bold">
                                        {(group.group_name || '群')[0]}
                                    </div>
                                    <div>
                                        <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                            {group.group_name || `群 ${group.group_id}`}
                                        </div>
                                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                            {group.group_id} · {group.member_count}/{group.max_member_count} 人
                                        </div>
                                    </div>
                                </div>
                                <button
                                    onClick={() => toggleGroup(group.group_id, !group.enabled)}
                                    className={`relative rounded-full transition-colors duration-200 ${group.enabled ? 'bg-brand-500' : 'bg-gray-300 dark:bg-gray-600'}`}
                                    style={{ width: 40, height: 22 }}
                                >
                                    <div className={`absolute top-0.5 w-[18px] h-[18px] rounded-full bg-white shadow transition-transform duration-200 ${group.enabled ? 'translate-x-[20px]' : 'translate-x-0.5'}`} />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
