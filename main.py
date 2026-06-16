"""JMComic Bot — 禁漫天堂插件 for AstrBot（v1.11.2）

功能：
  jm <id> — 下载整本本子
  jmc <id> — 下载单个章节
  jms <关键词> — 搜索本子
  jmi <id> — 查看本子详情
  jmrank [页码] — 排行榜
  jmfav [页码] — 收藏夹（需登录）
  jmlogin — 登录说明
  jmstatus — 插件状态
  jmhelp — 帮助
  jmchangelog — 更新日志

LLM 工具：
  jm_search — AI 可主动调用搜索本子
  jm_download — AI 可主动调用下载本子

基于 jmcomic 库: https://github.com/jujg12123/astrbot_plugin_jmcomic_bot
"""

import asyncio
import os
import sys
import subprocess
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from astrbot.api import AstrBotConfig, logger, FunctionTool
from astrbot.api.event import AstrMessageEvent, filter, MessageChain
from astrbot.api import message_components as Comp
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr

# ═════════════════════════ 依赖自举 ═════════════════════════

def _try_import(pkg):
    """真正尝试 import，而非 find_spec（jmcomic 可能有特殊加载机制）"""
    try:
        importlib.import_module(pkg)
        return True
    except ImportError:
        return False


def _bootstrap():
    """自动安装 jmcomic / pymupdf / pyzipper。
    返回 (ok: bool, detail: str, pip_output: str)"""
    required = ["jmcomic", "pymupdf", "pyzipper"]
    mirrors = [
        ("清华镜像", "https://pypi.tuna.tsinghua.edu.cn/simple"),
        ("阿里镜像", "https://mirrors.aliyun.com/pypi/simple"),
        ("官方源", "https://pypi.org/simple"),
    ]

    missing = [p for p in required if not _try_import(p)]
    if not missing:
        return True, "已安装", ""

    last_err = ""
    last_full_output = ""
    for name, url in mirrors:
        logger.info(f"[jmcomic_bot] 正在从 {name} 安装: {' '.join(missing)}...")
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--root-user-action=ignore",
                 "-i", url, *missing],
                capture_output=True, text=True, timeout=300,
            )
            full_output = (r.stdout + "\n" + r.stderr).strip()
            importlib.invalidate_caches()
            still_missing = [p for p in missing if not _try_import(p)]
            if not still_missing:
                logger.info(f"[jmcomic_bot] ✅ {name} 安装成功")
                return True, f"从 {name} 安装成功", full_output
            last_err = f"安装后仍无法导入: {still_missing}"
            last_full_output = full_output
            logger.warning(f"[jmcomic_bot] ⚠️ {name}: {last_err}")
        except subprocess.TimeoutExpired:
            last_err = "pip 安装超时 (300s)"
            last_full_output = ""
        except Exception as ex:
            last_err = str(ex)
            last_full_output = ""

    return False, f"{last_err}", last_full_output


def _import_jmcomic():
    """懒加载 jmcomic：自动安装 + --target 兜底"""
    try:
        import jmcomic
        from jmcomic import JmOption, JmModuleConfig, JmApiClient
        return jmcomic, JmOption, JmModuleConfig, JmApiClient
    except ImportError:
        pass

    logger.info("[jmcomic_bot] jmcomic 未导入，尝试自动安装...")
    ok, detail, pip_output = _bootstrap()

    if not ok:
        # 方案1：从 pip 输出提取 site-packages 路径
        import re
        path_match = re.search(r'in ([^\s]+?site-packages)', pip_output)
        if path_match:
            pkg_path = path_match.group(1)
            if pkg_path not in sys.path:
                sys.path.insert(0, pkg_path)
        # 方案2：pip install --target 到插件目录，绕过 AstrBot 的 import hook
        target_dir = os.path.join(os.path.dirname(__file__), "_deps")
        logger.info(f"[jmcomic_bot] 尝试 --target 安装到 {target_dir}...")
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--root-user-action=ignore",
                 "--target", target_dir, "jmcomic", "pymupdf", "pyzipper",
                 "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                capture_output=True, text=True, timeout=300,
            )
            pip_output += "\n--- --target 输出 ---\n" + (r.stdout + "\n" + r.stderr).strip()
            if target_dir not in sys.path:
                sys.path.insert(0, target_dir)
            importlib.invalidate_caches()
            try:
                import jmcomic
                from jmcomic import JmOption, JmModuleConfig, JmApiClient
                logger.info(f"[jmcomic_bot] ✅ jmcomic 通过 --target 加载成功 ({target_dir})")
                return jmcomic, JmOption, JmModuleConfig, JmApiClient
            except ImportError:
                logger.warning(f"[jmcomic_bot] --target 安装后仍无法导入")
        except Exception as ex:
            logger.warning(f"[jmcomic_bot] --target 安装异常: {ex}")

        raise ImportError(
            f"jmcomic 加载失败: {detail}\n"
            f"Python: {sys.executable}\n"
            f"sys.path: {sys.path[:5]}\n"
            f"--- pip 输出 ---\n{pip_output[:2000]}\n"
            f"手动: {sys.executable} -m pip install jmcomic pymupdf pyzipper"
        )

    importlib.invalidate_caches()
    try:
        import jmcomic
        from jmcomic import JmOption, JmModuleConfig, JmApiClient
        logger.info(f"[jmcomic_bot] ✅ jmcomic 加载成功 ({detail})")
        return jmcomic, JmOption, JmModuleConfig, JmApiClient
    except ImportError as e:
        raise ImportError(
            f"jmcomic 安装验证通过但导入仍失败: {e}\n"
            f"Python: {sys.executable}\nsys.path: {sys.path[:5]}\n"
            f"手动: {sys.executable} -m pip install jmcomic pymupdf pyzipper"
        )


# ═════════════════════════ 更新日志 ═════════════════════════
CHANGELOG = """
📋 **JMComic Bot 更新日志**

**v1.11.2** (2026-06-16)
- 🐛 修复封面预览不发送：`JmAlbumDetail` 无 `cover_url` 属性
  - 从第一话第一张图（`data_original_0`）获取封面
  - CDN 构造 URL 兜底：`cdn-msp.{domain}/media/albums/{id}_3x4.jpg`
  - 带 scramble_id 的 URL 作为第三兜底
  - 添加 debug 日志输出封面 URL
- 🐛 修复页数不准确：`len(album)` 返回章节数，`album.page_count` 有时为 0
  - 优先 `page_count`（>0 才用）
  - 回退 `len(album)`（章节数）
  - 下载后从实际文件数校准
- 🔗 metadata.yaml repo 更新为 https://github.com/jujg12123/astrbot_plugin_jmcomic_bot

**v1.11.1** (2026-06-16)
- 🐛 修复：不同本子 ID 返回相同内容的问题
  - 所有命令添加手动消息文本解析 fallback（防止 GreedyStr/str 参数绑定失败）
  - 所有命令添加 `logger.info` 日志记录收到的参数
  - JMBackend.download_album 添加日志记录 API 实际返回的 album ID
  - 封面召回改用 `asyncio.create_task` 后台任务实现（修复 `_send_with_recall` 因 async generator 被 `await` 导致永不执行的问题）
- 🐛 修复 PDF 加密保存报错：`user_password`/`owner_password` → `user_pw`/`owner_pw`（pymupdf 标准参数名）

**v1.11.0** (2026-06-16)
- ✨ 大量新功能（参考 jm_cosmos）：
  - 📷 图片格式选择（.jpg/.png/.webp）
  - 📱 客户端类型选择（api/html）
  - 📦 打包格式选择（zip/pdf/none）
  - 🔑 文件名显示密码提示
  - 🖼️ 发送封面预览
  - ⏱️ 封面消息自动撤回
  - ⏱️ 文件消息自动撤回（可配置延迟）
  - 👤 用户名/密码登录（替代 Cookie）

**v1.10.17** (2026-06-16)
- 🐛 LLM 工具下载后自动发送文件（之前只提示下载完成不发送）
- 🔐 LLM 工具加入权限/配额/群白名单检查

**v1.10.16** (2026-06-16)
- 📝 所有命令添加 description 描述（AstrBot UI 可显示）
- 🔗 更新仓库地址为 jujg12123/astrbot_plugin_jmcomic_bot

**v1.10.15** (2026-06-16)
- 🔐 新增 ZIP AES-256 加密防风控（仿 jm_cosmos）
  - 配置 zip_password 后使用 pyzipper AES 加密
  - 腾讯无法扫描加密内容，防止压缩包被风控
  - 不解密直接打开会提示密码错误

**v1.10.14** (2026-06-15)
- 🐛 Comp.File 在 aiocqhttp 上根本不支持（SnowLuma/NapCat 都不行）
  - 回退到 upload_private_file/upload_group_file + base64
  - 用 MessageType 判断群聊/私聊，不再依赖 get_group_id
  - 私聊(c2c)走 upload_private_file 直接送达

**v1.10.13** (2026-06-15)
- 🔄 回退到 Comp.File + MessageChain 方案（仿 jm_cosmos）
  - 使用 MessageChain 包装 + event.chain_result()
  - 绝对路径，不加 file:/// 前缀
  - 删除 _upload_file_via_onebot 及其 base64 fallback

**v1.10.12** (2026-06-15)
- 🔧 容器挂载后恢复 file:// 直传路径
  - 优先用 file:// 路径直接上传（快，零内存开销）
  - 失败自动回退 base64:// 编码（容器隔离兜底）
  - 文件上限提升到 100MB

**v1.10.11** (2026-06-15)
- 🐛 回退 send_group_msg + [CQ:file]（OneBot 不支持）
  - 恢复 upload_group_file / upload_private_file
  - 群聊下载后提示「📂 文件已上传到群文件，请前往群文件查看」
  - 私聊文件直接送达

**v1.10.10** (2026-06-15)
- 🐛 修复群聊下载文件去了「群文件」而非聊天消息
  - upload_group_file → send_group_msg + [CQ:file] 消息段
  - 文件直接出现在聊天中，不再需要去群文件里翻
  - 私聊同理：upload_private_file → send_private_msg + [CQ:file]

**v1.10.9** (2026-06-15)
- 🐛 修复私聊下载文件发到群聊的 bug
  - aiocqhttp 适配器在私聊时 get_group_id() 竟然返回群号
  - 改用 MessageType.GROUP_MESSAGE 判断群聊/私聊

**v1.10.8** (2026-06-15)
- 🐛 修复文件上传「ENOENT: no such file」— 容器间文件系统隔离
  - file:// 路径需要 OneBot 客户端能直接访问文件，容器间不通
  - 改用 base64:// 编码直传文件内容，彻底绕过文件系统隔离
  - 50MB 上限保护，避免超大文件撑爆 WebSocket

**v1.10.7** (2026-06-15)
- 🐛 修复下载路径错误（ENOENT: no such file or directory）
  - 不再依赖 download_album/download_photo 返回值拼路径
  - 自己从 download_dir 构造下载目录，失败时按时间搜索
  - _pack_to_zip 改用 resolve() 确保路径正确

**v1.10.6** (2026-06-15)
- 🐛 彻底修复文件发送（Comp.File 在 aiocqhttp 不支持）
  - 改用 OneBot upload_private_file / upload_group_file API
  - 自动检测 bot 实例（多种属性路径探测）
  - 失败回退为文字提示 + 文件路径

**v1.10.5** (2026-06-15)
- 🐛 修复文件发送失败（message is empty）
  - Comp.File 使用绝对路径 resolve()
  - 添加 file:/// 前缀（OneBot 协议要求）
  - 添加发送日志便于调试

**v1.10.4** (2026-06-15)
- 🐛 修复 download_album 缺少权限检查导致 is_admin 未定义

**v1.10.3** (2026-06-15)
- 🔐 新增管理员权限控制（参考 jm_cosmos）
  - admin_only: 仅管理员可用，非白名单用户被拒
  - admin_list: 管理员 ID 列表（逗号分隔）
  - enabled_groups: 群白名单（私聊不受限）
  - daily_download_limit: 每用户每日下载配额（管理员豁免）
- jmstatus 新增显示管理员模式/配额信息

**v1.10.2** (2026-06-15)
- 📦 下载完成自动打包 ZIP 并发送文件
  - 模仿 jm_cosmos，下载后自动打包为 ZIP
  - 通过 Comp.File 直接发送文件到聊天
  - 发送后自动清理临时文件

**v1.10.1** (2026-06-15)
- 🐛 适配 jmcomic 2.7.0 API 变更
  - from_dict → construct
  - album_detail → get_album_detail
  - photo_detail → get_photo_detail
  - rank_page → day_ranking
  - favorite_folder order → order_by

**v1.10.0** (2026-06-15)
- 🎯 终极方案：pip install --target 到插件目录
  - 绕过 AstrBot 的 import hook 限制
  - 依赖安装到插件 _deps/ 目录，100% 可控
  - 用 importlib.import_module 替代 find_spec 检测

**v1.0.9** (2026-06-15)
- 🐛 终极修复：自动检测并修复 sys.path
  - 从 pip 输出提取 site-packages 路径，自动加入 sys.path
  - 解决「包装了但 Python 找不到」的经典问题

**v1.0.8** (2026-06-15)
- 🐛 修复 pip 错误信息被 root 警告覆盖
  - 添加 --root-user-action=ignore 抑制 root 警告
  - 失败时返回完整 pip stdout+stderr 而非仅最后一行

**v1.0.7** (2026-06-15)
- 🐛 修复 pip 返回成功但模块仍不可见的问题
  - pip 安装后再次 find_spec 验证，不通过则继续尝试下一个镜像
  - 显示 pip 完整输出 + sys.path 帮助定位问题
  - 区分「pip 安装失败」和「pip 成功但模块不可见」两种错误

**v1.0.6** (2026-06-15)
- 🐛 修复 pip 安装后 import 仍失败的场景
  - 第二次 import 也包在 try/except 里，显示 sys.executable 路径
  - 帮助定位「pip 装到了错误的 Python 环境」问题

**v1.0.5** (2026-06-15)
- 🐛 修复 bootstrap 安装失败被静默吞掉的问题
  - pip install 不再用 --quiet，错误输出可见
  - 安装后调用 importlib.invalidate_caches() 刷新缓存
  - 返回详细错误信息（哪个镜像、什么错误）
  - 超时从 180s 增加到 300s

**v1.0.4** (2026-06-15)
- 🐛 修复 AstrBot 解析数字 ID 为 int 导致 .strip() 报错
  - 所有命令参数统一用 str() 包裹再 .strip()

**v1.0.3** (2026-06-15)
- 🐛 修复「No module named jmcomic」加载失败
  - 改为懒加载：不在模块顶层 import jmcomic
  - 首次使用时自动触发 bootstrap 安装
  - 安装失败不会阻止插件加载，仅提示错误

**v1.0.2** (2026-06-15)
- 🔧 对齐 AstrBot 插件格式（参考 web-search 插件）
- 🏗️ 后端注入模式重构（JMBackend → FunctionTool）
- 🌐 命令支持中文别名（搜索本子、下载本子、排行榜等）
- 📊 LLM 工具输出简化，去除装饰线
- ⚙️ _conf_schema.json 扁平化，添加 min/max/hint 约束
- 🔍 JMSearchTool 新增 max_results 参数
- 📝 新增 jmchangelog 查看更新日志

**v1.0.0** (2026-06-15)
- 🎉 初始版本 — 基于 jmcomic 库的 AstrBot 插件
- ✅ 搜索/下载/排行/收藏/详情
- 🤖 jm_search / jm_download LLM 工具
- 🚀 启动自动从清华镜像装依赖
""".strip()


# ═════════════════════════ 后端 ═════════════════════════

class JMBackend:
    """JMComic API 客户端封装（类似 SearchBackend 的注入模式）"""

    def __init__(self, config: dict, data_dir: str):
        self.config = config
        self.data_dir = data_dir
        self._jmcomic = None
        self._JmOption = None
        self._JmModuleConfig = None
        self._JmApiClient = None
        self._option = None
        self._api = None
        self._setup()

    def _setup(self):
        # 懒加载 jmcomic
        self._jmcomic, self._JmOption, self._JmModuleConfig, self._JmApiClient = _import_jmcomic()

        dl_dir = os.path.join(self.data_dir, self.config.get("download_dir", "downloads"))
        os.makedirs(dl_dir, exist_ok=True)

        image_suffix = self.config.get("image_suffix", ".jpg")
        client_type = self.config.get("client_type", "api")

        option_dict = {
            "dir_rule": {"rule": "Bd_Aid", "base_dir": dl_dir},
            "download": {
                "cache": True,
                "image": {"suffix": image_suffix},
                "threading": {"batch_count": 4},
            },
            "client": {
                "domain": [],
                "retry_times": 3,
                "impl": client_type,
            },
        }

        # 用户名/密码登录
        username = self.config.get("jm_username", "")
        password = self.config.get("jm_password", "")
        if username and password:
            option_dict["client"]["username"] = username
            option_dict["client"]["password"] = password

        proxy = self.config.get("proxy", "")
        if proxy:
            option_dict["client"]["proxy"] = proxy

        if self.config.get("debug"):
            self._JmModuleConfig.DEBUG = True

        self._option = self._JmOption.construct(option_dict)
        self._api = self._option.build_jm_client()

    @property
    def option(self):
        return self._option

    @property
    def api(self):
        return self._api

    @property
    def download_dir(self) -> str:
        return os.path.join(self.data_dir, self.config.get("download_dir", "downloads"))

    def is_logged_in(self) -> bool:
        try:
            if not self._api:
                return False
            self._api.favorite_folder(page=1)
            return True
        except Exception:
            return False

    def search(self, keyword: str, page: int = 1, max_results: int = 10) -> list:
        return self._api.search_site(search_query=keyword, page=page)[:max_results]

    def get_album(self, album_id: str):
        return self._api.get_album_detail(album_id)

    def get_photo(self, photo_id: str):
        return self._api.get_photo_detail(photo_id)

    def get_rankings(self, page: int = 1) -> list:
        return self._api.day_ranking(page=page)

    def get_favorites(self, page: int = 1, order: str = "mr") -> list:
        return self._api.favorite_folder(page=page, order_by=order)

    def get_album_cover(self, album_id: str) -> str | None:
        """获取本子封面图片，返回本地文件路径。"""
        try:
            album = self._api.get_album_detail(album_id)
            cover_url = None
            
            # 从第一话的第一张图获取封面
            if album.episode_list:
                first_photo_id = album.episode_list[0][0]
                try:
                    photo = self._api.get_photo_detail(first_photo_id, fetch_album=False)
                    logger.info(f"[jmcomic_bot] get_album_cover: photo_id={first_photo_id}, "
                               f"data_original_0={photo.data_original_0}, "
                               f"data_original_domain={getattr(photo, 'data_original_domain', 'N/A')}, "
                               f"page_arr={getattr(photo, 'page_arr', 'N/A')[:3] if photo.page_arr else 'N/A'}")
                    if photo and photo.data_original_0:
                        cover_url = photo.data_original_0
                    elif photo and photo.data_original_domain and photo.page_arr:
                        # data_original_0 为 None 时，用 domain + 第一张文件名构造
                        cover_url = f"https://{photo.data_original_domain}/media/photos/{first_photo_id}/{photo.page_arr[0]}"
                except Exception as e:
                    logger.warning(f"[jmcomic_bot] 获取第一话图片失败: {e}")
            
            logger.info(f"[jmcomic_bot] get_album_cover: album_id={album_id}, cover_url={cover_url}")
            if not cover_url:
                return None
                
            # 下载封面到本地
            cover_dir = os.path.join(self.data_dir, "covers")
            os.makedirs(cover_dir, exist_ok=True)
            cover_path = os.path.join(cover_dir, f"{album_id}.jpg")
            if os.path.exists(cover_path):
                return cover_path
            import urllib.request
            # JM CDN 需要 Referer 头，否则返回 403
            domain = self._api.domain_list[0] if hasattr(self._api, 'domain_list') and self._api.domain_list else ''
            req = urllib.request.Request(cover_url, headers={
                'Referer': f'https://{domain}/' if domain else '',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            })
            with urllib.request.urlopen(req, timeout=30) as resp, open(cover_path, 'wb') as f:
                f.write(resp.read())
            return cover_path if os.path.exists(cover_path) else None
        except Exception as e:
            logger.warning(f"[jmcomic_bot] 获取封面失败: {e}")
            return None

    def download_album(self, album_id: str) -> dict:
        try:
            album = self._api.get_album_detail(album_id)
            title = album.title if hasattr(album, 'title') else album.name
            album_actual_id = album.id if hasattr(album, 'id') else album.aid if hasattr(album, 'aid') else '?'
            # page_count 有时为 0，用章节数兜底
            count = album.page_count if (hasattr(album, 'page_count') and album.page_count) else len(album)
            logger.info(f"[jmcomic_bot] JMBackend.download_album: id={album_id} → 返回 title='{title}', actual_id={album_actual_id}, page_count={getattr(album, 'page_count', 'N/A')}, len={len(album)}, 最终count={count}")
            self._option.download_album(album_id)
            # 自己构造下载路径，不依赖 download_album 返回值（可能只是相对路径）
            dl_dir = Path(self.download_dir) / album_id
            if not dl_dir.exists():
                # 兼容 jmcomic 的实际目录名（可能含标题等）
                base = Path(self.download_dir)
                for d in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                    if d.is_dir() and str(album_id) in d.name:
                        dl_dir = d
                        break
            # 如果 count 仍为 0，从实际下载的文件数量获取
            if count == 0 and dl_dir.exists():
                image_files = list(dl_dir.rglob('*'))
                count = len([f for f in image_files if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')])
            pack_result = self._pack(dl_dir, album_id, title)
            return {"status": "ok", "pack_path": str(pack_result), "path": str(dl_dir), "count": count, "title": title, "encrypted": bool(self.config.get("zip_password", ""))}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def download_photo(self, photo_id: str) -> dict:
        try:
            photo = self._api.get_photo_detail(photo_id)
            title = photo.title if hasattr(photo, 'title') else photo.name
            count = len(photo)
            self._option.download_photo(photo_id)
            dl_dir = Path(self.download_dir) / photo_id
            if not dl_dir.exists():
                base = Path(self.download_dir)
                for d in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                    if d.is_dir() and str(photo_id) in d.name:
                        dl_dir = d
                        break
            pack_result = self._pack(dl_dir, photo_id, title)
            return {"status": "ok", "pack_path": str(pack_result), "path": str(dl_dir), "count": count, "title": title, "encrypted": bool(self.config.get("zip_password", ""))}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _pack(self, source_dir: Path, item_id: str, title: str) -> Path:
        """将下载目录打包（支持 ZIP/PDF/none，AES 加密防风控）"""
        import re
        pack_format = self.config.get("pack_format", "zip")
        password = self.config.get("zip_password", "")
        show_password = self.config.get("filename_show_password", False)
        safe_title = re.sub(r'[\\/*?:"<>|]', '_', title)[:50]
        resolved = source_dir.resolve()

        # 文件名密码提示
        pw_hint = ""
        if password and show_password:
            pw_hint = f" #PW{password}"

        if pack_format == "pdf":
            return self._pack_pdf(resolved, item_id, safe_title, password, pw_hint)
        elif pack_format == "none":
            # 不打包，直接返回目录
            return resolved
        else:  # zip
            return self._pack_zip(resolved, item_id, safe_title, password, pw_hint)

    def _pack_zip(self, source_dir: Path, item_id: str, safe_title: str, password: str, pw_hint: str) -> Path:
        """打包为 ZIP"""
        zip_path = source_dir.parent / f"[{item_id}] {safe_title}{pw_hint}.zip"
        if password:
            import pyzipper
            with pyzipper.AESZipFile(zip_path, 'w',
                                     compression=pyzipper.ZIP_DEFLATED,
                                     encryption=pyzipper.WZ_AES) as zf:
                zf.setpassword(password.encode('utf-8'))
                for f in sorted(source_dir.rglob('*')):
                    if f.is_file():
                        zf.write(f, f.relative_to(source_dir))
        else:
            import zipfile
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(source_dir.rglob('*')):
                    if f.is_file():
                        zf.write(f, f.relative_to(source_dir))
        return zip_path

    def _pack_pdf(self, source_dir: Path, item_id: str, safe_title: str, password: str, pw_hint: str) -> Path:
        """打包为 PDF（使用 pymupdf）"""
        import fitz
        pdf_path = source_dir.parent / f"[{item_id}] {safe_title}{pw_hint}.pdf"
        doc = fitz.open()
        image_files = sorted(
            [f for f in source_dir.rglob('*') if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')],
            key=lambda x: x.name
        )
        for img_file in image_files:
            try:
                img = fitz.open(str(img_file))
                rect = img[0].rect if img.page_count > 0 else None
                if rect:
                    page = doc.new_page(width=rect.width, height=rect.height)
                    page.insert_image(rect, filename=str(img_file))
                img.close()
            except Exception:
                continue
        if password:
            doc.save(pdf_path, encryption=fitz.PDF_ENCRYPT_AES_256,
                     user_pw=password, owner_pw=password)
        else:
            doc.save(pdf_path)
        doc.close()
        return pdf_path


# ═════════════════════════ 格式化 ═════════════════════════

def _fmt_search_for_llm(results: list, keyword: str) -> str:
    """LLM 工具输出：纯信息，无装饰线（参考 web-search 的 _format_for_llm）"""
    if not results:
        return f'未找到关于 "{keyword}" 的搜索结果。'
    lines = [f'搜索 "{keyword}" 的结果（共 {len(results)} 条）：', '']
    for i, a in enumerate(results, 1):
        aid = a.id if hasattr(a, 'id') else a.aid
        title = (a.title if hasattr(a, 'title') else a.name)[:40]
        author = (a.author if hasattr(a, 'author') else '')[:15]
        pages = len(a) if hasattr(a, '__len__') else '?'
        lines.append(f'{i}. [{aid}] {title} — {author} ({pages}P)')
    return '\n'.join(lines)


def _fmt_search(results: list, keyword: str, page: int = 1) -> str:
    """用户命令输出：结构化带装饰"""
    if not results:
        return f"🔍 搜索「{keyword}」无结果"
    lines = [f"🔍 搜索「{keyword}」(第{page}页):", "-" * 30]
    for i, a in enumerate(results[:10], 1):
        aid = a.id if hasattr(a, 'id') else a.aid
        title = (a.title if hasattr(a, 'title') else a.name)[:40]
        author = (a.author if hasattr(a, 'author') else "")[:15]
        pages = len(a) if hasattr(a, '__len__') else "?"
        lines.append(f"{i:2d}. [{aid}] {title} — {author} ({pages}P)")
        lines.append(f"   📥 jm {aid}")
    lines.append("-" * 30)
    return "\n".join(lines)


def _fmt_album(album) -> str:
    title = album.title if hasattr(album, 'title') else album.name
    author = album.author if hasattr(album, 'author') else "未知"
    pages = album.page_count if (hasattr(album, 'page_count') and album.page_count) else (len(album) if hasattr(album, '__len__') else "?")
    lines = [f"📖 [{album.id}] {title}", f"作者: {author}", f"页数: {pages}P"]
    if hasattr(album, 'tags') and album.tags:
        tags = album.tags[:5] if isinstance(album.tags, list) else []
        if tags:
            lines.append(f"标签: {' '.join(tags)}")
    lines.append(f"\n📥 下载: jm {album.id}")
    return "\n".join(lines)


def _fmt_rank(rankings: list, page: int = 1) -> str:
    if not rankings:
        return "📊 暂无排行数据"
    lines = [f"📊 排行榜 (第{page}页):", "-" * 30]
    for i, a in enumerate(rankings[:15], 1):
        aid = a.id if hasattr(a, 'id') else a.aid
        title = (a.title if hasattr(a, 'title') else a.name)[:25]
        author = (a.author if hasattr(a, 'author') else "")[:15]
        pages = len(a) if hasattr(a, '__len__') else "?"
        lines.append(f"{i:2d}. [{aid}] {title} — {author} ({pages}P)")
    lines.append("-" * 30)
    return "\n".join(lines)


def _fmt_fav(folder, page: int = 1) -> str:
    albums = folder if isinstance(folder, list) else getattr(folder, 'content', [])
    if not albums:
        return "📌 本页无收藏"
    lines = [f"📌 收藏夹 (第{page}页):", "-" * 30]
    for i, a in enumerate(albums[:15], 1):
        aid = a.id if hasattr(a, 'id') else a.aid
        title = (a.title if hasattr(a, 'title') else a.name)[:25]
        author = (a.author if hasattr(a, 'author') else "")[:15]
        lines.append(f"{i:2d}. [{aid}] {title} — {author}")
    lines.append("-" * 30)
    return "\n".join(lines)


def _fmt_dl(result: dict) -> str:
    """用户命令输出：下载结果"""
    if result["status"] == "ok":
        msg = f"✅ 下载完成: 《{result['title']}》\n📄 共 {result['count']} 张图片"
        if result.get("encrypted"):
            msg += "\n🔐 已加密"
        return msg
    return f"❌ 下载失败: {result.get('error', '未知错误')}"


def _fmt_dl_for_llm(result: dict) -> str:
    """LLM 工具输出：下载结果纯文本（参考 web-search 的 _format_for_llm）"""
    if result["status"] == "ok":
        return f'下载完成：《{result["title"]}》共 {result["count"]} 张图片，路径 {result["path"]}'
    return f'下载失败：{result.get("error", "未知错误")}'


# ═════════════════════════ LLM 函数工具 ═════════════════════════

@dataclass
class JMSearchTool(FunctionTool):
    """AI 可调用搜索禁漫天堂"""
    backend: JMBackend = field(repr=False, default=None)
    plugin: object = field(repr=False, default=None)  # JMComicBot 实例引用
    name: str = "jm_search"
    description: str = (
        "搜索禁漫天堂（JMComic）的本子。当用户想找某类漫画、本子时使用此工具。"
        "返回本子ID、标题、作者、页数等信息。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果数量，1-10，默认10",
                    "default": 10,
                },
            },
            "required": ["keyword"],
        }
    )

    async def run(self, event: AstrMessageEvent, keyword: str, max_results: int = 10) -> str:
        if not self.backend:
            return "JMComic 客户端未初始化"
        # 权限检查
        if self.plugin:
            ok, err = self.plugin._check_permission(event)
            if not ok:
                return err
        try:
            max_r = max(1, min(max_results, 10))
            logger.info(f"[jmcomic_bot] LLM 调用搜索: '{keyword}' (max={max_r})")
            results = await asyncio.to_thread(self.backend.search, keyword, max_results=max_r)
            return _fmt_search_for_llm(results, keyword)
        except Exception as e:
            return f"搜索失败: {e}"


@dataclass
class JMDownloadTool(FunctionTool):
    """AI 可调用下载本子"""
    backend: JMBackend = field(repr=False, default=None)
    plugin: object = field(repr=False, default=None)  # JMComicBot 实例引用
    name: str = "jm_download"
    description: str = (
        "下载禁漫天堂（JMComic）的本子。当用户明确要求下载某个本子时使用此工具。"
        "需要提供本子ID。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "album_id": {
                    "type": "string",
                    "description": "本子ID，如「123456」，可从搜索结果中获取",
                },
            },
            "required": ["album_id"],
        }
    )

    async def run(self, event: AstrMessageEvent, album_id: str) -> str:
        if not self.backend:
            return "JMComic 客户端未初始化"
        try:
            album_id = str(album_id).strip()
            # 权限检查
            if self.plugin:
                ok, err = self.plugin._check_permission(event)
                if not ok:
                    return err
                user_id = event.get_sender_id()
                is_admin = self.plugin._is_admin(user_id)
                if not is_admin:
                    can_dl, used = self.plugin._check_quota(user_id)
                    if not can_dl:
                        return f"❌ 今日下载次数已用完 ({used}/{self.plugin._daily_limit})，明天再试"

            logger.info(f"[jmcomic_bot] LLM 调用下载: {album_id}")
            result = await asyncio.to_thread(self.backend.download_album, album_id)

            if result["status"] == "ok" and self.plugin:
                # 消耗配额
                if not is_admin and self.plugin._daily_limit > 0:
                    self.plugin._consume_quota(user_id)
                # 上传文件
                pack_path = result.get("pack_path", "")
                if pack_path and Path(pack_path).exists():
                    abs_path = str(Path(pack_path).resolve())
                    file_name = Path(pack_path).name
                    logger.info(f"[jmcomic_bot] LLM下载: 上传文件 {abs_path}")
                    sent = await self.plugin._upload_file_via_onebot(event, abs_path, file_name)
                    if sent:
                        logger.info(f"[jmcomic_bot] LLM下载: 文件已发送")
                    else:
                        logger.warning(f"[jmcomic_bot] LLM下载: 文件发送失败")
                    # 清理
                    if self.plugin.config.get("auto_delete_after_send", True):
                        try:
                            import shutil
                            shutil.rmtree(result["path"], ignore_errors=True)
                            Path(pack_path).unlink(missing_ok=True)
                        except Exception:
                            pass

            return _fmt_dl_for_llm(result)
        except Exception as e:
            return f"下载失败: {e}"


# ═════════════════════════ 插件 ═════════════════════════

@register(
    "astrbot_plugin_jmcomic_bot",
    "custom",
    "禁漫天堂漫画下载插件 — 搜索/下载/排行/收藏，基于 jmcomic 库",
    "1.11.2",
    "https://github.com/jujg12123/astrbot_plugin_jmcomic_bot",
)
class JMComicBot(Star):
    """JMComic Bot 插件"""

    def __init__(self, context: Context, config: AstrBotConfig | dict | None = None):
        super().__init__(context)

        config = config or {}
        self.config = config
        self._downloading: set = set()
        self._backend_error: str = ""

        try:
            self.data_dir = Path("data") / "jmcomic_bot"
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.data_dir = Path(__file__).parent / "data"
            self.data_dir.mkdir(parents=True, exist_ok=True)

        # 初始化后端（懒加载 jmcomic，失败不阻止插件加载）
        self._backend = None
        try:
            self._backend = JMBackend(self.config, str(self.data_dir))
        except Exception as e:
            self._backend_error = str(e)
            logger.warning(f"[jmcomic_bot] 后端初始化失败: {e}")

        # 注册 LLM 工具（即使 backend 为 None 也注册，工具会返回友好提示）
        self._search_tool = JMSearchTool(backend=self._backend, plugin=self)
        self._download_tool = JMDownloadTool(backend=self._backend, plugin=self)
        context.add_llm_tools(self._search_tool)
        context.add_llm_tools(self._download_tool)

        if self._backend:
            logged_in = self._backend.is_logged_in()
            proxy = self.config.get("proxy", "")
            logger.info(
                f"[jmcomic_bot] v1.11.2 已就绪 | 已登录={logged_in} | "
                f"代理={'已设置' if proxy else '无'}"
            )
        else:
            logger.warning(
                f"[jmcomic_bot] v1.11.2 已加载（降级模式）| 错误: {self._backend_error}"
            )

        # 权限与配额
        self._admin_only: bool = self.config.get("admin_only", False)
        self._admin_list: set = {s.strip() for s in self.config.get("admin_list", "").split(",") if s.strip()}
        self._enabled_groups: set = {s.strip() for s in self.config.get("enabled_groups", "").split(",") if s.strip()}
        self._daily_limit: int = int(self.config.get("daily_download_limit", 0))
        self._quota: dict = {}  # {user_id: {"date": str, "count": int}}

    async def _upload_file_via_onebot(self, event: AstrMessageEvent, file_path: str, file_name: str) -> bool:
        """通过 OneBot upload API 上传文件（base64 编码）。
        Comp.File 在 aiocqhttp 适配器（SnowLuma/NapCat）中均不支持。
        成功返回 True，失败返回 False。"""
        import base64
        import os

        if not os.path.exists(file_path):
            logger.warning(f"[jmcomic_bot] 文件不存在: {file_path}")
            return False
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            logger.warning(f"[jmcomic_bot] 文件为空: {file_path}")
            return False
        if file_size > 50 * 1024 * 1024:
            logger.warning(f"[jmcomic_bot] 文件过大 ({file_size/1024/1024:.1f}MB)，跳过上传")
            return False

        try:
            with open(file_path, 'rb') as f:
                file_data = base64.b64encode(f.read()).decode('ascii')
        except Exception as e:
            logger.warning(f"[jmcomic_bot] 读取文件失败: {e}")
            return False

        file_uri = f"base64://{file_data}"

        bot = None
        for attr_name in dir(event):
            if attr_name.startswith('__'):
                continue
            try:
                val = getattr(event, attr_name, None)
                if val is not None and hasattr(val, 'call_action'):
                    bot = val
                    break
            except Exception:
                continue

        if bot is None:
            logger.warning("[jmcomic_bot] 未找到 bot 实例")
            return False

        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        msg_type = str(getattr(event.message_obj, 'type', '')).lower()
        is_group = 'group' in msg_type

        try:
            if is_group and group_id:
                await bot.call_action('upload_group_file',
                    group_id=int(group_id), file=file_uri, name=file_name)
            else:
                await bot.call_action('upload_private_file',
                    user_id=int(user_id), file=file_uri, name=file_name)
            logger.info(f"[jmcomic_bot] ✅ 文件上传成功: {file_name}")
            return True
        except Exception as e:
            logger.warning(f"[jmcomic_bot] ❌ 文件上传失败: {e}")
            return False

    async def _send_with_recall(self, event: AstrMessageEvent, chain: MessageChain, delay: int):
        """发送消息并在 delay 秒后自动撤回"""
        bot = None
        message_id = None

        # 方法1：通过 event.bot 的 OneBot API 发送（可获取 message_id）
        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            bot = getattr(event, 'bot', None)
            if bot and hasattr(bot, 'send_private_msg'):
                is_group = bool(event.get_group_id())
                session_id_str = event.get_group_id() if is_group else event.get_sender_id()
                if session_id_str and str(session_id_str).isdigit():
                    session_id = int(session_id_str)
                    messages = await AiocqhttpMessageEvent._parse_onebot_json(chain)
                    if messages:
                        if is_group:
                            result = await bot.send_group_msg(group_id=session_id, message=messages)
                        else:
                            result = await bot.send_private_msg(user_id=session_id, message=messages)
                        message_id = result.get("message_id") if isinstance(result, dict) else None
                        logger.info(f"[jmcomic_bot] OneBot 发送成功, message_id={message_id}")
        except Exception as e:
            logger.warning(f"[jmcomic_bot] OneBot 发送失败: {e}")

        # 方法2：如果 OneBot 没拿到 message_id，用 event.send() 兜底
        if message_id is None:
            try:
                result = await event.send(chain)
                if isinstance(result, dict):
                    message_id = result.get('message_id')
                elif hasattr(result, 'message_id'):
                    message_id = result.message_id
                logger.info(f"[jmcomic_bot] event.send 完成, result type={type(result).__name__}, message_id={message_id}")
            except Exception as e:
                logger.warning(f"[jmcomic_bot] event.send 失败: {e}")

        # 安排撤回
        if message_id and delay > 0:
            if bot is None:
                bot = getattr(event, 'bot', None)
            if bot:
                asyncio.create_task(self._delayed_recall(bot, message_id, delay))
                logger.info(f"[jmcomic_bot] 已安排消息 {message_id} 在 {delay}s 后撤回")
            else:
                logger.warning(f"[jmcomic_bot] 未找到 bot 实例，无法撤回 message_id={message_id}")
        elif message_id is None:
            logger.warning("[jmcomic_bot] 无法获取 message_id，撤回不可用")

    async def _delayed_recall(self, bot, message_id: int, delay: int):
        """后台任务：延迟撤回消息"""
        await asyncio.sleep(delay)
        try:
            await bot.call_action("delete_msg", message_id=message_id)
            logger.info(f"[jmcomic_bot] ✅ 已撤回消息 {message_id}")
        except Exception as e:
            logger.warning(f"[jmcomic_bot] 撤回消息 {message_id} 失败: {e}")

    def _is_admin(self, user_id: str) -> bool:
        """判断用户是否为管理员（admin_only=False 时所有人视为管理员）"""
        if not self._admin_only:
            return True
        return str(user_id) in self._admin_list

    def _check_group(self, group_id: str) -> bool:
        """判断群是否在白名单（空集合=全部允许，私聊 group_id 为空也允许）"""
        if not group_id or not self._enabled_groups:
            return True
        return str(group_id) in self._enabled_groups

    def _check_quota(self, user_id: str) -> tuple[bool, int]:
        """检查用户今日下载配额，返回 (是否允许, 已用次数)"""
        if self._daily_limit <= 0:
            return True, 0
        today = __import__("datetime").date.today().isoformat()
        rec = self._quota.get(user_id)
        if rec and rec["date"] == today:
            return rec["count"] < self._daily_limit, rec["count"]
        return True, 0

    def _consume_quota(self, user_id: str):
        """消耗一次下载配额"""
        if self._daily_limit <= 0:
            return
        today = __import__("datetime").date.today().isoformat()
        rec = self._quota.get(user_id)
        if rec and rec["date"] == today:
            rec["count"] += 1
        else:
            self._quota[user_id] = {"date": today, "count": 1}

    def _check_permission(self, event: AstrMessageEvent) -> tuple[bool, str]:
        """统一权限检查，返回 (ok, error_msg)"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        if not self._is_admin(user_id):
            return False, "🚫 该功能仅限管理员使用"
        if group_id and not self._check_group(group_id):
            return False, "🚫 本插件未在此群启用"
        return True, ""

    async def terminate(self):
        """插件卸载时清理"""
        self.context.provider_manager.llm_tools.remove_func(self._search_tool.name)
        self.context.provider_manager.llm_tools.remove_func(self._download_tool.name)
        logger.info("[jmcomic_bot] 已卸载")

    # ==================== 帮助 ====================
    @filter.command("jmhelp", alias={"jm帮助"}, description="显示帮助信息")
    async def help_command(self, event: AstrMessageEvent):
        status_line = "✅ 正常" if self._backend else f"⚠️ 降级模式 ({self._backend_error})"
        yield event.plain_result(
            f"🍶 **JMComic Bot v1.11.2**\n"
            f"状态: {status_line}\n\n"
            "📥 `jm <id>` — 下载整本本子\n"
            "📥 `jmc <id>` — 下载单个章节\n"
            "🔍 `jms <关键词>` — 搜索本子\n"
            "ℹ️  `jmi <id>` — 查看本子详情\n"
            "📊 `jmrank [页码]` — 排行榜\n"
            "📌 `jmfav [页码]` — 收藏夹（需登录）\n"
            "🔑 `jmlogin` — 登录说明\n"
            "📊 `jmstatus` — 插件状态\n"
            "📝 `jmchangelog` — 更新日志\n\n"
            "💡 AI 也可直接说「帮我搜个火影本子」"
        )

    # ==================== 更新日志 ====================
    @filter.command("jmchangelog", alias={"更新日志", "jm日志"}, description="显示更新日志")
    async def changelog(self, event: AstrMessageEvent):
        yield event.plain_result(CHANGELOG)

    # ==================== 下载本子 ====================
    @filter.command("jm", alias={"下载本子", "下载漫画"}, description="下载整本本子，用法: jm <ID>")
    async def download_album(self, event: AstrMessageEvent, album_id: GreedyStr = None):
        ok, err = self._check_permission(event)
        if not ok:
            yield event.plain_result(err)
            return
        user_id = event.get_sender_id()
        is_admin = self._is_admin(user_id)
        if not is_admin:
            can_dl, used = self._check_quota(user_id)
            if not can_dl:
                yield event.plain_result(f"❌ 今日下载次数已用完 ({used}/{self._daily_limit})，明天再试")
                return
        # 从 GreedyStr 参数提取 album_id，失败时从原始消息手动解析
        album_id = str(album_id or "").strip()
        if not album_id:
            raw_msg = getattr(event, 'message_str', '') or getattr(event, 'text', '') or ''
            parts = str(raw_msg).strip().split(maxsplit=1)
            if len(parts) > 1:
                album_id = parts[1].strip()
        logger.info(f"[jmcomic_bot] jm 命令收到 album_id='{album_id}'")
        if not album_id:
            yield event.plain_result("❌ 用法: jm <本子ID>")
            return
        if not self._backend:
            yield event.plain_result(f"❌ JMComic 客户端未初始化\n详情: {self._backend_error}")
            return
        if album_id in self._downloading:
            yield event.plain_result("⏳ 正在下载中，请稍候...")
            return

        self._downloading.add(album_id)
        try:
            yield event.plain_result(f"📥 开始下载本子 {album_id}...")

            # 封面预览
            if self.config.get("send_cover_preview", True):
                cover_path = await asyncio.to_thread(self._backend.get_album_cover, album_id)
                if cover_path:
                    cover_chain = MessageChain([Comp.Image(file=cover_path)])
                    if self.config.get("cover_recall_enabled", False):
                        await self._send_with_recall(event, cover_chain, self.config.get("auto_recall_delay", 60))
                    else:
                        yield event.chain_result(cover_chain.chain)

            album = await asyncio.to_thread(self._backend.get_album, album_id)
            title = album.title if hasattr(album, 'title') else album.name
            page_count = album.page_count if (hasattr(album, 'page_count') and album.page_count) else len(album)
            yield event.plain_result(f"📖 《{title}》共 {page_count}P，下载中...")
            result = await asyncio.to_thread(self._backend.download_album, album_id)
            result_msg = _fmt_dl(result)
            if result["status"] == "ok":
                # 消耗配额
                if not is_admin and self._daily_limit > 0:
                    self._consume_quota(user_id)
                pack_path = result.get("pack_path", "")
                if pack_path and Path(pack_path).exists():
                    abs_path = str(Path(pack_path).resolve())
                    file_name = Path(pack_path).name
                    logger.info(f"[jmcomic_bot] 上传文件: {abs_path}")
                    sent = await self._upload_file_via_onebot(event, abs_path, file_name)
                    if sent:
                        yield event.plain_result(result_msg)
                    else:
                        yield event.plain_result(result_msg + f"\n📁 文件已保存: {abs_path}")
                    # 清理
                    if self.config.get("auto_delete_after_send", True):
                        try:
                            import shutil
                            shutil.rmtree(result["path"], ignore_errors=True)
                            Path(pack_path).unlink(missing_ok=True)
                        except Exception:
                            pass
                else:
                    yield event.plain_result(result_msg + f"\n📁 {result.get('path', '')}")
            else:
                yield event.plain_result(result_msg)
        except Exception as e:
            yield event.plain_result(f"❌ 下载失败: {e}")
        finally:
            self._downloading.discard(album_id)

    # ==================== 下载章节 ====================
    @filter.command("jmc", alias={"下载章节"}, description="下载单个章节，用法: jmc <ID>")
    async def download_photo(self, event: AstrMessageEvent, photo_id: str = None):
        ok, err = self._check_permission(event)
        if not ok:
            yield event.plain_result(err)
            return
        # 配额检查
        user_id = event.get_sender_id()
        is_admin = self._is_admin(user_id)
        if not is_admin:
            can_dl, used = self._check_quota(user_id)
            if not can_dl:
                yield event.plain_result(f"❌ 今日下载次数已用完 ({used}/{self._daily_limit})，明天再试")
                return
        photo_id = str(photo_id or "").strip()
        if not photo_id:
            raw_msg = getattr(event, 'message_str', '') or getattr(event, 'text', '') or ''
            parts = str(raw_msg).strip().split(maxsplit=1)
            if len(parts) > 1:
                photo_id = parts[1].strip()
        logger.info(f"[jmcomic_bot] jmc 命令收到 photo_id='{photo_id}'")
        if not photo_id:
            yield event.plain_result("❌ 用法: jmc <章节ID>")
            return
        if not self._backend:
            yield event.plain_result(f"❌ JMComic 客户端未初始化\n详情: {self._backend_error}")
            return
        try:
            yield event.plain_result(f"📥 开始下载章节 {photo_id}...")
            result = await asyncio.to_thread(self._backend.download_photo, photo_id)
            result_msg = _fmt_dl(result)
            if result["status"] == "ok":
                # 消耗配额
                if not is_admin and self._daily_limit > 0:
                    self._consume_quota(user_id)
                pack_path = result.get("pack_path", "")
                if pack_path and Path(pack_path).exists():
                    abs_path = str(Path(pack_path).resolve())
                    file_name = Path(pack_path).name
                    logger.info(f"[jmcomic_bot] 上传文件: {abs_path}")
                    sent = await self._upload_file_via_onebot(event, abs_path, file_name)
                    if sent:
                        yield event.plain_result(result_msg)
                    else:
                        yield event.plain_result(result_msg + f"\n📁 文件已保存: {abs_path}")
                    # 清理
                    if self.config.get("auto_delete_after_send", True):
                        try:
                            import shutil
                            shutil.rmtree(result["path"], ignore_errors=True)
                            Path(pack_path).unlink(missing_ok=True)
                        except Exception:
                            pass
                else:
                    yield event.plain_result(result_msg + f"\n📁 {result.get('path', '')}")
            else:
                yield event.plain_result(result_msg)
        except Exception as e:
            yield event.plain_result(f"❌ 下载失败: {e}")

    # ==================== 搜索 ====================
    @filter.command("jms", alias={"搜索本子", "搜本子", "搜漫画"}, description="搜索本子，用法: jms <关键词>")
    async def search(self, event: AstrMessageEvent, keyword: GreedyStr):
        ok, err = self._check_permission(event)
        if not ok:
            yield event.plain_result(err)
            return
        keyword = str(keyword or "").strip()
        if not keyword:
            raw_msg = getattr(event, 'message_str', '') or getattr(event, 'text', '') or ''
            parts = str(raw_msg).strip().split(maxsplit=1)
            if len(parts) > 1:
                keyword = parts[1].strip()
        logger.info(f"[jmcomic_bot] jms 命令收到 keyword='{keyword}'")
        if not keyword:
            yield event.plain_result("❌ 用法: jms <关键词>")
            return
        if not self._backend:
            yield event.plain_result(f"❌ JMComic 客户端未初始化\n详情: {self._backend_error}")
            return
        try:
            yield event.plain_result(f"🔍 搜索中: {keyword}...")
            results = await asyncio.to_thread(self._backend.search, keyword)
            yield event.plain_result(_fmt_search(results, keyword))
        except Exception as e:
            yield event.plain_result(f"❌ 搜索失败: {e}")

    # ==================== 详情 ====================
    @filter.command("jmi", alias={"本子详情", "查看本子", "漫画详情"}, description="查看本子详细信息，用法: jmi <ID>")
    async def info(self, event: AstrMessageEvent, album_id: str = None):
        ok, err = self._check_permission(event)
        if not ok:
            yield event.plain_result(err)
            return
        album_id = str(album_id or "").strip()
        if not album_id:
            raw_msg = getattr(event, 'message_str', '') or getattr(event, 'text', '') or ''
            parts = str(raw_msg).strip().split(maxsplit=1)
            if len(parts) > 1:
                album_id = parts[1].strip()
        logger.info(f"[jmcomic_bot] jmi 命令收到 album_id='{album_id}'")
        if not album_id:
            yield event.plain_result("❌ 用法: jmi <本子ID>")
            return
        if not self._backend:
            yield event.plain_result(f"❌ JMComic 客户端未初始化\n详情: {self._backend_error}")
            return
        try:
            album = await asyncio.to_thread(self._backend.get_album, album_id)
            yield event.plain_result(_fmt_album(album))
        except Exception as e:
            yield event.plain_result(f"❌ 获取详情失败: {e}")

    # ==================== 排行榜 ====================
    @filter.command("jmrank", alias={"排行榜", "本子排行", "jm排行"}, description="查看排行榜，用法: jmrank [页码]")
    async def ranking(self, event: AstrMessageEvent, page: str = "1"):
        ok, err = self._check_permission(event)
        if not ok:
            yield event.plain_result(err)
            return
        if not self._backend:
            yield event.plain_result(f"❌ JMComic 客户端未初始化\n详情: {self._backend_error}")
            return
        page = str(page or "").strip() or "1"
        try:
            page_num = int(page) if page.isdigit() else 1
            yield event.plain_result(f"📊 获取排行榜 (第{page_num}页)...")
            rankings = await asyncio.to_thread(self._backend.get_rankings, page_num)
            yield event.plain_result(_fmt_rank(rankings, page_num))
        except Exception as e:
            yield event.plain_result(f"❌ 获取排行失败: {e}")

    # ==================== 收藏夹 ====================
    @filter.command("jmfav", alias={"收藏夹", "我的收藏", "jm收藏"}, description="查看收藏夹（需登录），用法: jmfav [页码]")
    async def favorites(self, event: AstrMessageEvent, page: str = "1"):
        ok, err = self._check_permission(event)
        if not ok:
            yield event.plain_result(err)
            return
        if not self._backend:
            yield event.plain_result(f"❌ JMComic 客户端未初始化\n详情: {self._backend_error}")
            return
        if not self._backend.is_logged_in():
            yield event.plain_result("❌ 未登录，请先配置 Cookie")
            return
        page = str(page or "").strip() or "1"
        try:
            page_num = int(page) if page.isdigit() else 1
            yield event.plain_result(f"📌 获取收藏夹 (第{page_num}页)...")
            folder = await asyncio.to_thread(self._backend.get_favorites, page_num)
            yield event.plain_result(_fmt_fav(folder, page_num))
        except Exception as e:
            yield event.plain_result(f"❌ 获取收藏夹失败: {e}")

    # ==================== 登录/登出 ====================
    @filter.command("jmlogin", alias={"登录说明", "jm登录", "账号设置"}, description="显示登录/账号设置说明")
    async def login(self, event: AstrMessageEvent):
        yield event.plain_result(
            "🔑 **登录说明**\n\n"
            "在 AstrBot 插件配置中填写：\n"
            "  • `jm_username` — JMComic 账号用户名\n"
            "  • `jm_password` — JMComic 账号密码\n\n"
            "登录后解锁收藏夹等功能。\n"
            "⚠️ 密码涉及隐私，请勿泄露！"
        )

    # ==================== 状态 ====================
    @filter.command("jmstatus", alias={"jm状态", "插件状态", "jm信息"}, description="显示插件运行状态")
    async def status(self, event: AstrMessageEvent):
        if self._backend:
            backend_ok = True
            logged_in = self._backend.is_logged_in()
            dl_dir = self._backend.download_dir
        else:
            backend_ok = False
            logged_in = False
            dl_dir = "N/A"
        user_id = event.get_sender_id()
        is_admin = self._is_admin(user_id)
        quota_info = "不限"
        if self._daily_limit > 0 and not is_admin:
            _, used = self._check_quota(user_id)
            quota_info = f"{used}/{self._daily_limit}"
        admin_mode = f"{'✅ 开启' if self._admin_only else '❌ 关闭'}"
        pack_fmt = self.config.get("pack_format", "zip")
        img_fmt = self.config.get("image_suffix", ".jpg")
        cli_type = self.config.get("client_type", "api")
        encrypted = "✅ 是" if self.config.get("zip_password", "") else "❌ 否"
        cover = "✅ 是" if self.config.get("send_cover_preview", True) else "❌ 否"
        recall = f"✅ {self.config.get('auto_recall_delay', 60)}s" if self.config.get("auto_recall_enabled", False) else "❌ 否"
        cover_recall = "✅ 是" if self.config.get("cover_recall_enabled", False) else "❌ 否"
        yield event.plain_result(
            "🍶 **JMComic Bot 状态**\n"
            f"客户端: {'✅ 正常' if backend_ok else '❌ 异常'}\n"
            f"登录状态: {'✅ 已登录' if logged_in else '❌ 未登录'}\n"
            f"下载目录: {dl_dir}\n"
            f"正在下载: {len(self._downloading)} 个任务\n"
            f"客户端类型: {cli_type}\n"
            f"图片格式: {img_fmt}\n"
            f"打包格式: {pack_fmt}\n"
            f"加密: {encrypted}\n"
            f"封面预览: {cover}\n"
            f"文件撤回: {recall}\n"
            f"封面撤回: {cover_recall}\n"
            f"管理员模式: {admin_mode}\n"
            f"是否管理员: {'✅ 是' if is_admin else '❌ 否'}\n"
            f"今日配额: {quota_info}\n"
            f"代理: {self.config.get('proxy') or '无'}\n"
            f"LLM工具: jm_search / jm_download"
            + (f"\n\n⚠️ 错误: {self._backend_error}" if self._backend_error else "")
        )