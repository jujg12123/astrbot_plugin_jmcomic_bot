# 🍶 JMComic Bot — 禁漫天堂 AstrBot 插件

基于 JMComic-Crawler-Python 的 AstrBot 插件，支持搜索、下载、排行榜、收藏夹等功能，LLM 可主动调用。

源码仓库：https://github.com/jujg12123/astrbot_plugin_jmcomic_bot
上游依赖：https://github.com/hect0x7/JMComic-Crawler-Python

## ✨ 功能

| 命令 | 功能 |
|------|------|
| `jm <id>` | 下载整本本子 |
| `jmc <id>` | 下载单个章节 |
| `jms <关键词>` | 搜索本子 |
| `jmi <id>` | 查看本子详情 |
| `jmrank [页码]` | 排行榜 |
| `jmfav [页码]` | 收藏夹（需登录） |
| `jmlogin` | 登录说明 |
| `jmstatus` | 插件状态 |
| `jmhelp` | 帮助 |
| `jmchangelog` | 更新日志 |

AI 也可以直接说「帮我搜个火影本子」— LLM 工具 `jm_search` / `jm_download` 自动触发。

## 📦 安装

1. 下载最新版 [Releases](https://github.com/jujg12123/astrbot_plugin_jmcomic_bot/releases)
2. 解压到 `AstrBot/plugins/jmcomic_bot/`
3. 重启 AstrBot，插件自动安装依赖（`jmcomic` / `pymupdf` / `pyzipper`）

## ⚙️ 配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `jm_username` | JM 账号用户名 | 空（匿名） |
| `jm_password` | JM 账号密码 | 空 |
| `download_dir` | 下载目录 | `downloads` |
| `image_suffix` | 图片格式 | `.jpg` |
| `client_type` | 客户端类型 | `api` |
| `max_photos` | 单次最大图片数 | `200` |
| `pack_format` | 打包格式（zip/pdf/none） | `zip` |
| `zip_password` | 打包密码（AES-256） | 空（不加密） |
| `filename_show_password` | 文件名显示密码 | `false` |
| `send_cover_preview` | 发送封面预览 | `true` |
| `cover_recall_enabled` | 封面消息自动撤回 | `false` |
| `auto_recall_enabled` | 文件消息自动撤回 | `false` |
| `auto_recall_delay` | 撤回延迟（秒） | `60` |
| `auto_delete_after_send` | 发送后自动删除本地文件 | `true` |
| `proxy` | HTTP 代理地址 | 空 |
| `admin_only` | 仅管理员可用 | `false` |
| `admin_list` | 管理员 ID 列表 | 空 |
| `enabled_groups` | 启用群号列表 | 空（全部启用） |
| `daily_download_limit` | 每日下载次数限制 | `0`（不限） |
| `debug` | 调试模式 | `false` |

### 🔐 防风控

设置 `zip_password` 后，下载的压缩包会使用 **AES-256 加密**，腾讯无法扫描内容，防止风控导致无法下载。用户解压时输入密码即可。

### 📦 打包格式

- **zip** — 压缩包，支持 AES 加密
- **pdf** — PDF 文件，支持密码加密（使用 pymupdf）
- **none** — 不打包，保留原文件夹

### 🖼️ 封面预览

开启 `send_cover_preview` 后，下载前会先发送漫画封面图片。配合 `cover_recall_enabled` 可自动撤回封面消息。

### ⏱️ 自动撤回

开启 `auto_recall_enabled` 后，文件发送后会在指定延迟后自动撤回，降低风控风险。

## 📝 更新日志

**v1.11.0** (2026-06-16)
- ✨ 图片格式 / 客户端类型 / 打包格式选择
- 🖼️ 封面预览 + 自动撤回
- ⏱️ 文件消息自动撤回
- 👤 用户名/密码登录（替代 Cookie）
- 🔑 文件名密码提示

**v1.10.17** (2026-06-16)
- 🐛 LLM 工具调用下载后自动发送文件
- 🔐 LLM 工具加入权限/配额/群白名单检查

**v1.10.0** — 初始版本，完整功能