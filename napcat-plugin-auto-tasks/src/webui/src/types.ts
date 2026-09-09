/** WebUI 前端类型定义 */

export interface PluginStatus {
    pluginName: string
    uptime: number
    uptimeFormatted: string
    config: PluginConfig
    stats: {
        processed: number
        todayProcessed: number
        lastUpdateDay: string
    }
}

export interface PluginConfig {
    enabled: boolean
    debug: boolean
    groupSign_enable: boolean
    groupSign_time: string
    groupSign_targets: string
    groupSpark_enable: boolean
    groupSpark_time: string
    groupSpark_message: string
    groupSpark_targets: string
    friendSpark_enable: boolean
    friendSpark_time: string
    friendSpark_message: string
    friendSpark_targets: string
    tasks: TaskConfig[]
    groupConfigs?: Record<string, GroupConfig>
}

export interface TaskConfig {
    enable: boolean
    type: 'group' | 'private' | 'group_notice'
    target: string
    time: string
    interval: number
    message: string
    image?: string
    is_pinned?: boolean
    is_confirm?: boolean
}

export interface BuiltinTasks {
    groupSign: {
        enable: boolean
        time: string
        targets: string
    }
    groupSpark: {
        enable: boolean
        time: string
        message: string
        targets: string
    }
    friendSpark: {
        enable: boolean
        time: string
        message: string
        targets: string
    }
}

export interface GroupConfig {
    enabled?: boolean
}

export interface GroupInfo {
    group_id: number
    group_name: string
    member_count: number
    max_member_count: number
    enabled: boolean
}

export interface ApiResponse<T = unknown> {
    code: number
    data?: T
    message?: string
}
