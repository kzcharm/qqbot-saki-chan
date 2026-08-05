import re
from functools import wraps
from typing import Any, Tuple, Union

from nonebot import logger
from nonebot.adapters.qq import Bot, Message, MessageSegment
from nonebot.adapters.qq.exception import ActionFailed

_PATCH_FLAG = "_gokz_send_retry_patched"
_BLOCKED_URL_CODE = 40034028
_DOMAIN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9-])((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63})(?![A-Za-z0-9-])"
)


def _should_retry(exc: ActionFailed) -> bool:
    if exc.code != _BLOCKED_URL_CODE:
        return False
    message = (exc.message or "").lower()
    return "url" in message or message == ""


def _sanitize_message_domains(
    message: Union[str, Message, MessageSegment]
) -> Tuple[Message, bool]:
    normalized = Message(message)
    sanitized = Message()
    changed = False

    for seg in normalized:
        if seg.type == "text":
            text = seg.data.get("text", "")
            replaced = _DOMAIN_PATTERN.sub(lambda m: m.group(1).replace(".", "-"), text)
            if replaced != text:
                changed = True
            sanitized += MessageSegment.text(replaced)
            continue
        sanitized.append(seg)

    return sanitized, changed


def _patch_send_method(method_name: str) -> None:
    original = getattr(Bot, method_name)

    @wraps(original)
    async def wrapped(self: Bot, *args: Any, **kwargs: Any) -> Any:
        try:
            return await original(self, *args, **kwargs)
        except ActionFailed as exc:
            if not _should_retry(exc):
                raise

            if "message" in kwargs:
                original_message = kwargs["message"]
                sanitized, changed = _sanitize_message_domains(original_message)
                if not changed:
                    raise
                retry_kwargs = dict(kwargs)
                retry_kwargs["message"] = sanitized
                logger.warning(
                    "QQ send blocked url-like text (code={}); retried with sanitized domain dots.",
                    exc.code,
                )
                return await original(self, *args, **retry_kwargs)

            if len(args) < 2:
                raise
            original_message = args[1]
            sanitized, changed = _sanitize_message_domains(original_message)
            if not changed:
                raise
            retry_args = list(args)
            retry_args[1] = sanitized
            logger.warning(
                "QQ send blocked url-like text (code={}); retried with sanitized domain dots.",
                exc.code,
            )
            return await original(self, *tuple(retry_args), **kwargs)

    setattr(Bot, method_name, wrapped)


def patch_qq_send_retry() -> None:
    if getattr(Bot, _PATCH_FLAG, False):
        return

    for method in ("send_to_group", "send_to_c2c", "send_to_channel", "send_to_dms"):
        _patch_send_method(method)

    setattr(Bot, _PATCH_FLAG, True)
