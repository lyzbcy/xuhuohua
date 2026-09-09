/**
 * 任务管理器
 *
 * 管理所有定时任务的启动、停止和执行
 * 使用 pluginState 全局状态，无需传递参数
 */

import { pluginState } from './core/state';
import type { TaskConfig, GroupInfo, FriendInfo } from './types';

export class TaskManager {
    private lastExecutedTime: string = '';

    constructor() {
        // 无需传参，通过 pluginState 访问上下文
    }

    // --- 停止所有任务 ---
    public stop() {
        if (pluginState.timers.size > 0) {
            pluginState.logger.info(`🛑 已清理 ${pluginState.timers.size} 个活跃定时器`);
        }
        for (const [jobId, timer] of pluginState.timers) {
            clearInterval(timer);
        }
        pluginState.timers.clear();
    }

    // --- 启动任务 ---
    public start() {
        // 先清除所有旧定时器
        this.stop();

        pluginState.logger.info('🚀 正在启动自动化任务...');

        const tasks = pluginState.config.tasks.filter(t => t.enable && t.target);
        pluginState.logger.info(`已加载 ${tasks.length} 个有效自定义任务`);

        // 主心跳 (每秒检查)
        const mainTicker = setInterval(() => {
            this.tick(tasks);
        }, 1000);
        pluginState.timers.set('main-ticker', mainTicker);

        // 循环间隔任务
        tasks.forEach((task, index) => {
            // 群公告不支持循环发送
            if (task.type === 'group_notice') return;

            if (task.interval > 0) {
                const ms = Math.max(task.interval * 1000, 5000);
                pluginState.logger.info(`[任务${index + 1}] ⏳ 循环启动: 目标 ${task.target}, 间隔 ${task.interval}s`);

                const timer = setInterval(() => {
                    try {
                        this.executeTask(task, index + 1).catch(e => {
                            pluginState.logger.error(`[任务${index + 1}] 循环执行异常:`, e);
                        });
                    } catch (e) {
                        pluginState.logger.error(`[任务${index + 1}] 循环触发异常:`, e);
                    }
                }, ms);

                pluginState.timers.set(`interval-task-${index}`, timer);
            }
        });
    }

    private async tick(tasks: TaskConfig[]) {
        const now = new Date();
        const timeStr = now.toTimeString().split(' ')[0];

        if (timeStr === this.lastExecutedTime) return;
        this.lastExecutedTime = timeStr;

        const config = pluginState.config;

        // 懒加载群/好友列表
        let allGroups: number[] | null = null;
        let allFriends: number[] | null = null;

        const getAllGroups = async (): Promise<number[]> => {
            if (allGroups !== null) return allGroups;
            try {
                const result = await pluginState.callApi('get_group_list', {}) as GroupInfo[] | undefined;
                allGroups = (result || []).map(g => g.group_id);
            } catch {
                allGroups = [];
            }
            return allGroups;
        };

        const getEnabledGroups = async (): Promise<number[]> => {
            try {
                const result = await pluginState.callApi('get_group_list', {}) as GroupInfo[] | undefined;
                return (result || [])
                    .filter(g => pluginState.isGroupEnabled(String(g.group_id)))
                    .map(g => g.group_id);
            } catch {
                return [];
            }
        };

        const getAllFriends = async (): Promise<number[]> => {
            if (allFriends !== null) return allFriends;
            try {
                const result = await pluginState.callApi('get_friend_list', {}) as FriendInfo[] | undefined;
                allFriends = (result || []).map(f => f.user_id);
            } catch {
                allFriends = [];
            }
            return allFriends;
        };

        // 内置任务 - 群打卡
        if (config.groupSign_enable && timeStr === config.groupSign_time) {
            const targets = config.groupSign_targets.toLowerCase() === 'all'
                ? (await getAllGroups()).join(',')
                : config.groupSign_targets.toLowerCase() === 'allallow'
                ? (await getEnabledGroups()).join(',')
                : config.groupSign_targets;
            this.executeBatch('群打卡', targets, async (id) => {
                await pluginState.callApi('send_group_sign', { group_id: id });
            });
        }

        // 内置任务 - 群续火花
        if (config.groupSpark_enable && timeStr === config.groupSpark_time) {
            const targets = config.groupSpark_targets.toLowerCase() === 'all'
                ? (await getAllGroups()).join(',')
                : config.groupSpark_targets.toLowerCase() === 'allallow'
                ? (await getEnabledGroups()).join(',')
                : config.groupSpark_targets;
            this.executeBatch('群火花', targets, async (id) => {
                await pluginState.callApi('send_msg', {
                    message_type: 'group', group_id: id, message: config.groupSpark_message,
                });
            });
        }

        // 内置任务 - 好友续火花
        if (config.friendSpark_enable && timeStr === config.friendSpark_time) {
            const targets = config.friendSpark_targets.toLowerCase() === 'all'
                ? (await getAllFriends()).join(',')
                : config.friendSpark_targets;
            this.executeBatch('好友火花', targets, async (id) => {
                await pluginState.callApi('send_msg', {
                    message_type: 'private', user_id: id, message: config.friendSpark_message,
                });
            });
        }

        // 自定义任务 (每日定时)
        for (let i = 0; i < tasks.length; i++) {
            const task = tasks[i];
            const isScheduleMode = task.interval <= 0 || task.type === 'group_notice';

            if (isScheduleMode && task.time === timeStr) {
                try {
                    this.executeTask(task, i + 1).catch(e => {
                        pluginState.logger.error(`[任务${i + 1}] 定时执行异步异常:`, e);
                    });
                } catch (e) {
                    pluginState.logger.error(`[任务${i + 1}] 定时触发异常:`, e);
                }
            }
        }
    }

    private async executeTask(task: TaskConfig, index: number) {
        try {
            pluginState.logger.info(`[任务${index}] ▶️ 触发: ${task.target} (${task.type})`);
            await new Promise(r => setTimeout(r, Math.random() * 3000));

            if (task.type === 'group_notice') {
                await pluginState.callApi('_send_group_notice', {
                    group_id: task.target,
                    content: task.message,
                    image: task.image || undefined,
                    pinned: task.is_pinned ? 1 : 0,
                    type: 1,
                    confirm_required: task.is_confirm ? 1 : 0,
                    is_show_edit_card: 0,
                    tip_window_type: 0,
                });
            } else {
                const payload: Record<string, unknown> = {
                    message_type: task.type,
                    message: task.message,
                };
                if (task.type === 'group') payload.group_id = task.target;
                else payload.user_id = task.target;
                await pluginState.callApi('send_msg', payload);
            }

            pluginState.incrementProcessed();
        } catch (e) {
            pluginState.logger.error(`[任务${index}] 执行失败:`, e);
        }
    }

    private async executeBatch(name: string, targetsStr: string, action: (id: string) => Promise<void>) {
        const targets = targetsStr.split(/[,，]/).map(t => t.trim()).filter(t => t);
        if (targets.length === 0) return;
        pluginState.logger.info(`[内置任务] ${name} 触发`);
        for (const id of targets) {
            await new Promise(r => setTimeout(r, 2000 + Math.random() * 3000));
            try {
                await action(id);
                pluginState.incrementProcessed();
            } catch (e) {
                pluginState.logger.error(`[${name}] 失败`, e);
            }
        }
    }
}
