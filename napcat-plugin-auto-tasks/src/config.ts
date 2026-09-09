/**
 * 配置定义和 WebUI Schema
 */

import type { PluginConfigSchema } from 'napcat-types/napcat-onebot/network/plugin/types';
import type { NapCatPluginContext } from 'napcat-types/napcat-onebot/network/plugin/types';
import { DEFAULT_CONFIG } from './types';

export { DEFAULT_CONFIG };

/**
 * 构建配置 Schema（用于 NapCat WebUI 配置面板）
 * 此函数保留为简易入口，主要的配置管理通过 WebUI 前端完成
 */
export function buildConfigSchema(ctx: NapCatPluginContext): PluginConfigSchema {
    const { NapCatConfig } = ctx;

    return NapCatConfig.combine(
        NapCatConfig.html('<div style="padding:10px; border-bottom:1px solid #ccc;"><h3>⏰ 自动定时任务 Pro</h3><p style="font-size:12px; color:#888;">请通过 WebUI 仪表盘页面管理任务配置</p></div>'),
        NapCatConfig.boolean('enabled', '启用插件', DEFAULT_CONFIG.enabled, '全局开关'),
        NapCatConfig.boolean('debug', '调试模式', DEFAULT_CONFIG.debug, '启用详细日志'),
    );
}
