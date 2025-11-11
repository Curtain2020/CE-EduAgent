"""
Flask Web应用 - 虚拟学生对话系统
提供教师与虚拟学生对话的网页界面
"""

import json
import asyncio
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
from src.config.settings import console
from src.services.funasr_ws import transcribe_audio, parse_chunk_sizes, FunASRClientError, TranscriptionResult
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import ToolNode
from langchain_core.messages import ToolMessage

app = Flask(__name__)
CORS(app)

# 全局虚拟学生实例
current_student: VirtualStudent = None

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


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/init', methods=['POST'])
def init_student():
    """初始化虚拟学生
    
    请求体：
    {
        "student_name": "小明",
        "enable_long_term_memory": true,
        "enable_knowledge_base": false
    }
    """
    global current_student
    
    try:
        data = request.json
        student_name = data.get('student_name', '小明')
        enable_long_term_memory = data.get('enable_long_term_memory', True)
        enable_knowledge_base = data.get('enable_knowledge_base', False)
        
        # 创建虚拟学生
        current_student = VirtualStudent(
            student_name=student_name,
            enable_long_term_memory=enable_long_term_memory,
            enable_knowledge_base=enable_knowledge_base
        )
        
        # 创建学生用户和线程
        student_id = run_async(current_student.create_student_user())
        thread_id = run_async(current_student.create_study_thread())
        
        if not student_id or not thread_id:
            return jsonify({
                'success': False,
                'error': '创建学生用户或线程失败'
            }), 500
        
        return jsonify({
            'success': True,
            'student_id': student_id,
            'thread_id': thread_id,
            'student_name': current_student.student_name,
            'enable_long_term_memory': enable_long_term_memory,
            'enable_knowledge_base': enable_knowledge_base
        })
    
    except Exception as e:
        console.print(f"[red]初始化学生失败: {e}[/red]")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """发送消息并获取回复
    
    请求体：
    {
        "message": "你好，小明"
    }
    """
    global current_student
    
    if current_student is None:
        return jsonify({
            'success': False,
            'error': '请先初始化虚拟学生'
        }), 400
    
    try:
        data = request.json
        user_message = data.get('message', '')
        
        if not user_message:
            return jsonify({
                'success': False,
                'error': '消息不能为空'
            }), 400
        
        # 异步处理对话
        result = run_async(_process_chat(user_message))
        
        return jsonify(result)
    
    except Exception as e:
        console.print(f"[red]对话处理失败: {e}[/red]")
        console.print(f"[red]错误堆栈: {traceback.format_exc()}[/red]")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


async def _process_chat(user_message: str):
    """处理对话的异步函数"""
    global current_student
    
    # 获取完整的记忆上下文
    context_info = await current_student.get_full_memory_context()
    
    # 获取系统提示词
    system_prompt = current_student.get_system_prompt(context_info)
    
    # 构建消息列表
    messages = [SystemMessage(content=system_prompt)]
    
    # 添加历史对话（短期记忆）
    for conv in current_student.short_term_memory.memory_queue:
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
    tools = current_student.get_tool_definitions()
    
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
        'intermediate_steps': []
    }
    
    # 处理工具调用
    tool_calls = response.get('tool_calls', [])
    if tool_calls:
        # 获取工具列表
        tools_list = current_student.get_tools()
        
        # 创建工具映射（按名称）
        tools_map = {}
        for tool in tools_list:
            if hasattr(tool, 'name'):
                tools_map[tool.name] = tool
            elif hasattr(tool, '__name__'):
                tools_map[tool.__name__] = tool
        
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
                            'result': str(tool_result)
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
                            'result': error_msg
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
    await current_student.add_conversation_to_memory(
        user_message,
        result['response']
    )
    
    return result


@app.route('/api/context', methods=['GET'])
def get_context():
    """获取虚拟学生的上下文信息"""
    global current_student
    
    if current_student is None:
        return jsonify({
            'success': False,
            'error': '请先初始化虚拟学生'
        }), 400
    
    try:
        # 获取完整上下文
        full_context = run_async(current_student.get_full_memory_context())
        
        # 获取短期记忆
        short_term_memory = current_student.short_term_memory.memory_queue.copy()
        
        # 获取长期记忆上下文
        long_term_context = run_async(current_student.get_long_term_memory_context())
        
        return jsonify({
            'success': True,
            'short_term_memory': short_term_memory,
            'long_term_context': long_term_context,
            'full_context': full_context,
            'student_name': current_student.student_name,
            'enable_long_term_memory': current_student.enable_long_term_memory,
            'enable_knowledge_base': current_student.enable_knowledge_base
        })
    
    except Exception as e:
        console.print(f"[red]获取上下文失败: {e}[/red]")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


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
    global current_student
    
    if current_student is None:
        return jsonify({'success': True})
    
    try:
        # 如果开启了长期记忆，先将短期记忆存入长期记忆
        if current_student.enable_long_term_memory and current_student.thread_id:
            # 检查是否有短期记忆需要保存
            if current_student.short_term_memory.memory_queue:
                console.print("[yellow]正在将短期记忆存入长期记忆...[/yellow]")
                
                try:
                    # 使用run_async确保事件循环正确管理
                    run_async(current_student.flush_memory_to_long_term())
                    console.print("[green]✓ 短期记忆已成功存入长期记忆[/green]")
                except Exception as e:
                    console.print(f"[red]保存短期记忆到长期记忆失败: {e}[/red]")
        
        # 清空上传的语音文件
        try:
            clear_uploads_directory()
            console.print("[green]✓ 已清空上传音频文件[/green]")
        except Exception as exc:
            console.print(f"[yellow]清理上传音频时发生错误: {exc}[/yellow]")
        
        # 重置虚拟学生
        current_student = None
        return jsonify({'success': True})
    
    except Exception as e:
        console.print(f"[red]重置时保存记忆失败: {e}[/red]")
        # 即使保存失败，也继续重置
        current_student = None
        try:
            clear_uploads_directory()
            console.print("[green]✓ 已清空上传音频文件[/green]")
        except Exception as exc:
            console.print(f"[yellow]清理上传音频时发生错误: {exc}[/yellow]")
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

