"""
VR接口调用工具
发送VR学生动作和表情到RabbitMQ
"""
import json

import pika

from ..config import settings
from ..config.settings import console

DEFAULT_CLASSROOM_ID = settings.VR_CLASSROOM_ID

ACTION_MAP = {
    "raiseHand": "举手",
    "lowerHand": "放下",
    "sitProperly": "端坐",
    "standUp": "起立",
    "sitDown": "坐下",
    "nod": "点头",
    "shakeHead": "摇头",
    "yawn": "打哈欠"
}

EXPRESSION_MAP = {
    "calm": "平静",
    "dazed": "思考",
    "smile": "开心",
    "surprised": "惊讶",
    "confused": "疑惑"
}


def send_to_vr(student_name: str,
               action: str = "standUp",
               expression: str = "calm",
               speech: str = "",
               classroom_id: str = DEFAULT_CLASSROOM_ID):
    """
    发送VR消息

    参数:
        student_name: 学生姓名
        action: 动作（raiseHand/lowerHand/sitProperly/standUp/sitDown/nod/shakeHead/yawn）
        expression: 表情（calm/dazed/smile/surprised/confused）
        speech: 说话内容
        classroom_id: 教室ID
    """
    if not settings.ENABLE_VR:
        return

    config = settings.RABBITMQ_CONFIG
    mapped_action = ACTION_MAP.get(action, action)
    mapped_expression = EXPRESSION_MAP.get(expression, expression)
    speech_text = speech or ""
    message_type = f"ecnu_digital_man{classroom_id}"
    message = {
        "msgRole": "all",
        "type": message_type,
        "body": {
            "name": student_name,
            "expression": mapped_expression,
            "action": mapped_action,
            "idea": speech_text,
            "isSay": bool(speech_text)
        }
    }

    try:
        credentials = pika.PlainCredentials(config["username"], config["password"])
        parameters = pika.ConnectionParameters(
            host=config["host"],
            port=config["port"],
            virtual_host=config.get("virtual_host", "/"),
            credentials=credentials,
            heartbeat=60,
            blocked_connection_timeout=30
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        channel.basic_publish(
            exchange=config["exchange"],
            routing_key=config["routing_key"],
            body=json.dumps(message, ensure_ascii=False).encode("utf-8")
        )

        connection.close()
        console.print(f"[green]✓ VR消息: {student_name} - {action}+{expression}[/green]")
        if speech:
            console.print(f"[cyan]  说话内容: {speech}[/cyan]")
    except Exception as e:
        console.print(f"[red]✗ VR消息发送失败: {e}[/red]")
