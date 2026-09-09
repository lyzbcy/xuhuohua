# reference · QQ 侧（NapCat + auto-tasks 插件）

> 深入改 QQ 侧行为前读这个。

## 运行原理

NapCat（NTQQ 协议端）把 QQ 账号变成一个 OneBot 服务常驻运行；`auto-tasks` 插件挂载在 NapCat 里，内部起定时器，到点通过 NapCat 的发消息 API 给指定好友/群发话术，从而保持火花。

```
qq启动.bat → tools/napcat/shell/launcher.bat → 从注册表定位本机QQ → NapCatWinBootMain.exe 注入
                                        └─ plugins/auto-tasks/index.mjs（本项目已部署）
                                             ├─ friendSpark（好友续火花）★
                                             ├─ groupSpark（群续火花）
                                             └─ 自定义任务槽位（UI 动态扩展）
```

## 关键文件

| 位置 | 作用 |
|------|------|
| `napcat-plugin-auto-tasks/src/config.ts` | 配置 schema 与 WebUI 表单生成 |
| `napcat-plugin-auto-tasks/src/taskManager.ts` | 定时器调度核心（重载清理也在里面） |
| `napcat-plugin-auto-tasks/dist/index.mjs` | 构建产物，部署到 NapCat 的 `plugins/auto-tasks/` |
| `tools/napcat/shell/` | NapCat v4.18.19 Shell 完整包（launcher.bat 为入口，自动找本机 QQ 注入） |

## 配置项（WebUI 里配，对应 src/types.ts）

| 键 | 说明 | 示例 |
|----|------|------|
| `enabled` | 插件总开关 | true |
| `friendSpark_enable` | 好友续火花开关 | true |
| `friendSpark_time` | 每日发送时间 | `08:00:00` |
| `friendSpark_targets` | 对方 QQ 号，逗号分隔 | `123456,234567` |
| `friendSpark_message` | 话术，支持 CQ 码 | `[CQ:face,id=14] 火花打卡` |
| `groupSpark_*` | 群续火花同款三件套 | — |
| `tasks[]` | 自定义任务：type/time/interval/target/message | — |

## 构建与部署

```powershell
cd napcat-plugin-auto-tasks
npm install
npm run build     # 产物 dist/index.mjs + dist/package.json
# 部署 = 把 dist 两个文件拷到 <NapCat>/plugins/auto-tasks/
```

改插件源码后：重复上面三步 + 重启 NapCat。

## 常见排障

1. **WebUI 打不开**：控制台打印的地址/token 每次可能不同，以控制台为准
2. **到点没发**：确认 NapCat 控制台没关；插件配置已保存；`enabled` 和 `friendSpark_enable` 都开着
3. **QQ 掉线**：重新 `qq启动.bat` 扫码；长期看建议给这台机器配开机自启
4. **风控风险**：NapCat 属第三方协议端，腾讯可能风控。控制话术频率（默认每日 1 次没问题），不要拿主号高频群发

## 已知边界

- 插件内置话术是**单条字符串**（非随机池）。想要随机：用它的自定义任务 `tasks[]` 配多条时间相近的任务各带不同话术，或改 `src/config.ts` 支持 `|` 分隔随机抽（改完记得构建部署 + 更新版本号）
