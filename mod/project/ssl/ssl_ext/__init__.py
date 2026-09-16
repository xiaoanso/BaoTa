# 二次开发隔离包：官方文件只留 BT_EXT 钩子，业务均从这里 import 官方类再调用。
from . import hooks

__all__ = ["hooks"]
