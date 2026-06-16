# 📋 JMComic Bot 更新日志

## v1.11.2 (2026-06-16)

- 🐛 修复封面预览不发送：`JmAlbumDetail` 无 `cover_url` 属性
  - 从第一话第一张图获取（`data_original_0`）
  - `data_original_0` 为 None 时用 `data_original_domain` + `page_arr[0]` 构造 URL
  - 封面下载添加 Referer 头防 403
- 🐛 修复封面自动撤回不生效
  - 改用 OneBot API 直接发送 + `delete_msg` 撤回（参考 jm_cosmos）
  - `event.send()` 兜底
- 🐛 修复页数不准确：`len(album)` 返回章节数，`album.page_count` 有时为 0
  - 优先 `page_count > 0`，回退 `len(album)`，下载后从实际文件数校准
- 🐛 修复 PDF 加密保存报错：`user_password` → `user_pw`（pymupdf 标准参数名）
- 🐛 修复不同 ID 返回相同内容：所有命令添加手动消息解析 fallback + 日志
- 🐛 修复搜索报错 `'tuple' object has no attribute 'aid'`
- 🐛 修复搜索结果显示 dict repr 而非标题：`_extract_item_info` 增加 dict 类型兼容
- 🔗 metadata.yaml repo 更新为 https://github.com/jujg12123/astrbot_plugin_jmcomic_bot
- 👤 git 提交作者修正为 jujg12123
  - 所有命令添加手动消息文本解析 fallback（防止 GreedyStr/str 参数绑定失败）
  - 所有命令添加 `logger.info` 日志记录收到的参数
  - JMBackend.download_album 添加日志记录 API 实际返回的 album ID（用于排查 API 缓存）
  - 封面召回（`cover_recall_enabled`）改用 `asyncio.create_task` 后台任务
  - 修复 `_send_with_recall` 因 async generator 被 `await` 导致永不执行的 bug

## v1.11.0 (2026-06-16)

- ✨ 大量新功能（参考 jm_cosmos）：
  - 📷 图片格式选择（`.jpg` / `.png` / `.webp`）
  - 📱 客户端类型选择（`api` / `html`）
  - 📦 打包格式选择（`zip` / `pdf` / `none`）
  - 🔑 文件名显示密码提示（`#PWxxx`）
  - 🖼️ 发送封面预览
  - ⏱️ 封面消息自动撤回（可配置延迟）
  - ⏱️ 文件消息自动撤回（可配置延迟）
  - 👤 用户名/密码登录（替代 Cookie）

## v1.10.17 (2026-06-16)

- 🐛 LLM 工具调用下载后自动发送文件（之前只提示下载完成，不发送）
- 🔐 LLM 工具（`jm_search` / `jm_download`）加入权限/配额/群白名单检查

## v1.10.16 (2026-06-16)

- 📝 所有命令添加 `description` 描述（AstrBot UI 可显示指令功能）
- 🔗 更新仓库地址为 jujg12123/astrbot_plugin_jmcomic_bot

## v1.10.15 (2026-06-16)

- 🔐 新增 ZIP AES-256 加密防风控（仿 jm_cosmos）
  - 配置 `zip_password` 后使用 pyzipper AES 加密
  - 腾讯无法扫描加密内容，防止压缩包被风控
  - 不解密直接打开会提示密码错误

## v1.10.14 (2026-06-15)

- 🐛 Comp.File 在 aiocqhttp 上根本不支持（SnowLuma/NapCat 都不行）
  - 回退到 `upload_private_file`/`upload_group_file` + base64
  - 用 MessageType 判断群聊/私聊，不再依赖 `get_group_id`
  - 私聊(c2c)走 `upload_private_file` 直接送达

## v1.10.13 (2026-06-15)

- 🔄 回退到 Comp.File + MessageChain 方案（仿 jm_cosmos）
  - 使用 MessageChain 包装 + `event.chain_result()`
  - 绝对路径，不加 `file:///` 前缀
  - 删除 `_upload_file_via_onebot` 及其 base64 fallback

## v1.10.12 (2026-06-15)

- 🔧 容器挂载后恢复 `file://` 直传路径
  - 优先用 `file://` 路径直接上传（快，零内存开销）
  - 失败自动回退 `base64://` 编码（容器隔离兜底）
  - 文件上限提升到 100MB

## v1.10.11 (2026-06-15)

- 🐛 回退 `send_group_msg` + `[CQ:file]`（OneBot 不支持）
  - 恢复 `upload_group_file` / `upload_private_file`
  - 群聊下载后提示「📂 文件已上传到群文件，请前往群文件查看」
  - 私聊文件直接送达

## v1.10.10 (2026-06-15)

- 🐛 修复群聊下载文件去了「群文件」而非聊天消息
  - `upload_group_file` → `send_group_msg` + `[CQ:file]` 消息段
  - 文件直接出现在聊天中，不再需要去群文件里翻
  - 私聊同理：`upload_private_file` → `send_private_msg` + `[CQ:file]`

## v1.10.9 (2026-06-15)

- 🐛 修复私聊下载文件发到群聊的 bug
  - aiocqhttp 适配器在私聊时 `get_group_id()` 竟然返回群号
  - 改用 `MessageType.GROUP_MESSAGE` 判断群聊/私聊

## v1.10.8 (2026-06-15)

- 🐛 修复文件上传「ENOENT: no such file」— 容器间文件系统隔离
  - `file://` 路径需要 OneBot 客户端能直接访问文件，容器间不通
  - 改用 `base64://` 编码直传文件内容，彻底绕过文件系统隔离
  - 50MB 上限保护，避免超大文件撑爆 WebSocket

## v1.10.7 (2026-06-15)

- 🐛 修复下载路径错误（ENOENT: no such file or directory）
  - 不再依赖 `download_album`/`download_photo` 返回值拼路径
  - 自己从 `download_dir` 构造下载目录，失败时按时间搜索
  - `_pack_to_zip` 改用 `resolve()` 确保路径正确

## v1.10.6 (2026-06-15)

- 🐛 彻底修复文件发送（Comp.File 在 aiocqhttp 不支持）
  - 改用 OneBot `upload_private_file` / `upload_group_file` API
  - 自动检测 bot 实例（多种属性路径探测）
  - 失败回退为文字提示 + 文件路径

## v1.10.5 (2026-06-15)

- 🐛 修复文件发送失败（message is empty）
  - `Comp.File` 使用绝对路径 `resolve()`
  - 添加 `file:///` 前缀（OneBot 协议要求）
  - 添加发送日志便于调试

## v1.10.4 (2026-06-15)

- 🐛 修复 `download_album` 缺少权限检查导致 `is_admin` 未定义

## v1.10.3 (2026-06-15)

- 🔐 新增管理员权限控制（参考 jm_cosmos）
  - `admin_only`: 仅管理员可用，非白名单用户被拒
  - `admin_list`: 管理员 ID 列表（逗号分隔）
  - `enabled_groups`: 群白名单（私聊不受限）
  - `daily_download_limit`: 每用户每日下载配额（管理员豁免）
- `jmstatus` 新增显示管理员模式/配额信息

## v1.10.2 (2026-06-15)

- 📦 下载完成自动打包 ZIP 并发送文件
  - 模仿 jm_cosmos，下载后自动打包为 ZIP
  - 通过 `Comp.File` 直接发送文件到聊天
  - 发送后自动清理临时文件

## v1.10.1 (2026-06-15)

- 🐛 适配 jmcomic 2.7.0 API 变更
  - `from_dict` → `construct`
  - `album_detail` → `get_album_detail`
  - `photo_detail` → `get_photo_detail`
  - `rank_page` → `day_ranking`
  - `favorite_folder` order → `order_by`

## v1.10.0 (2026-06-15)

- 🎯 终极方案：pip install --target 到插件目录
  - 绕过 AstrBot 的 import hook 限制
  - 依赖安装到插件 `_deps/` 目录，100% 可控
  - 用 `importlib.import_module` 替代 `find_spec` 检测

## v1.0.9 (2026-06-15)

- 🐛 终极修复：自动检测并修复 sys.path
  - 从 pip 输出提取 site-packages 路径，自动加入 sys.path
  - 解决「包装了但 Python 找不到」的经典问题

## v1.0.8 (2026-06-15)

- 🐛 修复 pip 错误信息被 root 警告覆盖
  - 添加 `--root-user-action=ignore` 抑制 root 警告
  - 失败时返回完整 pip stdout+stderr 而非仅最后一行

## v1.0.7 (2026-06-15)

- 🐛 修复 pip 返回成功但模块仍不可见的问题
  - pip 安装后再次 `find_spec` 验证，不通过则继续尝试下一个镜像
  - 显示 pip 完整输出 + sys.path 帮助定位问题
  - 区分「pip 安装失败」和「pip 成功但模块不可见」两种错误

## v1.0.6 (2026-06-15)

- 🐛 修复 pip 安装后 import 仍失败的场景
  - 第二次 import 也包在 try/except 里，显示 sys.executable 路径
  - 帮助定位「pip 装到了错误的 Python 环境」问题

## v1.0.5 (2026-06-15)

- 🐛 修复 bootstrap 安装失败被静默吞掉的问题
  - pip install 不再用 `--quiet`，错误输出可见
  - 安装后调用 `importlib.invalidate_caches()` 刷新缓存
  - 返回详细错误信息（哪个镜像、什么错误）
  - 超时从 180s 增加到 300s

## v1.0.4 (2026-06-15)

- 🐛 修复 AstrBot 解析数字 ID 为 int 导致 `.strip()` 报错
  - 所有命令参数统一用 `str()` 包裹再 `.strip()`

## v1.0.0 (2026-06-15)

- 🎉 初始版本
  - 搜索、下载、排行、收藏夹功能
  - LLM 工具 `jm_search` / `jm_download`
  - 自动安装依赖（清华源 → 阿里源 → 官方源）