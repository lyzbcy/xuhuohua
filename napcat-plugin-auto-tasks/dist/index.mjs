import fs from 'fs';
import path from 'path';

var EventType = /* @__PURE__ */ ((EventType2) => {
  EventType2["META"] = "meta_event";
  EventType2["REQUEST"] = "request";
  EventType2["NOTICE"] = "notice";
  EventType2["MESSAGE"] = "message";
  EventType2["MESSAGE_SENT"] = "message_sent";
  return EventType2;
})(EventType || {});

const DEFAULT_CONFIG = {
  enabled: true,
  debug: false,
  // 群打卡
  groupSign_enable: false,
  groupSign_time: "08:00:00",
  groupSign_targets: "",
  // 群续火花
  groupSpark_enable: false,
  groupSpark_time: "09:00:00",
  groupSpark_message: "自动续火花",
  groupSpark_targets: "",
  // 好友续火花
  friendSpark_enable: false,
  friendSpark_time: "10:00:00",
  friendSpark_message: "✨",
  friendSpark_targets: "",
  // 自定义任务
  tasks: [],
  // 群配置
  groupConfigs: {}
};

function buildConfigSchema(ctx) {
  const { NapCatConfig } = ctx;
  return NapCatConfig.combine(
    NapCatConfig.html('<div style="padding:10px; border-bottom:1px solid #ccc;"><h3>⏰ 自动定时任务 Pro</h3><p style="font-size:12px; color:#888;">请通过 WebUI 仪表盘页面管理任务配置</p></div>'),
    NapCatConfig.boolean("enabled", "启用插件", DEFAULT_CONFIG.enabled, "全局开关"),
    NapCatConfig.boolean("debug", "调试模式", DEFAULT_CONFIG.debug, "启用详细日志")
  );
}

function isObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}
function sanitizeConfig(raw) {
  if (!isObject(raw)) return { ...DEFAULT_CONFIG, tasks: [], groupConfigs: {} };
  const out = { ...DEFAULT_CONFIG, tasks: [], groupConfigs: {} };
  if (typeof raw.enabled === "boolean") out.enabled = raw.enabled;
  if (typeof raw.debug === "boolean") out.debug = raw.debug;
  if (typeof raw.groupSign_enable === "boolean") out.groupSign_enable = raw.groupSign_enable;
  if (typeof raw.groupSign_time === "string") out.groupSign_time = raw.groupSign_time;
  if (typeof raw.groupSign_targets === "string") out.groupSign_targets = raw.groupSign_targets;
  if (typeof raw.groupSpark_enable === "boolean") out.groupSpark_enable = raw.groupSpark_enable;
  if (typeof raw.groupSpark_time === "string") out.groupSpark_time = raw.groupSpark_time;
  if (typeof raw.groupSpark_message === "string") out.groupSpark_message = raw.groupSpark_message;
  if (typeof raw.groupSpark_targets === "string") out.groupSpark_targets = raw.groupSpark_targets;
  if (typeof raw.friendSpark_enable === "boolean") out.friendSpark_enable = raw.friendSpark_enable;
  if (typeof raw.friendSpark_time === "string") out.friendSpark_time = raw.friendSpark_time;
  if (typeof raw.friendSpark_message === "string") out.friendSpark_message = raw.friendSpark_message;
  if (typeof raw.friendSpark_targets === "string") out.friendSpark_targets = raw.friendSpark_targets;
  if (Array.isArray(raw.tasks)) {
    out.tasks = raw.tasks.filter(isObject).map(sanitizeTask);
  }
  if (out.tasks.length === 0) {
    const migratedTasks = migrateOldTasks(raw);
    if (migratedTasks.length > 0) out.tasks = migratedTasks;
  }
  if (isObject(raw.groupConfigs)) {
    for (const [groupId, groupConfig] of Object.entries(raw.groupConfigs)) {
      if (isObject(groupConfig)) {
        const cfg = {};
        if (typeof groupConfig.enabled === "boolean") cfg.enabled = groupConfig.enabled;
        out.groupConfigs[groupId] = cfg;
      }
    }
  }
  return out;
}
function sanitizeTask(raw) {
  return {
    enable: typeof raw.enable === "boolean" ? raw.enable : false,
    type: ["group", "private", "group_notice"].includes(raw.type) ? raw.type : "group",
    target: typeof raw.target === "string" ? raw.target : "",
    time: typeof raw.time === "string" ? raw.time : "",
    interval: typeof raw.interval === "number" ? raw.interval : 0,
    message: typeof raw.message === "string" ? raw.message : "",
    image: typeof raw.image === "string" ? raw.image : void 0,
    is_pinned: typeof raw.is_pinned === "boolean" ? raw.is_pinned : void 0,
    is_confirm: typeof raw.is_confirm === "boolean" ? raw.is_confirm : void 0
  };
}
function migrateOldTasks(raw) {
  const tasks = [];
  const count = typeof raw.taskCount === "number" ? raw.taskCount : typeof raw.taskCount === "string" ? parseInt(raw.taskCount, 10) || 0 : 0;
  for (let i = 1; i <= count; i++) {
    const enable = raw[`customTask_${i}_enable`];
    const target = raw[`customTask_${i}_target`];
    if (enable || target) {
      tasks.push({
        enable: Boolean(enable),
        type: ["group", "private", "group_notice"].includes(raw[`customTask_${i}_type`]) ? raw[`customTask_${i}_type`] : "group",
        target: String(target || ""),
        time: String(raw[`customTask_${i}_time`] || ""),
        interval: parseInt(String(raw[`customTask_${i}_interval`] || "0"), 10) || 0,
        message: String(raw[`customTask_${i}_message`] || ""),
        image: raw[`customTask_${i}_image`] ? String(raw[`customTask_${i}_image`]) : void 0,
        is_pinned: raw[`customTask_${i}_is_pinned`] ? Boolean(raw[`customTask_${i}_is_pinned`]) : void 0,
        is_confirm: raw[`customTask_${i}_is_confirm`] ? Boolean(raw[`customTask_${i}_is_confirm`]) : void 0
      });
    }
  }
  return tasks;
}
class PluginState {
  /** NapCat 插件上下文（init 后可用） */
  _ctx = null;
  /** 插件配置 */
  config = { ...DEFAULT_CONFIG };
  /** 插件启动时间戳 */
  startTime = 0;
  /** 机器人自身 QQ 号 */
  selfId = "";
  /** 活跃的定时器 Map: jobId -> NodeJS.Timeout */
  timers = /* @__PURE__ */ new Map();
  /** 配置变更回调（用于重启任务等） */
  _onConfigChange = null;
  /** 运行时统计 */
  stats = {
    processed: 0,
    todayProcessed: 0,
    lastUpdateDay: (/* @__PURE__ */ new Date()).toDateString()
  };
  /** 注册配置变更回调 */
  set onConfigChange(cb) {
    this._onConfigChange = cb;
  }
  /** 触发配置变更回调 */
  emitConfigChange() {
    if (this._onConfigChange) {
      try {
        this._onConfigChange();
      } catch (e) {
        this.logger.error("配置变更回调执行失败:", e);
      }
    }
  }
  /** 获取上下文（确保已初始化） */
  get ctx() {
    if (!this._ctx) throw new Error("PluginState 尚未初始化，请先调用 init()");
    return this._ctx;
  }
  /** 获取日志器的快捷方式 */
  get logger() {
    return this.ctx.logger;
  }
  // ==================== 生命周期 ====================
  /**
   * 初始化（在 plugin_init 中调用）
   */
  init(ctx) {
    this._ctx = ctx;
    this.startTime = Date.now();
    this.loadConfig();
    this.ensureDataDir();
    this.fetchSelfId();
  }
  /**
   * 获取机器人自身 QQ 号
   */
  async fetchSelfId() {
    try {
      const res = await this.ctx.actions.call(
        "get_login_info",
        {},
        this.ctx.adapterName,
        this.ctx.pluginManager.config
      );
      if (res?.user_id) {
        this.selfId = String(res.user_id);
        this.logger.debug("机器人 QQ: " + this.selfId);
      }
    } catch (e) {
      this.logger.warn("获取机器人 QQ 号失败:", e);
    }
  }
  /**
   * 清理（在 plugin_cleanup 中调用）
   */
  cleanup() {
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
  ensureDataDir() {
    const dataPath = this.ctx.dataPath;
    if (!fs.existsSync(dataPath)) {
      fs.mkdirSync(dataPath, { recursive: true });
    }
  }
  /** 获取数据文件完整路径 */
  getDataFilePath(filename) {
    return path.join(this.ctx.dataPath, filename);
  }
  // ==================== 通用数据文件读写 ====================
  loadDataFile(filename, defaultValue) {
    const filePath = this.getDataFilePath(filename);
    try {
      if (fs.existsSync(filePath)) {
        return JSON.parse(fs.readFileSync(filePath, "utf-8"));
      }
    } catch (e) {
      this.logger.warn("读取数据文件 " + filename + " 失败:", e);
    }
    return defaultValue;
  }
  saveDataFile(filename, data) {
    const filePath = this.getDataFilePath(filename);
    try {
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf-8");
    } catch (e) {
      this.logger.error("保存数据文件 " + filename + " 失败:", e);
    }
  }
  // ==================== 配置管理 ====================
  loadConfig() {
    const configPath = this.ctx.configPath;
    try {
      if (configPath && fs.existsSync(configPath)) {
        const raw = JSON.parse(fs.readFileSync(configPath, "utf-8"));
        this.config = sanitizeConfig(raw);
        if (isObject(raw) && isObject(raw.stats)) {
          Object.assign(this.stats, raw.stats);
        }
        this.ctx.logger.debug("已加载本地配置");
      } else {
        this.config = { ...DEFAULT_CONFIG, tasks: [], groupConfigs: {} };
        this.saveConfig();
        this.ctx.logger.debug("配置文件不存在，已创建默认配置");
      }
    } catch (error) {
      this.ctx.logger.error("加载配置失败，使用默认配置:", error);
      this.config = { ...DEFAULT_CONFIG, tasks: [], groupConfigs: {} };
    }
  }
  saveConfig() {
    if (!this._ctx) return;
    const configPath = this._ctx.configPath;
    try {
      const configDir = path.dirname(configPath);
      if (!fs.existsSync(configDir)) {
        fs.mkdirSync(configDir, { recursive: true });
      }
      const data = { ...this.config, stats: this.stats };
      fs.writeFileSync(configPath, JSON.stringify(data, null, 2), "utf-8");
    } catch (error) {
      this._ctx.logger.error("保存配置失败:", error);
    }
  }
  updateConfig(partial) {
    this.config = { ...this.config, ...partial };
    this.saveConfig();
    this.emitConfigChange();
  }
  replaceConfig(config) {
    this.config = sanitizeConfig(config);
    this.saveConfig();
    this.emitConfigChange();
  }
  updateGroupConfig(groupId, config) {
    this.config.groupConfigs[groupId] = {
      ...this.config.groupConfigs[groupId],
      ...config
    };
    this.saveConfig();
  }
  isGroupEnabled(groupId) {
    return this.config.groupConfigs[groupId]?.enabled !== false;
  }
  // ==================== OneBot API 调用 ====================
  async callApi(action, params) {
    try {
      return await this.ctx.actions.call(
        action,
        params,
        this.ctx.adapterName,
        this.ctx.pluginManager.config
      );
    } catch (e) {
      const errStr = String(e);
      if (errStr.includes("No data returned") || e instanceof Error && e.message.includes("No data returned")) {
        return;
      }
      this.logger.error(`[API] ${action} 失败:`, e);
    }
  }
  // ==================== 统计 ====================
  incrementProcessed() {
    const today = (/* @__PURE__ */ new Date()).toDateString();
    if (this.stats.lastUpdateDay !== today) {
      this.stats.todayProcessed = 0;
      this.stats.lastUpdateDay = today;
    }
    this.stats.todayProcessed++;
    this.stats.processed++;
  }
  // ==================== 工具方法 ====================
  getUptime() {
    return Date.now() - this.startTime;
  }
  getUptimeFormatted() {
    const ms = this.getUptime();
    const s = Math.floor(ms / 1e3);
    const m = Math.floor(s / 60);
    const h = Math.floor(m / 60);
    const d = Math.floor(h / 24);
    if (d > 0) return `${d}天${h % 24}小时`;
    if (h > 0) return `${h}小时${m % 60}分钟`;
    if (m > 0) return `${m}分钟${s % 60}秒`;
    return `${s}秒`;
  }
}
const pluginState = new PluginState();

async function handleMessage(ctx, event) {
}

function registerApiRoutes(ctx) {
  const router = ctx.router;
  router.getNoAuth("/status", (_req, res) => {
    res.json({
      code: 0,
      data: {
        pluginName: ctx.pluginName,
        uptime: pluginState.getUptime(),
        uptimeFormatted: pluginState.getUptimeFormatted(),
        config: pluginState.config,
        stats: pluginState.stats
      }
    });
  });
  router.getNoAuth("/config", (_req, res) => {
    res.json({ code: 0, data: pluginState.config });
  });
  router.postNoAuth("/config", async (req, res) => {
    try {
      const body = req.body;
      if (!body) {
        return res.status(400).json({ code: -1, message: "请求体为空" });
      }
      pluginState.updateConfig(body);
      ctx.logger.info("配置已通过 API 保存");
      res.json({ code: 0, message: "ok" });
    } catch (err) {
      ctx.logger.error("保存配置失败:", err);
      res.status(500).json({ code: -1, message: String(err) });
    }
  });
  router.getNoAuth("/tasks", (_req, res) => {
    res.json({
      code: 0,
      data: {
        // 内置任务状态
        builtinTasks: {
          groupSign: {
            enable: pluginState.config.groupSign_enable,
            time: pluginState.config.groupSign_time,
            targets: pluginState.config.groupSign_targets
          },
          groupSpark: {
            enable: pluginState.config.groupSpark_enable,
            time: pluginState.config.groupSpark_time,
            message: pluginState.config.groupSpark_message,
            targets: pluginState.config.groupSpark_targets
          },
          friendSpark: {
            enable: pluginState.config.friendSpark_enable,
            time: pluginState.config.friendSpark_time,
            message: pluginState.config.friendSpark_message,
            targets: pluginState.config.friendSpark_targets
          }
        },
        // 自定义任务
        tasks: pluginState.config.tasks
      }
    });
  });
  router.postNoAuth("/tasks", async (req, res) => {
    try {
      const body = req.body;
      if (!body) {
        return res.status(400).json({ code: -1, message: "请求体为空" });
      }
      const updates = {};
      if (body.builtinTasks && typeof body.builtinTasks === "object") {
        const bt = body.builtinTasks;
        if (bt.groupSign) {
          if (typeof bt.groupSign.enable === "boolean") updates.groupSign_enable = bt.groupSign.enable;
          if (typeof bt.groupSign.time === "string") updates.groupSign_time = bt.groupSign.time;
          if (typeof bt.groupSign.targets === "string") updates.groupSign_targets = bt.groupSign.targets;
        }
        if (bt.groupSpark) {
          if (typeof bt.groupSpark.enable === "boolean") updates.groupSpark_enable = bt.groupSpark.enable;
          if (typeof bt.groupSpark.time === "string") updates.groupSpark_time = bt.groupSpark.time;
          if (typeof bt.groupSpark.message === "string") updates.groupSpark_message = bt.groupSpark.message;
          if (typeof bt.groupSpark.targets === "string") updates.groupSpark_targets = bt.groupSpark.targets;
        }
        if (bt.friendSpark) {
          if (typeof bt.friendSpark.enable === "boolean") updates.friendSpark_enable = bt.friendSpark.enable;
          if (typeof bt.friendSpark.time === "string") updates.friendSpark_time = bt.friendSpark.time;
          if (typeof bt.friendSpark.message === "string") updates.friendSpark_message = bt.friendSpark.message;
          if (typeof bt.friendSpark.targets === "string") updates.friendSpark_targets = bt.friendSpark.targets;
        }
      }
      if (Array.isArray(body.tasks)) {
        updates.tasks = body.tasks;
      }
      pluginState.updateConfig(updates);
      ctx.logger.info("任务配置已更新");
      res.json({ code: 0, message: "ok" });
    } catch (err) {
      ctx.logger.error("更新任务配置失败:", err);
      res.status(500).json({ code: -1, message: String(err) });
    }
  });
  router.getNoAuth("/groups", async (_req, res) => {
    try {
      const groups = await ctx.actions.call(
        "get_group_list",
        {},
        ctx.adapterName,
        ctx.pluginManager.config
      );
      const groupsWithConfig = (groups || []).map((group) => {
        const groupId = String(group.group_id);
        return {
          group_id: group.group_id,
          group_name: group.group_name,
          member_count: group.member_count,
          max_member_count: group.max_member_count,
          enabled: pluginState.isGroupEnabled(groupId)
        };
      });
      res.json({ code: 0, data: groupsWithConfig });
    } catch (e) {
      ctx.logger.error("获取群列表失败:", e);
      res.status(500).json({ code: -1, message: String(e) });
    }
  });
  router.postNoAuth("/groups/:id/config", async (req, res) => {
    try {
      const groupId = req.params?.id;
      if (!groupId) {
        return res.status(400).json({ code: -1, message: "缺少群 ID" });
      }
      const body = req.body;
      const enabled = body?.enabled;
      pluginState.updateGroupConfig(groupId, { enabled: Boolean(enabled) });
      ctx.logger.info(`群 ${groupId} 配置已更新: enabled=${enabled}`);
      res.json({ code: 0, message: "ok" });
    } catch (err) {
      ctx.logger.error("更新群配置失败:", err);
      res.status(500).json({ code: -1, message: String(err) });
    }
  });
  router.postNoAuth("/groups/bulk-config", async (req, res) => {
    try {
      const body = req.body;
      const { enabled, groupIds } = body || {};
      if (typeof enabled !== "boolean" || !Array.isArray(groupIds)) {
        return res.status(400).json({ code: -1, message: "参数错误" });
      }
      for (const groupId of groupIds) {
        pluginState.updateGroupConfig(String(groupId), { enabled });
      }
      ctx.logger.info(`批量更新群配置完成 | 数量: ${groupIds.length}, enabled=${enabled}`);
      res.json({ code: 0, message: "ok" });
    } catch (err) {
      ctx.logger.error("批量更新群配置失败:", err);
      res.status(500).json({ code: -1, message: String(err) });
    }
  });
  ctx.logger.debug("API 路由注册完成");
}

class TaskManager {
  lastExecutedTime = "";
  constructor() {
  }
  // --- 停止所有任务 ---
  stop() {
    if (pluginState.timers.size > 0) {
      pluginState.logger.info(`🛑 已清理 ${pluginState.timers.size} 个活跃定时器`);
    }
    for (const [jobId, timer] of pluginState.timers) {
      clearInterval(timer);
    }
    pluginState.timers.clear();
  }
  // --- 启动任务 ---
  start() {
    this.stop();
    pluginState.logger.info("🚀 正在启动自动化任务...");
    const tasks = pluginState.config.tasks.filter((t) => t.enable && t.target);
    pluginState.logger.info(`已加载 ${tasks.length} 个有效自定义任务`);
    const mainTicker = setInterval(() => {
      this.tick(tasks);
    }, 1e3);
    pluginState.timers.set("main-ticker", mainTicker);
    tasks.forEach((task, index) => {
      if (task.type === "group_notice") return;
      if (task.interval > 0) {
        const ms = Math.max(task.interval * 1e3, 5e3);
        pluginState.logger.info(`[任务${index + 1}] ⏳ 循环启动: 目标 ${task.target}, 间隔 ${task.interval}s`);
        const timer = setInterval(() => {
          try {
            this.executeTask(task, index + 1).catch((e) => {
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
  async tick(tasks) {
    const now = /* @__PURE__ */ new Date();
    const timeStr = now.toTimeString().split(" ")[0];
    if (timeStr === this.lastExecutedTime) return;
    this.lastExecutedTime = timeStr;
    const config = pluginState.config;
    let allGroups = null;
    let allFriends = null;
    const getAllGroups = async () => {
      if (allGroups !== null) return allGroups;
      try {
        const result = await pluginState.callApi("get_group_list", {});
        allGroups = (result || []).map((g) => g.group_id);
      } catch {
        allGroups = [];
      }
      return allGroups;
    };
    const getEnabledGroups = async () => {
      try {
        const result = await pluginState.callApi("get_group_list", {});
        return (result || []).filter((g) => pluginState.isGroupEnabled(String(g.group_id))).map((g) => g.group_id);
      } catch {
        return [];
      }
    };
    const getAllFriends = async () => {
      if (allFriends !== null) return allFriends;
      try {
        const result = await pluginState.callApi("get_friend_list", {});
        allFriends = (result || []).map((f) => f.user_id);
      } catch {
        allFriends = [];
      }
      return allFriends;
    };
    if (config.groupSign_enable && timeStr === config.groupSign_time) {
      const targets = config.groupSign_targets.toLowerCase() === "all" ? (await getAllGroups()).join(",") : config.groupSign_targets.toLowerCase() === "allallow" ? (await getEnabledGroups()).join(",") : config.groupSign_targets;
      this.executeBatch("群打卡", targets, async (id) => {
        await pluginState.callApi("send_group_sign", { group_id: id });
      });
    }
    if (config.groupSpark_enable && timeStr === config.groupSpark_time) {
      const targets = config.groupSpark_targets.toLowerCase() === "all" ? (await getAllGroups()).join(",") : config.groupSpark_targets.toLowerCase() === "allallow" ? (await getEnabledGroups()).join(",") : config.groupSpark_targets;
      this.executeBatch("群火花", targets, async (id) => {
        await pluginState.callApi("send_msg", {
          message_type: "group",
          group_id: id,
          message: config.groupSpark_message
        });
      });
    }
    if (config.friendSpark_enable && timeStr === config.friendSpark_time) {
      const targets = config.friendSpark_targets.toLowerCase() === "all" ? (await getAllFriends()).join(",") : config.friendSpark_targets;
      this.executeBatch("好友火花", targets, async (id) => {
        await pluginState.callApi("send_msg", {
          message_type: "private",
          user_id: id,
          message: config.friendSpark_message
        });
      });
    }
    for (let i = 0; i < tasks.length; i++) {
      const task = tasks[i];
      const isScheduleMode = task.interval <= 0 || task.type === "group_notice";
      if (isScheduleMode && task.time === timeStr) {
        try {
          this.executeTask(task, i + 1).catch((e) => {
            pluginState.logger.error(`[任务${i + 1}] 定时执行异步异常:`, e);
          });
        } catch (e) {
          pluginState.logger.error(`[任务${i + 1}] 定时触发异常:`, e);
        }
      }
    }
  }
  async executeTask(task, index) {
    try {
      pluginState.logger.info(`[任务${index}] ▶️ 触发: ${task.target} (${task.type})`);
      await new Promise((r) => setTimeout(r, Math.random() * 3e3));
      if (task.type === "group_notice") {
        await pluginState.callApi("_send_group_notice", {
          group_id: task.target,
          content: task.message,
          image: task.image || void 0,
          pinned: task.is_pinned ? 1 : 0,
          type: 1,
          confirm_required: task.is_confirm ? 1 : 0,
          is_show_edit_card: 0,
          tip_window_type: 0
        });
      } else {
        const payload = {
          message_type: task.type,
          message: task.message
        };
        if (task.type === "group") payload.group_id = task.target;
        else payload.user_id = task.target;
        await pluginState.callApi("send_msg", payload);
      }
      pluginState.incrementProcessed();
    } catch (e) {
      pluginState.logger.error(`[任务${index}] 执行失败:`, e);
    }
  }
  async executeBatch(name, targetsStr, action) {
    const targets = targetsStr.split(/[,，]/).map((t) => t.trim()).filter((t) => t);
    if (targets.length === 0) return;
    pluginState.logger.info(`[内置任务] ${name} 触发`);
    for (const id of targets) {
      await new Promise((r) => setTimeout(r, 2e3 + Math.random() * 3e3));
      try {
        await action(id);
        pluginState.incrementProcessed();
      } catch (e) {
        pluginState.logger.error(`[${name}] 失败`, e);
      }
    }
  }
}

let taskManager = null;
let plugin_config_ui = [];
const plugin_init = async (ctx) => {
  try {
    pluginState.init(ctx);
    ctx.logger.info("🛠️ 插件初始化中...");
    plugin_config_ui = buildConfigSchema(ctx);
    registerWebUI(ctx);
    registerApiRoutes(ctx);
    taskManager = new TaskManager();
    taskManager.start();
    pluginState.onConfigChange = () => {
      ctx.logger.info("⚙️ 配置已变更，重启任务管理器...");
      if (taskManager) {
        taskManager.start();
      }
    };
    ctx.logger.info("✅ 插件初始化完成");
  } catch (error) {
    ctx.logger.error("插件初始化失败:", error);
  }
};
const plugin_onmessage = async (ctx, event) => {
  if (event.post_type !== EventType.MESSAGE) return;
  if (!pluginState.config.enabled) return;
  await handleMessage();
};
const plugin_onevent = async (_ctx, _event) => {
};
const plugin_cleanup = async (ctx) => {
  try {
    if (taskManager) {
      taskManager.stop();
      taskManager = null;
    }
    pluginState.cleanup();
    ctx.logger.info("🛑 插件已卸载");
  } catch (e) {
    ctx.logger.warn("插件卸载时出错:", e);
  }
};
const plugin_get_config = async (_ctx) => {
  return pluginState.config;
};
const plugin_set_config = async (ctx, config) => {
  pluginState.replaceConfig(config);
  ctx.logger.info("配置已通过 WebUI 更新");
  if (taskManager) {
    taskManager.start();
  }
};
const plugin_on_config_change = async (ctx, _ui, key, value, _currentConfig) => {
  try {
    pluginState.updateConfig({ [key]: value });
    ctx.logger.info(`⚙️ 配置项 ${key} 已更新`);
    if (taskManager) {
      taskManager.start();
    }
  } catch (err) {
    ctx.logger.error(`更新配置项 ${key} 失败:`, err);
  }
};
function registerWebUI(ctx) {
  const router = ctx.router;
  router.static("/static", "webui");
  router.page({
    path: "dashboard",
    title: "任务管理",
    htmlFile: "webui/index.html",
    description: "自动定时任务管理控制台"
  });
  ctx.logger.debug("WebUI 路由注册完成");
}

export { plugin_cleanup, plugin_config_ui, plugin_get_config, plugin_init, plugin_on_config_change, plugin_onevent, plugin_onmessage, plugin_set_config };
