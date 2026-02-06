"""
Flask Web应用 - 知识图谱可视化与编辑系统
提供知识图谱的网页界面，支持节点和边的编辑
"""

import json
import os
import re
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 知识图谱JSON文件路径
KG_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', '小学数学图谱_v3.json')
INDEX_PATH = os.path.join(os.path.dirname(__file__), 'data', 'student_graphs', 'index.json')


@app.route('/')
def index():
    """知识图谱可视化主页"""
    return render_template('kg_visualization.html')


@app.route('/api/kg/load', methods=['GET'])
def load_knowledge_graph():
    """加载知识图谱数据
    
    返回:
    {
        "success": true,
        "nodes": [...],
        "edges": [...]
    }
    """
    try:
        if not os.path.exists(KG_JSON_PATH):
            return jsonify({
                'success': False,
                'error': '知识图谱文件不存在'
            }), 404
        
        with open(KG_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 转换为前端需要的格式
        nodes = []
        for node in data.get('nodes', []):
            props = node.get('properties', {})
            nodes.append({
                'id': props.get('uuid'),
                'label': props.get('node_name', '未命名节点'),
                'uuid': props.get('uuid'),
                'node_name': props.get('node_name', ''),
                'description': props.get('description', ''),
                'grade': props.get('grade', ''),
                'subject': props.get('subject', ''),
                'publisher': props.get('publisher', ''),
                'status': props.get('status', -1),
                'bloom_qa_pairs': props.get('bloom_qa_pairs', [])
            })
        
        edges = []
        seen_edges = {}  # 用于跟踪已见过的边，避免重复
        
        for edge in data.get('edges', []):
            start_uuid = edge.get('start_uuid')
            end_uuid = edge.get('end_uuid')
            
            # 生成基础ID
            base_id = f"{start_uuid}-{end_uuid}"
            
            # 如果这条边已经存在，生成唯一ID（添加序号）
            if base_id in seen_edges:
                seen_edges[base_id] += 1
                edge_id = f"{base_id}-{seen_edges[base_id] - 1}"
            else:
                edge_id = base_id
                seen_edges[base_id] = 1
            
            edges.append({
                'id': edge_id,
                'from': start_uuid,
                'to': end_uuid,
                'label': edge.get('type', ''),
                'type': edge.get('type', ''),
                'description': edge.get('properties', {}).get('description', ''),
                'start_uuid': start_uuid,
                'end_uuid': end_uuid
            })
        
        return jsonify({
            'success': True,
            'nodes': nodes,
            'edges': edges,
            'total_nodes': len(nodes),
            'total_edges': len(edges)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ====== 版本索引与按学生/版本加载 ======
@app.route('/api/graph/index', methods=['GET'])
def api_graph_index():
    """返回 data/student_graphs/index.json 内容"""
    try:
        if not os.path.exists(INDEX_PATH):
            return jsonify({"success": False, "error": "index.json 不存在"}), 404
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/kg/graph', methods=['GET'])
def api_kg_graph():
    """返回指定学生+阶段的图谱（从 index.json 指向的 json 文件加载）"""
    try:
        student_cn = request.args.get('student')
        stage = request.args.get('stage')
        if not student_cn or not stage:
            return jsonify({"success": False, "error": "缺少 student 或 stage"}), 400
        if not os.path.exists(INDEX_PATH):
            return jsonify({"success": False, "error": "index.json 不存在"}), 404
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            idx = json.load(f)
        stu = idx.get(student_cn) or {}
        path = (stu.get("stages") or {}).get(stage)
        if not path:
            return jsonify({"success": False, "error": "未找到该阶段图谱"}), 404
        abs_path = os.path.join(os.path.dirname(__file__), path) if not os.path.isabs(path) else path
        if not os.path.exists(abs_path):
            return jsonify({"success": False, "error": "阶段图谱文件不存在"}), 404
        with open(abs_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({"success": True, "nodes": data.get("nodes", []), "edges": data.get("edges", [])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/graph/set_current', methods=['POST'])
def api_graph_set_current():
    """将某学生指定阶段设置为当前版本（修改 index.json）"""
    try:
        payload = request.json or {}
        student_cn = payload.get('student')
        stage = payload.get('stage')
        if not student_cn or not stage:
            return jsonify({"success": False, "error": "缺少 student 或 stage"}), 400
        if not os.path.exists(INDEX_PATH):
            return jsonify({"success": False, "error": "index.json 不存在"}), 404
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            idx = json.load(f)
        if student_cn not in idx:
            return jsonify({"success": False, "error": "index.json 无该学生"}), 404
        if stage not in (idx[student_cn].get("stages") or {}):
            return jsonify({"success": False, "error": "该学生无此阶段"}), 404
        idx[student_cn]["current_stage"] = stage
        with open(INDEX_PATH, 'w', encoding='utf-8') as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/kg/save', methods=['POST'])
def save_knowledge_graph():
    """保存知识图谱数据
    
    请求体:
    {
        "nodes": [...],
        "edges": [...]
    }
    """
    try:
        # 确保 request.json 解析正确
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': '请求数据格式错误：不是有效的JSON格式'
            }), 400
        
        data = request.json
        
        if 'nodes' not in data or 'edges' not in data:
            return jsonify({
                'success': False,
                'error': '请求数据格式错误：缺少nodes或edges字段'
            }), 400
        
        # 转换为保存格式
        nodes_data = []
        for node in data['nodes']:
            nodes_data.append({
                'labels': ['KnowledgePoint'],
                'properties': {
                    'uuid': node.get('uuid'),
                    'node_name': node.get('node_name', ''),
                    'description': node.get('description', ''),
                    'grade': node.get('grade', ''),
                    'subject': node.get('subject', ''),
                    'publisher': node.get('publisher', ''),
                    'status': node.get('status', -1),
                    'bloom_qa_pairs': node.get('bloom_qa_pairs', [])
                }
            })
        
        edges_data = []
        for edge in data['edges']:
            edges_data.append({
                'start_uuid': edge.get('start_uuid'),
                'end_uuid': edge.get('end_uuid'),
                'type': edge.get('type', ''),
                'properties': {
                    'description': edge.get('description', '')
                }
            })
        
        # 保存到文件
        output_data = {
            'nodes': nodes_data,
            'edges': edges_data
        }
        
        # 确保 data 目录存在
        data_dir = os.path.dirname(KG_JSON_PATH)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
        
        # 创建备份
        if os.path.exists(KG_JSON_PATH):
            backup_path = KG_JSON_PATH + '.backup'
            with open(KG_JSON_PATH, 'r', encoding='utf-8') as f:
                backup_data = f.read()
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(backup_data)
        
        # 保存新数据
        with open(KG_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        
        return jsonify({
            'success': True,
            'message': '知识图谱保存成功',
            'nodes_count': len(nodes_data),
            'edges_count': len(edges_data)
        })
    
    except Exception as e:
        print(f"保存知识图谱错误: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/kg/node/update', methods=['POST'])
def update_node():
    """更新单个节点
    
    请求体:
    {
        "uuid": "...",
        "node_name": "...",
        "description": "...",
        ...
    }
    """
    try:
        data = request.json
        node_uuid = data.get('uuid')
        
        if not node_uuid:
            return jsonify({
                'success': False,
                'error': '缺少uuid字段'
            }), 400
        
        # 解析目标文件（优先 student+stage）
        target_path = KG_JSON_PATH
        student_cn = data.get('student')
        stage = data.get('stage')
        if student_cn and stage and os.path.exists(INDEX_PATH):
            with open(INDEX_PATH, 'r', encoding='utf-8') as f:
                idx = json.load(f)
            rel = (idx.get(student_cn, {}).get('stages') or {}).get(stage)
            if rel:
                abs_path = os.path.join(os.path.dirname(__file__), rel) if not os.path.isabs(rel) else rel
                if os.path.exists(abs_path):
                    target_path = abs_path

        # 读取现有数据
        with open(target_path, 'r', encoding='utf-8') as f:
            kg_data = json.load(f)
        
        # 更新节点
        updated = False
        for node in kg_data.get('nodes', []):
            if node.get('properties', {}).get('uuid') == node_uuid:
                props = node['properties']
                props['node_name'] = data.get('node_name', props.get('node_name', ''))
                props['description'] = data.get('description', props.get('description', ''))
                props['grade'] = data.get('grade', props.get('grade', ''))
                props['subject'] = data.get('subject', props.get('subject', ''))
                props['publisher'] = data.get('publisher', props.get('publisher', ''))
                # 统一规范 status 到向量
                def _ensure_status_vector(val):
                    if isinstance(val, list) and len(val) == 3:
                        try:
                            return [1 if int(x) == 1 else 0 for x in val]
                        except Exception:
                            return [0, 0, 0]
                    try:
                        if val is None:
                            return [0, 0, 0]
                        ival = int(val)
                        return [1, 0, 0] if ival == 1 else [0, 0, 0]
                    except Exception:
                        return [0, 0, 0]
                # 三维向量：允许 -2..2 数值，若传入是 list 则逐项规整；若缺失则保留原值
                def _ensure_status_vector(val):
                    if isinstance(val, list) and len(val) == 3:
                        out = []
                        for x in val:
                            try:
                                xi = int(x)
                                out.append(max(-2, min(2, xi)))
                            except Exception:
                                out.append(0)
                        return out
                    # 若传入不是 list，则不强制转换，沿用原值（便于向后兼容）
                    return val
                incoming = data.get('status', props.get('status'))
                props['status'] = _ensure_status_vector(incoming)
                if 'bloom_qa_pairs' in data:
                    props['bloom_qa_pairs'] = data.get('bloom_qa_pairs')
                updated = True
                break
        
        if not updated:
            return jsonify({
                'success': False,
                'error': f'未找到uuid为{node_uuid}的节点'
            }), 404
        
        # 保存文件
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(kg_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'message': '节点更新成功'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/kg/edge/update', methods=['POST'])
def update_edge():
    """更新单条边
    
    请求体:
    {
        "start_uuid": "...",
        "end_uuid": "...",
        "type": "...",
        "description": "..."
    }
    """
    try:
        data = request.json
        start_uuid = data.get('start_uuid')
        end_uuid = data.get('end_uuid')
        
        if not start_uuid or not end_uuid:
            return jsonify({
                'success': False,
                'error': '缺少start_uuid或end_uuid字段'
            }), 400
        
        # 解析目标文件（优先 student+stage）
        target_path = KG_JSON_PATH
        student_cn = data.get('student')
        stage = data.get('stage')
        if student_cn and stage and os.path.exists(INDEX_PATH):
            with open(INDEX_PATH, 'r', encoding='utf-8') as f:
                idx = json.load(f)
            rel = (idx.get(student_cn, {}).get('stages') or {}).get(stage)
            if rel:
                abs_path = os.path.join(os.path.dirname(__file__), rel) if not os.path.isabs(rel) else rel
                if os.path.exists(abs_path):
                    target_path = abs_path

        # 读取现有数据
        with open(target_path, 'r', encoding='utf-8') as f:
            kg_data = json.load(f)
        
        # 更新边
        updated = False
        for edge in kg_data.get('edges', []):
            if edge.get('start_uuid') == start_uuid and edge.get('end_uuid') == end_uuid:
                edge['type'] = data.get('type', edge.get('type', ''))
                if 'properties' not in edge:
                    edge['properties'] = {}
                edge['properties']['description'] = data.get('description', edge['properties'].get('description', ''))
                updated = True
                break
        
        if not updated:
            return jsonify({
                'success': False,
                'error': f'未找到对应的边'
            }), 404
        
        # 保存文件
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(kg_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'message': '边更新成功'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/kg/upload', methods=['POST'])
def upload_to_graph_db():
    """上传知识图谱到图数据库
    
    请求体:
    {
        "nodes": [...],
        "edges": [...],
        "student": "..."  # 学生中文名
    }
    """
    try:
        data = request.json
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        student_cn = data.get('student')
        
        if not nodes:
            return jsonify({
                'success': False,
                'error': '缺少nodes字段'
            }), 400
        
        # 导入 KnowledgeGraphManager
        from knowledge_graph_manager import KnowledgeGraphManager
        
        # 生成学生英文标签（用于Neo4j标签）
        # 使用与virtual_student.py相同的映射关系
        def get_student_en_label(cn_name):
            if not cn_name:
                return "default"
            # 学生姓名映射关系
            mapping = {
                "崔展豪": "Cuizhanhao",
                "包梓群": "Baoziqun",
                "李昌龙": "Lichanglong",
                "丽娃": "Liwa",
                "萧华诗": "Xiaohuashi",
                "张晓丹": "Zhangxidan",
            }
            return mapping.get(cn_name, "UnknownStudent")
        
        student_en = get_student_en_label(student_cn)
        
        # 直接使用 KnowledgeGraphManager 的默认配置
        # 只传递学生标签，其他使用默认值
        graph_manager = KnowledgeGraphManager(
            student_label_en=student_en
        )
        
        # 测试连接
        try:
            if not graph_manager.test_connection():
                return jsonify({
                    'success': False,
                    'error': '无法连接到图数据库，请检查Neo4j是否启动'
                }), 500
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Neo4j认证失败: {str(e)}\n请检查.env文件中的Neo4j用户名和密码配置'
            }), 500
        
        # 转换数据格式为 KnowledgeGraphManager 期望的格式
        # 构建 Neo4j 导入格式的数据
        neo4j_data = {
            "nodes": [],
            "edges": []
        }
        
        # 转换节点
        print(f"开始转换节点数据，原始节点数: {len(nodes)}")
        for node in nodes:
            # 确保每个节点都有一个唯一的uuid
            uuid = node.get('uuid', '')
            if not uuid:
                print(f"跳过无效节点: 缺少uuid")
                continue
            
            node_props = {
                "uuid": uuid,
                "node_name": node.get('node_name', ''),
                "description": node.get('description', ''),
                "grade": node.get('grade', ''),
                "subject": node.get('subject', ''),
                "publisher": node.get('publisher', ''),
                "status": node.get('status', [0, 0, 0]),
                "bloom_qa_pairs": node.get('bloom_qa_pairs', [])
            }
            neo4j_data["nodes"].append({"properties": node_props})
        
        print(f"节点数据转换完成，转换后节点数: {len(neo4j_data['nodes'])}")
        
        # 转换边
        print(f"开始转换边数据，原始边数: {len(edges)}")
        for edge in edges:
            # 规范化关系类型
            edge_type = edge.get('type', '关联')
            # 移除所有非字母数字字符
            edge_type = re.sub(r"[^A-Za-z0-9]", "", edge_type)
            # 如果为空，使用默认值
            if not edge_type:
                edge_type = "关联"
            # 确保首字母大写
            edge_type = edge_type.capitalize()
            
            # 兼容前端使用from和to字段表示边的起点和终点的情况
            start_uuid = edge.get('start_uuid', edge.get('from', ''))
            end_uuid = edge.get('end_uuid', edge.get('to', ''))
            
            edge_data = {
                "start_uuid": start_uuid,
                "end_uuid": end_uuid,
                "type": edge_type,
                "properties": {
                    "description": edge.get('description', '')
                }
            }
            neo4j_data["edges"].append(edge_data)
        
        print(f"边数据转换完成，转换后边数: {len(neo4j_data['edges'])}")
        
        # 获取学生标签
        label = graph_manager._label()
        print(f"获取学生标签: {label}")
        
        # 清除现有的学生图谱数据
        print(f"清除现有的学生图谱数据")
        graph_manager._clear_student_graph(label)
        
        # 创建节点
        print(f"开始创建节点，节点数: {len(neo4j_data.get('nodes', []))}")
        graph_manager._create_nodes(label, neo4j_data.get("nodes", []))
        print(f"节点创建完成")
        
        # 创建边（关系）
        print(f"开始创建边（关系），边数: {len(neo4j_data.get('edges', []))}")
        graph_manager._create_relationships(label, neo4j_data.get("edges", []))
        print(f"边（关系）创建完成")
        
        # 关闭连接
        graph_manager.close()
        
        return jsonify({
            'success': True,
            'message': '知识图谱上传成功',
            'nodes_count': len(nodes),
            'edges_count': len(edges),
            'student_label': label
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/kg/pull', methods=['POST'])
def pull_from_graph_db():
    """从Neo4j拉取当前学生的最新图谱，并保存为新版本
    
    请求体:
    {
        "student": "..."  # 学生中文名
    }
    """
    try:
        import time
        import os
        import json
        
        data = request.json
        student_cn = data.get('student')
        
        if not student_cn:
            return jsonify({
                'success': False,
                'error': '缺少student字段'
            }), 400
        
        # 导入 KnowledgeGraphManager
        from knowledge_graph_manager import KnowledgeGraphManager
        
        # 生成学生英文标签（用于Neo4j标签）
        # 使用与virtual_student.py相同的映射关系
        def get_student_en_label(cn_name):
            if not cn_name:
                return "default"
            # 学生姓名映射关系
            mapping = {
                "崔展豪": "Cuizhanhao",
                "包梓群": "Baoziqun",
                "李昌龙": "Lichanglong",
                "丽娃": "Liwa",
                "萧华诗": "Xiaohuashi",
                "张晓丹": "Zhangxidan",
            }
            return mapping.get(cn_name, "UnknownStudent")
        
        student_en = get_student_en_label(student_cn)
        
        # 直接使用 KnowledgeGraphManager 的默认配置
        # 只传递学生标签，其他使用默认值
        graph_manager = KnowledgeGraphManager(
            student_label_en=student_en
        )
        
        # 测试连接
        try:
            if not graph_manager.test_connection():
                return jsonify({
                    'success': False,
                    'error': '无法连接到图数据库，请检查Neo4j是否启动'
                }), 500
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Neo4j认证失败: {str(e)}\n请检查.env文件中的Neo4j用户名和密码配置'
            }), 500
        
        # 从Neo4j导出学生的图谱
        try:
            # 保存原始student_label_en
            original_student_label_en = graph_manager.student_label_en
            # 确保使用正确的student_label_en
            graph_manager.student_label_en = student_en
            # 导出图谱
            neo4j_data = graph_manager.export_student_graph(student_en)
            # 恢复原始student_label_en
            graph_manager.student_label_en = original_student_label_en
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'从Neo4j导出图谱失败: {str(e)}'
            }), 500
        
        # 打印调试信息
        print(f"从Neo4j导出的节点数: {len(neo4j_data.get('nodes', []))}")
        print(f"从Neo4j导出的边数: {len(neo4j_data.get('edges', []))}")
        
        # 转换为前端需要的格式
        nodes = []
        for node in neo4j_data.get('nodes', []):
            props = node.get('properties', {})
            nodes.append({
                'id': props.get('uuid'),
                'label': props.get('node_name', '未命名节点'),
                'uuid': props.get('uuid'),
                'node_name': props.get('node_name', ''),
                'description': props.get('description', ''),
                'grade': props.get('grade', ''),
                'subject': props.get('subject', ''),
                'publisher': props.get('publisher', ''),
                'status': props.get('status', -1),
                'bloom_qa_pairs': props.get('bloom_qa_pairs', [])
            })
        
        edges = []
        seen_edges = {}  # 用于跟踪已见过的边，避免重复
        
        for edge in neo4j_data.get('edges', []):
            start_uuid = edge.get('start_uuid')
            end_uuid = edge.get('end_uuid')
            
            # 生成基础ID
            base_id = f"{start_uuid}-{end_uuid}"
            
            # 如果这条边已经存在，生成唯一ID（添加序号）
            if base_id in seen_edges:
                seen_edges[base_id] += 1
                edge_id = f"{base_id}-{seen_edges[base_id] - 1}"
            else:
                edge_id = base_id
                seen_edges[base_id] = 1
            
            edges.append({
                'id': edge_id,
                'from': start_uuid,
                'to': end_uuid,
                'label': edge.get('type', ''),
                'type': edge.get('type', ''),
                'description': edge.get('properties', {}).get('description', ''),
                'start_uuid': start_uuid,
                'end_uuid': end_uuid
            })
        
        # 打印调试信息
        print(f"转换后的边数: {len(edges)}")
        
        # 保存到新版本文件
        # 生成时间戳作为版本号
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # 创建学生目录
        student_dir = os.path.join('data', 'student_graphs', student_cn)
        os.makedirs(student_dir, exist_ok=True)
        
        # 生成文件路径
        json_path = os.path.join(student_dir, f'{timestamp}.json')
        
        # 转换为保存格式
        save_data = {
            'nodes': [],
            'edges': []
        }
        
        # 转换节点
        for node in nodes:
            save_data['nodes'].append({
                'labels': ['KnowledgePoint'],
                'properties': {
                    'uuid': node.get('uuid'),
                    'node_name': node.get('node_name', ''),
                    'description': node.get('description', ''),
                    'grade': node.get('grade', ''),
                    'subject': node.get('subject', ''),
                    'publisher': node.get('publisher', ''),
                    'status': node.get('status', -1),
                    'bloom_qa_pairs': node.get('bloom_qa_pairs', [])
                }
            })
        
        # 转换边
        for edge in edges:
            save_data['edges'].append({
                'start_uuid': edge.get('start_uuid'),
                'end_uuid': edge.get('end_uuid'),
                'type': edge.get('type', ''),
                'properties': {
                    'description': edge.get('description', '')
                }
            })
        
        # 保存到文件
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        # 更新index.json
        index_path = os.path.join('data', 'student_graphs', 'index.json')
        
        # 读取现有index.json
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
        else:
            index_data = {}
        
        # 确保学生条目存在
        if student_cn not in index_data:
            index_data[student_cn] = {
                'current_stage': timestamp,
                'stages': {}
            }
        
        # 添加新版本
        index_data[student_cn]['stages'][timestamp] = json_path
        # 设置为当前版本
        index_data[student_cn]['current_stage'] = timestamp
        
        # 保存更新后的index.json
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        
        # 关闭连接
        graph_manager.close()
        
        return jsonify({
            'success': True,
            'message': '从Neo4j拉取图谱成功并保存为新版本',
            'nodes': nodes,
            'edges': edges,
            'nodes_count': len(nodes),
            'edges_count': len(edges),
            'student_label': graph_manager._label(),
            'new_version': timestamp,
            'file_path': json_path
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/kg/delete_version', methods=['POST'])
def delete_version():
    """删除指定学生的指定版本
    
    请求体:
    {
        "student": "...",  # 学生中文名
        "stage": "..."     # 版本号
    }
    """
    try:
        import os
        import json
        
        data = request.json
        student_cn = data.get('student')
        stage = data.get('stage')
        
        if not student_cn or not stage:
            return jsonify({
                'success': False,
                'error': '缺少student或stage字段'
            }), 400
        
        # 读取index.json
        index_path = os.path.join('data', 'student_graphs', 'index.json')
        
        if not os.path.exists(index_path):
            return jsonify({
                'success': False,
                'error': 'index.json不存在'
            }), 404
        
        with open(index_path, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        
        # 检查学生是否存在
        if student_cn not in index_data:
            return jsonify({
                'success': False,
                'error': '学生不存在'
            }), 404
        
        # 检查版本是否存在
        student_data = index_data[student_cn]
        if stage not in student_data.get('stages', {}):
            return jsonify({
                'success': False,
                'error': '版本不存在'
            }), 404
        
        # 获取版本文件路径
        version_path = student_data['stages'][stage]
        absolute_path = os.path.join(os.path.dirname(__file__), version_path) if not os.path.isabs(version_path) else version_path
        
        # 删除版本文件
        if os.path.exists(absolute_path):
            os.remove(absolute_path)
        
        # 从index.json中移除版本
        del student_data['stages'][stage]
        
        # 如果删除的是当前版本，设置新的当前版本
        if student_data.get('current_stage') == stage:
            # 获取剩余版本列表，按时间戳排序
            remaining_stages = list(student_data['stages'].keys())
            if remaining_stages:
                # 按时间戳降序排序，选择最新的版本作为当前版本
                remaining_stages.sort(reverse=True)
                student_data['current_stage'] = remaining_stages[0]
            else:
                # 如果没有剩余版本，移除current_stage字段
                if 'current_stage' in student_data:
                    del student_data['current_stage']
        
        # 保存更新后的index.json
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'message': '版本删除成功',
            'student': student_cn,
            'deleted_stage': stage
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    import sys
    # 默认使用8081端口，避免与app.py的8080冲突
    port = 8081
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"警告: 无效的端口号 {sys.argv[1]}，使用默认端口 8081")
    
    print(f"启动知识图谱可视化应用，访问地址: http://localhost:{port}")
    app.run(debug=True, host='0.0.0.0', port=port)

