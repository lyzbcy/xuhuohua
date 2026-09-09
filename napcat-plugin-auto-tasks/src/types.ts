/**
 * 类型定义文件
 * 定义插件内部使用的接口和类型
 */

// ==================== 插件配置 ====================

/**
 * 插件主配置接口
 */
export interface PluginConfig {
    /** 全局开关：是否启用插件功能 */
    enabled: boolean;
    /** 调试模式：启用后输出详细日志 */
    debug: boolean;

    // --- 内置任务 ---
    /** 群自动打卡 */
    groupSign_enable: boolean;
    groupSign_time: string;
    groupSign_targets: string;

    /** 群自动续火花 */
    groupSpark_enable: boolean;
    groupSpark_time: string;
    groupSpark_message: string;
    groupSpark_targets: string;

    /** 好友自动续火花 */
    friendSpark_enable: boolean;
    friendSpark_time: string;
    friendSpark_message: string;
    friendSpark_targets: string;

    // --- 自定义任务 ---
    /** 自定义任务列表 */
    tasks: TaskConfig[];

    /** 按群的单独配置 */
    groupConfigs: Record<string, GroupConfig>;
}

/**
 * 自定义任务配置
 */
export interface TaskConfig {
    /** 是否启用 */
    enable: boolean;
    /** 任务类型 */
    type: 'group' | 'private' | 'group_notice';
    /** 目标号码（群号或QQ号） */
    target: string;
    /** 每日执行时间 (HH:mm:ss) */
    time: string;
    /** 循环间隔（秒），0 表示仅定时 */
    interval: number;
    /** 消息内容（支持CQ码，群公告为公告内容） */
    message: string;
    /** 群公告图片URL（群公告专用） */
    image?: string;
    /** 是否置顶（群公告专用） */
    is_pinned?: boolean;
    /** 是否需确认（群公告专用） */
    is_confirm?: boolean;
}

/**
 * 群配置
 */
export interface GroupConfig {
    /** 是否启用此群的功能 */
    enabled?: boolean;
}

// ==================== API 响应 ====================

/**
 * 统一 API 响应格式
 */
export interface ApiResponse<T = unknown> {
    /** 状态码，0 表示成功，-1 表示失败 */
    code: number;
    /** 错误信息（仅错误时返回） */
    message?: string;
    /** 响应数据（仅成功时返回） */
    data?: T;
}

// ==================== 辅助类型 ====================

export interface GroupInfo {
    group_id: number;
    group_name?: string;
    member_count?: number;
    max_member_count?: number;
}

export interface FriendInfo {
    user_id: number;
    nickname?: string;
}

// ==================== 默认配置 ====================

export const DEFAULT_CONFIG: PluginConfig = {
    enabled: true,
    debug: false,

    // 群打卡
    groupSign_enable: false,
    groupSign_time: '08:00:00',
    groupSign_targets: '',

    // 群续火花
    groupSpark_enable: false,
    groupSpark_time: '09:00:00',
    groupSpark_message: '自动续火花',
    groupSpark_targets: '',

    // 好友续火花
    friendSpark_enable: false,
    friendSpark_time: '10:00:00',
    friendSpark_message: '✨',
    friendSpark_targets: '',

    // 自定义任务
    tasks: [],

    // 群配置
    groupConfigs: {},
};
