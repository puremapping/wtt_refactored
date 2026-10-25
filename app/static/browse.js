/* 浏览页：三页签 + 瀑布流 + 搜索 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

let currentTab = 'content';
let currentKeyword = '';
let currentPage = 1;
let hasMore = true;
let loading = false;
let me = null;

// ── API ──
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

// ── 卡片 ──
const TAB_LABEL = { content: '内容', inspiration: '旅游灵感', hot: '今日热榜' };

function cardHTML(p) {
  const isInsp = p.type === 'inspiration';
  const cover = p.cover_url
    ? `<img src="${esc(p.cover_url)}" alt="" loading="lazy">`
    : `<div class="no-cover">${isInsp ? '🗺️' : '📷'}</div>`;

  const motiv = p.motivation
    ? `<span class="tag">${esc(p.motivation)}</span>` : '';

  const stat = isInsp
    ? `<div class="insp-stat">📍 ${p.stops_count} 站 · ${p.hours || '—'} 小时</div>`
    : '';

  return `
    <article class="card" data-id="${p.id}">
      <div class="cover">${cover}</div>
      <div class="card-body">
        ${stat}
        <h3 class="card-title">${esc(p.title)}</h3>
        ${motiv}
        <div class="card-foot">
          <span class="author">${esc(p.author.name)}</span>
          <span class="like ${p.liked ? 'on' : ''}" data-like="${p.id}">
            ♥ ${p.likes}
          </span>
        </div>
      </div>
    </article>`;
}

// ── 加载 ──
async function loadPosts(reset = false) {
  if (loading) return;
  if (reset) { currentPage = 1; hasMore = true; $('#feed').innerHTML = ''; }
  if (!hasMore) return;

  loading = true;
  $('#loading').classList.remove('hidden');

  try {
    const qs = new URLSearchParams({
      tab: currentTab, page: currentPage, size: 20,
    });
    if (currentKeyword) qs.set('keyword', currentKeyword);

    const d = await api('/api/posts?' + qs);

    if (!d.items.length && reset) {
      $('#empty').classList.remove('hidden');
    } else {
      $('#empty').classList.add('hidden');
    }

    $('#feed').insertAdjacentHTML('beforeend',
      d.items.map(cardHTML).join(''));

    hasMore = d.has_more;
    currentPage++;
    bindCards();
  } catch (e) {
    $('#feed').insertAdjacentHTML('beforeend',
      `<div class="feed-state">加载失败：${esc(e.message)}</div>`);
  } finally {
    loading = false;
    $('#loading').classList.add('hidden');
  }
}

function bindCards() {
  $$('.card').forEach((el) => {
    if (el.dataset.bound) return;
    el.dataset.bound = '1';
    el.addEventListener('click', (e) => {
      if (e.target.dataset.like) return;
      openPost(el.dataset.id);
    });
  });
  $$('[data-like]').forEach((el) => {
    if (el.dataset.boundLike) return;
    el.dataset.boundLike = '1';
    el.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!me) { location.href = '/chat'; return; }
      try {
        const d = await api(`/api/posts/${el.dataset.like}/like`, { method: 'POST' });
        el.classList.toggle('on', d.liked);
        el.textContent = '♥ ' + d.likes;
      } catch (err) { alert(err.message); }
    });
  });
}

// ── 详情 ──
async function openPost(id) {
  try {
    const p = await api(`/api/posts/${id}`);
    const imgs = (p.images || []).length
      ? `<div class="detail-gallery">${p.images.map(u =>
          `<img src="${esc(u)}" alt="">`).join('')}</div>` : '';

    const itin = p.itinerary && p.itinerary.stops
      ? `<div class="detail-itin">
           <h4>行程安排</h4>
           ${p.itinerary.stops.map((s, i) =>
             `<div class="stop-row"><b>${i + 1}</b> ${esc(s.name)}
              ${s.arrive ? `<span class="dim">${esc(s.arrive)}</span>` : ''}</div>`
           ).join('')}
         </div>` : '';

    $('#post-body').innerHTML = `
      <h2 class="detail-title">${esc(p.title)}</h2>
      <div class="detail-meta">
        @${esc(p.author.name)} · ${(p.created_at || '').slice(0, 10)}
        ${p.motivation ? `<span class="tag">${esc(p.motivation)}</span>` : ''}
      </div>
      ${imgs}
      ${p.body ? `<p class="detail-text">${esc(p.body)}</p>` : ''}
      ${itin}
      <div class="detail-foot">
        <button class="like-btn ${p.liked ? 'on' : ''}" id="detail-like">
          ♥ ${p.likes}
        </button>
        <span class="dim">${p.views} 次浏览</span>
      </div>
      <div class="comments">
        <h4>评论</h4>
        <div id="comment-list"></div>
        <div class="comment-input">
          <input id="comment-text" placeholder="说点什么…">
          <button id="comment-send" class="primary small">发送</button>
        </div>
      </div>`;

    $('#post-modal').classList.remove('hidden');
    loadComments(id);

    $('#detail-like').onclick = async (e) => {
      if (!me) return;
      const d = await api(`/api/posts/${id}/like`, { method: 'POST' });
      e.target.classList.toggle('on', d.liked);
      e.target.textContent = '♥ ' + d.likes;
    };

    $('#comment-send').onclick = async () => {
      if (!me) { alert('登录后才能评论'); return; }
      const t = $('#comment-text').value.trim();
      if (!t) return;
      await api(`/api/posts/${id}/comments`,
                { method: 'POST', body: JSON.stringify({ content: t }) });
      $('#comment-text').value = '';
      loadComments(id);
    };
  } catch (e) { alert(e.message); }
}

async function loadComments(postId) {
  try {
    const d = await api(`/api/posts/${postId}/comments`);
    $('#comment-list').innerHTML = d.items.length
      ? d.items.map(c => `
          <div class="comment-item">
            <b>${esc(c.author.name)}</b>
            <span>${esc(c.content)}</span>
          </div>`).join('')
      : '<div class="dim">还没有评论</div>';
  } catch (e) { /* 忽略 */ }
}

$('#post-close').onclick = () => $('#post-modal').classList.add('hidden');
$('#post-modal').onclick = (e) => {
  if (e.target.id === 'post-modal') $('#post-modal').classList.add('hidden');
};

// ── 页签 ──
$$('.tab').forEach((btn) => {
  btn.onclick = () => {
    $$('.tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentTab = btn.dataset.tab;
    loadPosts(true);
  };
});

// ── 搜索 ──
$('#search-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    currentKeyword = $('#search-input').value.trim();
    loadPosts(true);
  }
});

// 搜索框旁边的 AI 按钮：把词带进对话页
$('#btn-ai').onclick = () => {
  const q = $('#search-input').value.trim();
  location.href = '/chat' + (q ? '?q=' + encodeURIComponent(q) : '');
};

// ── 无限滚动 ──
window.addEventListener('scroll', () => {
  if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 600) {
    loadPosts();
  }
});

// ── 初始化 ──
function renderAuthNav() {
  const el = $('#nav-auth');
  if (!el) return;
  if (me) {
    el.href = '/me';
    el.textContent = me.nickname || '我的';
  } else {
    el.href = '/login?next=%2F';
    el.textContent = '登录';
  }
}

(async function init() {
  try { me = (await api('/api/auth/me')).user; } catch (e) { me = null; }
  renderAuthNav();
  loadPosts(true);
})();
