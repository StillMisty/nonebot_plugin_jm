from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    jm_pwd: str | None = None


config = get_plugin_config(Config)
