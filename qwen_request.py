import os
import time
import json
import re
import uuid
import logging
import uvicorn
import psutil
import signal
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.engine.async_llm_engine import AsyncLLMEngine
from vllm.sampling_params import SamplingParams
from vllm.lora.request import LoRARequest


try:
    from prompt import STUDENT_SYSTEM_PROMPT, TOOLS as LLM_TOOLS
    from knowledge_graph_manager import KnowledgeGraphManager
except ImportError as e:
    print(f"Error: 缺少必要的文件 (prompt.py 或 knowledge_graph_manager.py): {e}")
    exit(1)

# --- 1. 启动前精准清理 ---
def auto_cleanup(port=8000):
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for conn in proc.connections(kind='inet'):
                if conn.laddr.port == port:
                    os.kill(proc.pid, signal.SIGKILL)
        except: continue
    if os.path.exists("/dev/shm"):
        for f in os.listdir("/dev/shm"):
            if f.startswith("vllm"):
                try: os.remove(os.path.join("/dev/shm", f))
                except: pass

auto_cleanup(8000)

# --- 2. 初始化日志与数据库 ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger("vllm_api")

kg_manager = KnowledgeGraphManager(
    uri="bolt://localhost:7687", 
    username="neo4j", 
    password="51265903089", 
    student_label_en="Cuizhanhao"
)

# --- 3. vLLM 引擎封装 ---
class LLMService:
    def __init__(self, model_path, peft_path):
        logger.info(f"正在启动 vLLM 引擎: {model_path}")
        engine_args = AsyncEngineArgs(
            model=model_path,
            tensor_parallel_size=1,
            trust_remote_code=True,
            enable_lora=True,
            gpu_memory_utilization=0.5, 
            dtype="bfloat16",
            enforce_eager=True,
            max_num_seqs=256
        )
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)
        self.peft_path = peft_path
        self.lora_request = LoRARequest("qwen_lora", 1, self.peft_path)

    async def get_tokenizer(self):
        return await self.engine.get_tokenizer()

# --- 4. 核心工具执行逻辑 ---
# --- 4. 核心工具执行逻辑 (返回标准 JSON 格式) ---

async def recall_knowledge_vector_tool(name: str) -> str:
    """查询知识点并返回标准的 JSON 结构"""
    items = kg_manager.find_similar_knowledge_points(name, top_n=1)
    if not items:
        res = {"node_name": name, "status": [0, 0, 0], "content": "未找到相关知识点"}
    else:
        p = items[0]
        res = {
            "node_name": p.get('node_name'),
            "status": p.get('status'), 
            "content": p.get('description', '')
        }
    return json.dumps(res, ensure_ascii=False)

async def update_knowledge_vector_tool(name: str, index: int, value: int) -> str:
    """更新向量并返回包含操作详情的 JSON 结构"""
    items = kg_manager.find_similar_knowledge_points(name, top_n=1)
    
    if not items:
        res = {
            "name": name,
            "index": index,
            "value": value,
            "result": "fail (node not found)"
        }
    else:
        success = kg_manager.update_knowledge_vector(uuid=items[0]['uuid'], index=index, value=value)
        res = {
            "name": name,
            "index": index,
            "value": value,
            "result": "success" if success else "fail"
        }
    
    return json.dumps(res, ensure_ascii=False)

TOOLS_EXECUTOR = {
    "recall_knowledge_vector_tool": recall_knowledge_vector_tool,
    "update_knowledge_vector_tool": update_knowledge_vector_tool
}

# --- 5. FastAPI 核心逻辑 ---
app = FastAPI(title="Virtual Student Traceable API")
llm_service = None

@app.on_event("startup")
async def startup():
    global llm_service
    llm_service = LLMService("/home/gpu6/vllm/model/Qwen3-4B", 
                              "/home/gpu6/vllm/sft/Qwen3-4B/lora/rank_8_ep_2_lr_1e-4")

async def run_vllm(messages, sampling_params):
    tokenizer = await llm_service.get_tokenizer()
    prompt = tokenizer.apply_chat_template(messages, tools=LLM_TOOLS, tokenize=False, add_generation_prompt=True)
    prompt = "/no_think\n" + prompt
    
    # 调试日志：查看实时喂给模型的完整 Prompt
    logger.info(f"\n{'='*20} 内部推理 PROMPT {'='*20}\n{prompt}\n{'='*55}")
    
    gen_id = str(uuid.uuid4())
    results_generator = llm_service.engine.generate(prompt, sampling_params, gen_id, lora_request=llm_service.lora_request)
    
    final_res = None
    async for res in results_generator:
        final_res = res
    return final_res

@app.post("/generate")
async def generate(request: Request):
    try:
        body = await request.json()
        raw_msgs = body.get("messages", [])
        
        # 1. 初始化对话历史（注入 System Prompt）
        if not raw_msgs or raw_msgs[0]['role'] != 'system':
            messages = [{"role": "system", "content": STUDENT_SYSTEM_PROMPT}] + raw_msgs
        else:
            messages = raw_msgs

        sampling_params = SamplingParams(temperature=0.7, max_tokens=1024, stop=["<|im_end|>", "<|endoftext|>"])

        # --- 迭代推理逻辑 ---
        for i in range(2): 
            output = await run_vllm(messages, sampling_params)
            text = output.outputs[0].text
            
            # 搜索模型生成的工具调用标签
            tool_call_match = re.search(r'<tool_call>(.*?)</tool_call>', text, re.DOTALL)
            
            if tool_call_match:
                try:
                    call_info = json.loads(tool_call_match.group(1).strip())
                    func_name = call_info.get("name")
                    args = call_info.get("arguments") or call_info.get("params")
                    call_id = f"call_{str(uuid.uuid4())[:8]}"

                    if func_name in TOOLS_EXECUTOR:
                        logger.info(f"--- [Step {i+1}] 执行工具: {func_name} ---")
                        obs = await TOOLS_EXECUTOR[func_name](**args)
                        
                        # 记录中间状态到 messages 数组
                        messages.append({
                            "role": "assistant",
                            "content": text,
                            "tool_calls": [{
                                "id": call_id,
                                "type": "function",
                                "function": {"name": func_name, "arguments": json.dumps(args, ensure_ascii=False)}
                            }]
                        })
                        messages.append({
                            "role": "tool",
                            "name": func_name,
                            "tool_call_id": call_id,
                            "content": obs
                        })
                        # 继续循环，喂回结果进行下一次推理
                        continue 
                except Exception as e:
                    logger.error(f"工具解析/执行异常: {e}")
                    break
            else:
                # 无工具调用，获得最终回复
                break

        # 最终返回结果中包含完整的推理链 history
        return JSONResponse({
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"total_tokens": len(output.prompt_token_ids) + len(output.outputs[0].token_ids)},
            "history": messages  # 这里包含了 System, User, Assistant(ToolCall), Tool, Assistant(Final)
        })

    except Exception as e:
        logger.exception("API Critical Error")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)