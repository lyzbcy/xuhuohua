/* 续火花控制台 · 前端逻辑 */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));   // 返回真数组：NodeList 没有 .map

const PLACEHOLDER_RE = /^在这里填好友昵称/;
let lastSeq = 0;
let api = null;
let apiReady = false;
let state = null;
let lastQqConfig = null;
let qqSnapshot = "";
let waitApiTicks = 0;
let dyFriends = [];          // 抖音好友列表（抖音页本地编辑态）
let dyFetchNames = [];       // 拉取到的候选会话名
let poolDirty = { texts: [], stickerFiles: [] };
let poolSnapshot = "";

/* ---------- 基础工具 ---------- */
function setStatus(text) { $("#statusbar-text").textContent = text; }
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
async function call(method, ...args) {
  if (!apiReady) throw new Error("后端尚未就绪");
  return await api[method](...args);
}
async function withBtn(btn, fn) {
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  try { await fn(); } finally { btn.disabled = false; }
}
function normTime(v, fallback) {
  if (!v) return fallback;
  const p = String(v).split(":");
  while (p.length < 3) p.push("0");
  const [h, m, s] = p.map(x => parseInt(x, 10));
  if ([h, m, s].some(isNaN) || h > 23 || m > 59 || s > 59) return fallback;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}
function qqFormSnapshot() {
  return JSON.stringify([$("#fs-enable").checked, $("#fs-time").value, $("#fs-targets").value]);
}

/* ---------- 页面切换 ---------- */
let currentPage = "dashboard";
function gotoPage(name) {
  currentPage = name;
  $$(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.page === name));
  $$(".page").forEach(p => p.classList.toggle("active", p.id === "page-" + name));
  if (name === "logs") refreshLogs();
  if (name === "about") loadAbout();
  if (name === "schedule") loadSchedule();
}
$$(".nav-item").forEach(btn => btn.addEventListener("click", async () => {
  const target = btn.dataset.page;
  if (currentPage === "pool" && target !== "pool" && JSON.stringify(poolDirty) !== poolSnapshot) {
    if (!confirm("话术库还没保存，现在离开会丢失刚才的修改。确定离开吗？")) return;
  }
  if (currentPage === "qq" && target !== "qq" && lastQqConfig && qqFormSnapshot() !== qqSnapshot) {
    if (!confirm("QQ 页的配置改动还没保存，离开会丢失。确定离开吗？")) return;
  }
  if (target === "qq") await loadQqConfig();
  if (target === "pool") await loadPool();
  if (target === "douyin") renderDyFriends();
  gotoPage(target);
}));

/* ---------- 轮询 ---------- */
async function pollState() {
  if (!apiReady) return;
  try { state = await call("get_state"); renderState(); renderPlan(); } catch (e) { }
}
async function pollEvents() {
  if (!apiReady) return;
  try {
    const r = await call("get_events", lastSeq);
    if (r.events && r.events.length) {
      lastSeq = r.events[r.events.length - 1].seq;
      renderFeed(r.events);
      const last = r.events[r.events.length - 1];
      setStatus(last.message);
      document.querySelector(".statusbar .dot").style.background =
        last.level === "FAIL" ? "#e5484d" : last.level === "WARN" ? "#e8a013" : "#22a95e";
    }
  } catch (e) { }
}
async function pollQr() {
  if (!apiReady) return;
  try {
    const r = await call("qq_qrcode");
    const panel = $("#qq-qr-panel");
    if (r.has_qr) {
      panel.style.display = "";
      $("#qq-qr-img").src = r.data_url;
    } else if (currentPage !== "qq") {
      panel.style.display = "none";
    }
  } catch (e) { }
}
setInterval(pollEvents, 1600);
setInterval(pollState, 3200);
setInterval(pollQr, 4000);
setInterval(() => { $("#statusbar-time").textContent = new Date().toLocaleTimeString("zh-CN"); }, 1000);

/* ---------- 仪表盘渲染 ---------- */
function renderState() {
  if (!state) return;
  $("#ver-foot").textContent = state.version;

  const dy = state.douyin;
  const dyEl = $("#dash-douyin");
  dyEl.textContent = dy.logged_in ? "已登录 ✓" : "未登录";
  dyEl.className = "card-status " + (dy.logged_in ? "ok" : "bad");
  const realFriends = (dy.friends || []).filter(f => !PLACEHOLDER_RE.test(f));
  if (realFriends.length) {
    $("#dash-douyin-sub").textContent = "好友 " + realFriends.length + " 位：" + realFriends.slice(0, 3).join("、") + (realFriends.length > 3 ? "…" : "");
    $("#dash-douyin-sub").style.color = "";
  } else {
    $("#dash-douyin-sub").textContent = "还没填真实好友：到「抖音」页添加";
    $("#dash-douyin-sub").style.color = "#e8a013";
  }
  $("#dy-login-status").innerHTML = dy.logged_in
    ? '<span class="ok">✔ 已登录（登录凭证有效）</span>'
    : '<span class="bad">✘ 尚未登录，请点击下方按钮扫码</span>';
  const busy = Object.values(dy.running || {}).some(Boolean);
  $("#dy-proc").innerHTML = busy
    ? '<span class="mid">⏳ 有任务正在运行，进度见仪表盘「实时动态」</span>'
    : '<span class="ok">空闲</span>';

  const qqEl = $("#dash-qq");
  qqEl.textContent = state.qq.running ? "运行中 ✓" : "未运行";
  qqEl.className = "card-status " + (state.qq.running ? "ok" : "mid");
  $("#dash-qq-sub").textContent = state.qq.running
    ? "QQ 引擎工作中（别关它的黑色窗口）"
    : (state.qq.quick_account
      ? "点击下方「启动 QQ」——将快速登录（" + state.qq.quick_account + "），通常不用扫码"
      : "点击下方「启动 QQ」；首次需扫码一次，之后自动快速登录");

  const sc = $("#dash-sched");
  if (state.schedule && state.schedule.exists) {
    sc.textContent = state.schedule.next_run || "已注册";
    sc.className = "card-status mid";
    const resMap = { "0": "上次运行成功", "3": "上次运行时还没登录抖音（已跳过）" };
    $("#dash-sched-sub").textContent = (resMap[state.schedule.last_result] || "上次结果：" + (state.schedule.last_result || "-")) + " · 到点电脑需开机联网";
  } else {
    sc.textContent = "未注册";
    sc.className = "card-status bad";
    $("#dash-sched-sub").textContent = "到「定时」页注册";
  }
  renderDyFriends();
}

function renderPlan() {
  if (!state) return;
  const el = $("#dash-plan");
  if (!el) return;
  const dyNext = state.schedule && state.schedule.exists ? state.schedule.next_run : "未注册";
  const dyTime = dyNext !== "未注册" ? dyNext.split(" ")[1] || "" : "";
  const qqT = state.qq.send_time || "10:00:00";
  const items = [
    ["🎵 抖音发送", state.schedule && state.schedule.exists ? "每天 " + (dyTime || "") + "（下次 " + dyNext + "）" : "未注册定时，去「定时」页开启"],
    ["🐧 QQ 发送", "每天 " + qqT],
    ["🔄 话术轮换", state.rotate && state.rotate.exists ? "每天 00:05 自动换一条新话术" : "未启用"],
    ["🔍 更新检查", "每次打开软件时静默检查（手动在「关于」页）"],
  ];
  el.innerHTML = items.map(([k, v]) => `<div class="plan-item"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join("");
}

function renderFeed(events) {
  const feed = $("#dash-feed");
  const html = events.map(e =>
    `<div class="feed-item"><span class="t">${esc(e.time)}</span><span class="lv-${esc(e.level)} src">${esc(e.level)}</span><span class="src">${esc(e.source)}</span><span>${esc(e.message)}</span></div>`
  ).join("");
  feed.insertAdjacentHTML("beforeend", html);
  const items = feed.querySelectorAll(".feed-item");
  if (items.length > 120) for (let i = 0; i < items.length - 120; i++) items[i].remove();
  feed.scrollTop = feed.scrollHeight;
}

/* ---------- 仪表盘动作 ---------- */
$("#dash-run").addEventListener("click", () => { gotoPage("douyin"); doRun(false); });
$("#dash-dryrun").addEventListener("click", () => { gotoPage("douyin"); doRun(true); });
$("#dash-qq-start").addEventListener("click", qqStart);
$("#dash-qq-send").addEventListener("click", () => qqSendNow());

/* ---------- 抖音页 ---------- */
$("#dy-login-btn").addEventListener("click", (e) => withBtn(e.target, async () => {
  try {
    const r = await call("douyin_login");
    if (!r.started) { alert(r.msg); setStatus(r.msg); }
    else setStatus(r.msg === "已启动" ? "浏览器已打开，等待扫码（登录成功自动保存）…" : r.msg);
  } catch (err) { alert("启动失败：" + err.message); }
}));
$("#dy-dryrun").addEventListener("click", (e) => withBtn(e.target, () => doRun(true)));
$("#dy-run").addEventListener("click", (e) => withBtn(e.target, () => doRun(false)));

async function doRun(dry) {
  if (state && state.douyin && (state.douyin.friends || []).filter(f => !PLACEHOLDER_RE.test(f)).length === 0) {
    alert("还没有添加真实好友。请先在下方「管理好友」里添加，再回来运行。");
    return;
  }
  if (!dry && !confirm("将向好友列表里的所有抖音好友真实发送话术，确定？")) return;
  try {
    const r = await call("douyin_run", dry);
    if (!r.started) alert(r.msg);
    else setStatus(dry ? "演练运行中…结果看「实时动态」" : "正式发送中…结果看「实时动态」");
  } catch (err) { alert("启动失败：" + err.message); }
}

/* ---------- 抖音好友管理 ---------- */
function renderDyFriends() {
  if (currentPage === "douyin" || $("#dy-friend-list")) {
    if (state && !dyFriends.length) dyFriends = (state.douyin.friends || []).filter(f => !PLACEHOLDER_RE.test(f));
    $("#dy-friend-list").innerHTML = dyFriends.length
      ? dyFriends.map((f, i) =>
        `<div class="pool-item"><span class="friend-chip">${esc(f)}</span><button class="del" data-fd="${i}" title="删除">✕</button></div>`
      ).join("")
      : '<p class="hint">还没有好友。手动添加，或点「从抖音拉取最近会话」勾选。</p>';
    $$("#dy-friend-list .del").forEach(b => b.addEventListener("click", () => {
      dyFriends.splice(+b.dataset.fd, 1);
      renderDyFriends();
    }));
  }
}
$("#dy-add-friend").addEventListener("click", () => {
  const name = prompt("输入好友昵称（与抖音聊天列表显示一致，备注名最稳）：");
  if (name && name.trim()) { dyFriends.push(name.trim()); renderDyFriends(); }
});
$("#dy-save-friends").addEventListener("click", (e) => withBtn(e.target, async () => {
  try {
    const r = await call("douyin_save_friends", dyFriends);
    $("#dy-friend-note").textContent = r.ok ? "已保存 ✓" : (r.msg || "保存失败");
    if (r.ok) setStatus("抖音好友列表已保存（" + r.friends.length + " 位）");
  } catch (err) { alert("保存失败：" + err.message); }
}));
$("#dy-fetch-friends").addEventListener("click", (e) => withBtn(e.target, async () => {
  setStatus("正在拉取抖音最近会话（约半分钟）…");
  try {
    const r = await call("douyin_fetch_friends");
    if (!r.ok) { alert(r.msg); setStatus(r.msg); return; }
    dyFetchNames = r.names || [];
    $("#dy-fetch-area").style.display = "";
    renderFetchList();
    setStatus("拉取到 " + dyFetchNames.length + " 个会话名，勾选要续火花的好友");
  } catch (err) { alert("拉取失败：" + err.message); }
}));
function renderFetchList() {
  const kw = ($("#dy-fetch-search").value || "").trim();
  const list = dyFetchNames.filter(n => !kw || n.includes(kw));
  $("#dy-fetch-list").innerHTML = list.length
    ? list.map(n => `<label class="chk-cell"><input type="checkbox" value="${esc(n)}"> ${esc(n)}</label>`).join("")
    : '<p class="hint">没有匹配的会话名。会话列表只显示最近聊过的人；找不到就手动添加。</p>';
}
$("#dy-fetch-search").addEventListener("input", renderFetchList);
$("#dy-fetch-add").addEventListener("click", (e) => withBtn(e.target, async () => {
  const picked = $$("#dy-fetch-list input:checked").map(cb => cb.value);
  if (!picked.length) { alert("先在列表里勾选要添加的好友（点名字前面的方框）"); return; }
  // 合并去重：与现有列表同名的只保留一个，绝不重复粘贴
  const set = new Set(dyFriends);
  const added = picked.filter(n => !set.has(n));
  added.forEach(n => set.add(n));
  dyFriends = [...set];
  renderDyFriends();
  $("#dy-fetch-area").style.display = "none";
  // 立即保存，一步到位
  try {
    const r = await call("douyin_save_friends", dyFriends);
    $("#dy-friend-note").textContent = r.ok
      ? "已合并 " + added.length + " 位新好友（同名自动去重），已保存 ✓"
      : (r.msg || "保存失败");
    setStatus(r.ok ? "好友列表已更新（现 " + r.friends.length + " 位）" : "保存失败");
  } catch (err) { alert("保存失败：" + err.message); }
}));

/* ---------- QQ 页 ---------- */
$("#qq-start").addEventListener("click", qqStart);
async function qqStart() {
  try {
    const r = await call("qq_start");
    if (!r.started) alert(r.msg);
    setStatus(r.msg);
    setTimeout(pollQr, 4000);
  } catch (err) { alert("启动失败：" + err.message); }
}
$("#qq-stop").addEventListener("click", (e) => withBtn(e.target, async () => {
  if (!confirm("确定停止 QQ 和续火花引擎？（QQ 侧停止后不会再自动发；抖音侧不受影响）")) return;
  try { const r = await call("qq_stop"); setStatus(r.msg); } catch (err) { alert(err.message); }
}));
function qqSendNow() {
  if (!confirm("将立刻给「对方 QQ 号」里的所有好友随机发一条共享话术，确定？")) return;
  setStatus("正在通过 QQ 引擎发送…（首次使用会自动重启一次引擎，不用扫码）");
  call("qq_send_now").then(r => {
    if (r.results && r.results.length) alert(r.msg + "\n" + r.results.map(x => `${x.target}：${x.msg}`).join("\n"));
    else alert(r.msg);
    setStatus(r.msg || "发送结束");
  }).catch(err => alert("发送失败：" + err.message));
}
$("#qq-send-now").addEventListener("click", (e) => withBtn(e.target, () => qqSendNow()));

async function loadQqConfig(force) {
  try {
    const r = await call("qq_get_config");
    if (qqSnapshot && qqFormSnapshot() !== qqSnapshot && !force) return;
    lastQqConfig = r.config;
    const c = r.config;
    $("#fs-enable").checked = !!c.friendSpark_enable;
    $("#fs-time").value = normTime(c.friendSpark_time, "10:00:00");
    $("#fs-targets").value = c.friendSpark_targets || "";
    qqSnapshot = qqFormSnapshot();
  } catch (e) { lastQqConfig = null; }
}
$("#qq-save").addEventListener("click", (e) => withBtn(e.target, async () => {
  if (!lastQqConfig) { alert("配置还没读取成功，为防止覆盖丢失，请重启软件后再保存。"); return; }
  const targets = $("#fs-targets").value.trim();
  if (targets && !$("#fs-enable").checked) {
    if (confirm("你填了对方 QQ 号，但上面的「启用」还没打勾——不打勾是不会发送的。\n要帮你把「启用」一起勾上吗？")) {
      $("#fs-enable").checked = true;
    }
  }
  const config = {
    friendSpark_enable: $("#fs-enable").checked,
    friendSpark_time: normTime($("#fs-time").value, "10:00:00"),
    friendSpark_targets: targets,
    groupSpark_enable: $("#gs-enable").checked,
    groupSpark_time: normTime($("#gs-time").value, "09:00:00"),
    groupSpark_targets: $("#gs-targets").value.trim(),
    groupSpark_message: $("#gs-message").value.trim() || "自动续火花",
  };
  try {
    const r = await call("qq_save_config", config);
    if (r.saved) {
      qqSnapshot = qqFormSnapshot();
      $("#qq-save-note").textContent = r.need_restart
        ? "已保存 ✓（QQ 正在运行：点上方「停止」再「启动 QQ」生效，不用重新扫码）"
        : "已保存 ✓";
      setStatus("QQ 配置已保存");
      await loadQqConfig(true);
    } else $("#qq-save-note").textContent = "保存失败";
  } catch (err) { alert("保存失败：" + err.message); }
}));

/* ---------- 话术库页（QQ 和抖音共用） ---------- */
async function loadPool() {
  try {
    const r = await call("pool_get");
    poolDirty.texts = (r.pool.texts || []).slice();
    poolDirty.stickerFiles = (r.pool.stickers || []).slice();
    renderPoolTexts(); await renderPoolStickers();
    poolSnapshot = JSON.stringify(poolDirty);
  } catch (e) { }
}
function renderPoolTexts() {
  $("#pool-texts").innerHTML = poolDirty.texts.length
    ? poolDirty.texts.map((t, i) =>
      `<div class="pool-item"><input type="text" data-ti="${i}" value="${esc(t)}" placeholder="写一句走心的话～"><button class="del" data-td="${i}" title="删除这条">✕</button></div>`
    ).join("")
    : '<p class="hint">池子空了，加几句话吧～</p>';
  $$("#pool-texts input").forEach(inp => inp.addEventListener("change", () => { poolDirty.texts[+inp.dataset.ti] = inp.value.trim(); }));
  $$("#pool-texts .del").forEach(b => b.addEventListener("click", () => { poolDirty.texts.splice(+b.dataset.td, 1); renderPoolTexts(); }));
}
async function renderPoolStickers() {
  try {
    const r = await call("douyin_stickers");
    $("#pool-stickers").innerHTML = (r.stickers || []).map(s => {
      const on = poolDirty.stickerFiles.includes(s.file.split("/").pop());
      return `<div class="sticker-cell ${on ? "on" : ""}" data-file="${esc(s.file)}" title="点击${on ? "移除" : "加入"}话术池"><img src="${esc(s.rel)}" alt="${esc(s.name)}"><span>${esc(s.name)}${on ? " ✓" : ""}</span></div>`;
    }).join("");
    $$(".sticker-cell").forEach(cell => cell.addEventListener("click", async () => {
      const f = cell.dataset.file.split("/").pop();
      const idx = poolDirty.stickerFiles.indexOf(f);
      if (idx >= 0) poolDirty.stickerFiles.splice(idx, 1); else poolDirty.stickerFiles.push(f);
      await renderPoolStickers();
    }));
  } catch (e) { }
}
$("#pool-add-text").addEventListener("click", () => { poolDirty.texts.push(""); renderPoolTexts(); });
$("#pool-save").addEventListener("click", (e) => withBtn(e.target, async () => {
  const texts = poolDirty.texts.map(s => s.trim()).filter(Boolean);
  if (!texts.length && !poolDirty.stickerFiles.length) { alert("池子不能为空：至少留一句话或一个表情。"); return; }
  try {
    const r = await call("pool_save", texts, poolDirty.stickerFiles);
    if (r.ok) {
      await loadPool();
      $("#pool-note").textContent = "已保存 ✓ QQ 和抖音都会用这套话术（抖音好友名单不受影响）";
      setStatus("共享话术库已保存（" + r.texts + " 条文字 / " + r.stickers + " 个表情）");
    } else { $("#pool-note").textContent = "保存失败：" + (r.msg || ""); alert(r.msg || "保存失败"); }
  } catch (err) { alert("保存失败：" + err.message); }
}));

/* ---------- QQ 好友拉取与勾选添加（多好友） ---------- */
let qqFetchList = [];
$("#qq-fetch-friends").addEventListener("click", (e) => withBtn(e.target, async () => {
  setStatus("正在从 QQ 引擎拉取好友列表…");
  try {
    const r = await call("qq_friends");
    if (!r.ok) { alert(r.msg); setStatus(r.msg); return; }
    qqFetchList = r.friends || [];
    $("#qq-fetch-area").style.display = "";
    renderQqFetchList();
    setStatus("已拉取 " + qqFetchList.length + " 位 QQ 好友，勾选后点「添加勾选的好友」");
  } catch (err) { alert("拉取失败：" + err.message); }
}));
function renderQqFetchList() {
  const kw = ($("#qq-fetch-search").value || "").trim();
  const list = qqFetchList.filter(f => !kw || f.name.includes(kw) || f.id.includes(kw));
  const existing = new Set(($("#fs-targets").value || "").split(",").map(s => s.trim()).filter(Boolean));
  $("#qq-fetch-list").innerHTML = list.length
    ? list.map(f => `<label class="chk-cell"><input type="checkbox" value="${esc(f.id)}"> ${esc(f.name)} <span class="qq-id">(${esc(f.id)})</span>${existing.has(f.id) ? " ✓" : ""}</label>`).join("")
    : '<p class="hint">没有匹配的好友</p>';
}
$("#qq-fetch-search").addEventListener("input", renderQqFetchList);
$("#qq-fetch-add").addEventListener("click", (e) => withBtn(e.target, async () => {
  const picked = $$("#qq-fetch-list input:checked").map(cb => cb.value);
  if (!picked.length) { alert("先在列表里勾选要添加的好友（点名字前面的方框）"); return; }
  const existing = ($("#fs-targets").value || "").split(",").map(s => s.trim()).filter(Boolean);
  const merged = [...new Set(existing.concat(picked))];
  $("#fs-targets").value = merged.join(",");
  $("#qq-fetch-area").style.display = "none";
  $("#qq-save-note").textContent = "已合并 " + picked.length + " 位好友（共 " + merged.length + " 位），记得点「保存 QQ 配置」";
  setStatus("QQ 好友已合并（共 " + merged.length + " 位）");
}));

/* ---------- 定时页 ---------- */
async function loadSchedule() {
  try {
    const s = await call("schedule_status");
    if (!s.exists) { $("#sched-status").innerHTML = "尚未注册定时任务"; return; }
    const resMap = { "0": "上次运行成功 ✓", "3": "上次运行时还没登录抖音（已跳过）" };
    $("#sched-status").innerHTML = `已注册 · 下次运行：<b>${esc(s.next_run)}</b> · ${esc(resMap[s.last_result] || ("上次结果：" + (s.last_result || "-")))}`;
    if (state && state.qq && state.qq.send_time) $("#sched-qq-time").value = normTime(state.qq.send_time, "10:00:00");
  } catch (e) { }
}
$("#sched-qq-save").addEventListener("click", (e) => withBtn(e.target, async () => {
  try {
    const cur = (await call("qq_get_config")).config || {};
    cur.friendSpark_time = normTime($("#sched-qq-time").value, "10:00:00");
    const r = await call("qq_save_config", cur);
    $("#sched-qq-note").textContent = r.saved ? "已保存 ✓" : "保存失败";
    setStatus("QQ 发送时间已保存为每天 " + cur.friendSpark_time);
  } catch (err) { alert("保存失败：" + err.message); }
}));
$("#sched-register").addEventListener("click", (e) => withBtn(e.target, async () => {
  const t = $("#sched-time").value || "08:30";
  try { const r = await call("schedule_register", t); alert(r.msg); loadSchedule(); } catch (err) { alert(err.message); }
}));
$("#sched-remove").addEventListener("click", (e) => withBtn(e.target, async () => {
  if (!confirm("删除每日定时任务？（删除后抖音火花不会再自动续）")) return;
  try { const r = await call("schedule_remove"); alert(r.msg); loadSchedule(); } catch (err) { alert(err.message); }
}));

/* ---------- 日志页 ---------- */
async function refreshLogs() {
  try {
    const a = await call("logs_today");
    $("#log-app").textContent = a.text;
    const d = await call("douyin_runlog_tail", 80);
    $("#log-douyin").textContent = d.text;
  } catch (e) { }
}
$("#log-refresh").addEventListener("click", refreshLogs);
$("#log-open").addEventListener("click", () => call("open_folder", "logs").catch(() => { }));

/* ---------- 关于页 ---------- */
async function loadAbout() {
  try {
    const r = await call("get_version");
    $("#about-version").innerHTML = `当前版本：<b>v${esc(r.version)}</b>`;
    $("#about-changelog").textContent = r.changelog || "（无更新日志）";
  } catch (e) { }
}
$("#about-check").addEventListener("click", (e) => withBtn(e.target, async () => {
  $("#about-update-result").textContent = "检查中…（国内建议先开代理）";
  try {
    const r = await call("check_updates");
    const lines = Object.entries(r.repos || {})
      .map(([k, v]) => `${k}：${v.update_available ? "有新版本 ⬆" : "已是最新 ✓"}${v.note ? "（" + v.note + "）" : ""}`);
    $("#about-update-result").innerHTML = lines.map(esc).join("<br>") + "<br>" + esc(r.hint || "");
  } catch (err) { $("#about-update-result").textContent = "检查失败：" + err.message; }
}));
$("#about-apply").addEventListener("click", (e) => withBtn(e.target, async () => {
  if (!confirm("一键更新上游项目？（你的个人配置不会被覆盖）")) return;
  $("#about-update-result").textContent = "更新中…请留意底部状态栏";
  try {
    const r = await call("apply_updates");
    $("#about-update-result").textContent = r.msg;
  } catch (err) { $("#about-update-result").textContent = "更新失败：" + err.message + "（下次可重试）"; }
}));

/* ---------- 启动 ---------- */
function waitApi() {
  if (window.pywebview && window.pywebview.api) {
    api = window.pywebview.api;
    apiReady = true;
    setStatus("就绪");
    pollState();
    setTimeout(() => loadQqConfig(true), 300);
    setTimeout(loadPool, 500);
  } else {
    waitApiTicks++;
    if (waitApiTicks === 20) setStatus("启动有点慢…再等几秒；若一直没反应请重启软件");
    setTimeout(waitApi, 250);
  }
}
waitApi();
