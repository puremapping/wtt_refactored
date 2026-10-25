/* 个人主页 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

async function api(path, opts = {}) {
  const r = await fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `请求失败 (${r.status})`);
  return d;
}
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

let me = null;

// ── 页签 ──
$$('.me-tab').forEach((btn) => {
  btn.onclick = () => {
    $$('.me-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    $$('.pane').forEach(p => p.classList.add('hidden'));
    $('#pane-' + btn.dataset.pane).classList.remove('hidden');

    if (btn.dataset.pane === 'memories') loadMemories();
    if (btn.dataset.pane === 'posts') loadMyPosts();
    if (btn.dataset.pane === 'messages') loadMessages();
  };
});

// ── 回忆 ──
async function loadMemories() {
  const box = $('#memories-list');
  box.innerHTML = '<div class="dim">载入中…</div>';
  try {
    const d = await api('/api/me/memories');
    if (!d.items.length) {
      box.innerHTML = `<div class="empty-state">
        还没有旅行记录。<br>
        <a href="/chat">去和 AI 聊聊</a>，生成一条行程就有了。
      </div>`;
      return;
    }
    box.innerHTML = d.items.map(m => `
      <div class="memory-card">
        <div class="mem-head">
          <b>${esc(m.motivation || '一次旅行')}</b>
          <span class="dim">${(m.created_at || '').slice(0, 10)}</span>
        </div>
        <div class="mem-stat">📍 ${m.stops_count} 站 · ${m.hours || '—'} 小时</div>
        ${m.narrative ? `<p class="mem-text">${esc(m.narrative)}…</p>` : ''}
        <div class="mem-foot">
          <span class="dim">${esc(m.session_id)}</span>
        </div>
      </div>`).join('');
  } catch (e) {
    box.innerHTML = `<div class="dim">载入失败：${esc(e.message)}</div>`;
  }
}

// ── 我发布的 ──
async function loadMyPosts() {
  const box = $('#my-posts');
  box.innerHTML = '<div class="dim">载入中…</div>';
  try {
    const d = await api('/api/posts?tab=content&size=50');
    const mine = d.items.filter(p => me && p.author.id === me.id);
    if (!mine.length) {
      box.innerHTML = `<div class="empty-state">
        还没发布过内容。<br>生成行程后可以一键分享。
      </div>`;
      return;
    }
    box.innerHTML = mine.map(p => `
      <article class="card" data-id="${p.id}">
        <div class="cover">
          ${p.cover_url ? `<img src="${esc(p.cover_url)}" loading="lazy">`
                        : `<div class="no-cover">${p.type === 'inspiration' ? '🗺️' : '📷'}</div>`}
        </div>
        <div class="card-body">
          <h3 class="card-title">${esc(p.title)}</h3>
          <div class="card-foot">
            <span class="dim">♥ ${p.likes}</span>
            <button class="del-btn" data-del="${p.id}">删除</button>
          </div>
        </div>
      </article>`).join('');

    box.querySelectorAll('[data-del]').forEach(el => {
      el.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm('删除这条内容？')) return;
        try {
          await api(`/api/posts/${el.dataset.del}`, { method: 'DELETE' });
          el.closest('.card').remove();
        } catch (err) { alert(err.message); }
      };
    });
  } catch (e) {
    box.innerHTML = `<div class="dim">载入失败：${esc(e.message)}</div>`;
  }
}

// ── 消息 ──
async function loadMessages() {
  const box = $('#messages-list');
  box.innerHTML = '<div class="dim">载入中…</div>';
  try {
    const d = await api('/api/messages');
    if (!d.items.length) {
      box.innerHTML = '<div class="empty-state">还没有消息</div>';
      return;
    }
    box.innerHTML = d.items.map(m => `
      <div class="msg-item ${m.is_read ? '' : 'unread'}">
        <span class="msg-type">${esc(m.type)}</span>
        <span class="msg-content">${esc(m.content)}</span>
        <span class="dim">${(m.created_at || '').slice(5, 16)}</span>
      </div>`).join('');
    // 标记已读
    await api('/api/messages/read', { method: 'POST', body: '{}' });
  } catch (e) {
    box.innerHTML = `<div class="dim">载入失败：${esc(e.message)}</div>`;
  }
}

// ── 资料 ──
async function loadProfile() {
  try {
    const p = await api('/api/me/profile');
    $('#nickname').textContent = p.nickname || '旅行者';
    $('#email-line').textContent = p.email || '';
    $('#city-line').textContent = p.city ? '📍 ' + p.city : '';
    $('#set-nickname').value = p.nickname || '';
    $('#set-city').value = p.city || '';
    $('#set-bio').value = p.bio || '';
    if (p.avatar_url) {
      $('#avatar').innerHTML = `<img src="${esc(p.avatar_url)}" alt="">`;
    }
  } catch (e) { /* 忽略 */ }
}

$('#set-save').onclick = async () => {
  try {
    await api('/api/me/profile', {
      method: 'POST',
      body: JSON.stringify({
        nickname: $('#set-nickname').value.trim(),
        city: $('#set-city').value.trim(),
        bio: $('#set-bio').value.trim(),
      }),
    });
    $('#set-msg').textContent = '✓ 已保存';
    loadProfile();
    setTimeout(() => { $('#set-msg').textContent = ''; }, 2000);
  } catch (e) {
    $('#set-msg').textContent = '保存失败：' + e.message;
  }
};

$('#btn-logout').onclick = async () => {
  await api('/api/auth/logout', { method: 'POST' });
  location.href = '/';
};

$('#btn-gologin').onclick = () => { location.href = '/chat'; };

$('#btn-ai').onclick = () => {
  const q = $('#search-input').value.trim();
  location.href = '/chat' + (q ? '?q=' + encodeURIComponent(q) : '');
};

// ── 初始化 ──
(async function init() {
  try {
    const d = await api('/api/auth/me');
    me = d.user;
  } catch (e) { me = null; }

  if (!me) {
    $('#need-login').classList.remove('hidden');
    return;
  }
  $('#me-content').classList.remove('hidden');
  await loadProfile();
  loadMemories();
})();
