from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class Config(BaseModel):
    jm_pwd: str | None = None  # 压缩包密码，若不设置则不启用压缩包功能
    jm_forward: bool = True  # 是否启用转发功能
    jm_lock: bool = True  # 是否启用锁机制，防止同一用户并发请求
    jm_lock_size: int = Field(
        default=1, gt=0
    )  # 每个用户同时可以下载的数量，默认为1，必须大于0


config = get_plugin_config(Config)
