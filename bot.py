import nonebot
from nonebot.adapters.qq import Adapter as QQAdapter


nonebot.init()
nonebot.get_driver().register_adapter(QQAdapter)
nonebot.load_from_toml("pyproject.toml")
nonebot.run()
