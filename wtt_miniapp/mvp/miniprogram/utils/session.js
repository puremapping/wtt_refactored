/**
 * 小程序端凭证存储（方案一：存 token，不存账密）
 *
 * ⚠️ 这是给「模拟景区端」的参考实现，不是交付给景区的代码。
 *    景区做小程序时按自己的工程规范重写，平台侧契约不变。
 *
 * 为什么存 token 不存账密：
 *   - token 有 TTL、可撤销、只承载一次会话授权；密码存客户端等于永久泄露
 *   - wx.setStorageSync 没有 httponly，JS 能读到，更不能放密码
 *
 * 隔离边界：wx storage 按 (小程序 AppID + 微信用户) 由微信 runtime 隔离，
 *          同设备换微信不互通、同微信换设备不共享。所以方案一**不需要**
 *          额外建微信账号体系 —— 那是 R2 一键绑定才要的事。
 */
const TOKEN_KEY = 'wtt_token'
const USER_KEY = 'wtt_user'

function save(token, user) {
  try {
    wx.setStorageSync(TOKEN_KEY, token)
    wx.setStorageSync(USER_KEY, user || {})
  } catch (e) {
    // storage 写失败不该拦住本次使用，只是下次不能免密
  }
}

function read() {
  try {
    const token = wx.getStorageSync(TOKEN_KEY)
    if (!token) return null
    return { token: token, user: wx.getStorageSync(USER_KEY) || {} }
  } catch (e) {
    return null
  }
}

function clear() {
  try {
    wx.removeStorageSync(TOKEN_KEY)
    wx.removeStorageSync(USER_KEY)
  } catch (e) {
    // 忽略
  }
}

module.exports = { save, read, clear }
