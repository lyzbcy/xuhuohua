/**
 * 全局状态管理模块（单例模式）
 *
 * 封装插件的配置持久化和运行时状态，提供在项目任意位置访问
 * ctx、config、logger 等对象的能力，无需逐层传递参数。
 *
 * 使用方法：
 *   import { pluginState } from '../core/state';
 *   pluginState.config.enabled;       // 读取配置
 *   pluginState.ctx.logger.info(...); // 使用日志
 */

import fs from 'fs';
import path from 'path';
import type { NapCatPluginContext, PluginLogger } from 'napcat-types/napcat-onebot/network/plugin/types';
import { DEFAULT_CONFIG } from '../types';
import type { PluginConfig, TaskConfig, GroupConfig } from '../types';

// ==================== 配置清洗工具 ====================

function isObject(v: unknown): v is Record<string, unknown> {
    return v !== null && typeof v === 'object' && !Array.isArray(v);
}

/**
 * 配置清洗函数
 * 确保从文件读取的配置符合预期类型，防止运行时错误
 */
function sanitizeConfig(raw: unknown): PluginConfig {
    if (!isObject(raw)) return { ...DEFAULT_CONFIG, tasks: [], groupConfigs: {} };

    const out: PluginConfig = { ...DEFAULT_CONFIG, tasks: [], groupConfigs: {} };

    // 基础配置
    if (typeof raw.enabled === 'boolean') out.enabled = raw.enabled;
    if (typeof raw.debug === 'boolean') out.debug = raw.debug;

    // 内置任务 - 群打卡
    if (typeof raw.groupSign_enable === 'boolean') out.groupSign_enable = raw.groupSign_enable;
    if (typeof raw.groupSign_time === 'string') out.groupSign_time = raw.groupSign_time;
    if (typeof raw.groupSign_targets === 'string') out.groupSign_targets = raw.groupSign_targets;

    // 内置任务 - 群续火花
    if (typeof raw.groupSpark_enable === 'boolean') out.groupSpark_enable = raw.groupSpark_enable;
    if (typeof raw.groupSpark_time === 'string') out.groupSpark_time = raw.groupSpark_time;
    if (typeof raw.groupSpark_message === 'string') out.groupSpark_message = raw.groupSpark_message;
    if (typeof raw.groupSpark_targets === 'string') out.groupSpark_targets = raw.groupSpark_targets;

    // 内置任务 - 好友续火花
    if (typeof raw.friendSpark_enable === 'boolean') out.friendSpark_enable = raw.friendSpark_enable;
    if (typeof raw.friendSpark_time === 'string') out.friendSpark_time = raw.friendSpark_time;
    if (typeof raw.friendSpark_message === 'string') out.friendSpark_message = raw.friendSpark_message;
    if (typeof raw.friendSpark_targets === 'string') out.friendSpark_targets = raw.friendSpark_targets;

    // 自定义任务
    if (Array.isArray(raw.tasks)) {
        out.tasks = (raw.tasks as unknown[]).filter(isObject).map(sanitizeTask);
    }

    // 兼容旧式 customTask_N_xxx 格式迁移
    if (out.tasks.length === 0) {
        const migratedTasks = migrateOldTasks(raw);
        if (migratedTasks.length > 0) out.tasks = migratedTasks;
    }

    // 群配置清洗
    if (isObject(raw.groupConfigs)) {
        for (const [groupId, groupConfig] of Object.entries(raw.groupConfigs)) {
            if (isObject(groupConfig)) {
                const cfg: GroupConfig = {};
                if (typeof groupConfig.enabled === 'boolean') cfg.enabled = groupConfig.enabled;
                out.groupConfigs[groupId] = cfg;
            }
        }
    }

    return out;
}

/** 清洗单个任务配置 */
function sanitizeTask(raw: Record<string, unknown>): TaskConfig {
    return {
        enable: typeof raw.enable === 'boolean' ? raw.enable : false,
        type: (['group', 'private', 'group_notice'].includes(raw.type as string) ? raw.type : 'group') as TaskConfig['type'],
        target: typeof raw.target === 'string' ? raw.target : '',
        time: typeof raw.time === 'string' ? raw.time : '',
        interval: typeof raw.interval === 'number' ? raw.interval : 0,
        message: typeof raw.message === 'string' ? raw.message : '',
        image: typeof raw.image === 'string' ? raw.image : undefined,
        is_pinned: typeof raw.is_pinned === 'boolean' ? raw.is_pinned : undefined,
        is_confirm: typeof raw.is_confirm === 'boolean' ? raw.is_confirm : undefined,
    };
}

/** 兼容旧版 customTask_N_xxx 格式迁移 */
function migrateOldTasks(raw: Record<string, unknown>): TaskConfig[] {
    const tasks: TaskConfig[] = [];
    const count = typeof raw.taskCount === 'number' ? raw.taskCount :
        (typeof raw.taskCount === 'string' ? parseInt(raw.taskCount, 10) || 0 : 0);

    for (let i = 1; i <= count; i++) {
        const enable = raw[`customTask_${i}_enable`];
        const target = raw[`customTask_${i}_target`];
        if (enable || target) {
            tasks.push({
                enable: Boolean(enable),
                type: (['group', 'private', 'group_notice'].includes(raw[`customTask_${i}_type`] as string) ? raw[`customTask_${i}_type`] : 'group') as TaskConfig['type'],
                target: String(target || ''),
                time: String(raw[`customTask_${i}_time`] || ''),
                interval: parseInt(String(raw[`customTask_${i}_interval`] || '0'), 10) || 0,
                message: String(raw[`customTask_${i}_message`] || ''),
                image: raw[`customTask_${i}_image`] ? String(raw[`customTask_${i}_image`]) : undefined,
                is_pinned: raw[`customTask_${i}_is_pinned`] ? Boolean(raw[`customTask_${i}_is_pinned`]) : undefined,
                is_confirm: raw[`customTask_${i}_is_confirm`] ? Boolean(raw[`customTask_${i}_is_confirm`]) : undefined,
            });
        }
    }
    return tasks;
}

// ==================== 插件全局状态类 ====================

class PluginState {
    /** NapCat 插件上下文（init 后可用） */
    private _ctx: NapCatPluginContext | null = null;

    /** 插件配置 */
    config: PluginConfig = { ...DEFAULT_CONFIG };

    /** 插件启动时间戳 */
    startTime: number = 0;

    /** 机器人自身 QQ 号 */
    selfId: string = '';

    /** 活跃的定时器 Map: jobId -> NodeJS.Timeout */
    timers: Map<string, ReturnType<typeof setInterval>> = new Map();

    /** 配置变更回调（用于重启任务等） */
    private _onConfigChange: (() => void) | null = null;

    /** 运行时统计 */
    stats = {
        processed: 0,
        todayProcessed: 0,
        lastUpdateDay: new Date().toDateString(),
    };

    /** 注册配置变更回调 */
    set onConfigChange(cb: (() => void) | null) {
        this._onConfigChange = cb;
    }

    /** 触发配置变更回调 */
    private emitConfigChange(): void {
        if (this._onConfigChange) {
            try {
                this._onConfigChange();
            } catch (e) {
                this.logger.error('配置变更回调执行失败:', e);
            }
        }
    }

    /** 获取上下文（确保已初始化） */
    get ctx(): NapCatPluginContext {
        if (!this._ctx) throw new Error('PluginState 尚未初始化，请先调用 init()');
        return this._ctx;
    }

    /** 获取日志器的快捷方式 */
    get logger(): PluginLogger {
        return this.ctx.logger;
    }

    // ==================== 生命周期 ====================

    /**
     * 初始化（在 plugin_init 中调用）
     */
    init(ctx: NapCatPluginContext): void {
        this._ctx = ctx;
        this.startTime = Date.now();
        this.loadConfig();
        this.ensureDataDir();
        this.fetchSelfId();
    }

    /**
     * 获取机器人自身 QQ 号
     */
    private async fetchSelfId(): Promise<void> {
        try {
            const res = await this.ctx.actions.call(
                'get_login_info', {}, this.ctx.adapterName, this.ctx.pluginManager.config
            ) as { user_id?: number | string };
            if (res?.user_id) {
                this.selfId = String(res.user_id);
                this.logger.debug('机器人 QQ: ' + this.selfId);
            }
        } catch (e) {
            this.logger.warn('获取机器人 QQ 号失败:', e);
        }
    }

    /**
     * 清理（在 plugin_cleanup 中调用）
     */
    cleanup(): void {
        // 清理所有定时器
        for (const [jobId, timer] of this.timers) {
            clearInterval(timer);
            this.logger.debug(`清理定时器: ${jobId}`);
        }
        this.timers.clear();
        this.saveConfig();
        this._ctx = null;
    }

    // ==================== 数据目录 ====================

    /** 确保数据目录存在 */
    private ensureDataDir(): void {
        const dataPath = this.ctx.dataPath;
        if (!fs.existsSync(dataPath)) {
            fs.mkdirSync(dataPath, { recursive: true });
        }
    }

    /** 获取数据文件完整路径 */
    getDataFilePath(filename: string): string {
        return path.join(this.ctx.dataPath, filename);
    }

    // ==================== 通用数据文件读写 ====================

    loadDataFile<T>(filename: string, defaultValue: T): T {
        const filePath = this.getDataFilePath(filename);
        try {
            if (fs.existsSync(filePath)) {
                return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
            }
        } catch (e) {
            this.logger.warn('读取数据文件 ' + filename + ' 失败:', e);
        }
        return defaultValue;
    }

    saveDataFile<T>(filename: string, data: T): void {
        const filePath = this.getDataFilePath(filename);
        try {
            fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
        } catch (e) {
            this.logger.error('保存数据文件 ' + filename + ' 失败:', e);
        }
    }

    // ==================== 配置管理 ====================

    loadConfig(): void {
        const configPath = this.ctx.configPath;
        try {
            if (configPath && fs.existsSync(configPath)) {
                const raw = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
                this.config = sanitizeConfig(raw);
                // 加载统计信息
                if (isObject(raw) && isObject(raw.stats)) {
                    Object.assign(this.stats, raw.stats);
                }
                this.ctx.logger.debug('已加载本地配置');
            } else {
                this.config = { ...DEFAULT_CONFIG, tasks: [], groupConfigs: {} };
                this.saveConfig();
                this.ctx.logger.debug('配置文件不存在，已创建默认配置');
            }
        } catch (error) {
            this.ctx.logger.error('加载配置失败，使用默认配置:', error);
            this.config = { ...DEFAULT_CONFIG, tasks: [], groupConfigs: {} };
        }
    }

    saveConfig(): void {
        if (!this._ctx) return;
        const configPath = this._ctx.configPath;
        try {
            const configDir = path.dirname(configPath);
            if (!fs.existsSync(configDir)) {
                fs.mkdirSync(configDir, { recursive: true });
            }
            const data = { ...this.config, stats: this.stats };
            fs.writeFileSync(configPath, JSON.stringify(data, null, 2), 'utf-8');
        } catch (error) {
            this._ctx.logger.error('保存配置失败:', error);
        }
    }

    updateConfig(partial: Partial<PluginConfig>): void {
        this.config = { ...this.config, ...partial };
        this.saveConfig();
        this.emitConfigChange();
    }

    replaceConfig(config: PluginConfig): void {
        this.config = sanitizeConfig(config);
        this.saveConfig();
        this.emitConfigChange();
    }

    updateGroupConfig(groupId: string, config: Partial<GroupConfig>): void {
        this.config.groupConfigs[groupId] = {
            ...this.config.groupConfigs[groupId],
            ...config,
        };
        this.saveConfig();
    }

    isGroupEnabled(groupId: string): boolean {
        return this.config.groupConfigs[groupId]?.enabled !== false;
    }

    // ==================== OneBot API 调用 ====================

    async callApi(action: string, params: Record<string, unknown>): Promise<unknown> {
        try {
            return await this.ctx.actions.call(
                action as 'send_msg',
                params as never,
                this.ctx.adapterName,
                this.ctx.pluginManager.config
            );
        } catch (e: unknown) {
            const errStr = String(e);
            // 忽略 "No data returned" 错误
            if (errStr.includes('No data returned') ||
                (e instanceof Error && e.message.includes('No data returned'))) {
                return;
            }
            this.logger.error(`[API] ${action} 失败:`, e);
        }
    }

    // ==================== 统计 ====================

    incrementProcessed(): void {
        const today = new Date().toDateString();
        if (this.stats.lastUpdateDay !== today) {
            this.stats.todayProcessed = 0;
            this.stats.lastUpdateDay = today;
        }
        this.stats.todayProcessed++;
        this.stats.processed++;
    }

    // ==================== 工具方法 ====================

    getUptime(): number {
        return Date.now() - this.startTime;
    }

    getUptimeFormatted(): string {
        const ms = this.getUptime();
        const s = Math.floor(ms / 1000);
        const m = Math.floor(s / 60);
        const h = Math.floor(m / 60);
        const d = Math.floor(h / 24);

        if (d > 0) return `${d}天${h % 24}小时`;
        if (h > 0) return `${h}小时${m % 60}分钟`;
        if (m > 0) return `${m}分钟${s % 60}秒`;
        return `${s}秒`;
    }
}

/** 导出全局单例 */
export const pluginState = new PluginState();
