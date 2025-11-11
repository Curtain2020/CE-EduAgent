"""
Zep长期记忆工具
提供检索长期记忆的功能，供AI模型调用
"""

from typing import Dict, List
from langchain_core.tools import tool
from zep_cloud.client import AsyncZep

from ..config.settings import console


def create_zep_tools(student_name: str, zep_client: AsyncZep):
    """创建 Zep 长期记忆检索工具
    
    Args:
        student_name: 学生姓名
        zep_client: Zep客户端实例
        
    Returns:
        工具列表
    """
    
    @tool
    async def search_memory_comprehensive(query: str, limit: int = 5) -> Dict[str, List[str]]:
        """综合检索长期记忆（事实和节点）
        
        这个工具可以搜索学生的长期记忆，包括：
        - 事实（edges）：具体的知识点和关系
        - 节点（nodes）：知识点的摘要信息
        
        Args:
            query: 搜索查询关键词
            limit: 返回结果数量限制，默认为5
            
        Returns:
            包含facts和nodes的字典
        """
        try:
            # 搜索事实（edges）
            # 使用学生名字作为user_id进行搜索
            facts_result = await zep_client.graph.search(
                user_id=student_name,  # 使用学生名字作为user_id
                query=query, 
                limit=limit, 
                scope="edges"
            )
            facts = [edge.fact for edge in facts_result.edges or []]
            
            # 搜索节点
            nodes_result = await zep_client.graph.search(
                user_id=student_name,  # 使用学生名字作为user_id
                query=query, 
                limit=limit, 
                scope="nodes"
            )
            summaries = [node.summary for node in nodes_result.nodes or []]
            
            return {
                "facts": facts if facts else ["没有找到相关事实"],
                "nodes": summaries if summaries else ["没有找到相关节点"]
            }
        except Exception as e:
            console.print(f"[red]检索长期记忆失败: {e}[/red]")
            return {
                "facts": [f"检索事实时出错: {str(e)}"],
                "nodes": [f"检索节点时出错: {str(e)}"]
            }
    
    return [search_memory_comprehensive]

