const app = getApp()
const { KNOWLEDGE, VERSIONS } = require('../../data/knowledge.js')
const session = require('../../utils/session.js')

// 模拟景区侧的 AI 讲解代理（景区自建、密钥零落前端）
const SCENIC_LLM = 'http://127.0.0.1:8200'

Page({
  data: {
    stage: 'login',            // login | ready | guide
    users: [],                 // 演示账号提示（只显示 email，不给密码）
    email: '',
    password: '',
    loginStatus: '未登录',
    token: '',
    restored: false,           // 本次是否由本地凭证免密恢复
    context: null,
    guideVersion: '通用版',
    injected: false,
    noInjectReason: '',
    versionLead: '',
    versionStyle: '',
    stops: [],
    focus: '',
    depth: '',
    avoidText: '',
    abstract: '',
    promptText: '',
    aiAnswers: {},             // {站点id: AI 讲解正文}
    aiLoading: {},             // {站点id: 是否请求中}
    aiError: '',
    errorMsg: ''
  },

  onLoad() {
    this.fetchUsers()
    this.tryRestore()          // 方案一：下次进来先试本地凭证
  },

  /** 方案一：拿本地存的 token 问平台还认不认，认了就免密 */
  tryRestore() {
    const saved = session.read()
    if (!saved) return
    this.setData({ loginStatus: '正在恢复登录…' })
    wx.request({
      url: app.globalData.baseUrl + '/api/auth/verify?token='
        + encodeURIComponent(saved.token),
      success: (res) => {
        const d = res.data || {}
        if (res.statusCode !== 200 || !d.valid) {
          session.clear()        // token 失效：清掉、静默退回账密，不弹错误
          this.setData({ loginStatus: '请输入平台账号密码', restored: false })
          return
        }
        this.setData({
          token: saved.token,
          restored: true,
          loginStatus: '已免密恢复：' + (d.user && d.user.nickname || '平台账号'),
          stage: 'ready'
        })
      },
      fail: (err) => {
        // 平台没起/网络断：不清凭证（可能是暂时不可达），退回账密框但不报错
        this.setData({ loginStatus: '请输入平台账号密码（平台暂不可达）' })
      }
    })
  },

  fetchUsers() {
    wx.request({
      url: app.globalData.baseUrl + '/api/demo-users',
      success: (res) => {
        const users = (res.data && res.data.users) || []
        this.setData({
          users: users,
          email: users.length ? users[0].email : '',
          loginStatus: users.length ? '请输入平台账号密码' : '平台未连接'
        })
      },
      fail: (err) => {
        this.setData({ loginStatus: '平台未连接', errorMsg: err.errMsg })
      }
    })
  },

  // 点演示账号行只填 email，密码仍需用户输入
  onSelectUser(e) {
    this.setData({ email: e.currentTarget.dataset.email })
  },

  onEmailInput(e) {
    this.setData({ email: e.detail.value })
  },

  onPasswordInput(e) {
    this.setData({ password: e.detail.value })
  },

  doLogin() {
    const email = (this.data.email || '').trim()
    const password = this.data.password || ''
    if (!email || !password) {
      this.setData({ errorMsg: '请填邮箱和密码' })
      return
    }
    this.setData({ loginStatus: '登录中…', errorMsg: '' })
    wx.request({
      url: app.globalData.baseUrl + '/api/auth/login',
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: { email: email, password: password },
      success: (res) => {
        if (res.statusCode !== 200 || !res.data.token) {
          const detail = (res.data && res.data.detail) || '邮箱或密码不正确'
          this.setData({ loginStatus: '登录失败', errorMsg: detail })
          return
        }
        // 方案一：只存 token 与展示用的昵称，绝不存密码
        session.save(res.data.token, res.data.user)
        this.setData({
          token: res.data.token,
          password: '',              // 不把密码留在页面 data 里
          restored: false,
          loginStatus: '已登录：' + res.data.user.nickname,
          stage: 'ready'
        })
      },
      fail: (err) => {
        this.setData({ loginStatus: '登录失败', errorMsg: err.errMsg })
      }
    })
  },

  loadContext() {
    if (!this.data.token) return
    this.setData({ errorMsg: '' })
    wx.request({
      url: app.globalData.baseUrl + '/api/context?token='
        + encodeURIComponent(this.data.token),
      success: (res) => {
        if (res.statusCode !== 200) {
          // token 被撤/过期：清掉本地凭证，静默退回账密，不弹错误吓用户
          session.clear()
          this.setData({
            errorMsg: '', token: '', restored: false,
            stage: 'login', loginStatus: '登录已失效，请重新输入账密'
          })
          return
        }
        this.applyContext(res.data)
      },
      fail: (err) => {
        this.setData({ errorMsg: err.errMsg })
      }
    })
  },

  applyContext(ctx) {
    const g = ctx.guide_version || {}
    const ver = g.version || '通用版'
    const v = VERSIONS[ver] || VERSIONS['通用版']
    const injected = !!g.injected

    // 主题标签命中：只影响讲哪一版侧重，不改站点、不改顺序（DESIGN.md §1.2）
    const topics = g.topics || []
    const stops = KNOWLEDGE.map(k => {
      let text = k.body
      if (injected && g.focus) {
        // 深度：精简版只留经典句，深度版追加主题句
        if (g.depth && g.depth.indexOf('精简') >= 0) {
          text = k.classic
        } else if (g.depth && g.depth.indexOf('深度') >= 0 && topics.indexOf(k.topic) >= 0) {
          text = k.body + ' 这一处正对得上你在意的「' + k.topic + '」。'
        }
      }
      return {
        id: k.id, name: k.name, tag: k.tag,
        text: text,
        hit: injected && topics.indexOf(k.topic) >= 0
      }
    })

    // avoid 硬约束：命中 tag 的站点不主动提及（MVP 用标记演示，不删站点）
    const avoid = g.avoid || []

    this.setData({
      context: ctx,
      guideVersion: ver,
      injected: injected,
      noInjectReason: g.reason || '',
      versionLead: v.lead,
      versionStyle: v.style,
      stops: stops,
      focus: g.focus || '',
      depth: g.depth || '',
      avoidText: avoid.join('、'),
      abstract: ctx.abstract || '',
      promptText: ctx.injected_system_prompt || '',
      stage: 'guide'
    })
  },

  /** 点「AI 讲解」：把平台注入的 prompt + 该站知识库交给景区侧 LLM 代理 */
  askAI(e) {
    const id = e.currentTarget.dataset.id
    const stop = KNOWLEDGE.find(k => String(k.id) === String(id))
    if (!stop) return
    if (this.data.aiLoading[id]) return       // 防重复点

    const loading = Object.assign({}, this.data.aiLoading)
    loading[id] = true
    this.setData({ aiLoading: loading, aiError: '' })

    // 知识库是唯一事实来源：只给这一站的原文，不给模型自由发挥的余地
    const knowledge = `【${stop.name}】${stop.body}`

    wx.request({
      url: SCENIC_LLM + '/api/guide/ask',
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: {
        system_prompt: this.data.promptText,   // 来自 wtt 平台 /api/context
        knowledge: knowledge,
        question: `请讲解「${stop.name}」这一站。`
      },
      success: (res) => {
        const done = Object.assign({}, this.data.aiLoading)
        done[id] = false
        if (res.statusCode !== 200 || !res.data.answer) {
          const detail = (res.data && res.data.detail) || '服务暂时不可用'
          this.setData({ aiLoading: done, aiError: detail })
          return
        }
        const answers = Object.assign({}, this.data.aiAnswers)
        answers[id] = res.data.answer
        this.setData({ aiLoading: done, aiAnswers: answers })
      },
      fail: (err) => {
        const done = Object.assign({}, this.data.aiLoading)
        done[id] = false
        this.setData({ aiLoading: done, aiError: err.errMsg })
      }
    })
  },

  // 换账号 / 退出登录：一定要清本地凭证，否则下次进来又免密回这个账号
  reset() {
    session.clear()
    this.setData({
      stage: 'login', token: '', context: null, errorMsg: '',
      password: '', restored: false, loginStatus: '请重新登录',
      aiAnswers: {}, aiLoading: {}, aiError: '', promptText: ''
    })
  }
})
