// 用 CDP 直驱 headless Chrome 验证前端面板的真实行为（不依赖 playwright 包）
// 跑法：node spike_sse_stream/_ui_test.mjs
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const PORT = 9333;
const profile = 'C:/Users/mengzhe/AppData/Local/Temp/wtt-spike-prof';

const chrome = spawn(CHROME, [
  '--headless=new', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
  '--disable-gpu', '--disable-dev-shm-usage', 'about:blank',
], { stdio: ['ignore', 'pipe', 'pipe'] });
chrome.stderr.on('data', (d) => {
  const s = d.toString();
  if (/DevTools listening|error/i.test(s)) console.log('[chrome]', s.trim().slice(0, 200));
});
chrome.on('exit', (code) => console.log('[chrome] exited', code));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function cdpTargets() {
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const list = await r.json();
      const page = list.find((t) => t.type === 'page');
      if (page) return page;
    } catch { /* 还没起来 */ }
    await sleep(250);
  }
  throw new Error('chrome 没起来');
}

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map();
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && this.pending.has(msg.id)) {
        this.pending.get(msg.id)(msg);
        this.pending.delete(msg.id);
      }
    };
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      this.pending.set(id, (m) => (m.error ? rej(new Error(m.error.message)) : res(m.result)));
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async eval(expr) {
    const r = await this.send('Runtime.evaluate', {
      expression: expr, awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) throw new Error(r.result?.description || 'eval error');
    return r.result.value;
  }
}

const results = [];
function check(name, ok, extra = '') {
  results.push({ name, ok, extra });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  — ' + extra : ''}`);
}

try {
  const t = await cdpTargets();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  const c = new CDP(ws);
  await c.send('Page.enable');
  await c.send('Runtime.enable');
  await c.send('Page.navigate', { url: 'http://127.0.0.1:8077/spike' });
  await sleep(1200);

  // ── 场景 1：正常对话 ──
  await fetch('http://127.0.0.1:8077/api/_mode?plan=chat');
  await c.eval(`(() => {
    const ta = document.querySelector('#input');
    ta.value = '想去北京散心';
    ta.dispatchEvent(new Event('input'));
    document.querySelector('#send').click();
  })()`);

  // 采样「第一个字出现的时间」—— 验证真的是流式而不是最后一次性吐出
  let firstCharAt = null, lastLen = 0, samples = [];
  for (let i = 0; i < 120; i++) {
    const s = await c.eval(`(() => {
      const b = document.querySelectorAll('.proc ~ .bubble, .msg.assistant .bubble:not(#__none)');
      const el = [...document.querySelectorAll('.msg.assistant .bubble')].pop();
      return { open: document.querySelector('.proc')?.dataset.open,
               len: el ? el.textContent.length : 0,
               head: document.querySelector('.proc-head .sum')?.textContent || '' };
    })()`);
    if (s.len > 0 && firstCharAt === null) firstCharAt = i;
    if (s.len !== lastLen) samples.push(s.len);
    lastLen = s.len;
    if (s.open === '0' && s.head && !s.head.includes('…')) break;
    await sleep(100);
  }
  check('流式：正文逐步增长（非一次性）', samples.length > 5,
        `长度采样序列 ${samples.join(',')}`);
  check('流式：首字在 1s 内出现', firstCharAt !== null && firstCharAt < 10,
        `首个非空在第 ${firstCharAt} 次采样（每次 100ms）`);

  const s1 = await c.eval(`(() => {
    const p = document.querySelector('.proc');
    return { open: p.dataset.open, sum: p.querySelector('.sum').textContent,
             steps: [...p.querySelectorAll('.step')].map(d => d.innerText.replace(/\\s+/g,' ').trim()),
             reply: [...document.querySelectorAll('.msg.assistant .bubble')].pop().textContent };
  })()`);
  check('面板：完成后自动折叠', s1.open === '0', `open=${s1.open}`);
  check('面板：折叠摘要含轮数', /第 \d+ 轮/.test(s1.sum), s1.sum);
  check('面板：每步有结果（含耗时/字段）', s1.steps.length >= 3, s1.steps.join(' | ').slice(0, 160));
  check('正文：done 用权威全文覆盖（未重复拼接）', s1.reply.length > 20 && !s1.reply.includes('undefined'),
        `len=${s1.reply.length}`);

  // 展开折叠
  const s1b = await c.eval(`(() => {
    document.querySelector('.proc-head').click();
    return document.querySelector('.proc').dataset.open; })()`);
  check('面板：点击可展开', s1b === '1');

  // ── 场景 2：工具轮（正文为空，不能永远转圈）──
  await fetch('http://127.0.0.1:8077/api/_mode?plan=tool');
  await c.eval(`(() => {
    const ta = document.querySelector('#input');
    ta.value = '帮我排个行程';
    document.querySelector('#send').click();
  })()`);
  await sleep(3500);
  const s2 = await c.eval(`(() => {
    const all = [...document.querySelectorAll('.proc')];
    const p = all[all.length - 1];
    return { open: p.dataset.open, sum: p.querySelector('.sum').textContent,
             text: p.innerText.replace(/\\s+/g,' ').trim().slice(0,300),
             busy: document.querySelector('#send').disabled };
  })()`);
  check('工具轮：折叠摘要暴露「正文来自兜底」',
        /正文来自兜底/.test(s2.sum), s2.sum);
  check('工具轮：输入框已解锁（没卡住）', s2.busy === false);

  // ── 场景 3：抽取阶段失败 ──
  await fetch('http://127.0.0.1:8077/api/_mode?plan=chat&fail_at=extract');
  await c.eval(`(() => {
    document.querySelector('#input').value = '再来一次';
    document.querySelector('#send').click(); })()`);
  await sleep(4500);
  const s3 = await c.eval(`(() => {
    const all = [...document.querySelectorAll('.proc')];
    const p = all[all.length - 1];
    return { open: p.dataset.open, sum: p.querySelector('.sum').textContent,
             err: p.parentElement.querySelector('.errbox')?.textContent || '',
             busy: document.querySelector('#send').disabled };
  })()`);
  check('失败：显示错误框（不是永远转圈）', s3.err.includes('超时'), s3.err);
  check('失败：面板保持展开且头部标红', s3.open === '1' && /出错了/.test(s3.sum), s3.sum);
  check('失败：输入框已解锁', s3.busy === false);

  // ── 场景 4：流到一半失败 —— 已收到的正文要保留 ──
  await fetch('http://127.0.0.1:8077/api/_mode?plan=chat&fail_at=midway');
  await c.eval(`(() => {
    document.querySelector('#input').value = '中途会断';
    document.querySelector('#send').click(); })()`);
  await sleep(4000);
  const s4 = await c.eval(`(() => {
    const all = [...document.querySelectorAll('.proc')];
    const p = all[all.length - 1];
    const bubble = p.parentElement.querySelector('.bubble');
    return { err: p.parentElement.querySelector('.errbox')?.textContent || '',
             kept: bubble ? bubble.textContent.length : 0,
             busy: document.querySelector('#send').disabled,
             sum: p.querySelector('.sum').textContent };
  })()`);
  check('中途失败：保留已流出的正文', s4.kept >= 9, `保留 ${s4.kept} 字`);
  check('中途失败：有错误提示 + 解锁', s4.err.length > 0 && s4.busy === false, s4.err);

  // ── 场景 5：fetch 抛错的分支（服务端 400）──
  await fetch('http://127.0.0.1:8077/api/_mode?plan=chat');
  const s5 = await c.eval(`(async () => {
    const r = await fetch('/api/chat/stream', { method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({text:'   '}) });
    return { status: r.status, body: await r.json() };
  })()`);
  check('参数错：头发出前返回真实 400', s5.status === 400 && !!s5.body.error, JSON.stringify(s5.body));

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} 通过`);
  process.exitCode = failed.length ? 1 : 0;
} catch (e) {
  console.error('测试崩了：', e.message);
  process.exitCode = 2;
} finally {
  chrome.kill();
}
