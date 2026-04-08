# 账号管理手动登录工作台设计

## 背景

当前代码库已经具备以下分散能力：

- 注册模块内的 OpenAI 登录 / 邮箱验证码 / Token 抓取能力
- 支付模块内的 session bootstrap、官方登录辅助、验证码查询能力
- 账号模块内的账号创建、账号更新、收件箱验证码查询、Session Token 管理能力
- 账号总览中的手动添加账号能力

但这些能力分散在注册、支付、账号总览等页面，账号管理页缺少统一入口。目标是在**账号管理页顶部**新增一个**手动登录工作台**，把已有能力整合为可操作、可观测、可落库的统一流程。

## 目标

在账号管理页新增一个顶部按钮，打开“手动登录”弹窗，支持：

- 已有账号登录
- 新邮箱/密码登录成功后自动建号
- 全自动 / 半自动两种模式
- 默认全自动
- 实时日志监控台
- 邮箱已存在时弹窗确认是否覆盖
- 登录成功后完整更新账号字段

## 非目标

- 不重写 OpenAI 登录底层逻辑
- 不在第一版引入新的数据库任务表
- 不替换现有支付页 / 注册页相关能力
- 不在第一版做复杂的任务恢复与跨刷新续跑

## 用户需求确认

- 入口位置：账号管理页顶部独立入口
- 交互形式：顶部按钮打开弹窗
- 支持范围：已有账号 + 新账号
- 模式：全自动、半自动都支持
- 默认模式：全自动
- 覆盖策略：邮箱已存在时提示用户确认是否覆盖
- 落库范围：全部更新（密码、token、cookies、状态、来源、刷新时间等）
- 日志体验：参考注册模块，带实时监控台

## 现有能力地图

### 1. 注册模块

可复用能力主要位于：

- `src/core/register.py`
- `src/core/anyauto/register_flow.py`
- `src/core/anyauto/chatgpt_client.py`
- `src/core/anyauto/oauth_client.py`

已具备：

- 登录入口提交
- 登录密码提交
- 邮箱验证码获取与重试
- Session / Access Token 抓取
- OAuth callback / token 收集

### 2. 支付模块

可复用能力主要位于：

- `src/web/routes/payment.py`
- `templates/payment.html`
- `static/js/payment.js`

已具备：

- `POST /payment/accounts/{account_id}/session-bootstrap`
- 账号登录链路补会话
- 官方登录页打开辅助
- 账号邮箱验证码查询辅助

### 3. 账号模块

可复用能力主要位于：

- `src/web/routes/accounts.py`
- `templates/accounts.html`
- `static/js/accounts.js`
- `templates/accounts_overview.html`
- `static/js/accounts_overview.js`

已具备：

- 手动新增账号接口 `POST /accounts`
- 账号导入接口 `POST /accounts/import`
- 收件箱验证码接口 `POST /accounts/{account_id}/inbox-code`
- Session Token 展示、编辑、保存能力
- 账号总览页“添加账号”弹窗

## 方案概览

新增一个“账号管理手动登录任务层”，由账号管理页的弹窗驱动。该任务层不重写登录核心，而是编排已有模块能力：

- 已有账号 + 全自动：优先复用支付模块的 session bootstrap / relogin 能力
- 新账号 + 全自动：复用注册模块中的登录与验证码能力
- 半自动：复用支付模块中的官方登录辅助 + 会话补全能力
- 所有模式最后统一进入账号结果落库流程

## 前端设计

### 页面入口

文件：

- `templates/accounts.html`
- `static/js/accounts.js`

新增一个顶部按钮：

- `手动登录`

### 弹窗结构

#### 表单区

- 邮箱
- 密码
- 登录模式：全自动 / 半自动（默认全自动）
- 邮箱服务策略：自动匹配 / 手动指定
- 按钮：
  - 开始登录
  - 查询验证码
  - 打开 GPT 官方登录页（仅半自动）
  - 停止任务
  - 清空

#### 监控区

- 当前状态
- 当前阶段
- 日志滚动区
- 结果摘要区

### 覆盖确认

当任务状态进入 `waiting_confirm_overwrite` 时，前端弹出确认提示：

- 覆盖更新
- 取消保存

## 后端设计

### 建议新增接口

放在 `src/web/routes/accounts.py`：

- `POST /accounts/manual-login/start`
- `GET /accounts/manual-login/tasks/{task_id}`
- `POST /accounts/manual-login/tasks/{task_id}/cancel`
- `POST /accounts/manual-login/tasks/{task_id}/confirm-overwrite`

### 任务状态

- `pending`
- `running`
- `waiting_confirm_overwrite`
- `completed`
- `failed`
- `cancelled`

### 任务阶段

- `init`
- `detect_account`
- `resolve_email_service`
- `open_login_flow`
- `submit_password`
- `wait_email_code`
- `verify_email_code`
- `capture_session`
- `persist_account`
- `done`

### 日志结构

每条日志包含：

- `time`
- `level`
- `message`

日志级别：

- `info`
- `warning`
- `success`
- `error`

## 核心执行流程

### A. 全自动模式

#### A1. 输入邮箱命中已有账号

1. 检测已有账号
2. 记录任务上下文
3. 复用支付模块会话补全登录链路
4. 自动获取邮箱验证码
5. 抓取 session/access token
6. 若登录成功：
   - 暂不直接覆盖
   - 进入 `waiting_confirm_overwrite`
7. 用户确认后统一落库

#### A2. 输入邮箱未命中已有账号

1. 进入登录流程
2. 复用注册模块中的登录/验证码/token 抓取逻辑
3. 登录成功后创建账号
4. 完整落库

### B. 半自动模式

1. 用户填写邮箱/密码
2. 系统打开 GPT 官方登录页（可选无痕）
3. 用户手动完成页面交互
4. 系统负责：
   - 查询验证码
   - 补全 session_token
   - 抓取其它 token
   - 统一落库

## 邮箱服务匹配规则

统一规则如下：

1. 用户手动指定服务时优先使用指定服务
2. 否则按**邮箱地址精确匹配**
3. 匹配不到时回退到同类型首个启用服务
4. 仍找不到则报错并记录日志

此规则应统一用于：

- 手动登录任务
- `/accounts/{account_id}/inbox-code`
- session bootstrap 登录验证码获取

## 统一落库策略

### 新账号登录成功

- 创建账号
- `source=login`
- `status=active`
- 更新：
  - password
  - access_token
  - refresh_token
  - session_token
  - cookies
  - account_id
  - workspace_id
  - last_refresh
  - metadata

### 已有账号登录成功

- 先等待用户确认覆盖
- 用户确认后更新全部字段

### 用户取消覆盖

建议将任务记为：

- `completed`
- `account_action=skipped`

表示本次登录成功，但用户拒绝写回。

## 推荐实现顺序

### 阶段 1：打通已有账号 + 全自动

- 新增按钮、弹窗、日志区
- 新增任务接口
- 复用现有 session bootstrap / relogin
- 打通实时日志

### 阶段 2：支持新账号自动建号

- 接入注册模块登录能力
- 成功后自动创建账号

### 阶段 3：增加覆盖确认

- 挂起等待确认
- 覆盖 / 跳过写回

### 阶段 4：增加半自动模式

- 官方登录页辅助
- 查询验证码
- 会话补全与保存

### 阶段 5：统一邮箱服务匹配逻辑

- 对齐 inbox-code / session bootstrap / 手动登录任务

## 涉及文件

### 前端

- `templates/accounts.html`
- `static/js/accounts.js`

### 后端

- `src/web/routes/accounts.py`
- `src/web/routes/payment.py`（复用或轻量抽取）
- `src/core/register.py`（轻量抽取可复用登录能力）

### 可选新增

- `src/web/services/manual_login_service.py`

## 风险与注意事项

1. 登录核心逻辑分散在多个模块，必须通过编排层收口，避免继续复制逻辑
2. 覆盖确认时要保存完整上下文，避免用户确认后重跑登录链路
3. 日志输出要统一 callback/logger 入口，避免监控台日志风格割裂
4. 邮箱服务必须优先按同邮箱匹配，否则容易取错验证码
5. 第一版先不做任务持久化恢复，避免过度设计

## 验收标准

- 账号管理页可打开手动登录弹窗
- 默认模式为全自动
- 支持已有账号与新账号
- 支持实时日志监控
- 支持全自动获取验证码与会话补全
- 邮箱已存在时能提示覆盖确认
- 登录成功后能完整写回账号数据
- 半自动模式可打开官方登录页并继续补全结果

