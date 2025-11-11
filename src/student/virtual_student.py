"""
虚拟学生主类
完整的虚拟学生实现，集成tool、prompt、memory三大核心功能
"""

import uuid
from typing import List, Optional
from zep_cloud.client import AsyncZep

from ..config.settings import load_environment, console
from ..memory.short_term_memory import ShortTermMemoryManager
from ..api.qwen_client import QwenAPIClient
from .system_prompts import get_system_prompt, get_tool_definitions
from ..tools.zep_tools import create_zep_tools
from ..tools.knowledge_tools import create_knowledge_tools


class VirtualStudent:
    """完整的虚拟学生实现
    
    集成三大核心功能：
    1. Tool（工具）：提供长期记忆检索和知识库查询/更新工具
    2. Prompt（提示词）：管理系统提示词，支持基础模式和认知增强模式
    3. Memory（记忆）：管理短期记忆和长期记忆
    
    功能说明：
    1. 管理学生用户的创建和配置
    2. 管理学习对话线程
    3. 集成短期记忆和长期记忆功能
    4. 提供工具管理和提示词管理
    """
    
    def __init__(self, 
                 student_name: str = "崔展豪",
                 enable_long_term_memory: bool = True,
                 enable_knowledge_base: bool = False):
        """初始化虚拟学生
        
        Args:
            student_name: 学生姓名，默认为"崔展豪"
            enable_long_term_memory: 是否启用长期记忆，默认为True
            enable_knowledge_base: 是否启用知识库（认知增强），默认为False
        """
        # 加载环境配置
        env_config = load_environment()
        self.zep_api_key = env_config['ZEP_API_KEY']
        
        # 注意：不在初始化时创建AsyncZep客户端，避免事件循环绑定问题
        # 在需要使用时再创建，确保使用正确的事件循环
        self.zep = None
        
        # 初始化 Qwen 客户端
        self.qwen_client = QwenAPIClient()
        
        # ========== Memory（记忆管理） ==========
        self.short_term_memory = ShortTermMemoryManager(capacity=10)
        self.student_name = student_name
        self.enable_long_term_memory = enable_long_term_memory
        self.enable_knowledge_base = enable_knowledge_base
        
        # 学生ID和线程ID（在创建用户和线程后设置）
        self.student_id: Optional[str] = None
        self.thread_id: Optional[str] = None
    
    def _get_zep_client(self) -> AsyncZep:
        """获取Zep客户端（每次使用都创建新客户端，避免事件循环冲突）"""
        # 每次都创建新的客户端，确保使用当前线程的事件循环
        # 这样避免在不同事件循环中使用同一个客户端导致的错误
        zep = AsyncZep(api_key=self.zep_api_key)
        # 设置短期记忆管理器的客户端（如果还没有设置）
        if self.short_term_memory.zep_client is None:
            self.short_term_memory.set_zep_client(zep)
        return zep
    
    # ========== Tool（工具管理） ==========
    
    def get_tools(self) -> List:
        """获取工具列表
        
        根据配置返回可用的工具列表：
        - 如果启用长期记忆：包含Zep长期记忆检索工具
        - 如果启用知识库：包含知识库查询和更新工具
        
        Returns:
            工具列表
        """
        tools = []
        
        # 长期记忆工具（如果启用）
        if self.enable_long_term_memory:
            # 获取Zep客户端
            zep = self._get_zep_client()
            # 使用zep_tools中的长期记忆工具
            zep_tools = create_zep_tools(self.student_name, zep)
            tools.extend(zep_tools)
        
        # 知识库工具（如果启用）
        if self.enable_knowledge_base:
            knowledge_tools = create_knowledge_tools()
            tools.extend(knowledge_tools)
        
        return tools
    
    def get_tool_definitions(self) -> Optional[List]:
        """获取工具定义列表（用于Qwen API）
        
        根据配置返回工具定义：
        - 如果启用长期记忆：包含长期记忆检索工具定义
        - 如果启用知识库：包含知识库工具定义
        
        Returns:
            工具定义列表，如果都未启用则返回None
        """
        # 如果都没有启用，返回None
        if not self.enable_long_term_memory and not self.enable_knowledge_base:
            return None
        
        # 使用system_prompts中的工具定义函数
        return get_tool_definitions(
            enable_long_term_memory=self.enable_long_term_memory,
            enable_knowledge_base=self.enable_knowledge_base
        )
    
    # ========== Prompt（提示词管理） ==========
    
    def get_system_prompt(self, context_info: str = None) -> str:
        """获取系统提示词
        
        Args:
            context_info: 上下文信息（包含短期记忆和长期记忆），如果为None则自动获取
            
        Returns:
            系统提示词字符串
        """
        # 如果未提供上下文信息，自动获取
        if context_info is None:
            context_info = self.get_memory_context()
        
        # 根据配置返回对应的提示词
        return get_system_prompt(
            context_info, 
            enable_knowledge_base=self.enable_knowledge_base,
            enable_long_term_memory=self.enable_long_term_memory
        )
    
    # ========== Memory（记忆管理） ==========
    
    def get_memory_context(self) -> str:
        """获取记忆上下文
        
        整合短期记忆和长期记忆，返回格式化的上下文信息
        
        Returns:
            格式化的记忆上下文字符串
        """
        # 获取短期记忆上下文
        short_term_context = self.short_term_memory.get_context()
        
        # 长期记忆上下文（如果需要从Zep获取，需要异步调用，这里只返回短期记忆）
        # 长期记忆的获取应该在异步方法中进行
        long_term_context = ""
        
        # 合并上下文信息
        context_info = f"{short_term_context}\n长期记忆信息：\n{long_term_context if long_term_context else '长期记忆将在对话时获取'}"
        
        return context_info
    
    async def get_long_term_memory_context(self) -> str:
        """异步获取长期记忆上下文
        
        Returns:
            长期记忆上下文字符串
        """
        if not self.enable_long_term_memory or not self.thread_id:
            return "长期记忆功能已禁用或未创建线程。"
        
        try:
            # 获取Zep客户端（确保使用正确的事件循环）
            zep = self._get_zep_client()
            
            # 使用thread_id获取线程信息
            thread = await zep.thread.get(self.thread_id)
            if thread and hasattr(thread, 'summary') and thread.summary:
                return thread.summary
            elif thread and hasattr(thread, 'context') and thread.context:
                return thread.context
            else:
                # 尝试从线程获取消息历史
                # 注意：Zep API可能没有直接获取消息的方法，我们只返回线程摘要
                # 如果需要完整的消息历史，可以通过短期记忆获取
                return "长期记忆已保存，可通过短期记忆查看最近对话。"
        except Exception as e:
            console.print(f"[red]获取长期记忆失败: {e}[/red]")
            import traceback
            console.print(f"[red]错误堆栈: {traceback.format_exc()}[/red]")
            return f"获取长期记忆时出错: {str(e)}"
    
    async def get_full_memory_context(self) -> str:
        """获取完整的记忆上下文（包括短期和长期记忆）
        
        Returns:
            完整的记忆上下文字符串
        """
        # 获取短期记忆上下文
        short_term_context = self.short_term_memory.get_context()
        
        # 获取长期记忆上下文
        long_term_context = ""
        if self.enable_long_term_memory:
            long_term_context = await self.get_long_term_memory_context()
        else:
            long_term_context = "长期记忆功能已禁用。"
        
        # 合并上下文信息
        context_info = f"{short_term_context}\n长期记忆信息：\n{long_term_context}"
        
        return context_info
    
    # ========== 用户和线程管理 ==========
    
    async def create_student_user(self, student_name: str = None, email: str = None) -> str:
        """创建学生用户
        
        注意：user_id直接使用学生名字，这样在Zep中可以用名字检索
        
        Args:
            student_name: 学生姓名，如果为None则使用初始化时的姓名
            email: 学生邮箱，如果为None则自动生成
            
        Returns:
            学生ID（即学生名字），如果创建失败返回None
        """
        # 使用传入的姓名或默认姓名
        if student_name:
            self.student_name = student_name
        
        # 自动生成邮箱
        if email is None:
            email = f"{self.student_name}@student.com"
        
        # 直接使用学生名字作为user_id，这样更直观
        student_id = self.student_name
        
        try:
            # 获取Zep客户端
            zep = self._get_zep_client()
            await zep.user.add(
                user_id=student_id,  # 使用学生名字作为user_id
                email=email,
                first_name=self.student_name,
                last_name="学生"
            )
            console.print(f"[green]✓ 学生用户 {self.student_name} 创建成功，ID: {student_id}[/green]")
            self.student_id = student_id
            return student_id
        except Exception as e:
            # 如果用户已存在，也认为是成功的
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                console.print(f"[yellow]学生用户 {self.student_name} 已存在，继续使用[/yellow]")
                self.student_id = student_id
                return student_id
            console.print(f"[red]创建学生用户失败: {e}[/red]")
            return None
    
    async def create_study_thread(self, student_id: str = None) -> str:
        """创建学习对话线程
        
        注意：user_id应该是学生名字，thread_id用于区分不同的对话会话
        
        Args:
            student_id: 学生ID，如果为None则使用当前学生ID（实际会使用学生名字）
            
        Returns:
            线程ID，如果创建失败返回None
        """
        # 使用传入的学生ID或当前学生ID
        if student_id is None:
            if self.student_id is None:
                console.print("[red]请先创建学生用户[/red]")
                return None
            student_id = self.student_id
        
        thread_id = str(uuid.uuid4())
        
        try:
            # 获取Zep客户端
            zep = self._get_zep_client()
            # 使用学生名字作为user_id，thread_id用于区分不同的对话会话
            # 这样同一个学生可以有多个对话线程
            await zep.thread.create(
                user_id=self.student_name,  # 使用学生名字作为user_id
                thread_id=thread_id
            )
            console.print(f"[green]✓ 学习对话线程创建成功，ID: {thread_id}[/green]")
            console.print(f"[green]  用户ID(学生名字): {self.student_name}[/green]")
            self.thread_id = thread_id
            return thread_id
        except Exception as e:
            console.print(f"[red]创建学习对话线程失败: {e}[/red]")
            return None
    
    async def add_conversation_to_memory(self, user_message: str, 
                                        student_response: str, 
                                        thread_id: str = None):
        """将对话添加到短期记忆队列
        
        Args:
            user_message: 用户消息
            student_response: 学生回复
            thread_id: 线程ID，如果为None则使用当前线程ID
        """
        # 使用传入的线程ID或当前线程ID
        if thread_id is None:
            if self.thread_id is None:
                console.print("[red]请先创建学习线程[/red]")
                return
            thread_id = self.thread_id
        
        try:
            self.short_term_memory.add_conversation(
                user_message, student_response, self.student_name, thread_id
            )
            console.print(f"[green]✓ 对话已添加到短期记忆队列[/green]")
        except Exception as e:
            console.print(f"[red]添加对话到短期记忆失败: {e}[/red]")
    
    async def flush_memory_to_long_term(self, thread_id: str = None):
        """将短期记忆中的所有对话存入长期记忆
        
        Args:
            thread_id: 线程ID，如果为None则使用当前线程ID
        """
        # 使用传入的线程ID或当前线程ID
        if thread_id is None:
            if self.thread_id is None:
                console.print("[red]请先创建学习线程[/red]")
                return
            thread_id = self.thread_id
        
        await self.short_term_memory.flush_to_long_term_memory(thread_id)
    
    # ========== 配置管理 ==========
    
    def set_enable_long_term_memory(self, enable: bool):
        """设置是否启用长期记忆
        
        Args:
            enable: 是否启用
        """
        self.enable_long_term_memory = enable
    
    def set_enable_knowledge_base(self, enable: bool):
        """设置是否启用知识库（认知增强）
        
        Args:
            enable: 是否启用
        """
        self.enable_knowledge_base = enable

