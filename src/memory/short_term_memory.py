"""
短期记忆管理器
负责管理最近的对话记录，并在容量满时自动存入长期记忆
"""

import asyncio
from typing import List, Dict
from datetime import datetime
from zep_cloud import Message

from ..config.settings import console


class ShortTermMemoryManager:
    """短期记忆管理器
    
    功能说明：
    1. 维护一个固定容量的对话队列（默认10条）
    2. 当队列满时，自动将最旧的对话存入长期记忆
    3. 提供获取上下文的方法
    4. 支持将所有对话一次性存入长期记忆
    """
    
    def __init__(self, capacity: int = 10):
        """初始化短期记忆管理器
        
        Args:
            capacity: 短期记忆容量，默认10条对话
        """
        self.capacity = capacity
        self.memory_queue = []  # 对话队列
        self.zep_client = None  # Zep客户端，用于保存到长期记忆
    
    def set_zep_client(self, zep_client):
        """设置Zep客户端
        
        Args:
            zep_client: Zep客户端实例
        """
        self.zep_client = zep_client
    
    def add_conversation(self, user_message: str, student_response: str, 
                        student_name: str, thread_id: str = None) -> List[Dict[str, str]]:
        """添加对话到短期记忆队列
        
        Args:
            user_message: 用户（老师）的消息
            student_response: 学生回复
            student_name: 学生姓名
            thread_id: 线程ID，用于保存到长期记忆
            
        Returns:
            更新后的短期记忆队列
        """
        # 创建对话记录
        conversation = {
            "user_message": user_message,
            "student_response": student_response,
            "student_name": student_name,
            "timestamp": datetime.now().isoformat()
        }
        
        # 添加到队列
        self.memory_queue.append(conversation)
        
        # 如果超过容量，将最旧的对话存入长期记忆
        if len(self.memory_queue) > self.capacity:
            oldest_conversation = self.memory_queue.pop(0)
            if self.zep_client and thread_id:
                # 异步保存到长期记忆，不阻塞当前流程
                asyncio.create_task(
                    self._save_to_long_term_memory(oldest_conversation, thread_id)
                )
        
        return self.memory_queue.copy()
    
    async def _save_to_long_term_memory(self, conversation: Dict[str, str], thread_id: str):
        """将对话保存到长期记忆（私有方法）
        
        Args:
            conversation: 对话记录
            thread_id: 线程ID
        """
        try:
            messages = [
                Message(role="user", content=conversation["user_message"], name="老师"),
                Message(role="assistant", content=conversation["student_response"], 
                       name=conversation["student_name"])
            ]
            await self.zep_client.thread.add_messages(
                thread_id=thread_id,
                messages=messages
            )
            console.print(f"[yellow]对话已存入长期记忆: {conversation['user_message'][:30]}...[/yellow]")
        except Exception as e:
            console.print(f"[red]保存到长期记忆失败: {e}[/red]")
    
    async def flush_to_long_term_memory(self, thread_id: str):
        """将剩余的所有对话存入长期记忆
        
        通常在对话结束时调用，确保所有短期记忆都保存到长期记忆
        
        Args:
            thread_id: 线程ID
        """
        if not self.zep_client or not self.memory_queue:
            return
        
        try:
            for conversation in self.memory_queue:
                messages = [
                    Message(role="user", content=conversation["user_message"], name="老师"),
                    Message(role="assistant", content=conversation["student_response"], 
                           name=conversation["student_name"])
                ]
                await self.zep_client.thread.add_messages(
                    thread_id=thread_id,
                    messages=messages
                )
                console.print(f"[green]✓ 对话已存入长期记忆: {conversation['user_message'][:30]}...[/green]")
            
            # 清空短期记忆
            self.memory_queue.clear()
            console.print("[green]✓ 所有短期记忆已存入长期记忆[/green]")
        except Exception as e:
            console.print(f"[red]批量保存到长期记忆失败: {e}[/red]")
    
    def get_context(self) -> str:
        """获取短期记忆上下文
        
        Returns:
            格式化的短期记忆文本
        """
        if not self.memory_queue:
            return "没有短期记忆。"
        
        context = "短期记忆中的对话历史：\n"
        for i, conversation in enumerate(self.memory_queue, 1):
            context += f"{i}. 老师: {conversation['user_message']}\n"
            context += f"   学生: {conversation['student_response']}\n\n"
        
        return context

