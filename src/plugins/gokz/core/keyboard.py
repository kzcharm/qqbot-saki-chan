from nonebot.adapters.qq.models import (
    Button,
    InlineKeyboardRow,
    InlineKeyboard,
    MessageKeyboard,
    Permission,
    Action
)
from nonebot.adapters.qq.message import MessageSegment

class KeyboardBuilder:
    @staticmethod
    def button(id, label, visited_label, style, action_type, permission_type, action_data, 
                      specify_user_ids=None, specify_role_ids=None, reply=False, enter=False, unsupport_tips=None):
        """
        :param id: 按钮ID
        :param label: 按钮上的文字
        :param visited_label: 点击后按钮的上文字
        :param style: 按钮样式
        :param action_type: 动作类型
        :param permission_type: 权限类型
        :param action_data: 操作相关的数据
        :param specify_user_ids: 有权限的用户ID列表
        :param specify_role_ids: 有权限的身份组ID列表
        :param reply: 指令是否带引用回复本消息
        :param enter: 点击按钮后是否直接自动发送数据
        :param unsupport_tips: 客户端不支持本action时，弹出的toast文案
        :return: Button 对象
        """
        permission = Permission(
            type=permission_type,
            specify_user_ids=specify_user_ids,
            specify_role_ids=specify_role_ids
        )
        
        action = Action(
            type=action_type,
            permission=permission,
            data=action_data,
            reply=reply,
            enter=enter,
            unsupport_tips=unsupport_tips
        )
        
        # 创建按钮
        button = Button(
            id=id,
            render_data={
                "label": label,
                "visited_label": visited_label,
                "style": style
            },
            action=action
        )
        return button

    @classmethod
    def keyboard(cls, *button_rows):
        """
        创建键盘布局。
        :param button_rows: 一个或多个按钮列表，每个列表代表键盘的一行
        :return: 返回构建的 MessageSegment.keyboard
        """
        keyboard_rows = [InlineKeyboardRow(buttons=row) for row in button_rows]
        inline_keyboard = InlineKeyboard(rows=keyboard_rows)
        message_keyboard = MessageKeyboard(content=inline_keyboard)
        return MessageSegment.keyboard(message_keyboard)

