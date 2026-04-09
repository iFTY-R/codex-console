# 2026-04-09 ChatGPT 官方登录流程抓取与会话问题分析

## 背景

本次排查目标：

1. 解释为什么手动登录链路中多次出现：

   ```json
   {"WARNING_BANNER":"!!!!!!!!!!!!!!!!!!!! DO NOT SHARE ANY PART OF THE INFORMATION YOU SEE HERE. THIS INFORMATION IS SENSITIVE AND CAN GRANT ACCESS TO YOUR ACCOUNT. SHARING THIS INFORMATION IS LIKE SHARING YOUR PASSWORD. !!!!!!!!!!!!!!!!!!!!"}
   ```

2. 对比**官方浏览器真实登录流程**与当前项目中的 `src/core/register.py` 登录/补会话逻辑；
3. 在开始改造前，保留旧逻辑快照，避免“修着修着回不去”。

> 说明：为避免把完整 token / code / cookie 明文长期写入仓库，本文件对敏感值做了截断与省略。原始长值仍可在 `logs/app.log` 与本地浏览器调试现场中复核。

---

## 一、官方浏览器（js-reverse）实抓结果

### 1. 官方登录成功后的最终落点

- 页面：`https://chatgpt.com/`
- 标题：`ChatGPT`
- 当前页面显示了业务工作区内容，说明浏览器侧 Web 会话已经建立成功。

### 2. 官方浏览器成功登录后观察到的关键 Cookie / 状态

成功登录后的 `document.cookie` 中，至少可见这些与会话强相关的数据：

- `__Host-next-auth.csrf-token`
- `__Secure-next-auth.callback-url`
- `__Secure-next-auth.state`
- `oai-client-auth-session`
- `oai-client-auth-info`
- `auth-session-minimized`
- `auth-session-minimized-client-checksum`
- `_account`
- `oai-did`

其中最关键的是：

- `oai-client-auth-session`
  - 内含 `workspaces`
  - 内含 workspace 名称
  - 内含 `openai_client_id`
  - 内含当前用户与 auth-session 相关上下文

### 3. 官方浏览器里抓到的关键请求

#### A. Workspace 选择

- 请求：
  - `POST https://auth.openai.com/api/accounts/workspace/select`
- 请求体：

  ```json
  {"workspace_id":"93eb5215-..."}
  ```

- 请求时已附带大量认证上下文 Cookie，包括：
  - `oai-client-auth-session`
  - `auth-session-minimized`
  - `login_session`
  - `oai-did`
  - next-auth 相关 cookie

#### B. ChatGPT callback

- 请求：
  - `GET https://chatgpt.com/api/auth/callback/openai?...`

该请求发出时，浏览器已携带：

- `__Host-next-auth.csrf-token`
- `__Secure-next-auth.callback-url`
- `__Secure-next-auth.state`
- `oai-did`
- 其他 auth / session cookie

这说明官方浏览器不是“只拿到 callback URL”，而是：

1. 真正访问了 `chatgpt.com/api/auth/callback/openai`
2. 且访问时具备 next-auth 所需的状态 cookie
3. 最终由 ChatGPT Web 自身建立 Web 会话

---

## 二、本地手动登录链路日志证据

### 1. 主链路中已成功拿到 workspace

`logs/app.log` 中多次出现：

```text
Workspace: dmnrxvujvnmj（c8492cc2-dcc1-4ad3-89ba-f9c405dabec9）
选择 Workspace，安排个靠谱座位：dmnrxvujvnmj（c8492cc2-dcc1-4ad3-89ba-f9c405dabec9）
提交 workspace/select：dmnrxvujvnmj（c8492cc2-dcc1-4ad3-89ba-f9c405dabec9）
```

说明：

- workspace 本身并不是拿不到；
- `workspace/select` 也并非一直失败。

### 2. 主链路中 callback URL 已经出现

日志中可见：

```text
重定向链完成，callback=有，final=http://localhost:1455/auth/callback?code=...
```

说明：

- OAuth callback URL 能找到；
- 但 callback 指向的是本地 `localhost:1455`，而不是官方浏览器那种 `chatgpt.com/api/auth/callback/openai?...`。

### 3. `/api/auth/session` 连续返回 WARNING_BANNER

日志中重复出现：

```text
/api/auth/session 原始响应报文: {"WARNING_BANNER":"..."}
Auth Session 捕获结果: session_token=无, access_token=无
```

以及在 OAuth token 换出来后出现：

```text
Auth Session 捕获结果: session_token=无, access_token=有
```

这说明：

- OAuth token 有时已经能拿到；
- 但 ChatGPT Web 的 next-auth session 仍然没有建立；
- 所以 `chatgpt.com/api/auth/session` 不返回正常 session payload。

### 4. 补会话桥接链路也不稳定

典型日志：

```text
会话桥接重定向结束: callback=无, set_cookie_token=无, final=https://auth.openai.com/log-in...
会话桥接未命中 callback，final_url=https://auth.openai.com/log-in...
```

后续有一次改走 workspace 后得到：

```text
workspace/select 原始响应报文: {
  "continue_url": "https://chatgpt.com/api/auth/callback/openai?code=..."
}
```

但即便这次拿到了 `chatgpt.com/api/auth/callback/openai?...`，随后依然出现：

```text
/api/auth/session 原始响应报文: {"WARNING_BANNER":"..."}
Auth Session 捕获结果: session_token=无, access_token=有
```

说明：

- 仅仅“拿到 callback URL”并不足够；
- callback 必须以接近官方浏览器的上下文执行，才能真正落下 next-auth session。

---

## 三、根因判断

### 根因 1：OAuth 成功 ≠ ChatGPT Web 会话成功

当前项目里，`_handle_oauth_callback()` 主要做的是：

1. 解析 callback URL；
2. 本地直接用 code 去换取 OAuth token；
3. 得到 `access_token / refresh_token / id_token`。

但这一步**并不会自动保证**：

- `chatgpt.com/api/auth/callback/openai` 被完整执行；
- `__Secure-next-auth.session-token` 被成功下发；
- ChatGPT Web 会话真正建立。

### 根因 2：当前代码的 redirect / callback 处理方式与官方浏览器不一致

官方浏览器特征：

- callback 在 `chatgpt.com` 域上执行；
- 执行 callback 时已经带着 next-auth 状态 cookie；
- callback 执行后才有正常的 ChatGPT Web session。

当前项目特征：

- 主链路更偏向“先找到 callback，再本地换 OAuth token”；
- 对 ChatGPT Web callback 的执行不够接近官方浏览器；
- `/api/auth/session` 常在“OAuth token 已有，但 next-auth session 未建立”的状态下被调用。

### 根因 3：当前 `/api/auth/session` 的 WARNING_BANNER 是症状，不是独立根因

`WARNING_BANNER` 说明：

- 当前请求上下文不具备一个已建立完成的 ChatGPT Web 会话；
- 所以它只返回了敏感信息提示占位，而非真实 session 数据。

---

## 四、改造方向（准备动手）

### 改造原则

1. **优先复现官方浏览器在 ChatGPT 侧建立 next-auth session 的方式**；
2. 尽量不破坏当前已能拿到 workspace / OAuth token 的主链路；
3. 在改造前保留旧逻辑快照；
4. 所有新增分支要有明确日志，便于复盘。

### 优先改造点

#### 方向 A：补一个“更接近官方浏览器”的 callback 执行阶段

当已经具备：

- `workspace_id`
- 有效 `continue_url`
- 或能通过 `workspace/select` 拿到 `chatgpt.com/api/auth/callback/openai?...`

时，优先让 `self.session` 真实执行该 callback，并继续跟随其后续重定向链，直到：

- next-auth cookie 成功落地；
- 或明确失败。

#### 方向 B：在尝试 `/api/auth/session` 之前，明确检查关键 next-auth 状态 cookie

至少观察：

- `__Host-next-auth.csrf-token`
- `__Secure-next-auth.callback-url`
- `__Secure-next-auth.state`
- 以及是否出现 `__Secure-next-auth.session-token`

#### 方向 C：保留旧逻辑兜底

旧的：

- `csrf -> signin/openai -> auth/session`

桥接方案仍然保留，但应降级为后备路线，而不是唯一补会话路线。

#### 方向 D：已有账号续登时尽量复用旧浏览器上下文

为了降低 `push_auth_verification` 触发概率，续登场景应尽量复用：

- 历史 `oai-did`
- 历史 `oai-client-auth-session / auth-session-minimized / next-auth` 等会话 cookie
- 历史代理（若账号原本绑定了稳定代理）

这样可以让 OpenAI 看到的环境更接近“同一台已使用过的浏览器”，而不是每次都像全新设备登录。

---

## 六、2026-04-09 第一轮已实施改造

已落地的代码调整：

1. 新增 `workspace/select -> callback -> auth/session` 的会话引导路线；
2. 保留旧的 `csrf -> signin/openai -> auth/session` 兜底路线；
3. 已有账号续登时：
   - 注入旧 cookie / did / next-auth 相关上下文；
   - 优先复用历史代理；
4. 覆盖确认链路的脆弱内存依赖和 `update_account()` 参数冲突已修复。

当前下一步验证重点：

- 复跑手动登录；
- 观察是否仍在“提交密码后立即出现 `push_auth_verification`”；
- 若降低但未消失，再继续收缩到更具体的指纹 / cookie 差异。

---

## 五、当前建议的验收标准

改造后，至少要满足：

1. 主链路在成功 workspace/select 后，能够稳定建立 ChatGPT Web session；
2. `/api/auth/session` 不再只返回 `WARNING_BANNER`；
3. 日志中可以看到：
   - callback 已真实执行
   - next-auth cookie 已落地
   - `session_token=有`
4. 手动登录完成后，账号写库时能稳定带上正确的 `account_id / workspace_id`。
