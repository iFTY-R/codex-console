# codex-console

基于 [cnlimiter/codex-manager](https://github.com/cnlimiter/codex-manager) 持续修复和维护的增强版本。

这个版本的目标很直接：把近期 OpenAI 注册链路里那些“昨天还能跑，今天突然翻车”的坑补上，让注册、登录、拿 token、上传、任务调度、支付相关能力和打包运行都更稳一点。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-v1.1.2-2563eb.svg)](https://github.com/dou-jiang/codex-console/releases/tag/v1.1.2)

## 项目地址

- GitHub Repo: [https://github.com/dou-jiang/codex-console](https://github.com/dou-jiang/codex-console)
- Blog: [https://blog.cysq8.cn/](https://blog.cysq8.cn/)

## QQ群

- 交流群: [291638849（点击加群）](https://qm.qq.com/q/4TETC3mWco)
- Telegram 频道: [codex_console](https://t.me/codex_console)

## Blog 说明

我会在 Blog 持续更新这些内容：

- 部署教程和环境配置说明
- 每个版本的更新日志和 Release 说明
- 常见报错、排查思路和修复记录
- 邮箱服务、上传服务、任务调度、自检功能等使用说明
- 上游变化后的兼容性调整说明

访问地址：

- [https://blog.cysq8.cn/](https://blog.cysq8.cn/)

## 赞助支持

如果这个项目对你有帮助，欢迎赞助支持项目继续维护与更新。

<table>
  <tr>
    <td align="center">
      <strong>微信赞助</strong><br />
      <img src="docs/assets/wechat-pay.png" alt="微信赞助二维码" width="260" />
    </td>
    <td align="center">
      <strong>支付宝赞助</strong><br />
      <img src="docs/assets/alipay-pay.png" alt="支付宝赞助二维码" width="260" />
    </td>
  </tr>
</table>

## 致谢

首先感谢上游项目作者 [cnlimiter](https://github.com/cnlimiter) 提供的优秀基础工程。

本仓库是在原项目思路和结构之上进行兼容性修复、流程调整和体验优化，适合作为一个“当前可用的修复维护版”继续使用。

## 版本更新

### v1.0

1. 新增 Sentinel POW 求解逻辑。  
   OpenAI 现在会强制校验 Sentinel POW，原先直接传空值已经不行了，这里补上了实际求解流程。

2. 注册和登录拆成两段。  
   现在注册完成后通常不会直接返回可用 token，而是跳转到绑定手机或后续页面。  
   本分支改成“先注册成功，再单独走一次登录流程拿 token”，避免卡死在旧逻辑里。

3. 去掉重复发送验证码。  
   登录流程里服务端本身会自动发送验证码邮件，旧逻辑再手动发一次，容易让新旧验证码打架。  
   现在改成直接等待系统自动发来的那封验证码邮件。

4. 修复重新登录流程的页面判断问题。  
   针对重新登录时页面流转变化，调整了登录入口和密码提交逻辑，减少卡在错误页面的情况。

5. 优化终端和 Web UI 提示文案。  
   保留可读性的前提下，把一些提示改得更友好一点，出错时至少不至于像在挨骂。

### v1.1

1. 修复注册流程中的问题，解决 Outlook 和临时邮箱收不到邮件导致注册卡住、无法完成注册的问题。

2. 修复无法检查订阅状态的问题，提升订阅识别和状态检查的可用性。

3. 新增绑卡半自动模式，支持自动随机地址；3DS 无法跳过，需按实际流程完成验证。

4. 新增已订阅账号管理功能，支持查看和管理账号额度。

5. 新增后台日志功能，并补充数据导出与导入能力，方便排查问题和迁移数据。

6. 优化部分 UI 细节与交互体验，减少页面操作时的割裂感。

7. 补充细节稳定性处理，尽量减少注册、订阅检测和账号管理过程中出现卡住或误判的情况。

### v1.1.1

1. 新增 `CloudMail` 邮箱服务实现，并完成服务注册、配置接入、邮件轮询、验证码提取和基础收件处理能力。

2. 新增上传目标 `newApi` 支持，可根据配置选择不同导入目标类型。

3. 新增 `Codex` 账号导出格式，支持后续登录、迁移和导入使用。

4. 新增 `CPA` 认证文件 `proxy_url` 支持，现可在 CPA 服务配置中保存和使用代理地址。

5. 优化 OAuth token 刷新兼容逻辑，完善异常返回与一次性令牌场景处理，降低刷新报错概率。

6. 优化批量验证流程，改为受控并发执行，减少长时间阻塞和卡死问题。

7. 修复模板渲染兼容问题，提升不同 Starlette 版本下页面渲染稳定性。

8. 修复六位数字误判为 OTP 的问题，避免邮箱域名或无关文本中的六位数字被错误识别为验证码。

9. 新增 Outlook 账户“注册状态”识别与展示功能，可直接看到“已注册 / 未注册”，并支持显示关联账号编号。

10. 修复 Outlook 邮箱匹配大小写问题，避免 Outlook.com 因大小写差异被误判为未注册。

11. 修复 Outlook 列表列错位、乱码和占位文案问题，恢复中文显示并优化列表信息布局。

12. 优化 WebUI 端口冲突处理，默认端口占用时自动切换可用端口。

13. 增加启动时轻量字段迁移逻辑，自动补齐新增字段，提升旧数据升级兼容性。

14. 批量注册上限由 `100` 提升至 `1000`，前后端同步。

15. 公告区改为固定文案与固定链接，强化“永久免费开源、禁止倒卖、付费请退款”提示，并新增爱发电支持入口。

### v1.1.2

1. 新增统一鉴权与安全基线。  
   增加 `src/web/auth.py`、首次改密页面 `setup_password.html`，统一 API 与 WebSocket 鉴权口径，并补齐默认密码改密流程。

2. 新增系统自检能力与修复中心。  
   增加 `system_selfcheck.py`、`selfcheck.py`、`selfcheck.html`、`selfcheck_scheduler.py`，支持自检记录、调度与修复动作。

3. 新增统一任务中心。  
   增加 `tasks.py`，统一管理注册、支付、自检、Auto Team 等任务的状态、配额、暂停、继续、取消和重试。

4. 新增 Auto Team 模块。  
   增加后端 `auto_team.py` 与前端 `auto_team.js`、`auto_team_manage.js`。

5. 新增数据库迁移体系。  
   引入 Alembic，补齐 `alembic.ini`、`alembic/` 目录与迁移说明。

6. 新增母子标签系统和卡池功能。  
   补齐账号标签、池状态、自动绑卡与上游对接能力。

7. 扩展邮箱服务。  
   保留原有邮箱链路，同时补齐 `CloudMail`、`LuckMail`、`YYDS Mail` 等服务接入。

8. 新增周期任务调度。  
   支持计划任务创建、编辑、启停、立即执行以及前端轮询管理。

9. 新增 New-API 服务上传。  
   支持独立服务配置、测试、单账号上传、批量上传和注册成功后自动上传。

10. 增强自动注册与自动补货链路。  
    增加自动注册核心模块、库存监控、补货计划生成、取消感知、批次统计修复，以及 PR60 anyauto V2 回退流程。

11. 优化前端请求与轮询稳定性。  
    对 `app.js`、`accounts.js`、`payment.js`、`utils.js` 等进行了去重、降噪、超时、并发与降级路径增强。

12. 增强注册链路容错。  
    `src/core/register.py` 增加登录续跑、continue URL 缓存、workspace 缓存、OTP 重试等处理，对 native / abcard / outlook 等入口做了细分。

13. 增强账号模型与业务语义。  
    增加 `role_tag`、`biz_tag`、`pool_state`、`priority`、`last_used_at` 等字段，支持团队池、候选池、阻断池等状态表达。

14. 增强支付与历史数据保留。  
    `BindCardTask` 支持账号删除后保留 `account_email` 快照；新增审计日志模型 `OperationAuditLog` 与 `SelfCheckRun` 记录。

15. 扩展配置能力。  
    `settings.py` 增加自检、熔断、自动刷新、自动注册等多项配置，支持更多运行时调参。

16. 补充测试与 CI。  
    新增多组测试：任务、安全、自注册、新 API、自动刷新、邮箱服务等，并新增 `.github/workflows/tests.yml`。

17. 修复自动一键刷新、公告样式与页面外链。  
    修复定时自动一键刷新不可用、公告按钮样式问题、Footer 外链和 Blog 跳转问题。

## 核心能力

- Web UI 管理注册任务、账号、支付、自检、邮箱服务、卡池、Auto Team 和日志数据
- 支持单任务、批量任务、自动补货、计划任务、任务暂停 / 继续 / 取消 / 重试
- 支持多种邮箱服务接码和自部署邮箱接入
- 支持 CPA、Sub2API、Team Manager、New-API 等上传链路
- 支持 SQLite 和远程 PostgreSQL
- 支持打包为 Windows / Linux / macOS 可执行文件
- 更适配当前 OpenAI 注册与登录链路

## 环境要求

- Python 3.10+
- `uv`（推荐）或 `pip`

## 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

## 环境变量配置

可选。复制 `.env.example` 为 `.env` 后按需修改：

```bash
cp .env.example .env
```

常用变量如下：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `APP_HOST` | 监听主机 | `0.0.0.0` |
| `APP_PORT` | 监听端口 | `8000` |
| `APP_ACCESS_PASSWORD` | Web UI 访问密钥 | `admin123` |
| `APP_DATABASE_URL` | 数据库连接字符串 | `data/database.db` |

Docker Compose 常用变量如下：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `WEBUI_ACCESS_PASSWORD` | Docker Web UI 访问密钥，必填 | 无 |
| `PROXY_NETWORK` | 外部反向代理网络名称 | `1panel-network` |
| `CODEX_CONSOLE_IMAGE` | 拉取的镜像地址 | `ghcr.io/ifty-r/codex-console:latest` |
| `WEBUI_BIND_IP` | 宿主机绑定地址 | `127.0.0.1` |
| `WEBUI_PUBLISH_PORT` | 宿主机发布端口 | `1455` |
| `WEBUI_CPUS` | 容器 CPU 限制 | `1.0` |
| `WEBUI_MEM_LIMIT` | 容器内存限制 | `512m` |
| `WEBUI_SHM_SIZE` | 容器共享内存 | `1gb` |
| `ENABLE_VNC` | 是否启用容器内 VNC/noVNC | `0` |
| `NOVNC_BIND_IP` | noVNC 宿主机绑定地址 | `127.0.0.1` |
| `NOVNC_PUBLISH_PORT` | noVNC 宿主机发布端口 | `6080` |
| `APP_DATABASE_URL` | Docker 可选数据库连接字符串；不设置时自动使用挂载到 `/app/data` 的 SQLite | 不设置 |

优先级：

`命令行参数 > 环境变量(.env) > 数据库设置 > 默认值`

## 启动 Web UI

```bash
# 默认启动（127.0.0.1:8000）
python webui.py

# 指定地址和端口
python webui.py --host 0.0.0.0 --port 8080

# 调试模式（热重载）
python webui.py --debug

# 设置 Web UI 访问密钥
python webui.py --access-password mypassword

# 组合参数
python webui.py --host 0.0.0.0 --port 8080 --access-password mypassword
```

说明：

- `--access-password` 的优先级高于数据库中的密钥设置
- 该参数只对本次启动生效
- 打包后的 exe 也支持这个参数

例如：

```bash
codex-console.exe --access-password mypassword
```

启动后访问：

[http://127.0.0.1:8000](http://127.0.0.1:8000)

## Docker 部署

当前仓库默认提供两份 Compose 配置：

- `docker-compose.yml`：1Panel / 外部反向代理网络场景的生产基线，默认从 GHCR 拉镜像、不映射宿主机端口
- `docker-compose.debug-vnc.yml`：临时排障覆盖，额外开启 noVNC 端口

推荐的公网部署方式是：**容器仅监听宿主机回环地址，再由 1Panel / Nginx / Caddy 反向代理到 `127.0.0.1:1455`**。

### 1) 准备 `.env`

先复制示例文件并至少修改密码：

```bash
cp .env.example .env
```

至少确认：

```bash
WEBUI_ACCESS_PASSWORD=改成强密码
PROXY_NETWORK=1panel-network
CODEX_CONSOLE_IMAGE=ghcr.io/ifty-r/codex-console:latest
WEBUI_BIND_IP=127.0.0.1
WEBUI_PUBLISH_PORT=1455
ENABLE_VNC=0
```

如果你要接远程 PostgreSQL，再补；如果你使用默认 SQLite，**不要设置** `APP_DATABASE_URL`：

```bash
APP_DATABASE_URL=postgresql://user:password@host:5432/dbname
```

### 2) 首次启动（生产）

```bash
docker compose pull
docker compose up -d
```

查看状态：

```bash
docker compose ps
docker compose logs -f codex-console
```

生产基线默认行为：

- 加入外部网络 `${PROXY_NETWORK:-1panel-network}`（可保留给同网络容器使用）
- 将 Web UI 映射到 `${WEBUI_BIND_IP:-127.0.0.1}:${WEBUI_PUBLISH_PORT:-1455}`
- 仍使用当前编排目录下的 `./data` 和 `./logs` 做持久化

也就是说，1Panel 反向代理目标应指向：

```text
127.0.0.1:1455
```

### 3) 临时开启 noVNC 排障

平时不建议对外暴露 noVNC。只有在需要看浏览器自动化现场时，再临时叠加调试覆盖：

```bash
docker compose pull
docker compose -f docker-compose.yml -f docker-compose.debug-vnc.yml up -d
```

默认会额外发布：

- noVNC: `127.0.0.1:${NOVNC_PUBLISH_PORT:-6080}`

排障结束后，回到生产基线：

```bash
docker compose up -d
```

### 4) 常规更新

建议每次更新前先备份数据目录：

```bash
cp -r data "data.bak.$(date +%F-%H%M%S)"
cp -r logs "logs.bak.$(date +%F-%H%M%S)"
```

然后更新：

```bash
docker compose pull
docker compose up -d
```

这个项目当前启动时会执行数据库初始化和轻量迁移逻辑，所以常规升级通常直接拉取新镜像并启动即可。  
如果后续版本开始正式使用 Alembic 迁移文件，请以 Release / README 的升级说明为准。

### 5) 回滚

如果更新后异常：

```bash
docker compose up -d
```

如果你使用固定版本标签，也可以把 `.env` 里的 `CODEX_CONSOLE_IMAGE` 改回旧 tag 后再执行 `docker compose up -d`。如果问题与数据库结构或数据内容有关，再恢复之前备份的 `data/`。

### 6) 常用维护命令

```bash
# 停止
docker compose down

# 重启
docker compose restart

# 查看最后 200 行日志
docker compose logs --tail=200 codex-console

# 校验 compose 展开结果
docker compose config
```

### GitHub 自动构建镜像

推荐流程：

```bash
# 开发机
git add .
git commit -m "..."
git push origin master
```

GitHub Actions 会自动构建并推送到：

```text
ghcr.io/ifty-r/codex-console:latest
```

## 使用远程 PostgreSQL

```bash
export APP_DATABASE_URL="postgresql://user:password@host:5432/dbname"
python webui.py
```

也支持 `DATABASE_URL`，但优先级低于 `APP_DATABASE_URL`。

## 打包为可执行文件

```bash
# Windows
build.bat

# Linux/macOS
bash build.sh
```

Windows 打包完成后，默认会在 `dist/` 目录生成类似下面的文件：

```text
dist/codex-console-windows-X64.exe
```

如果打包失败，优先检查：

- Python 是否已加入 PATH
- 依赖是否安装完整
- 杀毒软件是否拦截了 PyInstaller 产物
- 终端里是否有更具体的报错日志

## 项目定位

这个仓库更适合作为：

- 原项目的修复增强版
- 当前注册链路的兼容维护版
- 自己二次开发的基础版本

如果你准备公开发布，建议在仓库描述里明确写上：

`Forked and fixed from cnlimiter/codex-manager`

这样既方便别人理解来源，也对上游作者更尊重。

## 仓库命名

当前仓库名：

`codex-console`

## 安全基线说明（新增）

- `/api/*` 与 `/api/ws/*` 已统一接入登录鉴权
- 首次启动检测到默认口令或默认密钥时，会强制跳转到 `/setup-password` 完成改密
- 支付相关 API Key 不再使用代码内硬编码默认值，需通过环境变量或配置显式提供

## 数据库迁移（Alembic）

```bash
alembic revision --autogenerate -m "your_change"
alembic upgrade head
```

初始化与更多说明见：

- `alembic/README.md`

## 免责声明

本项目仅供学习、研究和技术交流使用，请遵守相关平台和服务条款，不要用于违规、滥用或非法用途。

因使用本项目产生的任何风险和后果，由使用者自行承担。
