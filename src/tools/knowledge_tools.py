"""
知识库工具
提供知识库查询和更新的功能，供AI模型调用
"""

import sys
import os
from langchain_core.tools import tool
import json

# 添加项目根目录到路径
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from knowledge_graph_manager import KnowledgeGraphManager
from typing import Optional

from ..config.settings import console


def create_knowledge_tools(student_label_en: Optional[str] = None):
    """创建知识库检索和更新工具
    
    Returns:
        工具列表
    """
    
    # 初始化知识图谱管理器
    kg_manager = KnowledgeGraphManager(student_label_en=student_label_en)
    
    @tool
    async def recall_knowledge_vector_tool(name: str) -> str:
        """
        检索知识点，返回三维掌握向量 status=[m,u,c]（整数 -2..2），并按规则展示内容：
        - 若 status 全 0：不展示描述与 QA，仅提示“尚未掌握”
        - 若任一维 >0：展示描述，并仅展示与对应层级相关的 QA（m→记忆/理解；u→应用/分析；c→评价/创造）
        """
        try:
            items = kg_manager.find_similar_knowledge_points(name, top_n=3)
            if not items:
                return f"知识库中没有找到与 '{name}' 相关的知识点。"

            def explain(vec):
                v = vec if isinstance(vec, list) and len(vec) == 3 else [0,0,0]
                tags = []
                if v[0] > 0: tags.append("能记忆理解")
                if v[1] > 0: tags.append("能应用分析")
                if v[2] > 0: tags.append("能评价创造")
                if not tags: tags.append("尚未掌握")
                return f"{v}（" + "、".join(tags) + "）"

            def filter_qa_by_vector(qa_list, vec):
                """按向量开放层级筛选 QA"""
                if not isinstance(qa_list, list) or not qa_list:
                    return []
                v = vec if isinstance(vec, list) and len(vec) == 3 else [0,0,0]
                allow = set()
                if v[0] > 0: allow.update(["remember","understand","记忆","理解"])
                if v[1] > 0: allow.update(["apply","analyze","analyse","应用","分析"])
                if v[2] > 0: allow.update(["evaluate","create","评价","创造"])
                if not allow:
                    return []
                def norm(x: str) -> str:
                    return (x or "").strip().lower()
                out = []
                for qa in qa_list:
                    lv = norm(qa.get("level_zh") or qa.get("level"))
                    if any(tag in lv for tag in allow):
                        out.append(qa)
                return out

            lines = [f"与 '{name}' 相关的知识点（status=[m,u,c]）：" , ""]
            for i, p in enumerate(items, 1):
                vec = p.get('status') or [0,0,0]
                vec3 = vec if (isinstance(vec, list) and len(vec) == 3) else [0,0,0]
                any_pos = any((isinstance(x, int) and x > 0) for x in vec3)
                lines.append(f"{i}. 【{p.get('node_name','')}】  年级:{p.get('grade','')}  学科:{p.get('subject','')}")
                lines.append(f"   - 掌握向量: {explain(vec3)}")

                if any_pos:
                    # 描述
                    desc = (p.get('description') or '').strip()
                    if desc:
                        lines.append(f"   - 描述: {desc[:200]}{'...' if len(desc)>200 else ''}")
                    # QA（可能为 JSON 字符串）
                    qa_raw = p.get('bloom_qa_pairs')
                    try:
                        if isinstance(qa_raw, str):
                            qa_list = json.loads(qa_raw) or []
                        elif isinstance(qa_raw, list):
                            qa_list = qa_raw
                        else:
                            qa_list = []
                    except Exception:
                        qa_list = []
                    qa_list = filter_qa_by_vector(qa_list, vec3)
                    if qa_list:
                        lines.append("   - 相关问答：")
                        for idx, qa in enumerate(qa_list[:5], 1):
                            lv = (qa.get("level_zh") or qa.get("level") or "—").strip()
                            q = (qa.get("question") or "").strip()
                            a = (qa.get("answer") or "").strip()
                            q_show = q[:120] + ("..." if len(q) > 120 else "")
                            a_show = a[:160] + ("..." if len(a) > 160 else "")
                            lines.append(f"       {idx}. [{lv}] Q: {q_show}")
                            lines.append(f"               A: {a_show}")
                else:
                    lines.append("   - 提示：该知识点尚未掌握（向量全 0），暂不提供描述与问答。")

                lines.append(f"   - 相似度: {p.get('similarity_score')}")
                lines.append(f"   - UUID: {p.get('uuid')}\n")

            lines.append("作答请依据向量：若仅 m>0，请讲概念但不要直接做题；u/c≤0 时说明不足并提出需要的支架。")
            return "\n".join(lines)
        except Exception as e:
            console.print(f"[red]查询知识失败: {e}[/red]")
            return f"查询知识时发生错误: {str(e)}"
    
    @tool
    async def update_knowledge_vector_tool(name: str, index: int, value: int) -> str:
        """将知识点掌握向量的某一维（0/1/2）更新为 0/1，不覆盖其它维度"""
        try:
            items = kg_manager.find_similar_knowledge_points(name, top_n=1)
            if not items:
                return f"知识库中没有找到与 '{name}' 相关的知识点，无法更新。"
            uuid = items[0]['uuid']
            ok = kg_manager.update_knowledge_vector(uuid=uuid, index=int(index), value=int(value))
            if ok:
                return f"已更新 '{items[0]['node_name']}' 的向量第 {int(index)} 维 为 {int(value)}。"
            return "更新失败，请重试。"
        except Exception as e:
            console.print(f"[red]更新知识失败: {e}[/red]")
            return f"更新向量时发生错误: {str(e)}"
    
    return [recall_knowledge_vector_tool, update_knowledge_vector_tool]

