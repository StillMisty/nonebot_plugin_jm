import asyncio
import contextlib
import re
import shutil
from pathlib import Path

import pyzipper
from jmcomic import JmAlbumDetail, JmApiClient, JmHtmlClient, JmImageDetail
from nonebot import require
from nonebot.log import logger

from .Config import config

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store  # noqa: E402

# 用于防止并发下载冲突的锁字典
_download_locks = {}
# 用户锁字典改为存储信号量
_user_locks = {}

# 每次启动清理缓存目录
cache_directory = store.get_plugin_cache_dir()
if cache_directory.exists():
    shutil.rmtree(cache_directory)
# 清理后重新创建
cache_directory.mkdir(parents=True, exist_ok=True)


jm_pwd = config.jm_pwd
if jm_pwd:
    jm_pwd = jm_pwd.encode("utf-8")
jm_lock = config.jm_lock


def sanitize_and_truncate_filename(filename: str, max_length: int = 150) -> str:
    """
    清理并截断文件名以防止路径过长或包含非法字符。

    Args:
        filename (str): 原始文件名 (不含扩展名)。
        max_length (int): 文件名（不含扩展名）的最大长度。

    Returns:
        str: 处理后的安全文件名。
    """
    # 移除Windows和Linux下文件名中的非法字符
    sanitized_filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
    # 截断文件名以防止过长
    if len(sanitized_filename) > max_length:
        sanitized_filename = sanitized_filename[:max_length].strip()
        logger.warning(f"文件名过长，已截断: {filename} -> {sanitized_filename}")
    return sanitized_filename


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


class UserLockedException(Exception):
    pass


@contextlib.asynccontextmanager
async def acquire_user_lock(user_id: int):
    """获取针对特定用户的锁,支持配置并发数量"""
    if not jm_lock:
        yield
        return

    sem = _user_locks.get(user_id)
    if sem is None:
        sem = asyncio.Semaphore(config.jm_lock_size)
        _user_locks[user_id] = sem

    if sem._value > 0:  # 还有可用的锁
        async with sem:
            yield
    else:
        raise UserLockedException(
            f"您已达到最大并发下载数({config.jm_lock_size}),请等待当前任务完成后再试"
        )


async def get_album_detail(
    album_id: str, client: JmHtmlClient | JmApiClient
) -> JmAlbumDetail:
    """获取漫画的详细信息。"""
    return await asyncio.to_thread(client.get_album_detail, album_id)


async def download_album(
    album: JmAlbumDetail, client: JmHtmlClient | JmApiClient
) -> Path:
    """根据 album_id 下载漫画，并返回压缩后的文件路径。

    Args:
        album_id (str): 漫画的 album_id
        path (Path): 存放漫画的文件夹路径

    Returns:
        Path: 压缩后的文件路径
    """
    # 处理文件名
    safe_album_name = sanitize_and_truncate_filename(album.name)
    zip_file_name = cache_directory / f"{safe_album_name}.zip"

    # 如果已经下载过，直接返回
    if zip_file_name.exists():
        return zip_file_name

    album_folder = cache_directory / album.album_id

    total_photos = len(album)
    logger.info(f"开始下载漫画 {album.name}，共 {total_photos} 章节")

    index = 1
    for _, photo in enumerate(album, 1):
        photo = await asyncio.to_thread(client.get_photo_detail, photo.photo_id)
        # 根据章节数量决定路径结构
        base_path = album_folder
        if len(album) > 1:
            base_path = base_path / f"{index:03d}章"  # 保证文件夹按照章节顺序排序
            index += 1

        base_path.mkdir(parents=True, exist_ok=True)

        # 并发下载图片
        async def download_image(image: JmImageDetail):
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

    # 异步压缩文件
    logger.info(f"正在创建压缩文件: {zip_file_name}")
    await asyncio.to_thread(zip_folder, album_folder, zip_file_name)

    # 删除下载漫画所在的文件夹，仅保留压缩文件
    await asyncio.to_thread(shutil.rmtree, album_folder)

    return zip_file_name


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
            "user_id": "114514",
            "nickname": "JM助手",
            "content": [{"type": "text", "data": {"text": text}}],
        },
    }


def structure_node(jmAlbumDetail: JmAlbumDetail, zip_file_name: Path) -> list:
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
