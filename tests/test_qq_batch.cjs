// 只验证插件完成信号的时序，不连接 QQ 或发送消息。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('../napcat-plugin-auto-tasks/node_modules/typescript');

test('strict friend send never treats No data returned as success', () => {
  const source = fs.readFileSync(path.join(__dirname, '../napcat-plugin-auto-tasks/src/core/state.ts'), 'utf8');
  const strict = source.match(/async callApiStrict[\s\S]*?\n    }/);
  assert.ok(strict, 'callApiStrict should exist');
  assert.doesNotMatch(strict[0], /No data returned/);
  assert.match(strict[0], /return await this\.ctx\.actions\.call/);
});

test('friend batch is persisted only after every target is attempted', async () => {
  const now = new Date(2026, 8, 28, 10, 0, 0);
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [now.getTime()])); }
    static now() { return now.getTime(); }
  }
  const time = new FixedDate().toTimeString().split(' ')[0];
  const calls = [];
  const savedAt = [];
  const state = {
    config: {
      tasks: [], groupSign_enable: false, groupSpark_enable: false,
      friendSpark_enable: true, friendSpark_time: time,
      friendSpark_targets: '101,102', friendSpark_message: 'test',
    },
    stats: { friendSparkCompletedAt: 0 },
    logger: { info() {}, error() {} },
    async callApiStrict(action, payload) {
      assert.equal(action, 'send_msg');
      assert.equal(state.stats.friendSparkCompletedAt, 0);
      calls.push(payload.user_id);
    },
    incrementProcessed() {},
    saveConfig() { savedAt.push(calls.length); },
  };
  const source = fs.readFileSync(path.join(__dirname, '../napcat-plugin-auto-tasks/src/taskManager.ts'), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(js, {
    module, exports: module.exports, Date: FixedDate,
    require: (name) => {
      assert.equal(name, './core/state');
      return { pluginState: state };
    },
    setTimeout: (callback) => { callback(); return 0; },
  });
  const manager = new module.exports.TaskManager();
  await manager.tick([]);
  assert.deepEqual(calls, ['101', '102']);
  assert.deepEqual(savedAt, [2]);
  assert.equal(state.stats.friendSparkCompletedAt, now.getTime());
  assert.equal(state.stats.friendSparkSucceeded, 2);
  assert.equal(state.stats.friendSparkFailed, 0);
});

test('failed friend send is counted after the full batch', async () => {
  const now = new Date(2026, 8, 28, 10, 0, 0);
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [now.getTime()])); }
    static now() { return now.getTime(); }
  }
  const state = {
    config: { tasks: [], groupSign_enable: false, groupSpark_enable: false,
      friendSpark_enable: true, friendSpark_time: new FixedDate().toTimeString().split(' ')[0],
      friendSpark_targets: '101,102', friendSpark_message: 'test' },
    stats: { friendSparkCompletedAt: 0 },
    logger: { info() {}, error() {} },
    async callApiStrict(_action, payload) { if (payload.user_id === '102') throw new Error('send failed'); },
    incrementProcessed() {},
    saveConfig() {},
  };
  const source = fs.readFileSync(path.join(__dirname, '../napcat-plugin-auto-tasks/src/taskManager.ts'), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(js, {
    module, exports: module.exports, Date: FixedDate,
    require: (name) => { assert.equal(name, './core/state'); return { pluginState: state }; },
    setTimeout: (callback) => { callback(); return 0; },
  });
  await new module.exports.TaskManager().tick([]);
  assert.equal(state.stats.friendSparkSucceeded, 1);
  assert.equal(state.stats.friendSparkFailed, 1);
  assert.equal(state.stats.friendSparkCompletedAt, now.getTime());
});
