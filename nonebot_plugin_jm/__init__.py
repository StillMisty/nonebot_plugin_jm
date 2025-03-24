import jmcomic
import nonebot_plugin_localstore as store
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.log import logger
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (  # noqa: E402
    Alconna,
    Args,
    CommandMeta,
    Match,
    on_alconna,
)

from .Config import Config
from .utils import acquire_album_lock, download_album

__plugin_meta__ = PluginMetadata(
    name="禁漫下载",
    description="下载 jm 漫画",
    type="application",
    usage="jm [禁漫号]",
    homepage="https://github.com/StillMisty/nonebot_plugin_jm",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

jm = on_alconna(
    Alconna(
        "jm",
        Args["album_id", int],
        meta=CommandMeta(
            compact=True,
            description="下载 jm 漫画",
            usage="jm [禁漫号]",
        ),
    )
)


@jm.handle()
async def _(bot: Bot, event: Event, album_id: Match[int]):
    album_id_str = str(album_id.result)
    path = store.get_cache_dir("nonebot_plugin_jm")

    # 使用锁确保同一时间只有一个请求在处理同一个album_id
    async with acquire_album_lock(album_id_str):
        try:
            msg = await download_album(album_id_str, path)
        except jmcomic.jm_exception.MissingAlbumPhotoException:
            await jm.finish("请求的本子不存在！")
        except Exception as e:
            logger.error(f"下载漫画时发生错误: {e}")
            await jm.finish(f"下载失败: {str(e)}")

        await bot.send_forward_msg(
            user_id=event.user_id,
            group_id=getattr(event, "group_id", None),
            messages=msg,
        )
