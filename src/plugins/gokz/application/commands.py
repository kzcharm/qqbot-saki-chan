"""Alconna definitions and lossless Discord slash-option conversion."""

import re
from typing import Any
from nepattern import ANY
from .catalog import CommandSpec
from .models import CommandInput
from arclet.alconna import Arparma

from arclet.alconna import Alconna, Args, Option, MultiVar, CommandMeta


def definition(spec: CommandSpec) -> Alconna:
    return Alconna(
        spec.name,
        ["/"],
        Args["arguments", MultiVar(ANY), ()],
        Option("-m|--mode", Args["mode", str]),
        Option("-s|--steamid", Args["steamid", str]),
        Option("-q|--qid|--user", Args["user", str]),
        Option("-M|--map_name", Args["map_name", str]),
        Option("-u|--update"),
        meta=CommandMeta(description=spec.en),
    )


def request_from_result(result: Arparma, name: str | None = None) -> CommandInput:
    data = result.all_matched_args
    raw_args = tuple(data.get("arguments") or ())
    user = data.get("user")
    args = []
    for value in raw_args:
        if hasattr(value, "target"):
            user = str(value.target)
        else:
            args.append(str(value))
    args = tuple(args)
    steamid = data.get("steamid")
    if name not in {"bind", "comment", "rate", "find", "server", "set_server"}:
        positional = []
        for value in args:
            if re.fullmatch(r"7656119\d{10}|STEAM_[01]:[01]:\d+", value):
                steamid = value
            else:
                positional.append(value)
        args = tuple(positional)
    if data.get("map_name"):
        args = (data["map_name"], *args)
    mode = data.get("mode")
    if not mode and name in {
        "pb",
        "pr",
        "wr",
        "mp",
        "rank",
        "pk",
        "profile",
        "info",
        "kz",
        "daily",
        "ban",
    }:
        from ..core.kreedz import format_kzmode

        positional = []
        for value in args:
            try:
                candidate = format_kzmode(value, "m")
            except ValueError:
                positional.append(value)
            else:
                mode = candidate
        args = tuple(positional)
    if any(value.startswith("-") for value in args):
        from .models import UserError

        raise UserError(
            "Unsupported option. Use /help.", "不支持的参数，请使用 /help。"
        )
    return CommandInput(
        arguments=args,
        mode=mode,
        steamid=steamid,
        user=user,
        update=result.find("update"),
    )


def discord_request(spec: CommandSpec, options: Any) -> CommandInput:
    """Preserve typed slash values directly; never reparse user-authored text."""
    values = {
        option.name: option.value
        for option in (options if isinstance(options, list) else [])
    }
    arguments = (
        (str(values[spec.argument]),)
        if spec.argument and spec.argument in values
        else ()
    )
    return CommandInput(
        arguments=arguments,
        mode=values.get("mode") if spec.name != "mode" else None,
        steamid=values.get("steamid"),
        user=str(values["user"]) if values.get("user") else None,
        update=bool(values.get("update", False)),
        overall=values.get("overall"),
        gameplay=values.get("gameplay"),
        visuals=values.get("visuals"),
        comment=values.get("comment"),
    )
