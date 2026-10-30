from nonebot.adapters.qq import MessageEvent

from ..application.models import CommandInput
from ..presentation.qq_bridge import query
from ..presentation.qq_legacy import on_command

api_status = on_command("api", aliases={"API"})


@api_status.handle()
async def _(event: MessageEvent):
    result = await query(api_status, event, "api", CommandInput())
    status = result.data["status"]
    state = "🟢 可用" if status.available else "🔴 不可用"
    content = f"GlobalAPI 状态：{state}\n响应时间：{status.response_ms:.0f} ms"
    if status.error:
        content += f"\n原因：{status.error}"

    if getattr(event, "group_id", None):
        content = "\n" + content
    await api_status.finish(content)
