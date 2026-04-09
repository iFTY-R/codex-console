# 2026-04-09 ChatGPT Session Refactor 前旧逻辑备份

## 说明

本文件用于在继续改造 `src/core/register.py` 的 ChatGPT Web 会话建立逻辑前，保存旧思路与关键函数行为，便于回退与对比。

---

## 一、旧主链路的核心顺序

旧逻辑大致为：

1. 登录入口 -> 密码 -> OTP
2. 拿 `workspace_id`
3. `workspace/select`
4. `_follow_redirects(continue_url)`
5. `_handle_oauth_callback(callback_url)` 本地换 token
6. 调 `/api/auth/session`
7. 如无 `session_token`，再走 `csrf -> signin/openai -> auth/session` 桥接

---

## 二、旧逻辑关键函数与职责

### 1. `_follow_redirects(start_url)`

职责：

- 跟随主链路里的 `continue_url`
- 找 callback URL
- 返回 `(callback_url, final_url)`

旧特点：

- 更偏向“找回调 URL”
- 对 ChatGPT Web callback 的真实执行与会话落地保证不足

### 2. `_handle_oauth_callback(callback_url)`

职责：

- 用 callback URL 中的 code 本地换 OAuth token

旧特点：

- 能拿 `access_token / refresh_token / id_token`
- 但并不等于 ChatGPT next-auth session 已建立

### 3. `_capture_auth_session_tokens(result, access_hint=None)`

职责：

- 调用 `https://chatgpt.com/api/auth/session`
- 尝试从 JSON / cookie / set-cookie 中抓 session/access

旧特点：

- 在 next-auth session 未建立时会频繁得到 `WARNING_BANNER`

### 4. `_bootstrap_chatgpt_signin_for_session(result)`

职责：

- 通过 `csrf -> signin/openai -> follow redirects -> auth/session` 尝试补会话

旧特点：

- 在部分场景可用
- 但在当前问题样本中，常落到 `auth.openai.com/log-in`，未能稳定拿到 session token

---

## 三、旧逻辑中的关键脆弱点

1. **拿到 callback URL 后，不等于 callback 已在 ChatGPT Web 侧完整执行**
2. **OAuth token 已就绪，不等于 next-auth session 已就绪**
3. **`/api/auth/session` 在会话未建成时只会返回 WARNING_BANNER**
4. **补会话桥接路线过于依赖 `signin/openai`，与官方浏览器的真实成功路线不完全一致**

---

## 四、改造前保留的旧兜底原则

即使后续改造主路线，也保留以下旧兜底思想：

1. 先尝试主链路拿 session
2. 不行时，再走桥接补会话
3. 若仍拿不到 session，但 access_token 已有，则记录清晰日志并给出后续补救入口

---

## 五、与当前修复无关但已完成的稳定性补丁

在继续改造前，已完成：

1. 手动登录覆盖确认不再只依赖 `_task_context`
2. 覆盖确认写库的 `update_account()` 参数冲突已修复
3. 覆盖确认增加了前后值日志
4. 覆盖确认 route/service 增加了异常收口

这些补丁应保留，不应在本轮 ChatGPT session 改造中被回退。
