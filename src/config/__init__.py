"""
配置模块
统一管理系统的配置和常量
"""

from .settings import load_environment, console
from . import settings

__all__ = ['load_environment', 'console', 'settings']

