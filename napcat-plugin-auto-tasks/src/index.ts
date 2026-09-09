/**
 * NapCat 插件 - 自动定时任务 Pro
 *
 * 导出 PluginModule 接口定义的生命周期函数
 */

import type {
    PluginModule,
    PluginConfigSchema,
    NapCatPluginContext,
} from 'napcat-types/napcat-onebot/network/plugin/types';
import { EventType } from 'napcat-types/napcat-onebot/event/index';

import { buildConfigSchema } from './config';
import { pluginState } from './core/state';
import { handleMessage } from './handlers/message-handler';
import { registerApiRoutes } from './services/api-service';
import { TaskManager } from './taskManager';
import type { PluginConfig } from './types';

// ==================== 全局实例 ====================

let taskManager: TaskManager | null = null;

// ==================== 配置 UI Schema ====================

export let plugin_config_ui: PluginConfigSchema = [];

// ==================== 生命周期函数 ====================

/**
 * 插件初始化
 */
export const plugin_init: PluginModule['plugin_init'] = async (ctx) => {
    try {
        // 1. 初始化全局状态（加载配置）
        pluginState.init(ctx);

        ctx.logger.info('🛠️ 插件初始化中...');

        // 2. 生成配置 Schema
        plugin_config_ui = buildConfigSchema(ctx);

        // 3. 注册 WebUI 页面和静态资源
        registerWebUI(ctx);

        // 4. 注册 API 路由
        registerApiRoutes(ctx);

        // 5. 启动任务管理器
        taskManager = new TaskManager();
        taskManager.start();

        // 6. 注册配置变更回调 — WebUI 保存后自动重启任务
        pluginState.onConfigChange = () => {
            ctx.logger.info('⚙️ 配置已变更，重启任务管理器...');
            if (taskManager) {
                taskManager.start();
            }
        };

        ctx.logger.info('✅ 插件初始化完成');
    } catch (error) {
        ctx.logger.error('插件初始化失败:', error);
    }
};

/**
 * 消息/事件处理
 */
export const plugin_onmessage: PluginModule['plugin_onmessage'] = async (ctx, event) => {
    if (event.post_type !== EventType.MESSAGE) return;
    if (!pluginState.config.enabled) return;
    await handleMessage(ctx, event);
};

/**
 * 事件处理
 */
export const plugin_onevent: PluginModule['plugin_onevent'] = async (_ctx, _event) => {
    // 预留：处理通知、请求等非消息事件
};

/**
 * 插件卸载/重载
 */
export const plugin_cleanup: PluginModule['plugin_cleanup'] = async (ctx) => {
    try {
        if (taskManager) {
            taskManager.stop();
            taskManager = null;
        }
        pluginState.cleanup();
        ctx.logger.info('🛑 插件已卸载');
    } catch (e) {
        ctx.logger.warn('插件卸载时出错:', e);
    }
};

// ==================== 配置管理钩子 ====================

export const plugin_get_config: PluginModule['plugin_get_config'] = async (_ctx) => {
    return pluginState.config;
};

export const plugin_set_config: PluginModule['plugin_set_config'] = async (ctx, config) => {
    pluginState.replaceConfig(config as PluginConfig);
    ctx.logger.info('配置已通过 WebUI 更新');

    // 重启任务管理器
    if (taskManager) {
        taskManager.start();
    }
};

export const plugin_on_config_change: PluginModule['plugin_on_config_change'] = async (
    ctx, _ui, key, value, _currentConfig
) => {
    try {
        pluginState.updateConfig({ [key]: value });
        ctx.logger.info(`⚙️ 配置项 ${key} 已更新`);

        // 重启任务
        if (taskManager) {
            taskManager.start();
        }
    } catch (err) {
        ctx.logger.error(`更新配置项 ${key} 失败:`, err);
    }
};

// ==================== 内部函数 ====================

/**
 * 注册 WebUI 页面和静态资源
 */
function registerWebUI(ctx: NapCatPluginContext): void {
    const router = ctx.router;

    // 托管前端静态资源
    router.static('/static', 'webui');

    // 注册仪表盘页面
    router.page({
        path: 'dashboard',
        title: '任务管理',
        htmlFile: 'webui/index.html',
        description: '自动定时任务管理控制台',
    });

    ctx.logger.debug('WebUI 路由注册完成');
}