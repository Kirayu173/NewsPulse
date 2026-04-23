# coding=utf-8
"""
NewsPulse - 热点新闻聚合与分析工具

使用方式:
  python -m newspulse  # 模块执行
  newspulse            # 安装后执行
"""

__version__ = "1.0.0"

from newspulse.context import AppContext
__all__ = ["AppContext", "__version__"]
