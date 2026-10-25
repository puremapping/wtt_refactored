/* 文旅局智能体开发页 */
const $ = (s) => document.querySelector(s);

const me = window.__ME__ || {};

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

let editing = null;   // 正在编辑的智能体，null = 新建

function card(a) {
  const pub = a.status === 'published';
  return `
    <div class="agent-card ${pub ? 'is-pub' : ''}" data-id="${a.id}">
      <div class="ag-head">
        <b class="ag-name">${esc(a.name)}</b>
        <span class="ag-status ${pub ? 'pub' : 'draft'}">
          ${pub ? '已发布' : '草稿'}
        </span>
      </div>
      <div class="ag-region">📍 ${esc(a.region || '未设置覆盖地区')}</div>
      ${a.description ? `<p class="ag-desc">${esc(a.description)}</p>` : ''}
      ${a.prompt ? `<p class="ag-prompt">${esc(a.prompt.slice(0, 90))}${a.prompt.length > 90 ? '…' : ''}</p>` : ''}
      <div class="ag-foot">
        <button class="ag-btn" data-act="edit">编辑</button>
        ${pub ? '' : `<button class="ag-btn primary-mini" data-act="publish">发布</button>`}
        <button class="ag-btn danger" data-act="del">删除</button>
      </div>
    </div>`;
}

async function loadList() {
  const box = $('#agent-list');
  box.innerHTML = '<div class="empty-state">载入中…</div>';
  try {
    const d = await api('/api/agents');
    if (!d.items.length) {
      box.innerHTML = `<div class="empty-state">
        还没有智能体。<br>
        点右上角「新建」，先填上<b>覆盖地区</b>和<b>人设话术</b>。
      </div>`;
      return;
    }
    box.innerHTML = d.items.map(card).join('');
    // ⚠️ 存成 id→item 映射，供 bind() 里「编辑」取原始数据用
    window.__AGENTS__ = {};
    d.items.forEach(a => { window.__AGENTS__[a.id] = a; });
    bind();
  } catch (e) {
    box.innerHTML = `<div class="empty-state">载入失败：${esc(e.message)}</div>`;
  }
}

function bind() {
  document.querySelectorAll('.ag-btn').forEach((btn) => {
    btn.onclick = async (ev) => {
      ev.stopPropagation();
      const el = btn.closest('.agent-card');
      const id = el.dataset.id;
      const act = btn.dataset.act;
      const item = (window.__AGENTS__ || {})[id];

      if (act === 'edit') openForm(item);
      if (act === 'del') {
        if (!confirm('删除这个智能体？')) return;
        try {
          await api(`/api/agents/${id}`, { method: 'DELETE' });
          loadList();
        } catch (e) { alert(e.message); }
      }
      if (act === 'publish') {
        btn.disabled = true;
        try {
          await api(`/api/agents/${id}/publish`, { method: 'POST' });
          loadList();
        } catch (e) {
          alert(e.message);
          btn.disabled = false;
        }
      }
    };
  });
}

function openForm(item) {
  editing = item || null;
  $('#form-title').textContent = item ? '编辑智能体' : '新建智能体';
  $('#a-name').value = item?.name || '';
  $('#a-region').value = item?.region || '';
  $('#a-desc').value = item?.description || '';
  $('#a-prompt').value = item?.prompt || '';
  $('#form-error').textContent = '';
  $('#agent-modal').classList.remove('hidden');
  $('#a-name').focus();
}

$('#btn-new').onclick = () => openForm(null);
$('#agent-close').onclick = () => $('#agent-modal').classList.add('hidden');
$('#agent-modal').onclick = (e) => {
  if (e.target.id === 'agent-modal') $('#agent-modal').classList.add('hidden');
};

$('#form-save').onclick = async () => {
  const payload = {
    name: $('#a-name').value.trim(),
    region: $('#a-region').value.trim(),
    description: $('#a-desc').value.trim(),
    prompt: $('#a-prompt').value.trim(),
  };
  const err = $('#form-error');
  if (!payload.name) { err.textContent = '名称不能为空'; return; }

  const btn = $('#form-save');
  btn.disabled = true;
  try {
    if (editing) {
      await api(`/api/agents/${editing.id}`,
                { method: 'POST', body: JSON.stringify(payload) });
    } else {
      await api('/api/agents', { method: 'POST', body: JSON.stringify(payload) });
    }
    $('#agent-modal').classList.add('hidden');
    loadList();
  } catch (e) {
    err.textContent = e.message;
  } finally {
    btn.disabled = false;
  }
};

// 启动
loadList();
