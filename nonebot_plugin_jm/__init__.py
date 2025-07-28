from jmcomic import JmOption
from jmcomic.jm_exception import MissingAlbumPhotoException
from nonebot import require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.log import logger
from nonebot.plugin import PluginMetadata

from .Config import Config, config
from .utils import (
    UserLockedException,  # 新增
    acquire_album_lock,
    acquire_user_lock,
    download_album,
    get_album_detail,
    structure_node,
)

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import (  # noqa: E402
    Alconna,
    Args,
    CommandMeta,
    Match,
    on_alconna,
)

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
async def _(bot: Bot, event: MessageEvent, album_id: Match[int]):
    album_id_str = str(album_id.result)
    user_id = event.user_id

    try:
        # 先获取用户锁，确保同一用户同一时间只能请求一次
        async with acquire_user_lock(user_id):
            # 使用锁确保同一时间只有一个请求在处理同一个album_id
            await jm.send("正在下载漫画，请稍候...", at_sender=True)
            async with acquire_album_lock(album_id_str):
                try:
                    options = JmOption.default()
                    client = options.new_jm_client()
                    album_detail = await get_album_detail(album_id_str, client)
                    album_path = await download_album(album_detail, client)
                except MissingAlbumPhotoException:
                    await jm.finish("请求的本子不存在！")
                except Exception as e:
                    logger.error(f"下载漫画时发生错误: {e}")
                    await jm.finish(f"下载失败: {str(e)}")

                if config.jm_forward:
                    msg = structure_node(album_detail, album_path)
                    # 判断是否是群聊
                    if isinstance(event, GroupMessageEvent):
                        await bot.send_group_forward_msg(
                            group_id=event.group_id,
                            messages=msg,
                        )
                    else:
                        await bot.send_private_forward_msg(
                            user_id=event.user_id,
                            messages=msg,
                        )
                else:
                    if isinstance(event, GroupMessageEvent):
                        await bot.upload_group_file(
                            group_id=event.group_id,
                            file=str(album_path.resolve()),
                            name=album_path.name,
                        )
                    else:
                        await bot.upload_private_file(
                            user_id=event.user_id,
                            file=str(album_path.resolve()),
                            name=album_path.name,
                        )

                    msg = (
                        f"解压密码为: {config.jm_pwd}"
                        if config.jm_pwd
                        else "如无法下载，则是被风控，建议设置解压密码或是设置为转发或是在私聊中使用"
                    )
                    await jm.finish(msg)
    except UserLockedException as e:
        await jm.finish(str(e), at_sender=True)
