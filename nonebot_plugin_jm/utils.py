import asyncio
import contextlib
import shutil
from pathlib import Path

import jmcomic
import pyzipper
from nonebot import require
from nonebot.log import logger

from .Config import config

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store  # noqa: E402

# 用于防止并发下载冲突的锁字典
_download_locks = {}
# 每次启动清理缓存目录
cache_directory = store.get_cache_dir("nonebot_plugin_jm")
if cache_directory.exists():
    shutil.rmtree(cache_directory)

jm_pwd = config.jm_pwd
if jm_pwd:
    jm_pwd = jm_pwd.encode("utf-8")


@contextlib.asynccontextmanager
async def acquire_album_lock(album_id: str):
    """获取针对特定漫画ID的锁，防止并发下载冲突"""
    if album_id not in _download_locks:
        _download_locks[album_id] = asyncio.Lock()

    lock = _download_locks[album_id]
    try:
        await lock.acquire()
        yield
    finally:
        lock.release()
        if not lock.locked():
            _download_locks.pop(album_id, None)


async def download_album(album_id: str) -> list:
    """根据 album_id 下载漫画，并返回压缩后的文件路径。

    Args:
        album_id (str): 漫画的 album_id
        path (Path): 存放漫画的文件夹路径

    Returns:
        Path: 压缩后的文件路径
    """

    options = jmcomic.JmOption.default()
    client = options.new_jm_client()
    album: jmcomic.JmAlbumDetail = client.get_album_detail(album_id)

    zip_file_name = cache_directory / f"{album.name}.zip"
    # 如果已经下载过，直接返回
    if zip_file_name.exists():
        return zip_file_name

    album_folder = cache_directory / album_id

    total_photos = len(album)
    logger.info(f"开始下载漫画 {album.name}，共 {total_photos} 章节")

    index = 1
    for _, photo in enumerate(album, 1):
        photo = client.get_photo_detail(photo.photo_id)

        # 根据章节数量决定路径结构
        base_path = album_folder
        if len(album) > 1:
            base_path = base_path / f"{index:03d}章"  # 保证文件夹按照章节顺序排序
            index += 1

        base_path.mkdir(parents=True, exist_ok=True)

        # 并发下载图片
        async def download_image(image: jmcomic.JmImageDetail):
            image_path = base_path / image.filename
            try:
                # 将同步下载转为异步任务
                await asyncio.to_thread(
                    client.download_by_image_detail, image, image_path
                )
            except Exception as e:
                logger.error(f"下载图片失败: {e}")
                # 继续下载下一张

        # 创建所有图片的下载任务
        download_tasks = []
        for _, image in enumerate(photo, 1):
            download_tasks.append(download_image(image))

        # 并发执行所有下载任务，最大并发数为10个
        semaphore = asyncio.Semaphore(10)

        async def bounded_download(task):
            async with semaphore:
                await task

        await asyncio.gather(*[bounded_download(task) for task in download_tasks])

    # 压缩文件
    logger.info(f"正在创建压缩文件: {zip_file_name}")
    # 将同步压缩操作转为异步任务
    await asyncio.to_thread(zip_folder, album_folder, zip_file_name)

    # 删除下载的文件夹
    shutil.rmtree(album_folder)

    return structure_node(album, zip_file_name)


def zip_folder(folder_path: Path, output_path: Path):
    """
    将指定文件夹压缩成 ZIP 文件。

    Args:
        folder_path: 要压缩的文件夹路径，可以是 str 或 Path 对象。
        output_path: 输出的 ZIP 文件路径 (包括文件名和 .zip 扩展名)，可以是 str 或 Path 对象。
    """
    if jm_pwd:
        with pyzipper.AESZipFile(
            output_path, "w", compression=pyzipper.ZIP_LZMA, encryption=pyzipper.WZ_AES
        ) as zipf:
            zipf.setpassword(jm_pwd)
            for file_path in folder_path.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(folder_path)
                    zipf.write(file_path, str(arcname))
    else:
        with pyzipper.ZipFile(
            output_path, "w", compression=pyzipper.ZIP_DEFLATED
        ) as zipf:
            for file_path in folder_path.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(folder_path)
                    zipf.write(file_path, str(arcname))


def structure_text_node(text: str) -> dict:
    return {
        "type": "node",
        "data": {
            "content": [{"type": "text", "data": {"text": text}}],
        },
    }


def structure_node(jmAlbumDetail: jmcomic.JmAlbumDetail, zip_file_name: Path) -> dict:
    nodes = []
    nodes.append(structure_text_node(jmAlbumDetail.title))
    nodes.append(structure_text_node(f"作者：{' '.join(jmAlbumDetail.author)}"))
    nodes.append(structure_text_node(f"标签：{' '.join(jmAlbumDetail.tags)}"))
    nodes.append(structure_text_node(f"禁漫号：{jmAlbumDetail.album_id}"))
    nodes.append(
        {
            "type": "node",
            "data": {
                "content": [
                    {
                        "type": "file",
                        "data": {
                            "file": str(zip_file_name),
                            "name": zip_file_name.name,
                        },
                    }
                ]
            },
        }
    )
    if jm_pwd:
        nodes.append(
            structure_text_node(f"为防止腾讯风控，已加密，解压密码：{config.jm_pwd}")
        )
    return nodes
