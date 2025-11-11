"""
学生相关模块
包含虚拟学生类、状态定义和系统提示词
"""

from .virtual_student import VirtualStudent
from .student_state import StudentState
from .system_prompts import get_system_prompt, get_tool_definitions

__all__ = ['VirtualStudent', 'StudentState', 'get_system_prompt', 'get_tool_definitions']

