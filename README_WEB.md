# 虚拟学生对话系统 - Web应用

## 功能特性

1. **教师对话界面**：通过打字与虚拟学生进行对话
2. **模式选择**：可以选择虚拟学生的模式（长期记忆、认知增强）
3. **上下文显示**：右侧实时显示虚拟学生的上下文信息
4. **完整输出**：聊天框显示所有模型输出，包括function call的调用

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

确保 `.env` 文件中包含：
- `ZEP_API_KEY`：Zep API密钥
- `QWEN_API_KEY`：Qwen API密钥
- `QWEN_BASE_URL`：Qwen API地址（可选）
- `QWEN_MODEL`：Qwen模型名称（可选，默认qwen-max）

### 3. 启动应用

```bash
python app.py
```

应用将在 `http://localhost:8080` 启动（默认端口8080，避免与macOS的AirPlay Receiver冲突）

如果需要使用其他端口，可以运行：
```bash
python app.py 8080
```

### 4. 使用界面

1. 在顶部选择学生模式和姓名
2. 点击"初始化学生"按钮
3. 在输入框中输入消息与虚拟学生对话
4. 右侧面板会实时显示学生的上下文信息

## 项目结构

```
ZEP/
├── app.py                 # Flask后端应用
├── templates/
│   └── index.html        # 前端HTML页面
├── static/
│   ├── css/
│   │   └── style.css     # 样式文件
│   └── js/
│       └── app.js        # 前端JavaScript
└── src/                  # 源代码模块
```

## API接口

### POST /api/init
初始化虚拟学生

**请求体：**
```json
{
    "student_name": "小明",
    "enable_long_term_memory": true,
    "enable_knowledge_base": false
}
```

### POST /api/chat
发送消息并获取回复

**请求体：**
```json
{
    "message": "你好，小明"
}
```

**响应：**
```json
{
    "success": true,
    "response": "你好，老师！",
    "tool_calls": [
        {
            "name": "recall_knowledge_tool",
            "arguments": {"name": "数学"}
        }
    ],
    "intermediate_steps": [
        {
            "tool": "recall_knowledge_tool",
            "arguments": {"name": "数学"},
            "result": "找到相关知识点..."
        }
    ]
}
```

### GET /api/context
获取虚拟学生的上下文信息

**响应：**
```json
{
    "success": true,
    "short_term_memory": [...],
    "long_term_context": "...",
    "full_context": "...",
    "student_name": "小明",
    "enable_long_term_memory": true,
    "enable_knowledge_base": false
}
```

### POST /api/reset
重置虚拟学生

## 功能说明

### 模式选择

- **长期记忆**：启用Zep长期记忆功能，学生可以检索历史对话
- **认知增强**：启用知识库功能，学生可以查询和更新知识库

### 上下文显示

右侧面板显示：
- 学生信息（姓名、模式状态）
- 短期记忆（最近的10条对话）
- 长期记忆（从Zep获取的上下文）

### 工具调用显示

当学生调用工具时，聊天框会显示：
- 工具名称
- 工具参数
- 工具执行结果

## 注意事项

1. 确保Neo4j数据库已启动（如果使用认知增强模式）
2. 确保网络连接正常，可以访问Zep和Qwen API
3. 首次初始化可能需要几秒钟时间

