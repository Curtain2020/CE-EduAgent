import json
from neo4j import GraphDatabase

# 连接到 Neo4j
uri = "bolt://localhost:7687"
driver = GraphDatabase.driver(uri, auth=("neo4j", "51265903089"))

# 清空数据库
def clear_database(tx):
    tx.run("MATCH (n) DETACH DELETE n")

# 创建节点
def create_nodes(tx, nodes):
    for node in nodes:
        properties = node["properties"]
        # 将 bloom_qa_pairs 序列化为 JSON 字符串
        bloom_qa_pairs_json = json.dumps(properties.get("bloom_qa_pairs", []), ensure_ascii=False)
        # 将序列化后的 JSON 字符串存储为节点的属性
        properties["bloom_qa_pairs"] = bloom_qa_pairs_json
        tx.run("""
        MERGE (n:KnowledgePoint {uuid: $uuid})
        SET n.node_name = $node_name,
            n.description = $description,
            n.grade = $grade,
            n.subject = $subject,
            n.publisher = $publisher,
            n.status = $status,
            n.bloom_qa_pairs = $bloom_qa_pairs
        """, **properties)

# 创建关系
def create_relationships(tx, edges):
    for edge in edges:
        rel_type = edge["type"]
        description = edge["properties"].get("description", "No description provided")
        tx.run("""
        MATCH (start:KnowledgePoint {uuid: $start_uuid})
        MATCH (end:KnowledgePoint {uuid: $end_uuid})
        MERGE (start)-[r:%s]->(end)
        SET r.description = $description
        """ % rel_type, start_uuid=edge["start_uuid"], end_uuid=edge["end_uuid"], description=description)

# 验证数据
def validate_data(data):
    for edge in data.get("edges", []):
        if "start_uuid" not in edge or "end_uuid" not in edge or "type" not in edge:
            raise ValueError("Edge is missing required fields: start_uuid, end_uuid, or type")
        if "properties" not in edge or "description" not in edge["properties"]:
            print(f"Warning: Edge with start_uuid {edge['start_uuid']} and end_uuid {edge['end_uuid']} is missing description. Using default value.")
    for node in data.get("nodes", []):
        if "properties" not in node:
            raise ValueError("Node is missing properties field")
        if "uuid" not in node["properties"]:
            raise ValueError("Node is missing uuid in properties")
        if "node_name" not in node["properties"]:
            raise ValueError("Node is missing node_name in properties")

# 加载 JSON 数据
file_path = "小学数学图谱_v3.json"
with open(file_path, "r", encoding="utf-8") as file:
    data = json.load(file)

# 验证数据
validate_data(data)

# 执行导入
with driver.session() as session:
    # 清空数据库
    session.execute_write(clear_database)
    # 导入数据
    session.execute_write(create_nodes, data["nodes"])
    session.execute_write(create_relationships, data["edges"])

driver.close()