import nonebot
from nonebot import get_plugin_config
from nonebot import logger
from nonebot.log import default_format
from nonebot.plugin import PluginMetadata

nonebot.require("nonebot_plugin_alconna")
nonebot.require("nonebot_plugin_localstore")

from .config import Config
from .core import command_panel  # noqa: F401 - registers the bot-connect hook
from .core.send_retry import patch_qq_send_retry
from .db import models  # noqa: F401 - register tables before initialization
from .db.db import create_db_and_tables

__plugin_meta__ = PluginMetadata(
    name="gokz",
    description="A Plugin for GOKZ",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)
logger.add("error.log", level="ERROR", format=default_format, rotation="1 week")
patch_qq_send_retry()

create_db_and_tables()

unified = nonebot.load_plugin("src.plugins.gokz.plugins.unified")
if unified is None:
    raise RuntimeError("Unable to load the unified GOKZ command application")
sub_plugins = {unified}
