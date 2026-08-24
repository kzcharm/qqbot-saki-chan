import nonebot
from nonebot.adapters.qq import Adapter as QQAdapter
from nonebot.config import Env


environment = Env().environment
nonebot.init(_env_file=(".env", f".env.{environment}", f".env.{environment}.local"))
nonebot.get_driver().register_adapter(QQAdapter)
nonebot.load_from_toml("pyproject.toml")
nonebot.run()
