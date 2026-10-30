# GOKZ Bot — QQ and Discord

One NoneBot application runs the official QQ and Discord adapters. Alconna defines the commands once; shared services fetch data and apply feature rules, while QQ uses Chinese Markdown/keyboards and Discord uses English embeds/buttons. The existing repository, image, Compose project, and SQLite path are retained.

## Discord quick start

1. Sign in with Steam at [GOKZ.TOP](https://gokz.top/settings/binding-code) and generate a binding code.
2. Send `/bind code:KZTOP…` to Sakiko. The code is case-sensitive and expires at the time shown on the website. The response is private.
3. Use `/help`, `/mode`, `/profile`, `/kz`, `/pb`, `/pr`, `/wr`, `/rank`, `/daily`, `/server`, `/rate`, or `/comment`.

Both platforms verify codes with `QQ_BOT_SECRET`. Discord bindings and mode preferences are stored locally under platform-qualified account IDs. This does not modify the website's Discord social links. Modes and daily map assignments are independent across platforms. Automatic voice compliments are QQ-only.

## Adapter configuration

Set `QQ_BOTS` and/or `DISCORD_BOTS` and optionally `BOT_PLATFORMS=qq,discord`. Omit `BOT_PLATFORMS` to enable configured accounts automatically. Discord uses native slash commands and does not require Message Content intent. Example (replace the placeholder securely):

```dotenv
BOT_PLATFORMS=qq,discord
DISCORD_BOTS='[{"token":"REPLACE_ME","application_commands":{"*":["*"]}}]'
```

Use a guild ID instead of `"*"` in the inner list to register commands only in a test server. Configure root identities as `qq:<openid>` or `discord:<user-id>` in `SUPERUSERS`; legacy unqualified QQ IDs remain supported. Discord server settings use the guild ID. Buttons are restricted to the invoking user and expire after ten minutes or a restart. Slow commands defer and update the original reply in place, without an extra acknowledgement message. Binding and account-connection errors stay private. `/api` uses green/red status colours; record replies include map images, compact fields, and Discord timestamps. Ban history shows readable reasons, notes, server details, and expiry. Known legacy guild commands are retired after global command sync to prevent duplicate menu entries.

## Deployment and rollback

The existing CI/CD workflow tests and publishes an immutable SHA image, takes a consistent SQLite backup, records the previous image, and waits for QQ and Discord connections on E. Configure the `DISCORD_BOTS` repository secret as a JSON array alongside the existing production secrets. The bot needs View Channel, Send Messages, Embed Links, and Attach Files where it is used.

Backups live under `/opt/qqbot-saki-chan/backups/<sha>/`. To roll back, stop the bot, restore the matching backup to the existing SQLite file, select the recorded previous image, and start the same Compose service. Never remove the database volume. SQLite migrations preserve QQ bindings, preferences, daily picks, and compliment history while adding independent Discord state.

Run `python -m unittest discover -s tests -p 'test*.py' -v` for regression coverage. `python healthcheck.py` succeeds only when every configured platform is connected.

> 该机器人支持添加到好友列表私聊命令使用, 机器人会自动同意
> 也可以拉到其他群里使用

### 本地开发

本地默认使用 `ENVIRONMENT=dev`，会合并读取 `.env`、`.env.dev` 与被 Git 忽略的 `.env.dev.local`；后者可配置独立的 QQ 沙盒机器人凭据。

```bash
nb run --reload
```

保存 Python 文件后，NoneBot CLI 会自动重启。生产环境不读取本地 `.env`，而是由部署流程生成并使用 `.env.deploy`。

### 通用指定参数:

- `-q` | `--qid` 指定你想查询的人的QQ号
- `-s` | `--steamid` 指定你想查询的人的steamid
- `-m` | `--mode` 指定KZ模式 `k, s, v` | `kzt, skz, vnl`
- `-u` | `--update` 重新生成图片。玩家卡片缓存 15 分钟；此参数跳过图片缓存，不会强制同步玩家数据

例:

- > - `/kz -m s` 用 `-m s` 指定生成skz模式的截图
  > - `/kz -q 986668916 -m v` 生成qq号*986668916*用户的VNL模式截图
  > - `/kz -s 1061976400 -u` 生成steamid为*1061976400*用户的截图, 并强制更新

### 通用

- `/help` 查看帮助

- `/markdown_test` 发送 QQ 自定义 Markdown 渲染测试消息。

- `/test` 尝试发送带内嵌图片和键盘按钮的 Markdown 消息。

- `/bind <binding-code>` 绑定 Steam 账号。在 [绑定码页面](https://gokz.top/settings/binding-code) 使用 Steam 登录并生成绑定码后发送，例如：`/bind KZTOP...`。绑定码区分大小写，有效期为 5 分钟。
- `/mode <mode>` 切换默认模式 例: `/mode skz`
- `/profile` 查看玩家 GOKZ.TOP 资料、Steam 链接，以及已验证的 Bilibili 链接。支持通用的 `-q`、`-s` 参数或 @ 指定其他已绑定用户。

### GOKZ全球

- `/api` | `/API` 直接检查 GlobalAPI 的公开模式接口，显示当前可用状态、响应时间及失败原因。每次查询都会发起新请求，最多等待 10 秒，无需 API 密钥。此结果仅反映机器人到公开接口的可用性，不代表服务器具备全球记录提交资格。

- `/kz` | `/kzgo` 生成 GOKZ.TOP 玩家卡片，包含基本资料、NUB 完成度和技能雷达图。支持 `OVR`、`KZT`、`SKZ`、`VNL`。

- `/pb <map_name>` 查询玩家在某张地图上的PB
- `/pr` 查询玩家最新跳的一张图
- `/wr  <map_name>` 查询世界记录

### GOKZ.TOP

- `/rank` | `/排行` 查询玩家的[gokz.top](https://gokz.top/)排名
- `/pk` 与他人进行Rank PK, 需要用 `-q` 或者 `-s` 指定对手
- `/server` 列出可用服务器组；`/server <服务器组或名称>` 查看实时服务器状态，例如 `/server axekz`。别名：`/s`、`/servers`、`/serv`。
- `/group_info` 在群聊中查看群组 ID 与默认服务器组；根用户可用 `/set_server <服务器组>` 为当前群设置默认值，或 `/set_server <群组 ID> <服务器组>` 远程设置。此后直接 `/server` 查询该服务器组。

- `/mp`| `/mapprogress` |`/进度 <map_name>` 查询玩家在某张地图上的进步情况
- `/daily` | `/每日地图` 获取今日的挑战旧图和开荒新图；当天重复查询会返回相同结果
-  `/ccf` | `/查成分` 查询玩家游玩最多的服务器
- `/find <name>` 通过昵称查找玩家(注意这个并不是实时更新)

### 玩家卡片截图

截图由机器人现有的 Chromium 生成，无需额外服务。机器人访问 `/cards/player/{SteamID64}?scope=OVR&lang=zh-CN`，等待 `data-render-state="ready"` 后截取卡片元素，宽度为 480 CSS 像素，分辨率为 2 倍。卡片不显示站点标识、Steam ID 或网址。

可在机器人环境中设置 `GOKZ_TOP_WEBSITE_URL`，默认值为 `https://gokz.top`；本地和预发布环境可覆盖此地址。先部署网站卡片页面，再部署机器人。

缓存按玩家、模式、语言、布局版本和网站地址区分，有效期为 15 分钟。同一卡片的并发请求共用一次渲染，最多同时运行两个截图浏览器。渲染失败时发送错误消息和资料链接，不缓存失败结果。


## 数据库升级

机器人仅支持 GOKZ，默认模式为 OVR、KZT、SKZ 或 VNL。使用 `/mode <mode>` 切换模式。

启动时会自动执行 Alembic SQLite 迁移，保留 Steam 绑定、GOKZ 默认模式和时间戳，并移除旧的游戏选择设置。升级前请停止机器人并备份 `data/qqbot.sqlite3`；数据库升级失败时启动会中止，事务会回滚。不要同时运行多个机器人实例升级同一个数据库。

### Discord profile, rank, and server layouts

Profile and rank embeds show Steam identity/avatar, compact rating and ranking fields, public links, and profile activity. Profile enrichment uses `/player-social-links/players/{steamid64}` and tolerates optional-section failures. Server embeds show live maps, player slots/rosters, and copyable connection commands, with a link to the complete group list. Warnings are amber, operational errors are red, and `/pr` uses relative Discord timestamps.
