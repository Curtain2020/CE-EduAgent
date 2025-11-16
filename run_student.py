"""
Flask Web应用 - 虚拟学生对话系统
提供教师与虚拟学生对话的网页界面
"""

import json
import asyncio
import re
from typing import Dict, List, Any, Optional, Tuple
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import sys
import os
import traceback
import threading
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename
import shutil

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.student.virtual_student import VirtualStudent
from src.api.qwen_client import QwenAPIClient
from src.config.settings import console, ENABLE_VR
from src.services.funasr_ws import transcribe_audio, parse_chunk_sizes, FunASRClientError, TranscriptionResult
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import ToolNode
from langchain_core.messages import ToolMessage
from datetime import datetime
from flask import Response

app = Flask(__name__)
CORS(app)

# 支持的学生名单
ALLOWED_STUDENTS = ["崔展豪", "李昌龙", "包梓群", "丽娃", "张晓丹", "萧华诗"]
DEFAULT_POSITIVITY = 0.5

ACTION_STATES = {"raiseHand", "sitProperly", "standUp", "sitDown"}
DEFAULT_ACTION_STATE = "sitProperly"

EXPRESSION_STATES = {"calm", "dazed", "smile"}
DEFAULT_EXPRESSION_STATE = "calm"

INTENT_CONTINUE = "continue"
INTENT_QUESTION = "question"
INTENT_CALL = "call"
INTENT_SIT_DOWN = "sit_down"
SUPPORTED_INTENTS = {INTENT_CONTINUE, INTENT_QUESTION, INTENT_CALL, INTENT_SIT_DOWN}

# 全局虚拟学生实例集合
current_students: Dict[str, VirtualStudent] = {}
active_student_names: List[str] = []
vr_control_enabled = ENABLE_VR

# 意图识别客户端
intent_detection_client = QwenAPIClient()

# 语音识别配置
FUNASR_HOST = os.environ.get("FUNASR_HOST", "59.78.189.185")
FUNASR_PORT = int(os.environ.get("FUNASR_PORT", "9999"))
FUNASR_MODE = os.environ.get("FUNASR_MODE", "2pass")
FUNASR_CHUNK_SIZE = parse_chunk_sizes(os.environ.get("FUNASR_CHUNK_SIZE", "2,8,3"))
FUNASR_CHUNK_INTERVAL = int(os.environ.get("FUNASR_CHUNK_INTERVAL", "8"))
FUNASR_USE_ITN = bool(int(os.environ.get("FUNASR_USE_ITN", "1")))
FUNASR_USE_SSL = bool(int(os.environ.get("FUNASR_USE_SSL", "0")))
FUNASR_SSL_VERIFY = bool(int(os.environ.get("FUNASR_SSL_VERIFY", "0")))
FUNASR_HOTWORD = os.environ.get("FUNASR_HOTWORD")
FUNASR_SEND_WITHOUT_SLEEP = bool(int(os.environ.get("FUNASR_SEND_WITHOUT_SLEEP", "1")))

UPLOAD_ROOT = Path(os.environ.get("AUDIO_UPLOAD_DIR", Path(__file__).parent / "uploads"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


def normalize_positivity(value, default: float = DEFAULT_POSITIVITY) -> float:
    """将积极性限制在0-1范围"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, num))


def normalize_action_state(value: str, default: str = DEFAULT_ACTION_STATE) -> str:
    if isinstance(value, str) and value in ACTION_STATES:
        return value
    return default


def normalize_expression_state(value: str, default: str = DEFAULT_EXPRESSION_STATE) -> str:
    if isinstance(value, str) and value in EXPRESSION_STATES:
        return value
    return default


def extract_student_name(text: str) -> Optional[str]:
    if not text:
        return None
    best_match = None
    best_score = 0
    for name in ALLOWED_STUDENTS:
        score = sum(1 for ch in name if ch and ch in text)
        if score > best_score:
            best_score = score
            best_match = name
    return best_match if best_score > 0 else None


def detect_intent_by_rule(text: str) -> Optional[str]:
    if not text:
        return None
    lowered = text.lower()
    if any(keyword in lowered for keyword in ["坐下", "回座", "sit down", "坐回去"]):
        return INTENT_SIT_DOWN
    name_in_text = extract_student_name(text)
    if name_in_text and re.search(r"(点名|请.?回答|请.?发言|来回答|回答|发言)", text):
        return INTENT_CALL
    if any(keyword in lowered for keyword in ["提问", "问题", "回答", "谁知道", "想问"]) or text.strip().endswith(("?", "？")):
        return INTENT_QUESTION
    return None


async def _detect_intent_via_llm(message: str) -> Optional[str]:
    prompt = (
        "你是课堂助手，请根据老师的一句话判断意图，仅可从"
        f"{list(SUPPORTED_INTENTS)}中选择一个，并以JSON格式返回，示例：{{\"intent\": \"question\"}}。"
        "若难以判断请输出{\"intent\": \"continue\"}。老师的话："
    )
    try:
        completion = await intent_detection_client.chat_completion(
            [
                {"role": "system", "content": "你是课堂助手，负责提取老师意图。"},
                {"role": "user", "content": f"{prompt}{message}"}
            ],
            temperature=0.1
        )
    except Exception as exc:
        console.print(f"[yellow]LLM意图识别失败: {exc}[/yellow]")
        return None

    content = (completion.get('content') or "").strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None

    intent = data.get("intent")
    if isinstance(intent, str) and intent in SUPPORTED_INTENTS:
        return intent
    return None


def detect_intent(message: str) -> Tuple[str, Optional[str], str]:
    student_name = extract_student_name(message)
    intent = detect_intent_by_rule(message)
    source = "rule"

    if intent is None:
        llm_intent = run_async(_detect_intent_via_llm(message))
        if llm_intent:
            intent = llm_intent
            source = "llm"
        else:
            intent = INTENT_CONTINUE
    return intent, student_name, source


def get_students_by_action(action: str) -> List[VirtualStudent]:
    return [
        student for student in current_students.values()
        if getattr(student, "action_state", DEFAULT_ACTION_STATE) == action
    ]


def get_standing_student() -> Optional[VirtualStudent]:
    standing = get_students_by_action("standUp")
    return standing[0] if standing else None


def get_raising_students() -> List[VirtualStudent]:
    return get_students_by_action("raiseHand")


def clear_raise_states(exclude: Optional[str] = None):
    for student in current_students.values():
        if student.action_state == "raiseHand" and student.student_name != exclude:
            student.set_action_state(DEFAULT_ACTION_STATE)


def reset_other_standing(active_student_name: str):
    for student in current_students.values():
        if student.student_name != active_student_name and student.action_state == "standUp":
            student.set_action_state(DEFAULT_ACTION_STATE)


def record_teacher_statement(message: str):
    for student in current_students.values():
        try:
            run_async(student.add_conversation_to_memory(message, "【课堂记录】"))
        except Exception as exc:
            console.print(f"[yellow]记录老师讲课失败: {exc}[/yellow]")


def build_wait_response(intent: str, action: str, message: str) -> dict:
    return {
        'success': True,
        'intent': intent,
        'action': action,
        'message': message,
        'responses': [],
        'response': message,
        'students_state': get_students_state_snapshot()
    }


def trigger_student_stand_and_speak(student: VirtualStudent, user_message: str) -> dict:
    reset_other_standing(student.student_name)
    clear_raise_states(exclude=student.student_name)
    return run_async(student.stand_up_and_speak(user_message, _process_chat_for_student))


def attempt_students_raise() -> List[VirtualStudent]:
    raised_students = []
    for student in current_students.values():
        if student.action_state in ("standUp", "raiseHand"):
            continue
        if student.raise_hand():
            raised_students.append(student)
    return raised_students


def get_students_state_snapshot() -> List[dict]:
    states = []
    for student in current_students.values():
        states.append({
            'student_name': student.student_name,
            'action_state': getattr(student, 'action_state', DEFAULT_ACTION_STATE),
            'expression_state': getattr(student, 'expression_state', DEFAULT_EXPRESSION_STATE)
        })
    return states


def build_response_with_results(intent: str, action: str, responses: List[dict]) -> dict:
    success = all(item.get('success', True) for item in responses)
    primary_response = next(
        (item.get('response') for item in responses if item.get('success')),
        ''
    )
    return {
        'success': success,
        'intent': intent,
        'action': action,
        'responses': responses,
        'response': primary_response,
        'students_state': get_students_state_snapshot()
    }


def handle_continue_intent(user_message: str) -> dict:
    """当老师继续讲解：
    - 若有学生已起立，则由该学生继续回答
    - 否则，仅记录并由课堂助手提示
    """
    standing_student = get_standing_student()
    if standing_student:
        result = trigger_student_stand_and_speak(standing_student, user_message)
        return build_response_with_results(INTENT_CONTINUE, 'standing_continue', [result])
    return build_wait_response(INTENT_CONTINUE, 'recorded', '已记录老师讲课内容。')


def handle_question_intent(user_message: str, named_student: Optional[str]) -> dict:
    standing_student = get_standing_student()
    if standing_student:
        result = trigger_student_stand_and_speak(standing_student, user_message)
        return build_response_with_results(INTENT_QUESTION, 'standing_answer', [result])

    raising_students = get_raising_students()
    if named_student:
        target_student = current_students.get(named_student)
        if target_student:
            result = trigger_student_stand_and_speak(target_student, user_message)
            return build_response_with_results(INTENT_QUESTION, 'called_student', [result])
        return build_wait_response(INTENT_QUESTION, 'student_not_found', f"未找到学生 {named_student}")

    if not raising_students:
        raising_students = attempt_students_raise()
        if not raising_students:
            return build_wait_response(INTENT_QUESTION, 'waiting', '老师提问，等待学生举手。')

    return build_wait_response(INTENT_QUESTION, 'awaiting_call', '有学生举手，等待老师点名。')


def handle_call_intent(user_message: str, named_student: Optional[str]) -> dict:
    if not named_student:
        return handle_question_intent(user_message, None)

    target_student = current_students.get(named_student)
    if not target_student:
        return build_wait_response(INTENT_CALL, 'student_not_found', f"未找到学生 {named_student}")

    result = trigger_student_stand_and_speak(target_student, user_message)
    return build_response_with_results(INTENT_CALL, 'called_student', [result])


def handle_sit_down_intent(_: str) -> dict:
    standing_student = get_standing_student()
    if not standing_student:
        return build_wait_response(INTENT_SIT_DOWN, 'no_standing', '当前没有学生起立。')

    standing_student.sit_down()
    return build_wait_response(INTENT_SIT_DOWN, 'student_sat', f"{standing_student.student_name} 已坐下。")


def clear_uploads_directory():
    """清空上传目录中的语音文件。"""
    if not UPLOAD_ROOT.exists():
        return
    for entry in UPLOAD_ROOT.iterdir():
        try:
            if entry.is_file():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)
        except Exception as exc:
            console.print(f"[yellow]清理上传文件失败: {exc}[/yellow]")

# 全局事件循环（每个线程一个）
def get_or_create_event_loop():
    """获取或创建当前线程的事件循环"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop is closed")
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

def run_async(coro):
    """在线程中运行异步函数"""
    try:
        loop = get_or_create_event_loop()
        return loop.run_until_complete(coro)
    except RuntimeError:
        # 如果当前线程没有事件循环，创建一个新的
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

# ===== 图谱导入/导出 支持 =====
INDEX_PATH = os.path.join(os.path.dirname(__file__), "data", "student_graphs", "index.json")

def student_label_en_from_cn(name: str) -> str:
    mapping = {
        "崔展豪": "Cuizhanhao",
        "包梓群": "Baoziqun",
        "李昌龙": "Lichanglong",
        "丽娃": "Liwa",
        "萧华诗": "Xiaohuashi",
        "张晓丹": "Zhangxidan",
    }
    return mapping.get(name, name)

def read_index() -> dict:
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def write_index(data: dict):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/api/graph/index', methods=['GET'])
def api_graph_index():
    try:
        return jsonify({"success": True, "data": read_index()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/graph/import_latest', methods=['POST'])
def api_graph_import_latest():
    """按 index.json 的 current_stage 为所选学生导入最新图谱到 Neo4j"""
    try:
        payload = request.json or {}
        student_names = payload.get("student_names") or active_student_names or []
        if not student_names:
            return jsonify({"success": False, "error": "没有可导入的学生"}), 400

        idx = read_index()
        from knowledge_graph_manager import KnowledgeGraphManager
        results = []
        for cn in student_names:
            item = idx.get(cn)
            if not item:
                results.append({"student": cn, "success": False, "error": "index.json 无该学生"})
                continue
            stage = item.get("current_stage")
            path = (item.get("stages") or {}).get(stage)
            if not stage or not path:
                results.append({"student": cn, "success": False, "error": "未找到最新阶段文件"})
                continue
            en = student_label_en_from_cn(cn)
            kgm = KnowledgeGraphManager(student_label_en=en)
            abs_path = os.path.join(os.path.dirname(__file__), path) if not os.path.isabs(path) else path
            kgm.import_student_graph_from_file(en, abs_path, clear_existing=True)
            results.append({"student": cn, "success": True, "stage": stage})
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/graph/export', methods=['POST'])
def api_graph_export():
    """将当前 Neo4j 中各学生的子图导出为 json，并更新 index.json 为最新版本"""
    try:
        payload = request.json or {}
        student_names = payload.get("student_names") or active_student_names or []
        if not student_names:
            return jsonify({"success": False, "error": "没有可导出的学生"}), 400

        base_dir = os.path.join(os.path.dirname(__file__), "data", "student_graphs")
        os.makedirs(base_dir, exist_ok=True)
        idx = read_index()

        from knowledge_graph_manager import KnowledgeGraphManager
        results = []
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        for cn in student_names:
            en = student_label_en_from_cn(cn)
            kgm = KnowledgeGraphManager(student_label_en=en)
            data = kgm.export_student_graph(en)

            stu_dir = os.path.join(base_dir, cn)
            os.makedirs(stu_dir, exist_ok=True)
            rel_path = f"data/student_graphs/{cn}/{timestamp}.json"
            abs_path = os.path.join(os.path.dirname(__file__), rel_path)
            with open(abs_path, "w", encoding="utf-8") as f:
                # 以缩进格式写入并关闭 ASCII 转义
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 更新 index.json
            stu = idx.get(cn) or {"current_stage": "", "stages": {}}
            stu_stages = stu.get("stages") or {}
            stu_stages[timestamp] = rel_path
            stu["stages"] = stu_stages
            stu["current_stage"] = timestamp
            idx[cn] = stu

            results.append({"student": cn, "success": True, "stage": timestamp, "path": rel_path})

        write_index(idx)
        return jsonify({"success": True, "results": results, "timestamp": timestamp})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ===== 知识图谱管理（按学生/版本加载与设置当前） =====
@app.route('/api/kg/graph', methods=['GET'])
def api_kg_graph():
    """返回指定学生+阶段的图谱（读取 index.json 指向的 JSON 文件）"""
    try:
        student_cn = request.args.get('student')
        stage = request.args.get('stage')
        if not student_cn or not stage:
            return jsonify({"success": False, "error": "缺少 student 或 stage"}), 400
        if not os.path.exists(INDEX_PATH):
            return jsonify({"success": False, "error": "index.json 不存在"}), 404
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            idx = json.load(f)
        stu = idx.get(student_cn) or {}
        path = (stu.get("stages") or {}).get(stage)
        if not path:
            return jsonify({"success": False, "error": "未找到该阶段图谱"}), 404
        abs_path = os.path.join(os.path.dirname(__file__), path) if not os.path.isabs(path) else path
        with open(abs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({"success": True, "nodes": data.get("nodes", []), "edges": data.get("edges", [])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/graph/set_current', methods=['POST'])
def api_graph_set_current():
    """将某学生指定阶段设置为当前版本"""
    try:
        payload = request.json or {}
        student_cn = payload.get("student")
        stage = payload.get("stage")
        if not student_cn or not stage:
            return jsonify({"success": False, "error": "缺少 student 或 stage"}), 400
        if not os.path.exists(INDEX_PATH):
            return jsonify({"success": False, "error": "index.json 不存在"}), 404
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            idx = json.load(f)
        if student_cn not in idx:
            return jsonify({"success": False, "error": "index.json 无该学生"}), 404
        if stage not in (idx[student_cn].get("stages") or {}):
            return jsonify({"success": False, "error": "该学生无此阶段"}), 404
        idx[student_cn]["current_stage"] = stage
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/init', methods=['POST'])
def init_student():
    """初始化虚拟学生，可同时初始化多名学生"""
    global current_students, active_student_names

    data = request.json or {}
    raw_configs = data.get('student_configs')

    try:
        if raw_configs and isinstance(raw_configs, list):
            validated_configs = []
            for item in raw_configs:
                if not isinstance(item, dict):
                    continue
                name = item.get('student_name')
                if not name or name not in ALLOWED_STUDENTS:
                    return jsonify({
                        'success': False,
                        'error': f"存在非法学生：{name or '未命名学生'}"
                    }), 400
                validated_configs.append({
                    'student_name': name,
                    'enable_long_term_memory': bool(item.get('enable_long_term_memory', True)),
                    'enable_knowledge_base': bool(item.get('enable_knowledge_base', False)),
                    'positivity': normalize_positivity(item.get('positivity', DEFAULT_POSITIVITY)),
                    'action_state': normalize_action_state(item.get('action_state', DEFAULT_ACTION_STATE)),
                    'expression_state': normalize_expression_state(item.get('expression_state', DEFAULT_EXPRESSION_STATE))
                })
        else:
            # 向后兼容旧版单学生初始化
            student_name = data.get('student_name')
            student_names = data.get('student_names')
            if student_name:
                student_names = [student_name]
            if not student_names or not isinstance(student_names, list):
                return jsonify({
                    'success': False,
                    'error': '请提供至少一名学生名称'
                }), 400
            invalid = [name for name in student_names if name not in ALLOWED_STUDENTS]
            if invalid:
                return jsonify({
                    'success': False,
                    'error': f"存在非法学生：{'、'.join(invalid)}"
                }), 400
            enable_long_term_memory = bool(data.get('enable_long_term_memory', True))
            enable_knowledge_base = bool(data.get('enable_knowledge_base', False))
            default_positivity = normalize_positivity(data.get('positivity', DEFAULT_POSITIVITY))
            default_action_state = normalize_action_state(data.get('action_state', DEFAULT_ACTION_STATE))
            default_expression_state = normalize_expression_state(data.get('expression_state', DEFAULT_EXPRESSION_STATE))
            validated_configs = [
                {
                    'student_name': name,
                    'enable_long_term_memory': enable_long_term_memory,
                    'enable_knowledge_base': enable_knowledge_base,
                    'positivity': default_positivity,
                    'action_state': default_action_state,
                    'expression_state': default_expression_state
                }
                for name in student_names
            ]

        if not validated_configs:
            return jsonify({
                'success': False,
                'error': '请提供有效的学生配置'
            }), 400

        # 重置现有学生
        current_students.clear()
        active_student_names = []

        response_configs: List[Dict[str, Any]] = []

        for cfg in validated_configs:
            name = cfg['student_name']
            student = VirtualStudent(
                student_name=name,
                enable_long_term_memory=cfg['enable_long_term_memory'],
                enable_knowledge_base=cfg['enable_knowledge_base'],
                positivity=cfg['positivity'],
                action_state=cfg['action_state'],
                expression_state=cfg['expression_state']
            )
            student.enable_vr = vr_control_enabled

            student_id = run_async(student.create_student_user())
            thread_id = run_async(student.create_study_thread())
            if not student_id or not thread_id:
                raise RuntimeError(f"{name} 创建学生用户或线程失败")

            if student.enable_vr:
                student._send_vr_event(student.action_state)

            current_students[name] = student
            active_student_names.append(name)
            response_configs.append({
                'student_name': name,
                'enable_long_term_memory': cfg['enable_long_term_memory'],
                'enable_knowledge_base': cfg['enable_knowledge_base'],
                'positivity': student.positivity,
                'action_state': student.action_state,
                'expression_state': student.expression_state,
                'student_id': student_id,
                'thread_id': thread_id
            })
            console.print(f"[green]✓ 学生 {name} 初始化完成[/green]")

        return jsonify({
            'success': True,
            'student_names': active_student_names,
            'student_configs': response_configs
        })

    except Exception as e:
        console.print(f"[red]初始化学生失败: {e}[/red]")
        current_students.clear()
        active_student_names = []
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """发送消息并根据课堂流程处理意图"""
    if not active_student_names:
        return jsonify({
            'success': False,
            'error': '请先初始化虚拟学生'
        }), 400

    try:
        data = request.json or {}
        user_message = data.get('message', '').strip()

        if not user_message:
            return jsonify({
                'success': False,
                'error': '消息不能为空'
            }), 400

        record_teacher_statement(user_message)
        intent, named_student, intent_source = detect_intent(user_message)

        if intent == INTENT_CONTINUE:
            payload = handle_continue_intent(user_message)
        elif intent == INTENT_QUESTION:
            payload = handle_question_intent(user_message, named_student)
        elif intent == INTENT_CALL:
            payload = handle_call_intent(user_message, named_student)
        elif intent == INTENT_SIT_DOWN:
            payload = handle_sit_down_intent(user_message)
        else:
            payload = build_wait_response(INTENT_CONTINUE, 'unhandled', '未能识别老师意图，默认记录。')

        payload['intent'] = intent
        payload['named_student'] = named_student
        payload['intent_source'] = intent_source
        return jsonify(payload)

    except Exception as e:
        console.print(f"[red]对话处理失败: {e}[/red]")
        console.print(f"[red]错误堆栈: {traceback.format_exc()}[/red]")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


async def _process_chat_for_student(student: VirtualStudent, user_message: str):
    """处理指定学生对话的异步函数"""
    # 获取完整的记忆上下文
    context_info = await student.get_full_memory_context()

    # 获取系统提示词
    system_prompt = student.get_system_prompt(context_info)

    # 构建消息列表
    messages = [SystemMessage(content=system_prompt)]

    # 添加历史对话（短期记忆）
    for conv in student.short_term_memory.memory_queue:
        messages.append(HumanMessage(content=conv['user_message']))
        messages.append(AIMessage(content=conv['student_response']))

    # 添加当前用户消息
    messages.append(HumanMessage(content=user_message))

    # 转换为Qwen API格式
    qwen_client = QwenAPIClient()
    qwen_messages = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            qwen_messages.append({"role": "system", "content": msg.content})
        elif isinstance(msg, AIMessage):
            # AI消息，检查是否有tool_calls
            msg_dict = {"role": "assistant", "content": msg.content or ""}
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                # 转换tool_calls格式
                tool_calls_qwen = []
                for tc in msg.tool_calls:
                    if isinstance(tc, dict):
                        tool_calls_qwen.append({
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False)
                            }
                        })
                if tool_calls_qwen:
                    msg_dict["tool_calls"] = tool_calls_qwen
            qwen_messages.append(msg_dict)
        else:
            qwen_messages.append({"role": "user", "content": msg.content})

    # 获取工具定义
    tools = student.get_tool_definitions()

    # 调用Qwen API
    response = await qwen_client.chat_completion(
        qwen_messages, 
        temperature=0.7, 
        tools=tools
    )

    # 处理响应
    result = {
        'success': True,
        'response': response.get('content', ''),
        'tool_calls': [],
        'intermediate_steps': [],
        'student_name': student.student_name
    }

    # 处理工具调用
    tool_calls = response.get('tool_calls', [])
    if tool_calls:
        # 获取工具列表
        tools_list = student.get_tools()

        # 转换工具调用格式
        formatted_tool_calls = []
        for call in tool_calls:
            if isinstance(call, dict) and "function" in call:
                args_str = call["function"].get("arguments", "{}")
                try:
                    args_dict = json.loads(args_str) if isinstance(args_str, str) else args_str
                except:
                    args_dict = {}

                tool_name = call["function"]["name"]
                tool_id = call.get("id", f"call_{len(formatted_tool_calls)}")

                formatted_tool_calls.append({
                    "name": tool_name,
                    "args": args_dict,
                    "id": tool_id
                })
                
                result['tool_calls'].append({
                    'name': tool_name,
                    'arguments': args_dict
                })
        
        # 执行工具
        if formatted_tool_calls:
            # 创建工具消息
            tool_messages = []
            for tool_call in formatted_tool_calls:
                tool_name = tool_call['name']
                tool_args = tool_call['args']
                tool_id = tool_call['id']

                # 找到对应的工具
                matched_tool = None
                for tool in tools_list:
                    # 检查工具名称 - langchain tool对象
                    if hasattr(tool, 'name') and tool.name == tool_name:
                        matched_tool = tool
                        break

                if matched_tool:
                    # 执行工具
                    try:
                        # langchain的tool对象，使用invoke方法
                        if hasattr(matched_tool, 'ainvoke'):
                            # 异步invoke
                            tool_result = await matched_tool.ainvoke(tool_args)
                        elif hasattr(matched_tool, 'invoke'):
                            # 同步invoke，在线程池中执行
                            loop = asyncio.get_event_loop()
                            tool_result = await loop.run_in_executor(
                                None,
                                lambda: matched_tool.invoke(tool_args)
                            )
                        elif hasattr(matched_tool, 'func'):
                            # 直接调用func
                            tool_func = matched_tool.func
                            if asyncio.iscoroutinefunction(tool_func):
                                tool_result = await tool_func(**tool_args)
                            else:
                                loop = asyncio.get_event_loop()
                                tool_result = await loop.run_in_executor(
                                    None,
                                    lambda: tool_func(**tool_args)
                                )
                        else:
                            # 直接调用（应该不会到这里）
                            loop = asyncio.get_event_loop()
                            tool_result = await loop.run_in_executor(
                                None,
                                lambda: matched_tool(**tool_args)
                            )
                        
                        tool_messages.append(ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_id
                        ))
                        
                        result['intermediate_steps'].append({
                            'tool': tool_name,
                            'arguments': tool_args,
                            'result': str(tool_result),
                            'student_name': student.student_name
                        })
                    except Exception as e:
                        error_msg = f"工具执行错误: {str(e)}"
                        tool_messages.append(ToolMessage(
                            content=error_msg,
                            tool_call_id=tool_id
                        ))
                        
                        result['intermediate_steps'].append({
                            'tool': tool_name,
                            'arguments': tool_args,
                            'result': error_msg,
                            'student_name': student.student_name
                        })
            
            # 如果有工具结果，再次调用API获取最终回复
            if tool_messages:
                # 添加工具消息到历史
                messages.append(AIMessage(
                    content=response.get('content', ''),
                    tool_calls=formatted_tool_calls
                ))
                messages.extend(tool_messages)
                
                # 再次调用API
                # Qwen API需要特殊格式处理工具消息
                qwen_messages = []
                for msg in messages:
                    if isinstance(msg, SystemMessage):
                        qwen_messages.append({"role": "system", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        # 处理包含tool_calls的AI消息
                        msg_dict = {"role": "assistant", "content": msg.content or ""}
                        # 如果有tool_calls，需要转换格式
                        if hasattr(msg, 'tool_calls') and msg.tool_calls:
                            # Qwen API的tool_calls格式
                            tool_calls_qwen = []
                            for tc in msg.tool_calls:
                                if isinstance(tc, dict):
                                    tool_calls_qwen.append({
                                        "id": tc.get("id", ""),
                                        "type": "function",
                                        "function": {
                                            "name": tc.get("name", ""),
                                            "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False)
                                        }
                                    })
                            if tool_calls_qwen:
                                msg_dict["tool_calls"] = tool_calls_qwen
                        qwen_messages.append(msg_dict)
                    elif isinstance(msg, ToolMessage):
                        # Qwen API的tool消息格式
                        qwen_messages.append({
                            "role": "tool",
                            "content": msg.content,
                            "tool_call_id": getattr(msg, 'tool_call_id', '')
                        })
                    else:
                        qwen_messages.append({"role": "user", "content": msg.content})
                
                final_response = await qwen_client.chat_completion(
                    qwen_messages,
                    temperature=0.7,
                    tools=tools
                )

                result['response'] = final_response.get('content', '')

    # 保存对话到短期记忆
    await student.add_conversation_to_memory(
        user_message,
        result['response']
    )

    result['action_state'] = getattr(student, 'action_state', DEFAULT_ACTION_STATE)
    result['expression_state'] = getattr(student, 'expression_state', DEFAULT_EXPRESSION_STATE)
    return result


@app.route('/api/context', methods=['GET'])
def get_context():
    """获取虚拟学生的上下文信息"""
    if not active_student_names:
        return jsonify({
            'success': False,
            'error': '请先初始化虚拟学生'
        }), 400

    try:
        students_payload = []
        for name in active_student_names:
            student = current_students.get(name)
            if not student:
                continue

            full_context = run_async(student.get_full_memory_context())
            short_term_memory = student.short_term_memory.memory_queue.copy()
            long_term_context = run_async(student.get_long_term_memory_context())

            students_payload.append({
                'student_name': student.student_name,
                'short_term_memory': short_term_memory,
                'long_term_context': long_term_context,
                'full_context': full_context,
                'enable_long_term_memory': student.enable_long_term_memory,
                'enable_knowledge_base': student.enable_knowledge_base,
                'positivity': student.positivity,
                'action_state': student.action_state,
                'expression_state': student.expression_state
            })

        return jsonify({
            'success': True,
            'students': students_payload
        })

    except Exception as e:
        console.print(f"[red]获取上下文失败: {e}[/red]")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/settings/vr', methods=['GET', 'POST'])
def vr_settings():
    """获取或设置数字人控制开关"""
    global vr_control_enabled
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'enabled': vr_control_enabled
        })

    data = request.json or {}
    if 'enabled' not in data:
        return jsonify({
            'success': False,
            'error': '缺少enabled字段'
        }), 400

    enabled = data.get('enabled')
    if isinstance(enabled, str):
        enabled = enabled.lower() in ('1', 'true', 'yes', 'on')
    else:
        enabled = bool(enabled)

    vr_control_enabled = enabled
    for student in current_students.values():
        student.enable_vr = enabled

    return jsonify({
        'success': True,
        'enabled': vr_control_enabled
    })


@app.route('/api/students/<student_name>/positivity', methods=['POST'])
def update_positivity(student_name: str):
    """更新指定学生的积极性"""
    if student_name not in current_students:
        return jsonify({
            'success': False,
            'error': '学生未初始化'
        }), 404

    data = request.json or {}
    if 'positivity' not in data:
        return jsonify({
            'success': False,
            'error': '缺少positivity字段'
        }), 400

    student = current_students[student_name]
    value = normalize_positivity(
        data.get('positivity'),
        student.positivity if hasattr(student, 'positivity') else DEFAULT_POSITIVITY
    )
    student.set_positivity(value)

    return jsonify({
        'success': True,
        'student_name': student_name,
        'positivity': student.positivity
    })


@app.route('/api/students/<student_name>/action', methods=['POST'])
def update_action_state(student_name: str):
    """更新学生动作状态"""
    student = current_students.get(student_name)
    if not student:
        return jsonify({'success': False, 'error': '学生未初始化'}), 404

    data = request.json or {}
    action_state = normalize_action_state(data.get('action_state'))
    student.set_action_state(action_state)

    return jsonify({
        'success': True,
        'student_name': student_name,
        'action_state': student.action_state
    })


@app.route('/api/students/<student_name>/expression', methods=['POST'])
def update_expression_state(student_name: str):
    """更新学生表情状态"""
    student = current_students.get(student_name)
    if not student:
        return jsonify({'success': False, 'error': '学生未初始化'}), 404

    data = request.json or {}
    expression_state = normalize_expression_state(data.get('expression_state'))
    student.set_expression_state(expression_state)

    return jsonify({
        'success': True,
        'student_name': student_name,
        'expression_state': student.expression_state
    })


@app.route('/api/speech/transcribe', methods=['POST'])
def speech_transcribe():
    """接收前端上传的音频文件，调用 FunASR 服务进行识别，并返回文本。"""
    if 'audio' not in request.files:
        return jsonify({'success': False, 'error': '缺少音频文件字段 audio'}), 400

    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'success': False, 'error': '音频文件名为空'}), 400

    filename = secure_filename(audio_file.filename)
    if not filename.lower().endswith(('.wav', '.pcm')):
        # 默认保存为 wav
        filename = f"{filename.rsplit('.', 1)[0] if '.' in filename else filename}.wav"

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    stored_name = f"{timestamp}_{filename}"
    stored_path = UPLOAD_ROOT / stored_name
    try:
        audio_file.save(stored_path)
    except Exception as exc:
        return jsonify({'success': False, 'error': f'保存音频失败: {exc}'}), 500

    try:
        results = transcribe_audio(
            host=FUNASR_HOST,
            port=FUNASR_PORT,
            audio_path=str(stored_path),
            chunk_size=FUNASR_CHUNK_SIZE,
            chunk_interval=FUNASR_CHUNK_INTERVAL,
            mode=FUNASR_MODE,
            hotword_path=FUNASR_HOTWORD,
            use_itn=FUNASR_USE_ITN,
            send_without_sleep=FUNASR_SEND_WITHOUT_SLEEP,
            use_ssl=FUNASR_USE_SSL,
            ssl_verify=FUNASR_SSL_VERIFY,
        )
    except (FunASRClientError, Exception) as exc:
        console.print(f"[red]语音识别失败: {exc}[/red]")
        return jsonify({'success': False, 'error': f'语音识别失败: {exc}'}), 500

    # 组合识别文本（优先使用最终结果）
    final_segments = [r.text for r in results if r.is_final and r.text]
    if final_segments:
        transcript = " ".join(final_segments)
    else:
        transcript = " ".join(r.text for r in results if r.text)

    return jsonify({
        'success': True,
        'transcript': transcript,
        'segments': [
            {
                'text': r.text,
                'mode': r.mode,
                'is_final': r.is_final,
                'timestamp': r.timestamp,
            } for r in results
        ],
        'audio_path': f"/api/speech/audio/{stored_name}"
    })


@app.route('/api/speech/audio/<path:filename>', methods=['GET'])
def download_audio(filename: str):
    """提供已上传音频的访问入口（用于调试或下载）。"""
    try:
        return send_from_directory(UPLOAD_ROOT, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({'success': False, 'error': '音频文件不存在'}), 404


@app.route('/api/reset', methods=['POST'])
def reset():
    """重置虚拟学生
    
    在重置前，如果开启了长期记忆，自动将短期记忆存入长期记忆
    """
    global current_students, active_student_names

    if not current_students:
        return jsonify({'success': True})

    try:
        for student in list(current_students.values()):
            if student.enable_long_term_memory and student.thread_id:
                if student.short_term_memory.memory_queue:
                    console.print(f"[yellow]正在将 {student.student_name} 的短期记忆存入长期记忆...[/yellow]")
                    try:
                        run_async(student.flush_memory_to_long_term())
                        console.print(f"[green]✓ {student.student_name} 的短期记忆已成功存入长期记忆[/green]")
                    except Exception as e:
                        console.print(f"[red]保存 {student.student_name} 的短期记忆失败: {e}[/red]")

        # 清空上传的语音文件
        try:
            clear_uploads_directory()
            console.print("[green]✓ 已清空上传音频文件[/green]")
        except Exception as exc:
            console.print(f"[yellow]清理上传音频时发生错误: {exc}[/yellow]")

        current_students.clear()
        active_student_names = []
        return jsonify({'success': True})

    except Exception as e:
        console.print(f"[red]重置时保存记忆失败: {e}[/red]")
        current_students.clear()
        active_student_names = []
        return jsonify({'success': True})


if __name__ == '__main__':
    import sys
    # 默认使用8080端口，避免与macOS的AirPlay Receiver冲突
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"警告: 无效的端口号 {sys.argv[1]}，使用默认端口 8080")
    
    print(f"启动Flask应用，访问地址: http://localhost:{port}")
    app.run(debug=True, host='0.0.0.0', port=port)

