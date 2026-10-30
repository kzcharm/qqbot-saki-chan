import nonebot
from runtime import enabled_platforms
from nonebot.config import Env


environment = Env().environment
nonebot.init(
    log_level="INFO",
    _env_file=(".env", f".env.{environment}", f".env.{environment}.local"),
)
driver = nonebot.get_driver()
for platform in enabled_platforms(driver.config):
    if platform == "qq":
        from nonebot.adapters.qq import Adapter as QQAdapter

        driver.register_adapter(QQAdapter)
    else:
        from nonebot.adapters.discord import Adapter as DiscordAdapter

        driver.register_adapter(DiscordAdapter)
nonebot.load_from_toml("pyproject.toml")
nonebot.run()
