const { chromium } = require('playwright');
/** AI 讲解端到端：模拟景区侧代理真调 BUPT 网关 */
const BASE = process.env.MVP_URL || 'http://127.0.0.1:3401/';
const PASSWORD = process.env.MVP_DEMO_PASSWORD || 'wtt-mvp-demo';

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
function assert(c, m) { if (!c) throw new Error('FAIL: ' + m); console.log('  ok - ' + m); }

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 460, height: 1000 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));

  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(2000);

  // 登录（R1）
  const f = await wv(page);
  await f.locator('.useritem').first().click();
  await f.locator('wx-input input[type="password"]').fill(PASSWORD);
  await f.locator('wx-input input[type="password"]').dispatchEvent('input');
  await page.waitForTimeout(300);
  await click(page, '.btn.primary');
  await page.waitForTimeout(1200);
  assert((await text(page)).includes('已登录'), '账密登录成功');

  // 拉 context
  await click(page, '.btn.primary');
  await page.waitForTimeout(1500);
  const t = await text(page);
  assert(t.includes('长辈版'), '个性化讲解版本生效');
  assert(t.includes('听 AI 讲这一站'), 'AI 讲解按钮出现');

  // 点第一站的 AI 讲解 —— 真调 BUPT 网关
  console.log('\n  正在调用 BUPT LLM（约 10-30 秒）…');
  await click(page, '.aibtn', 0);
  await page.waitForTimeout(2000);
  assert((await text(page)).includes('正在生成讲解'), '显示生成中状态');

  // 等答案出现（最多 90 秒）
  let answered = false;
  for (let i = 0; i < 45; i++) {
    const cur = await text(page);
    if (cur.includes('AI 讲解 · 内容由 AI 生成')) { answered = true; break; }
    await page.waitForTimeout(2000);
  }
  assert(answered, 'AI 讲解正文真的生成了');

  const final = await text(page);
  assert(final.includes('内容由 AI 生成，仅供参考'), 'AI 生成标识落地');
  assert(!final.includes('服务暂时不可用'), '没有报错');
  assert(final.length > t.length + 50, '答案确实追加了新内容');
  assert(errs.length === 0, '无 JS 运行时错误' + (errs.length ? ': ' + errs.join(';') : ''));

  // 打印答案片段作为实证
  const m = final.match(/AI 讲解 · 内容由 AI 生成，仅供参考\n([\s\S]{0,260})/);
  console.log('\n--- AI 讲解片段 ---\n' + (m ? m[1].trim() : '(未取到)'));

  await page.screenshot({ path: process.env.SHOT_PATH || 'ai-guide.png', fullPage: true });
  console.log('\n全部通过，截图已存。');
  await browser.close();
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
