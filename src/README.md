# 虚拟学生系统 - 代码结构说明

## 📁 目录结构

```
src/
├── config/              # 配置模块
│   ├── __init__.py
│   └── settings.py     # 环境变量和配置管理
│
├── memory/             # 记忆管理模块
│   ├── __init__.py
│   └── short_term_memory.py  # 短期记忆管理器
│
├── api/                # API客户端模块
│   ├── __init__.py
│   └── qwen_client.py  # Qwen API客户端
│
├── student/            # 学生相关模块（完整集成tool、prompt、memory）
│   ├── __init__.py
│   ├── student_state.py      # 学生状态定义
│   ├── virtual_student.py   # 虚拟学生主类
│   └── system_prompts.py  # 系统提示词定义（Prompt）
│
├── tools/              # 工具模块
│   ├── __init__.py
│   ├── zep_tools.py    # Zep长期记忆工具
│   └── knowledge_tools.py   # 知识库工具
│
└── README.md          # 本文件
```

## 🎯 模块说明

### 1. config/ - 配置模块
**作用**：统一管理系统配置和环境变量

- `settings.py`：加载和验证环境变量，提供控制台输出对象

### 2. memory/ - 记忆管理模块
**作用**：管理短期记忆和长期记忆

- `short_term_memory.py`：短期记忆管理器
  - 维护固定容量的对话队列（默认10条）
  - 自动将旧对话存入长期记忆
  - 提供获取上下文的方法

### 3. api/ - API客户端模块
**作用**：封装外部API调用

- `qwen_client.py`：Qwen API客户端
  - 异步调用Qwen API
  - 支持工具调用（function calling）
  - 统一错误处理

### 4. student/ - 学生相关模块
**作用**：完整的虚拟学生实现，集成Tool、Prompt、Memory三大核心功能

- `student_state.py`：定义学生状态结构（已移除current_topic字段）
- `virtual_student.py`：虚拟学生主类
  - 创建学生用户
  - 管理对话线程
  - 集成记忆功能（Memory）
  - 提供工具管理（Tool，使用tools/zep_tools.py中的工具）
  - 提供提示词管理（Prompt）
- `system_prompts.py`：系统提示词定义（Prompt）
  - `get_system_prompt()`：根据模式获取系统提示词
  - `get_tool_definitions()`：获取工具定义列表（用于Qwen API）
  - 支持基础模式和认知增强模式两种提示词
  - 包含长期记忆工具和知识库工具的定义（用于模型tool call）

### 5. tools/ - 工具模块
**作用**：提供AI模型可调用的工具函数

- `zep_tools.py`：Zep长期记忆检索工具
- `knowledge_tools.py`：知识库查询和更新工具

## 🚀 使用方法

### 环境变量配置
确保在 `.env` 文件中配置：
- `ZEP_API_KEY`：Zep API密钥
- `QWEN_API_KEY`：Qwen API密钥
- `QWEN_BASE_URL`：Qwen API地址（可选）
- `QWEN_MODEL`：Qwen模型名称（可选，默认qwen-max）

## 📝 代码特点

1. **模块化设计**：每个模块职责明确，易于维护
2. **易于扩展**：新增功能只需在对应模块添加代码
3. **通俗易懂**：每个文件都有详细的中文注释
4. **统一配置**：所有配置集中在config模块
5. **清晰分层**：配置 → 数据 → 业务逻辑 → 工具
6. **集中管理**：系统提示词定义在student模块中，便于管理

## 🔧 扩展指南

### 添加新功能
1. 根据功能类型，在对应模块创建文件
2. 在模块的 `__init__.py` 中导出新功能
3. 在需要使用的地方导入并调用

### 修改配置
直接修改 `config/settings.py` 中的配置即可

### 添加新工具
1. 在 `tools/` 目录创建新文件
2. 使用 `@tool` 装饰器定义工具函数
3. 在需要使用工具的地方导入并调用

### 修改系统提示词
直接修改 `student/system_prompts.py` 中的提示词定义即可

