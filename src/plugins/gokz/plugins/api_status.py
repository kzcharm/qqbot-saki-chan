from ..presentation.qq_legacy import on_command
from nonebot.adapters.qq import MessageEvent

from ..api.global_status import check_global_api


api_status = on_command("api", aliases={"API"})


@api_status.handle()
async def _(event: MessageEvent):
    status = await check_global_api()
    state = "🟢 可用" if status.available else "🔴 不可用"
    content = f"GlobalAPI 状态：{state}\n响应时间：{status.response_ms:.0f} ms"
    if status.error:
        content += f"\n原因：{status.error}"

    if getattr(event, "group_id", None):
        content = "\n" + content
    await api_status.finish(content)
