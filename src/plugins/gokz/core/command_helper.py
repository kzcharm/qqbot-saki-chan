import argparse
import shlex
import re
from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple
from pathlib import Path

from sqlmodel import Session

from src.plugins.gokz.db.db import engine
from src.plugins.gokz.db.models import User
from src.plugins.gokz.core.kreedz import format_kzmode
from src.plugins.gokz.core.steam_user import convert_steamid
from src.plugins.gokz.core.game import format_cs2kz_mode


@dataclass
class CommandData:
    game: str
    mode: str
    qid: str
    map_name: str
    course: str
    steamid: str
    steamid2: Optional[str] = None
    args: Tuple = field(default_factory=tuple)
    update: bool = False
    error: Optional[str] = None
    error_image: Optional[Path] = None

    def __init__(self, event, args):
        self.qid = event.get_user_id()
        parsed_args = parse_args(args.extract_plain_text())
        if 'error' in parsed_args:
            self.error = parsed_args['error']
            print(f"Error during argument parsing: {self.error}")
            return

        with Session(engine) as session:
            user = session.get(User, self.qid)  # NOQA

            if not user or not user.steamid:
                self.error = '客服小祥温馨提示您: 请先 /bind'
                self.error_image = Path('data/img/binding.png')
                print(self.error)
                return

            # SteamID64 is the bot's internal representation. Normalize older
            # rows that were stored as Steam2 IDs when they are read.
            stored_steamid = user.steamid
            user.steamid = convert_steamid(stored_steamid, 64)
            if user.steamid != stored_steamid:
                session.add(user)
                session.commit()

            qid = parsed_args.get('qid')
            if not qid:
                at_msg = event.get_message().copy()
                for segment in at_msg:
                    if segment.type == 'at':
                        qid = segment.data['qq']
                        break

            if qid:
                user2 = session.get(User, qid)
                if not user2 or not user2.steamid:
                    self.error = "你指定的用户未绑定steamid"
                    return
                self.steamid = convert_steamid(user2.steamid, 64)
                self.steamid2 = user.steamid
            else:
                requested_steamid = parsed_args.get('steamid')
                self.steamid = convert_steamid(requested_steamid, 64) if requested_steamid else user.steamid
                self.steamid2 = user.steamid if requested_steamid else None

        self.game = parsed_args.get('game') or getattr(user, "game", "gokz")
        if self.game == "cs2kz":
            mode = parsed_args.get('mode') or getattr(user, "cs2kz_mode", "classic")
            try:
                self.mode = format_cs2kz_mode(mode)
            except ValueError:
                self.error = "CS2KZ模式格式不正确"
                return
        else:
            try:
                self.mode = format_kzmode(parsed_args.get('mode') or user.mode)
            except ValueError:
                self.error = "模式格式不正确"
                return
        self.map_name = parsed_args.get('map_name', "")
        self.course = parsed_args.get('course') or "Main"
        self.update = parsed_args.get('update', False)
        self.args = parsed_args.get('args', ())

    def to_dict(self):
        return asdict(self)


def parse_args(text: str) -> dict:
    steamid64_pattern = re.compile(r"7656119\d{10}")
    steamid_pattern = re.compile(r"STEAM_[0-1]:[0-1]:\d+")
    
    parser = argparse.ArgumentParser(description='Parse arguments from a text string.')
    parser.add_argument('args', nargs='*', help='Positional arguments before the flags')
    parser.add_argument('-M', '--map_name', type=str, help='Name of the map')
    parser.add_argument('-m', '--mode', type=str, help='KZ模式')
    parser.add_argument('-s', '--steamid', type=str, help='Steam ID')
    parser.add_argument('-q', '--qid', type=str, help='QQ ID')
    parser.add_argument('-u', '--update', action='store_true', help='Update flag')
    parser.add_argument('-c', '--course', type=str, help='CS2KZ course name')

    game_group = parser.add_mutually_exclusive_group()
    game_group.add_argument('-g', '--gokz', action='store_const', const='gokz', dest='game', help='Use GOKZ')
    game_group.add_argument('-2', '--cs2kz', action='store_const', const='cs2kz', dest='game', help='Use CS2KZ')

    try:
        args = shlex.split(text)
        
        # Preprocess: find mode flags in positional arguments and convert them to -m <mode>
        # Only do this if -m or --mode is not already present
        has_mode_flag = any(
            arg in ['-m', '--mode'] or arg.startswith('--mode=')
            for arg in args
        )
        if not has_mode_flag:
            new_args = []
            mode_found = None
            for arg in args:
                try:
                    format_kzmode(arg)
                except (TypeError, ValueError):
                    new_args.append(arg)
                else:
                    # Found a mode flag, convert it to -m <mode>
                    mode_found = arg
                    new_args.extend(['-m', arg])
            if mode_found is not None:
                args = new_args
        
        parsed_args = parser.parse_args(args)

        if parsed_args.steamid:
            parsed_args.steamid = convert_steamid(parsed_args.steamid, 64)

        # Search for steamid64 or steamid in the positional arguments
        for arg in parsed_args.args:
            if steamid64_pattern.fullmatch(arg):
                parsed_args.steamid = convert_steamid(arg, 64)
                break
            elif steamid_pattern.fullmatch(arg):
                parsed_args.steamid = convert_steamid(arg, 64)  # Convert to steamid64
                break

        result = vars(parsed_args)
        result['args'] = tuple(result['args'])
        return result

    except argparse.ArgumentError as e:
        return {'error': f'Argument error: {str(e)}'}
    except SystemExit:
        return {'error': f'未指定参数'}
    except Exception as e:
        return {'error': str(e)}
