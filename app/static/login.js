/* 登录 / 注册页 */
const $ = (s) => document.querySelector(s);

const init = window.__INITIAL__ || { role: 'person', next: '/' };
let mode = 'login';        // login | register
let role = init.role || 'person';

async function post(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `请求失败 (${r.status})`);
  return d;
}

function showError(msg) { $('#login-error').textContent = msg || ''; }

function applyMode() {
  const isReg = mode === 'register';
  $('#login-title').textContent = isReg ? '注册' : '登录';
  $('#login-submit').textContent = isReg ? '注册并继续' : '登录';
  $('#mode-toggle').textContent = isReg ? '已有账号？登录' : '还没有账号？注册';
  $('#role-picker').classList.toggle('hidden', !isReg);
  $('#reg-fields').classList.toggle('hidden', !isReg);
  $('#f-password').autocomplete = isReg ? 'new-password' : 'current-password';

  if (isReg) {
    $('#login-side-feats')?.classList.toggle('show-agency', role === 'agency');
  } else {
    // 登录时隐藏机构字段（登录不需要重新选身份）
    $('#agency-fields').classList.add('hidden');
  }
}

function applyRole() {
  document.querySelectorAll('.role-opt').forEach((b) => {
    b.classList.toggle('active', b.dataset.role === role);
  });
  $('#agency-fields').classList.toggle('hidden', role !== 'agency');
  // 文旅局注册时昵称非必填（会用机构名）
  const nick = $('#f-nickname');
  if (role === 'agency') {
    nick.placeholder = '留空则用机构名称';
  } else {
    nick.placeholder = '怎么称呼你';
  }
}

// 身份选择
document.querySelectorAll('.role-opt').forEach((btn) => {
  btn.onclick = () => { role = btn.dataset.role; applyRole(); };
});

// 登录 / 注册切换
$('#mode-toggle').onclick = (e) => {
  e.preventDefault();
  mode = mode === 'login' ? 'register' : 'login';
  showError('');
  applyMode();
};

// 提交
$('#login-form').onsubmit = async (e) => {
  e.preventDefault();
  const email = $('#f-email').value.trim();
  const password = $('#f-password').value;
  const nickname = $('#f-nickname')?.value.trim() || '';
  const org = $('#f-org')?.value.trim() || '';
  const region = $('#f-region')?.value.trim() || '';

  if (!email || !password) { showError('邮箱和密码都要填'); return; }
  if (mode === 'register' && role === 'agency' && !org) {
    showError('请填写机构名称'); return;
  }

  const btn = $('#login-submit');
  btn.disabled = true;
  showError('');

  try {
    if (mode === 'login') {
      await post('/api/auth/login', { email, password });
    } else {
      await post('/api/auth/register', {
        email, password, nickname,
        role, org_name: org, region,
      });
    }
    // 跳到 next；文旅局注册成功后直接进开发页
    let target = init.next || '/';
    if (mode === 'register' && role === 'agency') target = '/console';
    location.href = target;
  } catch (err) {
    showError(err.message);
    btn.disabled = false;
  }
};

// 初始化
applyMode();
if (mode === 'register') applyRole();
// 从 /login?role=agency 进来时，预选身份
if (init.role === 'agency') { role = 'agency'; applyRole(); }
