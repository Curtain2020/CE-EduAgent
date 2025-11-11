"""
Qwen API客户端
负责与Qwen API进行通信，生成对话回复
"""

import os
import json
import requests
import asyncio
from typing import List, Dict

from ..config.settings import console, load_environment


class QwenAPIClient:
    """Qwen API 客户端
    
    功能说明：
    1. 封装Qwen API的调用逻辑
    2. 支持异步调用
    3. 支持工具调用（function calling）
    4. 统一错误处理
    """
    
    def __init__(self):
        """初始化Qwen API客户端"""
        env_config = load_environment()
        self.api_key = env_config['QWEN_API_KEY']
        self.base_url = env_config['QWEN_BASE_URL']
        self.model = env_config['QWEN_MODEL']
        
        if not self.api_key:
            raise ValueError("请设置 QWEN_API_KEY 环境变量")
    
    async def chat_completion(self, messages: List[Dict[str, str]], 
                             temperature: float = 0.7, 
                             tools: List[Dict] = None) -> Dict:
        """异步调用 Qwen API 进行对话生成
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 温度参数，控制回复的随机性
            tools: 工具定义列表（可选）
            
        Returns:
            包含content和tool_calls的字典
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }
        
        # 如果有工具，添加到请求中
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"
        
        try:
            # 使用 asyncio 在线程池中运行同步请求
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=30
                )
            )
            response.raise_for_status()
            
            result = response.json()
            message = result["choices"][0]["message"]
            
            # 返回完整的消息对象，包括工具调用
            return {
                "content": message.get("content", ""),
                "tool_calls": message.get("tool_calls", [])
            }
            
        except requests.exceptions.HTTPError as e:
            # 打印详细的错误信息
            error_detail = ""
            try:
                error_response = e.response.json()
                error_detail = f"错误详情: {error_response}"
                console.print(f"[red]Qwen API HTTP错误: {e}[/red]")
                console.print(f"[red]{error_detail}[/red]")
            except:
                error_detail = f"状态码: {e.response.status_code}, 响应: {e.response.text[:200]}"
                console.print(f"[red]Qwen API HTTP错误: {e}[/red]")
                console.print(f"[red]{error_detail}[/red]")
            
            return {
                "content": "抱歉，我现在无法回应您的消息。",
                "tool_calls": []
            }
        except Exception as e:
            console.print(f"[red]Qwen API 调用失败: {e}[/red]")
            console.print(f"[red]请求数据: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}[/red]")
            return {
                "content": "抱歉，我现在无法回应您的消息。",
                "tool_calls": []
            }

