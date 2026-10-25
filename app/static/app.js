/* Where to Travel — 前端（多轮对话版 + 用户系统） */

const $ = (s) => document.querySelector(s);
const show = (el) => el.classList.remove('hidden');
const hide = (el) => el.classList.add('hidden');

let sessionId = null;
let readyForItinerary = false;
let map = null;
let mapLayer = null;
let lastItinerary = null;
let busy = false;
let currentUser = null;      // 登录用户，null = 匿名

// ────────── 基础 ──────────

async function loadStats() {
  try {
    const d = await (await fetch('/api/stats')).json();
    $('#stats').textContent =
      `${d.attractions} 个景区 · ${d.crowd_index} 条人流`;
  } catch (e) { /* 忽略 */ }
}

// ⚠️ 所有请求都要带 cookie（credentials），否则后端认不出登录用户
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `请求失败 (${r.status})`);
  return d;
}

async function getJSON(url) {
  const r = await fetch(url, { credentials: 'include' });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `请求失败 (${r.status})`);
  return d;
}

function loading(on, text) {
  const el = $('#loading');
  if (text) $('#loading-text').textContent = text;
  on ? show(el) : hide(el);
}

function scrollToBottom() {
  const box = $('#messages');
  box.scrollTop = box.scrollHeight;
}

// ────────── 消息渲染 ──────────

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  div.appendChild(bubble);
  $('#messages').appendChild(div);
  scrollToBottom();
  return div;
}

function addTyping() {
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.id = 'typing';
  div.innerHTML = '<div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>';
  $('#messages').appendChild(div);
  scrollToBottom();
  return div;
}

function removeTyping() {
  const t = $('#typing');
  if (t) t.remove();
}

// ────────── 画像面板 ──────────

const FIELD_LABELS = {
  primary: '动机',
  primary_intensity: null,      // 跟 primary 合并显示
  secondary: '次要',
  hours: '时长',
  companions: '同伴',
  pace: '节奏',
  interests: '兴趣',
  avoid: '避开',
  must_see: '必去',
};

function renderProfile(p) {
  const box = $('#profile');
  const keys = Object.keys(FIELD_LABELS).filter(k => p[k] !== undefined && p[k] !== null && p[k] !== '');
  if (!keys.length) {
    box.innerHTML = '<div class="empty">还在了解中……</div>';
    return;
  }

  let html = '';
  // 主动机单独突出
  if (p.primary) {
    const inten = p.primary_intensity || 3;
    html += `
      <div class="pf-primary">
        <span class="pf-main">${p.primary}</span>
        <span class="pf-inten">${inten}/5</span>
      </div>
      <div class="bar"><i style="width:${inten * 20}%"></i></div>`;
  }

  const rows = [];
  if (p.secondary && p.secondary.length) rows.push(['次要', p.secondary.join('、')]);
  if (p.hours) rows.push(['时长', `约 ${p.hours} 小时`]);
  if (p.companions) rows.push(['同伴', p.companions]);
  if (p.pace) rows.push(['节奏', p.pace]);
  if (p.interests && p.interests.length) rows.push(['兴趣', p.interests.join('、')]);
  if (p.avoid && p.avoid.length) rows.push(['避开', p.avoid.join('、')]);
  if (p.must_see && p.must_see.length) rows.push(['必去', p.must_see.join('、')]);

  if (rows.length) {
    html += '<dl class="pf-list">';
    for (const [k, v] of rows) {
      html += `<dt>${k}</dt><dd>${v}</dd>`;
    }
    html += '</dl>';
  }
  box.innerHTML = html;
}

// ────────── 发送 ──────────

async function send(text) {
  if (busy) return;
  const t = (text || $('#input').value).trim();
  if (!t) return;

  busy = true;
  $('#input').value = '';
  $('#input').style.height = 'auto';
  hide($('#starters'));

  addMessage('user', t);
  addTyping();
  loading(true, '正在理解你的想法……');

  try {
    const d = await postJSON('/api/chat', { text: t, session_id: sessionId });

    sessionId = d.session_id;
    removeTyping();
    addMessage('assistant', d.reply);
    renderProfile(d.profile || {});

    // 匿名用户第一次生成行程后，提示登录
    if (d.logged_in === false && d.itinerary) {
      showLoginHint();
    }

    readyForItinerary = !!d.ready;
    if (readyForItinerary && !lastItinerary) show($('#cta-block'));
    show($('#btn-restart'));

    // AI 直接生成了行程
    if (d.itinerary || d.action === 'generate') {
      const it = d.itinerary;
      if (it) {
        lastItinerary = it;
        renderItinerary(it);
        show($('#result-block'));
        $('#result-block').scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }

    // AI 提议修改 → 显示确认卡片
    if (d.proposal) {
      showProposal(d.proposal);
    }

    if (d.action_error) {
      addMessage('assistant', `（${d.action_error}）`);
    }
  } catch (e) {
    removeTyping();
    addMessage('assistant', `抱歉，出了点问题：${e.message}`);
  } finally {
    loading(false);
    busy = false;
    $('#input').focus();
  }
}

// 匿名用户看到行程后 → 提示登录可保存（不强制）
function showLoginHint() {
  if (currentUser || document.getElementById('login-hint')) return;
  const box = document.createElement('div');
  box.className = 'msg assistant';
  box.id = 'login-hint';
  box.innerHTML = `
    <div class="bubble hint-bubble">
      这一版行程只在当前页面，<b>刷新就没了</b>。
      <a href="/login?next=%2Fchat" class="hint-login">登录</a>后可以保存到账号，以后能翻回来。
    </div>`;
  $('#messages').appendChild(box);
  scrollToBottom();
}

// ────────── 修改确认卡片 ──────────

const ACTION_LABELS = {
  replace: '换掉', remove: '去掉', add: '增加一站',
  reorder: '调整顺序', regenerate: '重新生成整条',
};

function showProposal(p) {
  const label = ACTION_LABELS[p.action] || '调整';
  const box = document.createElement('div');
  box.className = 'msg assistant';
  box.innerHTML = `
    <div class="bubble proposal">
      <div class="proposal-title">待确认的修改</div>
      <div class="proposal-body">
        ${label}${p.target ? `「${p.target}」` : ''}
        ${p.reason ? `<div class="proposal-reason">${p.reason}</div>` : ''}
      </div>
      <div class="proposal-actions">
        <button class="primary small" data-act="yes">确认修改</button>
        <button class="ghost small" data-act="no">取消</button>
      </div>
    </div>`;
  $('#messages').appendChild(box);
  scrollToBottom();

  box.querySelector('[data-act="yes"]').onclick = () => {
    box.querySelector('.proposal-actions').innerHTML = '<span class="ok-text">已确认</span>';
    applyModification(p);
  };
  box.querySelector('[data-act="no"]').onclick = () => {
    box.querySelector('.proposal-actions').innerHTML = '<span class="dim-text">已取消</span>';
    addMessage('assistant', '好的，那就不改。还有什么想调整的吗？');
  };
}

async function applyModification(p) {
  if (busy) return;
  busy = true;
  loading(true, '正在调整行程……');
  try {
    const d = await postJSON('/api/itinerary/modify', {
      session_id: sessionId,
      action: p.action,
      target: p.target,
    });

    lastItinerary = d;
    renderItinerary(d);
    show($('#result-block'));
    addMessage('assistant', '已经改好了，看看现在还合适吗？');
  } catch (e) {
    addMessage('assistant', `改不动：${e.message}`);
  } finally {
    loading(false);
    busy = false;
  }
}

// ────────── 生成行程 ──────────

async function makeItinerary() {
  if (busy) return;
  busy = true;
  loading(true, '正在编排行程……');

  try {
    const d = await postJSON('/api/itinerary', { session_id: sessionId });

    lastItinerary = d;
    renderItinerary(d);
    show($('#result-block'));
    $('#result-block').scrollIntoView({ behavior: 'smooth', block: 'start' });

    if (!currentUser) showLoginHint();
  } catch (e) {
    alert('生成失败：' + e.message);
  } finally {
    loading(false);
    busy = false;
  }
}

function renderItinerary(d) {
  $('#narrative').textContent = d.narrative || '（未生成叙述）';

  const a = d.assessment || {};
  $('#assessment').innerHTML = `
    <div>整体强度：<span class="lvl ${a.intensity || ''}">${a.intensity || '—'}</span></div>
    ${a.strength ? `<div class="a-line">${a.strength}</div>` : ''}
    ${a.suggestion ? `<div class="a-line accent">建议：${a.suggestion}</div>` : ''}
    ${(d.risks || []).map(r => `<div class="risk">${r}</div>`).join('')}
  `;

  const stops = d.stops || [];
  $('#timeline').innerHTML = stops.map(s => {
    let crowd = '';
    if (s.crowd !== null && s.crowd !== undefined) {
      const cls = s.crowd >= 60 ? 'crowd-high' : (s.crowd <= 10 ? 'crowd-low' : '');
      crowd = `<span class="badge ${cls}">人流 ${s.crowd.toFixed(0)}</span>`;
    }
    const metro = s.metro
      ? `<span class="badge">${String(s.metro).slice(0, 14)}</span>` : '';
    const reasons = (s.reasons && s.reasons.length)
      ? `<div class="stop-reasons">${s.reasons.join('；')}</div>` : '';
    return `
      <div class="stop">
        <div class="stop-head">
          <span class="stop-time">${s.arrive}</span>
          <span class="stop-name">${s.name}</span>
          <span class="badge">${s.level || '—'}</span>
          ${crowd}${metro}
        </div>
        <div class="stop-meta">${s.district || ''} · 停留约 ${s.duration_min} 分钟</div>
        ${reasons}
      </div>`;
  }).join('') + `<div class="stop-meta total">
      全程约 ${d.total_distance_km} 公里（直线估算）</div>`;

  renderMap(stops);
}

function renderMap(stops) {
  if (!stops || !stops.length) return;
  const valid = stops.filter(s => s.lat != null && s.lon != null);
  if (!valid.length) {
    $('#map').innerHTML = '<div class="empty">无坐标数据</div>';
    return;
  }
  if (!map) {
    map = L.map('map').setView([valid[0].lat, valid[0].lon], 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18, attribution: '&copy; OpenStreetMap',
    }).addTo(map);
  }
  if (mapLayer) map.removeLayer(mapLayer);
  mapLayer = L.layerGroup().addTo(map);

  const coords = [];
  valid.forEach((s, i) => {
    coords.push([s.lat, s.lon]);
    L.marker([s.lat, s.lon])
      .bindPopup(`<b>${i + 1}. ${s.name}</b><br>${s.arrive} · ${s.district || ''}`)
      .addTo(mapLayer);
  });
  if (coords.length > 1) {
    L.polyline(coords, { color: '#4c8dff', weight: 2.5, opacity: 0.85 }).addTo(mapLayer);
    map.fitBounds(coords, { padding: [30, 30] });
  }
  setTimeout(() => map.invalidateSize(), 120);
}

// ────────── 重置 ──────────

function restart() {
  sessionId = null;
  readyForItinerary = false;
  lastItinerary = null;
  $('#messages').innerHTML = '';
  $('#profile').innerHTML = '<div class="empty">还没开始聊</div>';
  hide($('#cta-block'));
  hide($('#result-block'));
  hide($('#btn-restart'));
  show($('#starters'));
  $('#result-block').classList.add('hidden');
  if (mapLayer && map) { map.removeLayer(mapLayer); mapLayer = null; }
  greet();
  $('#input').focus();
}

function greet() {
  addMessage('assistant',
    '你好，我是 Where to Travel 的旅行助手。\n\n先别急着说去哪——我更想知道，你这次是**为什么**想出去走走？');
}

// ────────── 用户系统 ──────────

async function refreshUser() {
  try {
    const d = await getJSON('/api/auth/me');
    currentUser = d.user;
  } catch (e) {
    currentUser = null;
  }
  renderUserBox();
}

function renderUserBox() {
  const box = $('#user-box');
  if (!box) return;
  if (currentUser) {
    const tag = currentUser.role === 'agency'
      ? `<span class="role-badge">文旅局</span>` : '';
    const org = currentUser.org_name
      ? `<span class="org-name">${esc(currentUser.org_name)}</span>` : '';
    box.innerHTML = `${tag}${org}<span class="user-name">${esc(currentUser.nickname || currentUser.email)}</span>
      ${currentUser.role === 'agency' ? '<a href="/console">开发台</a>' : ''}
      <a href="#" id="btn-logout">退出</a>`;
    $('#btn-logout').onclick = async (e) => {
      e.preventDefault();
      await postJSON('/api/auth/logout', {});
      currentUser = null;
      renderUserBox();
      addMessage('assistant', '已退出登录。当前对话仍在页面上，但刷新后就没了。');
    };
    show($('#btn-history'));
  } else {
    // ⚠️ 登录入口不放在本页 —— 跳独立登录页，登录后回到对话
    box.innerHTML = `<a href="/login?next=%2Fchat" id="btn-login">登录</a>`;
    hide($('#btn-history'));
  }
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

// 登录/注册统一走独立页 /login（本页不再内嵌弹窗）。
// 需要用户主动登录的场景（分享、看历史）一律跳转，并带 next 回跳地址。
function gotoLogin(nextPath) {
  location.href = '/login?next=' + encodeURIComponent(nextPath || '/chat');
}

async function openHistory() {
  show($('#history-drawer'));
  const list = $('#history-list');
  list.innerHTML = '<div class="empty">载入中……</div>';
  try {
    const d = await getJSON('/api/history');
    if (!d.items.length) {
      list.innerHTML = '<div class="empty">还没有保存的行程。</div>';
      return;
    }
    list.innerHTML = d.items.map((it) => `
      <div class="history-item" data-sid="${it.id}">
        <div class="hi-main">
          <div class="hi-motiv">${esc(it.motivation || '未定动机')}</div>
          <div class="hi-meta">${fmtTime(it.created_at)} · ${it.turn_count} 轮${it.has_itinerary ? ' · 有行程' : ''}</div>
        </div>
        <button class="hi-del" data-del="${it.id}" title="删除">×</button>
      </div>`).join('');

    list.querySelectorAll('.history-item').forEach((el) => {
      el.onclick = (e) => {
        if (e.target.dataset.del) return;
        loadHistory(el.dataset.sid);
      };
    });
    list.querySelectorAll('.hi-del').forEach((el) => {
      el.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm('删除这次记录？')) return;
        try {
          await fetch(`/api/history/${el.dataset.del}`, {
            method: 'DELETE', credentials: 'include',
          });
          el.closest('.history-item').remove();
        } catch (err) { alert(err.message); }
      };
    });
  } catch (e) {
    list.innerHTML = `<div class="empty">载入失败：${esc(e.message)}</div>`;
  }
}

async function loadHistory(sid) {
  try {
    const d = await getJSON(`/api/history/${sid}`);
    hide($('#history-drawer'));
    $('#messages').innerHTML = '';
    sessionId = d.session_id;
    (d.messages || []).forEach((m) => {
      addMessage(m.role === 'user' ? 'user' : 'assistant', m.content);
    });
    if (d.itinerary) {
      lastItinerary = d.itinerary;
      renderItinerary(d.itinerary);
      show($('#result-block'));
    }
    addMessage('assistant', `（已载入 ${fmtTime(d.created_at)} 的对话，继续聊会接着这个会话。）`);
  } catch (e) { alert(e.message); }
}

function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return iso.slice(0, 16);
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// ────────── 事件绑定 ──────────

$('#btn-send').onclick = () => send();
$('#btn-itinerary').onclick = makeItinerary;
$('#btn-restart').onclick = restart;

$('#input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

// 自动调整高度
$('#input').addEventListener('input', function () {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 140) + 'px';
});

document.querySelectorAll('button.st').forEach(btn => {
  btn.onclick = () => send(btn.textContent);
});

// 历史抽屉
$('#btn-history').onclick = openHistory;
$('#history-close').onclick = () => hide($('#history-drawer'));

// ────────── 启动 ──────────

loadStats();
greet();
refreshUser();
$('#input').focus();

// ────────── 分享行程 ──────────

(function initShare() {
  const btn = document.getElementById('btn-share');
  const modal = document.getElementById('share-modal');
  if (!btn || !modal) return;

  btn.onclick = () => {
    if (!lastItinerary) { alert('先生成一条行程再分享'); return; }
    if (!currentUser) {
      // ⚠️ 匿名会话刷新即丢 —— 先把行程暂存到浏览器，登录回来再接上
      try {
        sessionStorage.setItem('pending_share',
          JSON.stringify({ itinerary: lastItinerary, at: Date.now() }));
      } catch (e) { /* 存不下就算了 */ }
      gotoLogin('/chat');
      return;
    }
    openShareForm(lastItinerary);
  };

  function openShareForm(itin) {
    const mot = (itin.motivation || '').trim();
    document.getElementById('share-title').value =
      mot ? `${mot} · 一日行程` : '我的一日行程';
    document.getElementById('share-body').value = '';
    document.getElementById('share-error').textContent = '';
    modal.classList.remove('hidden');
  }
  window.__openShareForm = openShareForm;

  // 登录后若有待分享的行程，自动弹出
  (function resumePendingShare() {
    let raw = null;
    try { raw = sessionStorage.getItem('pending_share'); } catch (e) {}
    if (!raw) return;
    try {
      const p = JSON.parse(raw);
      // 30 分钟内有效
      if (!p.itinerary || Date.now() - (p.at || 0) > 30 * 60 * 1000) {
        sessionStorage.removeItem('pending_share');
        return;
      }
      sessionStorage.removeItem('pending_share');
      lastItinerary = p.itinerary;
      const wait = setInterval(() => {
        if (currentUser) {
          clearInterval(wait);
          openShareForm(p.itinerary);
          addMessage('assistant', '欢迎回来。接着把刚才那条行程分享出去吧。');
        }
      }, 400);
      setTimeout(() => clearInterval(wait), 15000);
    } catch (e) { sessionStorage.removeItem('pending_share'); }
  })();

  document.getElementById('share-close').onclick =
    () => modal.classList.add('hidden');
  modal.onclick = (e) => {
    if (e.target === modal) modal.classList.add('hidden');
  };

  document.getElementById('share-submit').onclick = async () => {
    const title = document.getElementById('share-title').value.trim();
    const body = document.getElementById('share-body').value.trim();
    const err = document.getElementById('share-error');
    if (!title) { err.textContent = '给行程起个名字吧'; return; }

    const btnS = document.getElementById('share-submit');
    btnS.disabled = true;
    try {
      await postJSON('/api/posts', {
        title,
        body,
        type: 'inspiration',
        itinerary: lastItinerary,
        motivation: lastItinerary.motivation || null,
        cover_url: null,
      });
      modal.classList.add('hidden');
      addMessage('assistant',
        `已发布到「旅游灵感」：**${title}**。去首页能看到它。`);
    } catch (e) {
      err.textContent = e.message;
    } finally {
      btnS.disabled = false;
    }
  };
})();

// ────────── 从浏览页带词进来 ──────────
// /chat?q=成都  → 填进输入框，不自动发送（让用户补全意图）
(function fillQuery() {
  const q = new URLSearchParams(location.search).get('q');
  if (!q) return;
  const input = document.getElementById('input');
  if (input) {
    input.value = q;
    input.focus();
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  }
})();
