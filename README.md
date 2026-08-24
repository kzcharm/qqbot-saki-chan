# qqbot-saki-chan

>  该机器人支持添加到好友列表私聊命令使用, 机器人会自动同意
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
- `-u` | `--update` 强制更新. 例如kzgo.eu的截图默认会缓存一天, 加上此条会强制生成新的截图

例:

- > - `/kz -m s` 用 `-m s` 指定生成skz模式的截图
  > - `/kz -q 986668916 -m v` 生成qq号*986668916*用户的VNL模式截图
  > - `/kz -s 1061976400 -u` 生成steamid为*1061976400*用户的截图, 并强制更新

### 通用

- `/help` 查看帮助

- `/markdown_test` 发送 QQ 自定义 Markdown 渲染测试消息。

- `/bind <binding-code>` 绑定 Steam 账号。在 [gokz.top](https://gokz.top/) 生成绑定码后发送，例如：`/bind KZTOP...`。绑定码区分大小写且会过期。
- `/mode <mode>` 切换默认模式 例: `/mode skz`

### GOKZ全球

- `/kz` | `/kzgo` 生成kzgo.eu截图. 例:

- `/pb <map_name>` 查询玩家在某张地图上的PB
- `/pr` 查询玩家最新跳的一张图
- `/wr  <map_name>` 查询世界记录

### GOKZ.TOP

- `/rank` | `/排行` 查询玩家的[gokz.top](https://gokz.top/)排名
- `/pk` 与他人进行Rank PK, 需要用 `-q` 或者 `-s` 指定对手

- `/mp`| `/mapprogress` |`/进度 <map_name>` 查询玩家在某张地图上的进步情况
-  `/ccf` | `/查成分` 查询玩家游玩最多的服务器
- `/find <name>` 通过昵称查找玩家(注意这个并不是实时更新)
