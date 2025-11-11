"""
系统配置和常量设置
"""

import os
from dotenv import load_dotenv
from rich.console import Console

# 加载环境变量
load_dotenv()

# 控制台输出对象
console = Console()


def load_environment():
    """加载并验证必要的环境变量"""
    required_vars = {
        'ZEP_API_KEY': 'Zep API密钥',
        'QWEN_API_KEY': 'Qwen API密钥'
    }
    
    missing_vars = []
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing_vars.append(f"{var} ({description})")
    
    if missing_vars:
        raise ValueError(f"缺少必要的环境变量: {', '.join(missing_vars)}")
    
    return {
        'ZEP_API_KEY': os.getenv('ZEP_API_KEY'),
        'QWEN_API_KEY': os.getenv('QWEN_API_KEY'),
        'QWEN_BASE_URL': os.getenv('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
        'QWEN_MODEL': os.getenv('QWEN_MODEL', 'qwen-max')
    }

