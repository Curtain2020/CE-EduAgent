"""
Neo4j知识图谱管理类
用于与Neo4j数据库交互，实现知识点的查询和更新
"""

import os
import json
import jellyfish
from typing import List, Dict, Optional, Tuple
from neo4j import GraphDatabase
from rich.console import Console

console = Console()


class KnowledgeGraphManager:
    """Neo4j知识图谱管理器"""
    
    def __init__(self, uri: str = "bolt://localhost:7687", username: str = "neo4j", password: str = "51265903089"):
        """初始化Neo4j连接"""
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.console = Console()
    
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
                result = session.run("""
                    MATCH (n:KnowledgePoint)
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
                result = session.run("""
                    MATCH (n:KnowledgePoint {uuid: $uuid})
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
                # 更新状态
                session.run("""
                    MATCH (n:KnowledgePoint {uuid: $uuid})
                    SET n.status = $new_status
                """, uuid=uuid, new_status=new_status)
                
                # 如果有新内容，更新bloom_qa_pairs
                if new_content:
                    # 获取现有的bloom_qa_pairs
                    result = session.run("""
                        MATCH (n:KnowledgePoint {uuid: $uuid})
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
                    session.run("""
                        MATCH (n:KnowledgePoint {uuid: $uuid})
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


# 导入datetime
from datetime import datetime
