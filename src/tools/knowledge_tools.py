"""
知识库工具
提供知识库查询和更新的功能，供AI模型调用
"""

import sys
import os
from langchain_core.tools import tool

# 添加项目根目录到路径
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from knowledge_graph_manager import KnowledgeGraphManager

from ..config.settings import console


def create_knowledge_tools():
    """创建知识库检索和更新工具
    
    Returns:
        工具列表
    """
    
    # 初始化知识图谱管理器
    kg_manager = KnowledgeGraphManager()
    
    @tool
    async def recall_knowledge_tool(name: str) -> str:
        """查询知识
        
        从知识库中查找与指定名称相关的知识点，返回top3相似结果
        
        Args:
            name: 知识点名称
            
        Returns:
            知识点内容，包含top3相似结果供模型选择
        """
        try:
            # 查找相似的知识点
            similar_points = kg_manager.find_similar_knowledge_points(name, top_n=3)
            
            if not similar_points:
                return f"知识库中没有找到与 '{name}' 相关的知识点。"
            
            # 构建返回结果，让模型选择其中一个
            result_text = f"找到以下与 '{name}' 相关的知识点，请选择其中一个：\n\n"
            
            for i, point in enumerate(similar_points, 1):
                # 状态映射
                status_text = {
                    1: "已掌握",
                    -1: "未学习", 
                    2: "知识混淆",
                    -2: "知识混淆"
                }.get(point["status"], "未知状态")
                
                result_text += f"{i}. 【{point['node_name']}】\n"
                result_text += f"   - 描述: {point['description']}\n"
                result_text += f"   - 年级: {point['grade']}\n"
                result_text += f"   - 学科: {point['subject']}\n"
                result_text += f"   - 掌握状态: {status_text}\n"
                result_text += f"   - 相似度: {point['similarity_score']}\n"
                result_text += f"   - UUID: {point['uuid']}\n\n"
            
            result_text += "请根据以上信息选择最相关的知识点进行回答。"
            return result_text
            
        except Exception as e:
            console.print(f"[red]查询知识失败: {e}[/red]")
            return f"查询知识时发生错误: {str(e)}"
    
    @tool
    async def update_knowledge_tool(name: str, content: str) -> str:
        """学习并记录老师教的新内容
        
        当学生学会新知识后，调用此工具更新知识库中的知识点状态
        
        Args:
            name: 知识点名称
            content: 学会的内容
            
        Returns:
            学习结果
        """
        try:
            # 首先查找相似的知识点
            similar_points = kg_manager.find_similar_knowledge_points(name, top_n=1)
            
            if not similar_points:
                return f"知识库中没有找到与 '{name}' 相关的知识点，无法更新。"
            
            # 使用最相似的知识点进行更新
            target_point = similar_points[0]
            uuid = target_point["uuid"]
            
            # 更新知识点状态为已掌握(1)，并添加学习内容
            success = kg_manager.update_knowledge_status(
                uuid=uuid,
                new_status=1,  # 已掌握
                new_content=content
            )
            
            if success:
                console.print(f"[green]✓ 成功学习并记录知识: {target_point['node_name']}[/green]")
                return f"已成功学习并记录关于 '{target_point['node_name']}' 的新内容：{content}"
            else:
                return f"学习记录失败，请重试。"
                
        except Exception as e:
            console.print(f"[red]更新知识失败: {e}[/red]")
            return f"学习记录时发生错误: {str(e)}"
    
    return [recall_knowledge_tool, update_knowledge_tool]

