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
  // 补引号转义（BUG-8）：textContent→innerHTML 不处理引号，
  // 值插入 src="..."/value="..." 等属性时可被引号逃逸
  return d.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

let editing = null;   // 正在编辑的智能体，null = 新建

const KIND_LABEL = { builtin: '平台内自建', external: '外部智能体' };

/** 按类型切换表单可见字段 + 提示语 */
function applyKind(kind, isEdit) {
  const k = kind === 'external' ? 'external' : 'builtin';
  $('#fld-builtin').classList.toggle('hidden', k !== 'builtin');
  $('#fld-external').classList.toggle('hidden', k !== 'external');
  $('#kind-hint').textContent = k === 'external'
    ? '外部智能体：你的智能体在别处（Dify / Coze / 自建），我们只负责转发'
    : '平台内自建：零额外部署，填一段人设就能回答';
  // ⚠️ 类型定了不让改（后端 update_agent 也不接受 kind）——
  //    两条轨的准入条件不同，中途换轨会让原本合法的记录变成不合法
  $('#a-kind').disabled = !!isEdit;
  if (isEdit) {
    $('#kind-hint').textContent += '　（类型创建后不可修改）';
  }
}

function card(a) {
  const pub = a.status === 'published';
  const kind = a.kind === 'external' ? 'external' : 'builtin';
  const body = kind === 'external'
    ? `<p class="ag-prompt">🔗 ${esc(a.endpoint || '未填写调用地址')}
         ${a.has_auth ? '　🔑 已设置鉴权' : '　（无鉴权）'}</p>`
    : (a.prompt
        ? `<p class="ag-prompt">${esc(a.prompt.slice(0, 90))}${a.prompt.length > 90 ? '…' : ''}</p>`
        : '');
  return `
    <div class="agent-card ${pub ? 'is-pub' : ''}" data-id="${a.id}">
      <div class="ag-head">
        <b class="ag-name">${esc(a.name)}</b>
        <span class="ag-status ${pub ? 'pub' : 'draft'}">
          ${pub ? '已发布' : '草稿'}
        </span>
      </div>
      <div class="ag-region">
        📍 ${esc(a.region || '未设置覆盖地区')}
        <span class="ag-kind kind-${kind}">${KIND_LABEL[kind]}</span>
      </div>
      ${a.description ? `<p class="ag-desc">${esc(a.description)}</p>` : ''}
      ${body}
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
  $('#a-endpoint').value = item?.endpoint || '';
  // 后端不回传 auth 明文。编辑时留空 = 不改；填了才覆盖；勾「清除」才清空
  $('#a-auth').value = '';
  $('#a-auth').checked = false;
  $('#a-auth-clear').checked = false;
  $('#a-auth').placeholder = item?.has_auth ? '已设置（留空则不修改）' : 'Bearer sk-xxxxx';
  // 只有「原本就有鉴权」时才给清除入口
  $('#auth-clear-row').classList.toggle('hidden', !item?.has_auth);

  const kind = item?.kind === 'external' ? 'external' : 'builtin';
  $('#a-kind').value = kind;
  applyKind(kind, !!item);

  $('#form-error').textContent = '';
  $('#agent-modal').classList.remove('hidden');
  $('#a-name').focus();
}

$('#a-kind').onchange = () => applyKind($('#a-kind').value, false);

$('#btn-new').onclick = () => openForm(null);
$('#agent-close').onclick = () => $('#agent-modal').classList.add('hidden');
$('#agent-modal').onclick = (e) => {
  if (e.target.id === 'agent-modal') $('#agent-modal').classList.add('hidden');
};

$('#form-save').onclick = async () => {
  const kind = $('#a-kind').value === 'external' ? 'external' : 'builtin';
  const payload = {
    name: $('#a-name').value.trim(),
    region: $('#a-region').value.trim(),
    description: $('#a-desc').value.trim(),
  };
  const err = $('#form-error');

  if (kind === 'external') {
    payload.endpoint = $('#a-endpoint').value.trim();
    // ⚠️ auth 三种情况，语义必须分清：
    //   填了新值        → 覆盖
    //   留空            → 不改（后端不回传明文，所以空值不能当「清空」）
    //   勾了「清除」     → 显式传空字符串
    const authInput = $('#a-auth').value.trim();
    if ($('#a-auth-clear').checked) {
      payload.auth = '';
    } else if (authInput) {
      payload.auth = authInput;
    }
    if (!payload.endpoint) { err.textContent = '外部智能体必须填写调用地址'; return; }
  } else {
    payload.prompt = $('#a-prompt').value.trim();
    if (!payload.prompt) { err.textContent = '人设与话术不能为空'; return; }
  }

  if (!payload.name) { err.textContent = '名称不能为空'; return; }

  const btn = $('#form-save');
  btn.disabled = true;
  try {
    if (editing) {
      await api(`/api/agents/${editing.id}`,
                { method: 'POST', body: JSON.stringify(payload) });
    } else {
      await api('/api/agents',
                { method: 'POST', body: JSON.stringify({ ...payload, kind }) });
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
