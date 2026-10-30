"""One command catalog for Alconna, Discord registration, help, and QQ panels."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    name: str
    en: str
    zh: str
    aliases: tuple[str, ...] = ()
    argument: str | None = None
    admin: bool = False


COMMANDS = (
    CommandSpec("help", "Show available commands", "查看帮助", ("帮助",)),
    CommandSpec(
        "bind",
        "Connect your Steam account on GOKZ.TOP",
        "绑定 Steam 账号",
        ("绑定",),
        "code",
    ),
    CommandSpec(
        "mode", "Show or change your default mode", "切换默认模式", ("模式",), "mode"
    ),
    CommandSpec("info", "Show your linked account and settings", "查看绑定信息"),
    CommandSpec(
        "profile", "Show a player profile and public links", "查看玩家资料", ("资料",)
    ),
    CommandSpec("api", "Check GlobalAPI availability", "查询 GlobalAPI 状态", ("API",)),
    CommandSpec("kz", "Generate a player card", "生成玩家卡片", ("kzgo",)),
    CommandSpec(
        "pb", "Show personal bests on a map", "查询个人最佳", ("personal-best",), "map"
    ),
    CommandSpec("pr", "Show the most recent completion", "查询最近记录"),
    CommandSpec("wr", "Show world records on a map", "查询世界记录", (), "map"),
    CommandSpec("ban", "Show player ban history", "查询封禁记录"),
    CommandSpec("rank", "Show player rankings", "查询玩家排名", ("排行",)),
    CommandSpec(
        "pk", "Compare rankings with another player", "比较玩家排名", (), "opponent"
    ),
    CommandSpec(
        "mp",
        "Show personal-best progression",
        "查询地图进度",
        ("progress", "mapprogress", "进度"),
        "map",
    ),
    CommandSpec(
        "daily",
        "Get your daily new and improvement maps",
        "获取每日地图",
        ("每日地图",),
    ),
    CommandSpec(
        "server",
        "Show live servers or available groups",
        "查询服务器",
        ("s", "servers", "serv"),
        "group",
    ),
    CommandSpec(
        "group_info", "Show this conversation and its server default", "查看群组设置"
    ),
    CommandSpec(
        "set_server",
        "Set the default server group (root only)",
        "设置默认服务器组",
        (),
        "group",
        True,
    ),
    CommandSpec("find", "Find players by name", "通过昵称查找玩家", ("查找",), "name"),
    CommandSpec(
        "ccf", "Show most-played server groups", "查询常玩服务器", ("查成分",), "period"
    ),
    CommandSpec(
        "review",
        "Show map reviews and comments",
        "查询地图评价",
        ("评价", "评论"),
        "map",
    ),
    CommandSpec(
        "rate",
        "Rate a map from one to five stars",
        "为地图评分",
        ("评分", "评价地图"),
        "map",
    ),
    CommandSpec(
        "comment",
        "Update your comment on a rated map",
        "评论已评分地图",
        ("地图评论",),
        "map",
    ),
    CommandSpec(
        "pw",
        "Show Perfect World player statistics",
        "查询完美平台数据",
        ("完美", "perfectworld"),
        "season",
    ),
    CommandSpec("feedback", "Get support and send feedback", "问题反馈"),
    CommandSpec(
        "group_rank",
        "Show rankings for locally linked players (root only)",
        "查询群排名",
        ("群排名",),
        None,
        True,
    ),
)
BY_NAME = {name: spec for spec in COMMANDS for name in (spec.name, *spec.aliases)}
