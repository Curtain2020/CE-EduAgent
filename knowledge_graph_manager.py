"""
Neo4j知识图谱管理类
用于与Neo4j数据库交互，实现知识点的查询和更新
"""

import json
import jellyfish
from typing import List, Dict, Optional, Tuple
from neo4j import GraphDatabase
from rich.console import Console
import re
import os
from datetime import datetime

console = Console()


class KnowledgeGraphManager:
    """Neo4j知识图谱管理器"""
    
    def __init__(self, uri: str = "bolt://localhost:7687", username: str = "neo4j", password: str = "51265903089", student_label_en: Optional[str] = None):
        """初始化Neo4j连接"""
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.console = Console()
        # 学生英文标签（例如 Ccuizhanhao），用于拼接成 KnowledgePoint_Ccuizhanhao
        self.student_label_en = self._sanitize_label(student_label_en)
    
    def _sanitize_label(self, label: Optional[str]) -> Optional[str]:
        """将传入的英文标签清洗为只包含字母数字下划线，返回 None 表示使用通用标签"""
        if not label:
            return None
        safe = re.sub(r"[^A-Za-z0-9_]", "", str(label))
        return safe or None
    
    def _label(self) -> str:
        """返回当前应使用的节点标签"""
        base = "KnowledgePoint"
        if self.student_label_en:
            return f"{base}_{self.student_label_en}"
        return base
    
    def close(self):
        """关闭数据库连接"""
        self.driver.close()
    
    def test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1")
                result.single()
                return True
        except Exception as e:
            self.console.print(f"[red]Neo4j连接失败: {e}[/red]")
            return False
    
    def find_similar_knowledge_points(self, target_name: str, top_n: int = 3) -> List[Dict]:
        """查找相似的知识点，返回top_n个结果
        
        Args:
            target_name (str): 目标知识点名称
            top_n (int): 返回结果数量
            
        Returns:
            List[Dict]: 相似知识点列表，包含相似度分数
        """
        try:
            with self.driver.session() as session:
                # 查询所有知识点
                label = self._label()
                result = session.run(f"""
                    MATCH (n:`{label}`)
                    RETURN n.uuid as uuid, 
                           n.node_name as node_name,
                           n.description as description,
                           n.grade as grade,
                           n.subject as subject,
                           n.status as status,
                           n.bloom_qa_pairs as bloom_qa_pairs
                """)
                
                all_nodes = []
                for record in result:
                    node_data = {
                        "uuid": record["uuid"],
                        "node_name": record["node_name"],
                        "description": record["description"],
                        "grade": record["grade"],
                        "subject": record["subject"],
                        "status": record["status"],
                        "bloom_qa_pairs": record["bloom_qa_pairs"]
                    }
                    all_nodes.append(node_data)
                
                # 使用jellyfish计算相似度
                scored_nodes = []
                for node in all_nodes:
                    node_name = node["node_name"]
                    if node_name:  # 确保节点名称不为空
                        score = jellyfish.jaro_winkler_similarity(target_name, node_name)
                        scored_nodes.append((node, score))
                
                # 按相似度降序排序
                scored_nodes.sort(key=lambda x: x[1], reverse=True)
                
                # 返回top_n个结果
                top_results = []
                for node, score in scored_nodes[:top_n]:
                    result_item = {
                        "uuid": node["uuid"],
                        "node_name": node["node_name"],
                        "description": node["description"],
                        "grade": node["grade"],
                        "subject": node["subject"],
                        "status": node["status"],
                        "similarity_score": round(score, 3),
                        "bloom_qa_pairs": node["bloom_qa_pairs"]
                    }
                    top_results.append(result_item)
                
                return top_results
                
        except Exception as e:
            self.console.print(f"[red]查询相似知识点失败: {e}[/red]")
            return []
    
    def get_knowledge_point_by_uuid(self, uuid: str) -> Optional[Dict]:
        """根据UUID获取知识点详情
        
        Args:
            uuid (str): 知识点UUID
            
        Returns:
            Optional[Dict]: 知识点信息，如果不存在则返回None
        """
        try:
            with self.driver.session() as session:
                label = self._label()
                result = session.run(f"""
                    MATCH (n:`{label}` {{uuid: $uuid}})
                    RETURN n.uuid as uuid,
                           n.node_name as node_name,
                           n.description as description,
                           n.grade as grade,
                           n.subject as subject,
                           n.status as status,
                           n.bloom_qa_pairs as bloom_qa_pairs
                """, uuid=uuid)
                
                record = result.single()
                if record:
                    return {
                        "uuid": record["uuid"],
                        "node_name": record["node_name"],
                        "description": record["description"],
                        "grade": record["grade"],
                        "subject": record["subject"],
                        "status": record["status"],
                        "bloom_qa_pairs": record["bloom_qa_pairs"]
                    }
                return None
                
        except Exception as e:
            self.console.print(f"[red]获取知识点详情失败: {e}[/red]")
            return None
    
    def update_knowledge_status(self, uuid: str, new_status: int, new_content: str = None) -> bool:
        """更新知识点的掌握状态
        
        Args:
            uuid (str): 知识点UUID
            new_status (int): 新的掌握状态 (1: 已掌握, -1: 未学习, 2/-2: 知识混淆)
            new_content (str): 新的学习内容（可选）
            
        Returns:
            bool: 更新是否成功
        """
        try:
            with self.driver.session() as session:
                label = self._label()
                # 更新状态
                session.run(f"""
                    MATCH (n:`{label}` {{uuid: $uuid}})
                    SET n.status = $new_status
                """, uuid=uuid, new_status=new_status)
                
                # 如果有新内容，更新bloom_qa_pairs
                if new_content:
                    # 获取现有的bloom_qa_pairs
                    result = session.run(f"""
                        MATCH (n:`{label}` {{uuid: $uuid}})
                        RETURN n.bloom_qa_pairs as bloom_qa_pairs
                    """, uuid=uuid)
                    
                    record = result.single()
                    if record and record["bloom_qa_pairs"]:
                        try:
                            # 解析现有的bloom_qa_pairs
                            existing_pairs = json.loads(record["bloom_qa_pairs"])
                        except:
                            existing_pairs = []
                    else:
                        existing_pairs = []
                    
                    # 添加新的学习内容
                    new_pair = {
                        "question": f"关于{uuid}的学习内容",
                        "answer": new_content,
                        "timestamp": str(datetime.now())
                    }
                    existing_pairs.append(new_pair)
                    
                    # 更新bloom_qa_pairs
                    session.run(f"""
                        MATCH (n:`{label}` {{uuid: $uuid}})
                        SET n.bloom_qa_pairs = $bloom_qa_pairs
                    """, uuid=uuid, bloom_qa_pairs=json.dumps(existing_pairs, ensure_ascii=False))
                
                self.console.print(f"[green]✓ 知识点状态更新成功: {uuid} -> 状态: {new_status}[/green]")
                return True
                
        except Exception as e:
            self.console.print(f"[red]更新知识点状态失败: {e}[/red]")
            return False
    
    def get_knowledge_statistics(self) -> Dict:
        """获取知识图谱统计信息
        
        Returns:
            Dict: 统计信息
        """
        try:
            with self.driver.session() as session:
                # 总节点数
                total_result = session.run("MATCH (n:KnowledgePoint) RETURN count(n) as total")
                total_count = total_result.single()["total"]
                
                # 按状态统计
                status_result = session.run("""
                    MATCH (n:KnowledgePoint)
                    RETURN n.status as status, count(n) as count
                    ORDER BY status
                """)
                
                status_stats = {}
                for record in status_result:
                    status_stats[record["status"]] = record["count"]
                
                # 按年级统计
                grade_result = session.run("""
                    MATCH (n:KnowledgePoint)
                    RETURN n.grade as grade, count(n) as count
                    ORDER BY grade
                """)
                
                grade_stats = {}
                for record in grade_result:
                    grade_stats[record["grade"]] = record["count"]
                
                return {
                    "total_nodes": total_count,
                    "status_distribution": status_stats,
                    "grade_distribution": grade_stats
                }
                
        except Exception as e:
            self.console.print(f"[red]获取统计信息失败: {e}[/red]")
            return {}

    # ========== 导入管理（按学生与阶段） ==========
    def _validate_data(self, data: Dict) -> None:
        """验证节点与边的基本字段"""
        for edge in data.get("edges", []):
            if "start_uuid" not in edge or "end_uuid" not in edge or "type" not in edge:
                raise ValueError("Edge is missing required fields: start_uuid, end_uuid, or type")
            if "properties" not in edge or "description" not in edge["properties"]:
                # 允许缺省描述，走默认
                pass
        for node in data.get("nodes", []):
            if "properties" not in node:
                raise ValueError("Node is missing properties field")
            if "uuid" not in node["properties"]:
                raise ValueError("Node is missing uuid in properties")
            if "node_name" not in node["properties"]:
                raise ValueError("Node is missing node_name in properties")

    def _clear_student_graph(self, label: str):
        with self.driver.session() as session:
            session.run(f"MATCH (n:`{label}`) DETACH DELETE n")

    def _create_nodes(self, label: str, nodes: List[Dict]):
        with self.driver.session() as session:
            for node in nodes:
                properties = node["properties"]
                bloom_qa_pairs_json = json.dumps(properties.get("bloom_qa_pairs", []), ensure_ascii=False)
                properties["bloom_qa_pairs"] = bloom_qa_pairs_json
                session.run(f"""
                    MERGE (n:`{label}` {{uuid: $uuid}})
                    SET n.node_name = $node_name,
                        n.description = $description,
                        n.grade = $grade,
                        n.subject = $subject,
                        n.publisher = $publisher,
                        n.status = $status,
                        n.bloom_qa_pairs = $bloom_qa_pairs
                """, **properties)

    def _create_relationships(self, label: str, edges: List[Dict]):
        with self.driver.session() as session:
            for edge in edges:
                rel_type = edge["type"]
                description = edge.get("properties", {}).get("description", "No description provided")
                session.run(f"""
                    MATCH (start:`{label}` {{uuid: $start_uuid}})
                    MATCH (end:`{label}` {{uuid: $end_uuid}})
                    MERGE (start)-[r:{rel_type}]->(end)
                    SET r.description = $description
                """, start_uuid=edge["start_uuid"], end_uuid=edge["end_uuid"], description=description)

    def import_student_graph_from_file(self, student_en: str, json_path: str, clear_existing: bool = True) -> None:
        """从给定 JSON 文件导入某个学生的图谱到其专属标签"""
        label = f"KnowledgePoint_{re.sub(r'[^A-Za-z0-9_]', '', student_en or '')}"
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"未找到阶段文件: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._validate_data(data)
        if clear_existing:
            self._clear_student_graph(label)
        self._create_nodes(label, data.get("nodes", []))
        self._create_relationships(label, data.get("edges", []))
        self.console.print(f"[green]✓ 学生 {student_en} 图谱已导入: {os.path.basename(json_path)}[/green]")

    def import_latest_student_graph(self, student_en: str, base_dir: str = "data/student_graphs", clear_existing: bool = True) -> None:
        """导入该学生在 base_dir 下的最新阶段文件"""
        student_dir = os.path.join(base_dir, student_en)
        if not os.path.isdir(student_dir):
            raise FileNotFoundError(f"未找到学生目录: {student_dir}")
        candidates = [f for f in os.listdir(student_dir) if f.endswith(".json")]
        if not candidates:
            raise FileNotFoundError(f"学生目录无阶段文件: {student_dir}")
        latest_ts = sorted([os.path.splitext(f)[0] for f in candidates])[-1]
        json_path = os.path.join(student_dir, f"{latest_ts}.json")
        self.import_student_graph_from_file(student_en, json_path, clear_existing=clear_existing)

    def export_student_graph(self, student_en: str) -> Dict:
        """导出指定学生标签下的图谱为 dict"""
        label = f"KnowledgePoint_{re.sub(r'[^A-Za-z0-9_]', '', student_en or '')}"
        data = {"nodes": [], "edges": []}
        try:
            with self.driver.session() as session:
                # 导出节点
                nodes_res = session.run(f"""
                    MATCH (n:`{label}`)
                    RETURN n
                """)
                for rec in nodes_res:
                    n = rec["n"]
                    props = dict(n)
                    # 将 bloom_qa_pairs 从存储的 JSON 字符串还原为对象，避免导出时出现转义
                    try:
                        if "bloom_qa_pairs" in props and isinstance(props["bloom_qa_pairs"], str):
                            props["bloom_qa_pairs"] = json.loads(props["bloom_qa_pairs"])
                    except Exception:
                        # 解析失败则保持原字符串
                        pass
                    data["nodes"].append({"properties": props})

                # 导出关系
                rels_res = session.run(f"""
                    MATCH (a:`{label}`)-[r]->(b:`{label}`)
                    RETURN a.uuid AS start_uuid, b.uuid AS end_uuid, type(r) AS type, r AS rel
                """)
                for rec in rels_res:
                    rel_props = dict(rec["rel"]) if rec["rel"] else {}
                    data["edges"].append({
                        "start_uuid": rec["start_uuid"],
                        "end_uuid": rec["end_uuid"],
                        "type": rec["type"],
                        "properties": {"description": rel_props.get("description", "No description provided")}
                    })
            return data
        except Exception as e:
            self.console.print(f"[red]导出学生图谱失败: {e}[/red]")
            return data
