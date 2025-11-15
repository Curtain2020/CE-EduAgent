"""
学生状态定义
定义虚拟学生在对话过程中的状态结构
"""

from typing import Annotated, TypedDict, List, Dict, Literal
from langgraph.graph import add_messages


class StudentState(TypedDict):
    """虚拟学生状态定义
    
    状态包含的信息：
    - messages: 对话消息列表
    - student_name: 学生姓名
    - student_id: 学生ID
    - thread_id: 对话线程ID
    - knowledge_base: 知识库存储（字典）
    - enable_long_term_memory: 是否启用长期记忆
    - enable_knowledge_base: 是否启用知识库
    - short_term_memory: 短期记忆队列
    - positivity: 学生积极性（0-1）
    - action_state: 当前动作状态
    - expression_state: 当前表情状态
    """
    messages: Annotated[list, add_messages]
    student_name: str
    student_id: str
    thread_id: str
    knowledge_base: Dict[str, any]  # 知识库存储
    enable_long_term_memory: bool  # 是否启用长期记忆
    enable_knowledge_base: bool  # 是否启用知识库
    short_term_memory: List[Dict[str, str]]  # 短期记忆队列，容量为10
    positivity: float  # 学生积极性，范围0-1
    action_state: Literal["raiseHand", "sitProperly", "standUp", "sitDown"]
    expression_state: Literal["calm", "dazed", "smile"]

