from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown, MessageMarkdownParams

class MarkdownBuilder:
    CUSTOM_TEMPLATE_ID = "" # 请在这里填入你的md模板id

    @classmethod
    def markdown(cls, params):
        """
        创建一个 Markdown 消息段。
        :param params: 一个包含键值对的字典，键是模板中的变量名，值是要替换的文本。
        :return: 返回构建的 MessageSegment.markdown 对象。
        """
        markdown_params = []
        for key, values in params.items():
            if not isinstance(values, list):
                values = [values]
            markdown_params.append(MessageMarkdownParams(key=key, values=values))

        markdown_message = MessageMarkdown(
            custom_template_id=cls.CUSTOM_TEMPLATE_ID,
            params=markdown_params
        )
        return MessageSegment.markdown(markdown_message)
