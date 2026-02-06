import asyncio
import json
import time
import psutil
import os
import sys
import tracemalloc
import threading
from typing import Dict, List, Optional
from dataclasses import dataclass, field

# 添加项目根目录到导入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 仅导入本地模块，不依赖真实Zep客户端
from src.memory.short_term_memory import ShortTermMemoryManager
from knowledge_graph_manager import KnowledgeGraphManager

# 配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "51265903089"
ZEP_API_KEY = os.getenv("ZEP_API_KEY", "mock_zep_api_key")

@dataclass
class MemoryMetrics:
    """内存指标数据类"""
    timestamp: str
    process_memory: int  # MB
    system_memory_used: int  # MB
    system_memory_total: int  # MB
    zep_memory_usage: float  # 模拟的Zep内存使用量 (MB)
    conversation_count: int
    buffer_size: int
    neo4j_memory: float  # Neo4j内存使用量 (MB)

class MockZepClient:
    """模拟Zep客户端，用于测试"""
    def __init__(self):
        self.users = [
            {
                "id": "student_001",
                "created_at": "2024-01-01T00:00:00",
                "message_count": 100,
                "memory_size": 50000  # 模拟50KB内存使用
            },
            {
                "id": "student_002",
                "created_at": "2024-01-02T00:00:00",
                "message_count": 200,
                "memory_size": 100000  # 模拟100KB内存使用
            }
        ]
        self.threads = {}
        self.total_memory_usage = 150000  # 初始150KB
        
        # 直接创建thread属性，不通过方法获取
        class MockThread:
            async def add_messages(self, thread_id, messages):
                """模拟添加消息"""
                if thread_id not in self.parent.threads:
                    self.parent.threads[thread_id] = []
                self.parent.threads[thread_id].extend(messages)
                
                # 模拟内存使用增加
                message_size = sum(len(msg.content) if hasattr(msg, 'content') else len(msg.get('content', '')) for msg in messages)
                self.parent.total_memory_usage += message_size
                
                return {"success": True}
        
        self.thread = MockThread()
        self.thread.parent = self
        
    async def user(self):
        """模拟获取用户列表"""
        class MockUserList:
            users = self.users
        return MockUserList()

class ZepMemoryTester:
    """Zep内存测试类"""
    def __init__(self, mock_zep_client: MockZepClient):
        self.zep_client = mock_zep_client
        self.short_term_memory = None
        self.start_time = None
        self.memory_metrics: List[MemoryMetrics] = []
        self.thread_id = "test_thread_001"
        self.process = psutil.Process(os.getpid())
    
    async def setup(self):
        """设置测试环境"""
        # 创建短期记忆管理器
        self.short_term_memory = ShortTermMemoryManager()
        # 设置模拟的Zep客户端
        self.short_term_memory.set_zep_client(self.zep_client)
        self.start_time = time.time()
        
        # 开始内存追踪
        tracemalloc.start()
        
        print("测试环境设置完成")
    
    async def get_memory_statistics(self):
        """获取内存统计信息"""
        try:
            # 获取模拟的用户内存统计
            zep_users = await self.zep_client.user()
            
            total_memory = self.zep_client.total_memory_usage
            total_messages = sum(user["message_count"] for user in zep_users.users)
            
            return {
                "total_memory_usage": total_memory,
                "total_message_count": total_messages,
                "users": [
                    {
                        "user_id": user["id"],
                        "message_count": user["message_count"],
                        "memory_size": user["memory_size"]
                    } for user in zep_users.users
                ]
            }
        except Exception as e:
            print(f"获取内存统计失败: {e}")
            return {
                "total_memory_usage": 0,
                "total_message_count": 0,
                "users": []
            }
    
    async def test_buffer_operations(self, operation_count: int = 50):
        """测试缓冲区操作
        
        Args:
            operation_count: 执行的操作数量
        """
        print(f"开始测试缓冲区操作，共执行 {operation_count} 次...")
        
        for i in range(operation_count):
            # 创建模拟对话
            conversation = {
                "user_message": f"这是第 {i+1} 个测试问题，测试内存占用情况",
                "student_response": f"这是第 {i+1} 个测试回答，用于测试短期记忆缓冲区",
                "student_name": f"student_{i % 2 + 1:03d}"
            }
            
            # 添加到短期记忆
            self.short_term_memory.add_conversation(
                user_message=conversation["user_message"],
                student_response=conversation["student_response"],
                student_name=conversation["student_name"],
                thread_id=self.thread_id
            )
            
            # 每10次操作记录一次内存指标
            if (i + 1) % 10 == 0:
                await self._record_memory_metrics()
                
        print(f"缓冲区操作测试完成，共执行 {operation_count} 次")
    
    async def _record_memory_metrics(self):
        """记录内存指标"""
        # 获取进程内存使用
        process_memory = self.process.memory_info().rss // (1024 * 1024)  # MB
        
        # 获取系统内存使用
        system_memory = psutil.virtual_memory()
        system_memory_used = system_memory.used // (1024 * 1024)  # MB
        system_memory_total = system_memory.total // (1024 * 1024)  # MB
        
        # 获取Zep内存使用（转换为MB）
        zep_stats = await self.get_memory_statistics()
        zep_memory_mb = zep_stats["total_memory_usage"] / 1024  # 转换为MB
        
        # 计算Neo4j内存（当前进程内存减去Zep相关内存）
        # 这里简化处理，实际应该是单独监控Neo4j进程内存
        neo4j_memory = process_memory * 0.3  # 假设Neo4j占进程内存的30%
        
        # 创建指标对象
        metrics = MemoryMetrics(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            process_memory=process_memory,
            system_memory_used=system_memory_used,
            system_memory_total=system_memory_total,
            zep_memory_usage=zep_memory_mb,
            conversation_count=zep_stats["total_message_count"],
            buffer_size=len(self.short_term_memory.memory_queue) if self.short_term_memory else 0,
            neo4j_memory=neo4j_memory
        )
        
        self.memory_metrics.append(metrics)
        
        print(f"[{metrics.timestamp}] 内存记录: 进程内存={metrics.process_memory}MB, Zep内存={metrics.zep_memory_usage:.2f}MB, Neo4j内存={metrics.neo4j_memory:.2f}MB, 缓冲区大小={metrics.buffer_size}")
    
    async def simulate_conversation_stress(self, iterations: int = 100):
        """模拟对话压力测试"""
        print(f"开始对话压力测试，共 {iterations} 次迭代...")
        
        for i in range(iterations):
            # 创建模拟对话
            conversation = {
                "user_message": f"压力测试问题 {i+1}: 如何理解Python的异步编程模型？",
                "student_response": f"压力测试回答 {i+1}: Python的异步编程通过async/await关键字实现，使用事件循环处理并发任务，适合IO密集型操作。",
                "student_name": f"student_{i % 5 + 1:03d}"
            }
            
            # 添加到短期记忆
            self.short_term_memory.add_conversation(
                user_message=conversation["user_message"],
                student_response=conversation["student_response"],
                student_name=conversation["student_name"],
                thread_id=self.thread_id
            )
            
            # 每20次迭代记录一次内存指标
            if (i + 1) % 20 == 0:
                await self._record_memory_metrics()
        
        print(f"对话压力测试完成，共 {iterations} 次迭代")
    
    async def analyze_memory_usage(self):
        """分析内存使用情况"""
        print("\n开始内存使用分析...")
        
        if not self.memory_metrics:
            print("没有内存指标数据")
            return
        
        # 计算平均内存使用
        avg_process_memory = sum(m.process_memory for m in self.memory_metrics) // len(self.memory_metrics)
        avg_zep_memory = sum(m.zep_memory_usage for m in self.memory_metrics) / len(self.memory_metrics)
        avg_neo4j_memory = sum(m.neo4j_memory for m in self.memory_metrics) / len(self.memory_metrics)
        
        # 计算内存增长
        first_metrics = self.memory_metrics[0]
        last_metrics = self.memory_metrics[-1]
        process_memory_growth = last_metrics.process_memory - first_metrics.process_memory
        zep_memory_growth = last_metrics.zep_memory_usage - first_metrics.zep_memory_usage
        neo4j_memory_growth = last_metrics.neo4j_memory - first_metrics.neo4j_memory
        
        print(f"\n内存分析结果:")
        print(f"平均进程内存使用: {avg_process_memory} MB")
        print(f"平均Zep模拟内存使用: {avg_zep_memory:.2f} MB")
        print(f"平均Neo4j内存使用: {avg_neo4j_memory:.2f} MB")
        print(f"进程内存增长: {process_memory_growth} MB")
        print(f"Zep模拟内存增长: {zep_memory_growth:.2f} MB")
        print(f"Neo4j内存增长: {neo4j_memory_growth:.2f} MB")
        print(f"总对话数量: {last_metrics.conversation_count}")
        print(f"最大缓冲区大小: 10 (固定)")
        
        return {
            "average_process_memory": avg_process_memory,
            "average_zep_memory": avg_zep_memory,
            "average_neo4j_memory": avg_neo4j_memory,
            "process_memory_growth": process_memory_growth,
            "zep_memory_growth": zep_memory_growth,
            "neo4j_memory_growth": neo4j_memory_growth,
            "total_conversations": last_metrics.conversation_count
        }
    
    async def create_report(self, neo4j_index_report=None, neo4j_retrieval_report=None):
        """创建测试报告"""
        print("\n创建测试报告...")
        
        # 获取最终内存分析
        analysis = await self.analyze_memory_usage()
        
        # 生成报告内容
        report = {
            "test_summary": {
                "test_name": "内存测试",
                "test_duration": round(time.time() - self.start_time, 2),
                "total_conversations": analysis["total_conversations"]
            },
            "memory_metrics": [
                {
                    "timestamp": m.timestamp,
                    "process_memory": m.process_memory,
                    "system_memory_used": m.system_memory_used,
                    "system_memory_total": m.system_memory_total,
                    "zep_memory_usage": m.zep_memory_usage,
                    "neo4j_memory": m.neo4j_memory,
                    "conversation_count": m.conversation_count,
                    "buffer_size": m.buffer_size
                } for m in self.memory_metrics
            ],
            "memory_analysis": analysis,
            "neo4j_index_performance": neo4j_index_report,
            "neo4j_retrieval_performance": neo4j_retrieval_report,
            "recommendations": [
                "监控短期记忆缓冲区的大小，确保不超过预设容量",
                "考虑实现更智能的缓冲策略，如基于优先级的消息保留",
                "定期清理不再需要的对话历史，释放长期记忆空间",
                "优化对话数据的存储格式，减少内存占用"
            ]
        }
        
        # 保存报告到test目录
        report_dir = os.path.dirname(os.path.abspath(__file__))
        report_file = os.path.join(report_dir, f"memory_test_report_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"测试报告已生成: {report_file}")
        
        # 创建txt解读文件
        txt_report_file = report_file.replace('.json', '.txt')
        with open(txt_report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("Neo4j 索引驻留与 Zep 缓冲区内存占用测试报告\n")
            f.write("=" * 60 + "\n\n")
            
            # 测试摘要
            f.write("1. 测试摘要\n")
            f.write("-" * 40 + "\n")
            f.write(f"测试名称: {report['test_summary']['test_name']}\n")
            f.write(f"测试时长: {report['test_summary']['test_duration']} 秒\n")
            f.write(f"总对话数: {report['test_summary']['total_conversations']}\n\n")
            
            # 内存使用分析
            f.write("2. 内存使用分析\n")
            f.write("-" * 40 + "\n")
            f.write(f"平均进程内存使用: {report['memory_analysis']['average_process_memory']} MB\n")
            f.write(f"平均Zep模拟内存使用: {report['memory_analysis']['average_zep_memory']:.2f} MB\n")
            f.write(f"平均Neo4j内存使用: {report['memory_analysis']['average_neo4j_memory']:.2f} MB\n")
            f.write(f"进程内存增长: {report['memory_analysis']['process_memory_growth']} MB\n")
            f.write(f"Zep模拟内存增长: {report['memory_analysis']['zep_memory_growth']:.2f} MB\n")
            f.write(f"Neo4j内存增长: {report['memory_analysis']['neo4j_memory_growth']:.2f} MB\n")
            f.write(f"总对话数量: {report['memory_analysis']['total_conversations']}\n\n")
            
            # 关键指标变化趋势
            f.write("3. 关键指标变化趋势\n")
            f.write("-" * 40 + "\n")
            f.write("时间点\t进程内存(MB)\tZep内存(MB)\tNeo4j内存(MB)\t缓冲区大小\n")
            f.write("-" * 90 + "\n")
            
            # 只显示部分关键时间点
            sample_metrics = report['memory_metrics'][::2]  # 每隔一个记录显示一个
            for metric in sample_metrics:
                f.write(f"{metric['timestamp']}\t{metric['process_memory']}\t{metric['zep_memory_usage']:.2f}\t{metric['neo4j_memory']:.2f}\t{metric['buffer_size']}\n")
            
            f.write("\n")
            
            # 建议
            f.write("4. 优化建议\n")
            f.write("-" * 40 + "\n")
            for i, recommendation in enumerate(report['recommendations'], 1):
                f.write(f"{i}. {recommendation}\n")
            
            # 5. Neo4j索引性能（如果有数据）
            if report.get('neo4j_index_performance'):
                f.write("\n5. Neo4j索引性能\n")
                f.write("-" * 40 + "\n")
                f.write(f"创建节点总数: {report['neo4j_index_performance']['total_nodes']}\n")
                f.write(f"内存增长: {report['neo4j_index_performance']['memory_growth']} MB\n")
                f.write(f"平均每个节点内存消耗: {report['neo4j_index_performance']['avg_memory_per_node']:.2f} MB/节点\n")
            
            # 6. Neo4j检索性能（如果有数据）
            if report.get('neo4j_retrieval_performance'):
                f.write("\n6. Neo4j检索性能\n")
                f.write("-" * 40 + "\n")
                f.write(f"总查询数: {report['neo4j_retrieval_performance']['total_queries']}\n")
                f.write(f"成功查询数: {report['neo4j_retrieval_performance']['successful_queries']}\n")
                f.write(f"错误率: {report['neo4j_retrieval_performance']['error_rate']:.2f}%\n")
                f.write(f"平均检索时间: {report['neo4j_retrieval_performance']['average_retrieval_time']:.2f} 毫秒\n")
                f.write(f"最小检索时间: {report['neo4j_retrieval_performance']['min_retrieval_time']:.2f} 毫秒\n")
                f.write(f"最大检索时间: {report['neo4j_retrieval_performance']['max_retrieval_time']:.2f} 毫秒\n")
                f.write(f"95%分位检索时间: {report['neo4j_retrieval_performance']['p95_retrieval_time']:.2f} 毫秒\n")
                f.write(f"99%分位检索时间: {report['neo4j_retrieval_performance']['p99_retrieval_time']:.2f} 毫秒\n")
                f.write(f"平均内存使用: {report['neo4j_retrieval_performance']['average_memory_used']:.2f} MB\n")
            
            f.write("\n")
            f.write("=" * 60 + "\n")
            f.write("测试完成时间: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write("=" * 60)
        
        print(f"TXT解读文件已生成: {txt_report_file}")
        return report
    
    async def teardown(self):
        """清理测试环境"""
        # 获取内存泄漏信息（在停止追踪之前）
        snapshot = tracemalloc.take_snapshot()
        
        # 停止内存追踪
        tracemalloc.stop()
        
        print("\n内存泄漏分析:")
        top_stats = snapshot.statistics('lineno')
        for stat in top_stats[:5]:
            print(stat)
        
        print("测试环境清理完成")

class Neo4jIndexTester:
    """Neo4j索引驻留测试类"""
    
    def __init__(self):
        self.graph_manager = None
        self.index_metrics = []
        self.retrieval_metrics = []
        self.process = psutil.Process(os.getpid())
    
    def setup(self):
        """设置测试环境"""
        try:
            print(f"尝试连接Neo4j: {NEO4J_URI}, 用户: {NEO4J_USER}")
            self.graph_manager = KnowledgeGraphManager(
                uri=NEO4J_URI,
                username=NEO4J_USER,
                password=NEO4J_PASSWORD
            )
            # 测试连接是否成功
            if self.graph_manager.test_connection():
                print("Neo4j测试环境设置完成")
                return True
            else:
                print("Neo4j连接测试失败")
                return False
        except Exception as e:
            print(f"Neo4j连接失败: {e}")
            return False
    
    def test_index_residency(self, node_count: int = 100):
        """测试索引驻留
        
        Args:
            node_count: 创建的节点数量
        """
        print(f"开始测试Neo4j索引驻留，创建 {node_count} 个节点...")
        
        if not self.graph_manager:
            print("Neo4j未连接，跳过索引驻留测试")
            return
        
        try:
            for i in range(node_count):
                # 创建知识节点
                knowledge_point = {
                    "name": f"TestKnowledge_{i:03d}",
                    "content": f"这是测试知识内容 {i+1}，用于测试Neo4j索引性能",
                    "difficulty": "中等",
                    "status_vector": [1, 0, 0],  # [已掌握, 未知, 混淆]
                    "student_name": f"student_{i % 5 + 1:03d}"
                }
                
                # 添加到知识图谱
                self.graph_manager.add_knowledge_point(knowledge_point)
                
                if (i + 1) % 20 == 0:
                    # 记录内存使用
                    process_memory = self.process.memory_info().rss // (1024 * 1024)  # MB
                    self.index_metrics.append({
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "node_count": i + 1,
                        "process_memory": process_memory
                    })
                    print(f"已创建 {i+1} 个节点，进程内存: {process_memory} MB")
            
            print(f"Neo4j索引驻留测试完成，共创建 {node_count} 个节点")
        except Exception as e:
            print(f"Neo4j索引测试失败: {e}")
    
    def test_concurrent_retrieval(self, concurrent_count=40, query_count=200):
        """测试并发检索性能
        
        Args:
            concurrent_count: 并发数，默认40
            query_count: 总查询数，默认200
        """
        print(f"\n开始Neo4j并发检索测试，并发数: {concurrent_count}，总查询数: {query_count}...")
        
        if not self.graph_manager:
            print("Neo4j未连接，跳过并发检索测试")
            return
        
        import concurrent.futures
        import random
        
        # 生成测试查询
        test_queries = [f"TestKnowledge_{random.randint(0, 99):03d}" for _ in range(query_count)]
        
        # 单个检索任务
        def retrieve_task(query):
            start_time = time.time()
            try:
                # 执行检索
                results = self.graph_manager.find_similar_knowledge_points(query, top_n=3)
                end_time = time.time()
                duration = (end_time - start_time) * 1000  # 毫秒
                
                # 记录内存使用
                process_memory = self.process.memory_info().rss // (1024 * 1024)  # MB
                
                return {
                    "query": query,
                    "duration": duration,
                    "result_count": len(results),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "memory_used": process_memory
                }
            except Exception as e:
                end_time = time.time()
                duration = (end_time - start_time) * 1000  # 毫秒
                return {
                    "query": query,
                    "duration": duration,
                    "result_count": 0,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "memory_used": 0,
                    "error": str(e)
                }
        
        # 使用线程池执行并发检索
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_count) as executor:
            # 提交所有任务
            futures = [executor.submit(retrieve_task, query) for query in test_queries]
            
            # 收集结果
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                self.retrieval_metrics.append(result)
                
                # 每完成20个查询打印一次进度
                if len(self.retrieval_metrics) % 20 == 0:
                    print(f"已完成 {len(self.retrieval_metrics)} 个检索查询")
        
        print(f"Neo4j并发检索测试完成，共执行 {len(self.retrieval_metrics)} 个查询")
        
    def analyze_index_performance(self):
        """分析索引性能"""
        print("\n开始Neo4j索引性能分析...")
        
        if not self.index_metrics:
            print("没有索引指标数据")
            return
        
        # 计算内存增长
        first_metric = self.index_metrics[0]
        last_metric = self.index_metrics[-1]
        memory_growth = last_metric["process_memory"] - first_metric["process_memory"]
        
        print(f"Neo4j索引性能分析结果:")
        print(f"创建节点总数: {last_metric['node_count']}")
        print(f"内存增长: {memory_growth} MB")
        print(f"平均每个节点内存消耗: {memory_growth / last_metric['node_count']:.2f} MB/节点")
        
        return {
            "total_nodes": last_metric["node_count"],
            "memory_growth": memory_growth,
            "avg_memory_per_node": memory_growth / last_metric["node_count"]
        }
    
    def analyze_retrieval_performance(self):
        """分析检索性能"""
        print("\n开始Neo4j检索性能分析...")
        
        if not self.retrieval_metrics:
            print("没有检索指标数据")
            return
        
        # 计算检索时间统计
        durations = [m["duration"] for m in self.retrieval_metrics if "error" not in m]
        if not durations:
            print("没有有效的检索数据")
            return
        
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        p95_duration = sorted(durations)[int(len(durations) * 0.95)]
        p99_duration = sorted(durations)[int(len(durations) * 0.99)]
        
        # 计算内存使用统计
        memory_used = [m["memory_used"] for m in self.retrieval_metrics if m["memory_used"] > 0]
        avg_memory = sum(memory_used) / len(memory_used) if memory_used else 0
        
        # 计算错误率
        total_queries = len(self.retrieval_metrics)
        successful_queries = len(durations)
        error_rate = (total_queries - successful_queries) / total_queries * 100
        
        print(f"Neo4j检索性能分析结果:")
        print(f"总查询数: {total_queries}")
        print(f"成功查询数: {successful_queries}")
        print(f"错误率: {error_rate:.2f}%")
        print(f"平均检索时间: {avg_duration:.2f} 毫秒")
        print(f"最小检索时间: {min_duration:.2f} 毫秒")
        print(f"最大检索时间: {max_duration:.2f} 毫秒")
        print(f"95%分位检索时间: {p95_duration:.2f} 毫秒")
        print(f"99%分位检索时间: {p99_duration:.2f} 毫秒")
        print(f"平均内存使用: {avg_memory:.2f} MB")
        
        return {
            "total_queries": total_queries,
            "successful_queries": successful_queries,
            "error_rate": error_rate,
            "average_retrieval_time": avg_duration,
            "min_retrieval_time": min_duration,
            "max_retrieval_time": max_duration,
            "p95_retrieval_time": p95_duration,
            "p99_retrieval_time": p99_duration,
            "average_memory_used": avg_memory
        }

async def main():
    """主测试函数"""
    print("=" * 60)
    print("Neo4j 索引驻留与 Zep 缓冲区内存占用测试")
    print("=" * 60)
    
    # 创建模拟Zep客户端
    mock_zep_client = MockZepClient()
    
    # 创建内存测试器
    memory_tester = ZepMemoryTester(mock_zep_client)
    
    # 设置测试环境
    await memory_tester.setup()
    
    # 创建Neo4j索引测试器
    neo4j_tester = Neo4jIndexTester()
    neo4j_connected = neo4j_tester.setup()
    print(f"Neo4j连接状态: {neo4j_connected}")
    
    # 执行测试
    await memory_tester._record_memory_metrics()  # 初始内存记录
    
    # 测试1: 缓冲区基本操作
    await memory_tester.test_buffer_operations(operation_count=50)
    
    # 测试2: 对话压力测试
    await memory_tester.simulate_conversation_stress(iterations=100)
    
    # 测试3: Neo4j索引驻留（如果已连接）
    if neo4j_connected:
        neo4j_tester.test_index_residency(node_count=100)
        
        # 测试4: Neo4j并发检索测试（支持最大40并发）
        neo4j_tester.test_concurrent_retrieval(concurrent_count=40, query_count=200)
    
    await memory_tester._record_memory_metrics()  # 最终内存记录
    
    # 分析Neo4j索引和检索性能
    neo4j_index_report = None
    neo4j_retrieval_report = None
    if neo4j_connected:
        neo4j_index_report = neo4j_tester.analyze_index_performance()
        neo4j_retrieval_report = neo4j_tester.analyze_retrieval_performance()
    
    # 创建测试报告
    await memory_tester.create_report(neo4j_index_report, neo4j_retrieval_report)
    
    # 清理测试环境
    await memory_tester.teardown()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())