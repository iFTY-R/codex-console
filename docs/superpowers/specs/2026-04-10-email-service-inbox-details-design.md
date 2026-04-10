# 邮箱服务收件箱详情展开设计

## 背景

当前 `src/web/routes/email.py` 中的 `get_email_service_inbox()` 会把不同邮箱服务返回的原始邮件对象统一压缩成 `_serialize_inbox_message()` 的摘要结构。这样虽然便于前端列表展示，但会丢失大量调试和排障时有价值的信息，例如：

- 纯文本正文
- HTML 正文
- 原始字段结构
- 服务侧返回的扩展字段

现有前端 `static/js/email_services.js` 也只渲染摘要、主题、发件人和邀请信息，无法在同一界面继续深入查看邮件详情。

## 目标

为邮箱服务收件箱提供“摘要列表 + 单卡片展开详情”的体验：

1. 默认保持当前列表卡片式摘要浏览体验
2. 用户点击某封邮件后，可在卡片内展开查看完整详情
3. 后端不再丢失邮件原始字段，前端可以查看完整正文、HTML 预览和原始消息
4. 展示层要防止恶意邮件 HTML 直接影响管理页面

## 非目标

- 本次不新增单独的 `/inbox/{message_id}` 详情接口
- 不修改账号登录验证码相关的收件箱读取流程
- 不引入新的第三方依赖
- 不在后端做激进脱敏；重点是安全展示而不是数据裁剪

## 推荐方案

采用“**单接口返回摘要 + 完整详情分层字段**”方案。

原因：

- 当前接口已经限制最近邮件数量（默认 5 封），一次性返回详情的负载可控
- 不需要为不同邮箱服务额外设计稳定 message_id 查询协议
- 前端切换展开/收起无需再次请求，交互更直接
- 能最直接解决“`_serialize_inbox_message()` 丢字段”的核心问题

## 后端设计

### 1. `/email-services/{service_id}/inbox` 保持入口不变

接口路径与调用方式不变，继续返回：

- `success`
- `service_id`
- `service_name`
- `service_type`
- `limit`
- `mailbox`
- `messages`

这样可最大限度保持现有前端调用兼容。

### 2. `messages[*]` 从“纯摘要”升级为“摘要 + 详情分层”

每封邮件保留现有摘要字段：

- `id`
- `subject`
- `from`
- `received_at`
- `snippet`
- `is_seen`
- `business_invite`

同时新增详情字段：

- `text_body`: 纯文本正文，优先给前端默认展示
- `html_body`: 原始 HTML 正文，用于隔离预览
- `safe_preview`: 面向 UI 的安全纯文本预览
- `raw_message`: 原始消息字典，尽量完整透传
- `content_meta`:
  - `has_text`
  - `has_html`
  - `has_raw`
  - `available_fields`

### 3. `_serialize_inbox_message()` 调整方向

该函数不再只负责压缩摘要，而是负责：

1. 统一抽取跨服务通用字段
2. 尽量从已有字段中提取 `text_body` 与 `html_body`
3. 生成适合列表展示的 `snippet` / `safe_preview`
4. 保留 `business_invite` 提取逻辑
5. 透传 `raw_message`

建议按以下优先级提取内容：

#### `text_body` 优先级

1. `text`
2. `body`
3. `content`
4. `raw` 中可归一化为文本的内容
5. 其他服务特定文本字段

#### `html_body` 优先级

1. `html`
2. `body.html` / `content.html` 这类嵌套字段
3. 其他服务特定 HTML 字段

#### `raw_message`

- 使用 `dict(message or {})` 的浅拷贝返回
- 不为了“统一结构”提前删除未知字段
- 只要可 JSON 序列化，就尽量保留

### 4. 安全文本生成策略

后端额外生成 `safe_preview`，规则如下：

- 对 HTML 内容先去标签再归一化空白
- 限制预览长度，避免 UI 被超长内容撑爆
- 不把 `safe_preview` 当作替代原文，而是作为列表和兜底展示字段

### 5. 兼容性要求

- 当前依赖 `message.subject / from / received_at / snippet / business_invite` 的前端逻辑必须继续可用
- 对于没有 HTML 或正文的服务，相关字段返回空字符串即可
- 不要求所有邮箱服务都返回完全一致的原始字段；统一出口只负责补足“通用展示层”

## 前端设计

### 1. 保持现有 modal 和列表结构

继续使用 `templates/email_services.html` 中现有的“服务收件箱”弹窗，不改为左右双栏或二次弹窗。

邮件列表默认仍展示：

- 发件人
- 接收时间
- 主题
- 摘要
- `business_invite` 卡片（若存在）

### 2. 单卡片展开详情

每封邮件卡片新增“展开详情 / 收起详情”按钮。

展开后，在该卡片下方显示三个分区：

#### 正文

- 展示 `text_body`
- 使用纯文本方式渲染
- 保留换行

#### HTML 预览

- 若 `html_body` 存在，则提供 HTML 预览区域
- 该区域不直接注入主页面 DOM
- 采用 `sandbox iframe` 渲染隔离内容

#### 原始字段

- 展示 `raw_message`
- 使用格式化 JSON 文本块展示
- 支持折叠/展开，避免默认占用过多空间

### 3. 展开交互

建议交互规则：

- 默认全部收起
- 单击“展开详情”时，仅展开当前邮件
- 再次点击时可收起
- 若用户展开另一封邮件，则自动收起之前已展开的邮件

这样可以控制信息密度，避免 modal 变成难以滚动的长页面。

## 邮件内容安全展示设计

本次重点不是“隐藏数据”，而是“防止恶意邮件内容攻击管理页”。

### 1. 纯文本正文

- 使用 `textContent` 或等价方式渲染
- 不允许把正文作为 HTML 直接插入 DOM

### 2. HTML 预览

- 使用 `iframe sandbox` 进行隔离展示
- 不给 iframe 注入父页面权限
- 不允许访问父页面脚本上下文

建议的最小原则：

- 不在主文档中直接 `innerHTML = html_body`
- 链接统一要求 `target="_blank" rel="noopener noreferrer"`

### 3. 原始字段展示

- `raw_message` 仅以 JSON 文本形式显示
- 不解释、不渲染其中潜在 HTML 字段

### 4. UI 防护

- 正文和 JSON 区域都需要 `word-break` / `white-space: pre-wrap`
- 对超长内容区域设置最大高度和内部滚动
- 避免单封恶意邮件通过超长字符串破坏整体布局

## 涉及文件

后端：

- `src/web/routes/email.py`

前端：

- `static/js/email_services.js`
- `templates/email_services.html`
- 如有必要：`static/css/style.css`

## 数据流

1. 前端点击“查看收件箱”
2. 调用 `/email-services/{id}/inbox?limit=5`
3. 后端读取服务收件箱并返回“摘要 + 详情分层”消息数组
4. 前端先渲染摘要列表
5. 用户点击某封邮件的“展开详情”
6. 前端就地展开该消息的：
   - 纯文本正文
   - HTML 隔离预览
   - 原始字段 JSON

## 错误处理

### 后端

- 未找到服务：返回 `404`
- 服务类型不支持：返回 `400`
- 收件箱服务初始化失败：返回 `400`
- 服务不支持收件箱预览：返回 `400`
- 实际读取失败：返回 `500`

### 前端

- 加载失败时保留现有 empty-state / error-state
- 单封邮件缺少正文或 HTML 时，显示“无正文 / 无 HTML 预览”
- `raw_message` 序列化失败时，展示兜底文本，不影响摘要列表使用

## 测试方案

### 后端测试

建议补充覆盖以下行为的测试：

1. `messages[*]` 继续保留现有摘要字段
2. 当原始消息包含 `text/html/raw` 时，能返回对应详情字段
3. `raw_message` 会保留未知字段
4. `business_invite` 逻辑不回退

### 前端测试/验收

手工验收以下场景：

1. 默认只显示摘要，不自动展开
2. 点击“展开详情”后能看到正文
3. 有 HTML 的邮件能在隔离区域预览
4. 原始字段可以查看，且不会被当成 HTML 执行
5. 切换展开不同邮件时，UI 保持稳定

## 风险与权衡

### 1. 接口响应体增大

由于 `raw_message`、`text_body`、`html_body` 一起返回，响应会变大。但当前只拉取最近 5 封，风险可接受。

### 2. 不同邮箱服务字段差异大

不能要求所有服务实现同样的消息结构，因此统一层只负责：

- 提供标准摘要字段
- 尽量抽取正文/HTML
- 原样保留剩余字段

### 3. HTML 预览的安全性

如果未来直接把 HTML 注入主文档，会重新引入风险。因此本方案明确要求使用隔离渲染。

## 实施顺序

1. 调整 `email.py` 的消息序列化输出
2. 保持 `/inbox` 响应模型兼容并补充详情字段
3. 改造 `email_services.js`，增加单卡片展开详情逻辑
4. 调整 `email_services.html` / 样式，补充详情区结构与展示样式
5. 做回归验证，确认摘要列表、邀请信息和错误态仍正常
