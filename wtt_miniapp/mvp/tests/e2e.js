const { chromium } = require('playwright');
/**
 * wtt_miniapp MVP — 端到端验收（在真实浏览器里跑微信官方基础库 3.7.0）
 *
 * 前置：两个服务已起（见 ../start.sh）
 *   node e2e.js
 *
 * 依赖：npm install playwright@1.65.0 --no-save（本机 Chrome）
 * 可在无头环境（CI）运行，不需要微信开发者工具。
 */
const BASE = process.env.MVP_URL || 'http://127.0.0.1:3401/';
const DEMO_PASSWORD = process.env.MVP_DEMO_PASSWORD || 'wtt-mvp-demo';
const ORIGINAL_SPEECH = '想陪爸妈慢慢逛';

async function wv(page) {
  for (const f of page.frames()) if (f.url().includes('/__wxa__/webview/')) return f;
  return null;
}
async function click(page, sel, nth = 0) {
  const f = await wv(page);
  await f.locator(sel).nth(nth).click();
}
async function text(page) {
  const f = await wv(page);
  return await f.locator('body').innerText();
}
function assert(cond, msg) {
  if (!cond) throw new Error('ASSERT FAILED: ' + msg);
  console.log('  ok - ' + msg);
}

/** 在小程序里填账密并登录（R1） */
async function login(page, opts) {
  await click(page, '.useritem', opts.userIdx);       // 填 email
  const f = await wv(page);
  // wx-input 是自定义组件，真正可 fill 的是内部的原生 <input>
  const pwd = f.locator('wx-input input[type="password"]');
  await pwd.fill(opts.password || DEMO_PASSWORD);
  // 触发小程序 bindinput（wxa-runner 会把 input 事件转给逻辑层）
  await pwd.dispatchEvent('input');
  await page.waitForTimeout(300);
  await click(page, '.btn.primary');
  await page.waitForTimeout(1200);
}

async function scenario(browser, label, opts) {
  // 每个场景独立 context：wxa-runner 的 storage 落在 localStorage，
  // 同 origin 共享。不隔离的话上一个场景存的 token 会让下一个场景自动免密，
  // 账密框不出现，测试就假了。
  const ctx = await browser.newContext({ viewport: { width: 460, height: 1000 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(2000);

  console.log('\n=== ' + label + ' ===');
  assert((await text(page)).includes('扫码即用'), '小程序页面渲染');
  assert((await text(page)).includes('密码'), 'R1 账密表单存在');

  if (opts.wrongPassword) {
    await login(page, opts);
    assert(!(await text(page)).includes('已登录'), '错误密码被拒绝');
    assert((await text(page)).includes('登录失败'), '显示登录失败');
    await ctx.close();
    return;
  }

  await login(page, opts);
  assert((await text(page)).includes('已登录'), 'R1 平台账密登录成功');

  await click(page, '.btn.primary');            // 拉 context
  await page.waitForTimeout(1500);
  const t = await text(page);

  assert(t.includes(opts.version), '讲解版本 = ' + opts.version);
  assert(opts.injected ? t.includes('已注入个性化') : t.includes('未注入'),
         opts.injected ? '启用个性化' : '退回通用版、不注入');
  assert(t.includes('今日路线'), '设计师预设路线保留');
  assert(t.includes('假山迷宫') && t.includes('燕誉堂') && t.includes('指柏轩'),
         '三个站点完整、未重排');
  assert(t.includes('BEGIN VISITOR CONTEXT'), '注入 prompt 有上下文分隔符');
  assert(t.includes('知识库事实 > 讲解侧重偏好'), '冲突优先级写进契约');
  assert(errs.length === 0, '无 JS 运行时错误' + (errs.length ? ': ' + errs.join(';') : ''));

  // D1 已定：不留原话，只导出概括 —— 每个场景都要过
  assert(!t.includes(ORIGINAL_SPEECH), 'D1：用户原话不出平台');
  assert(t.includes('画像概括（非原话）') || !opts.injected,
         'D1：展示结构化概括');
  assert(!t.includes('游客原话（'), 'prompt 里没有原话行');
  assert(t.includes('游客画像概括（由结构化字段生成，非用户原话）') || !opts.injected,
         'prompt 里只有概括行');

  if (opts.expectAvoid) assert(t.includes('硬约束（不要讲）'), 'avoid 单独成硬约束段');
  if (opts.expectPlaceholderStripped) assert(!t.includes('未知还查不了'), '占位词未泄漏');

  await ctx.close();
}

/** 方案一：第一次账密登录 → 关掉重开 → 免密恢复 */
async function scenarioSilentRestore(browser) {
  const ctx = await browser.newContext({ viewport: { width: 460, height: 1000 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));

  console.log('\n=== E 方案一：下次进来免密 ===');

  // 第一次：输账密
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(2000);
  assert((await text(page)).includes('密码'), '首次进入有账密表单');
  await login(page, { userIdx: 0 });
  assert((await text(page)).includes('已登录'), '首次账密登录成功');
  assert(!(await text(page)).includes('免密恢复'), '首次不算免密恢复');

  // 关掉页面，同一个 context 重开 —— storage 保留，模拟「下次进小程序」
  await page.close();
  const page2 = await ctx.newPage();
  page2.on('pageerror', e => errs.push(e.message));
  await page2.goto(BASE, { waitUntil: 'networkidle', timeout: 45000 });
  // 探活是异步 wx.request，固定 sleep 会偶发竞态（实测假失败过一次）→ 轮询等状态
  let t = '';
  for (let i = 0; i < 15; i++) {
    t = await text(page2);
    if (t.includes('已免密恢复') || t.includes('请输入平台账号密码')) break;
    await page2.waitForTimeout(600);
  }

  assert(t.includes('已免密恢复'), '第二次进入免密恢复成功');
  assert(t.includes('已用本地凭证免密恢复'), '明确提示是免密恢复');
  assert(!t.includes('平台账号密码'), '不再要求输入账密');
  assert(!t.includes('登录失败'), '不弹错误');
  assert(errs.length === 0, '无 JS 运行时错误' + (errs.length ? ': ' + errs.join(';') : ''));

  // 退出登录要清凭证
  await click(page2, '.btn.ghost');
  await page2.waitForTimeout(400);
  assert((await text(page2)).includes('密码'), '退出登录后回到账密表单');
  await page2.close();
  const page3 = await ctx.newPage();
  await page3.goto(BASE, { waitUntil: 'networkidle', timeout: 45000 });
  await page3.waitForTimeout(2000);
  assert(!(await text(page3)).includes('已免密恢复'), '退出后不再免密');

  await ctx.close();
}

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
  });
  await scenario(browser, 'A 完整画像 → 长辈版深度文化讲解', {
    userIdx: 0, version: '长辈版', injected: true, expectAvoid: true,
  });
  await scenario(browser, 'B 稀薄画像 → 退回通用版、不注入', {
    userIdx: 1, version: '通用版', injected: false,
  });
  await scenario(browser, 'C 含占位词画像 → 不按「未知」选版本', {
    userIdx: 2, version: '通用版', injected: false, expectPlaceholderStripped: true,
  });
  await scenario(browser, 'D 错误密码 → 拒绝登录', {
    userIdx: 0, wrongPassword: true, password: 'wrong',
  });
  await scenarioSilentRestore(browser);
  await browser.close();
  console.log('\n全部场景通过。');
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
