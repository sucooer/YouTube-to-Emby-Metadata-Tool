import os
import sys
import shutil
import requests
import xml.etree.ElementTree as ET
import re  # 用于正则表达式解析
import subprocess
import importlib.util
import zipfile
import tarfile
import tempfile
from urllib.parse import urlparse, parse_qs

ILLEGAL_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

# 直接导入pip安装的yt-dlp
try:
    import yt_dlp
    print("✓ 成功加载pip安装的yt-dlp")
    
    # 尝试快速获取版本信息
    version_info = "版本信息不可用"
    try:
        from importlib.metadata import version
        version_info = version('yt-dlp')
    except:
        try:
            import pkg_resources
            version_info = pkg_resources.get_distribution('yt-dlp').version
        except:
            pass
    
    print(f"✓ 版本: {version_info}")
except ImportError as e:
    print("❌ 未找到yt-dlp，请运行: pip install --pre yt-dlp")
    print(f"错误详情: {e}")
    # 不直接退出，让程序继续运行，在Web界面中提示用户安装
    yt_dlp = None

def clean_xml_text(value):
    """清理会破坏XML格式的非法控制字符，并统一换行符。"""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return ILLEGAL_XML_CHARS_RE.sub("", text)

def indent_xml(element, level=0):
    """为ElementTree添加可读的缩进格式。"""
    indent = "\n" + "  " * level
    child_indent = "\n" + "  " * (level + 1)
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = child_indent
        for child in children:
            indent_xml(child, level + 1)
        if not children[-1].tail or not children[-1].tail.strip():
            children[-1].tail = indent
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indent

def add_text_element(parent, tag, value):
    """仅在文本非空时创建节点，避免空标签影响NFO可读性。"""
    text = clean_xml_text(value)
    if text:
        ET.SubElement(parent, tag).text = text
        return True
    return False

def description_outline(text, max_len=180):
    """提取简介首行作为outline，保持简洁。"""
    content = clean_xml_text(text)
    if not content:
        return ""
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    if not first_line:
        return ""
    return first_line[:max_len].rstrip()

def normalize_actor_name(name):
    """规范化演员名，去掉频道属性后缀和噪声标记。"""
    text = clean_xml_text(name).strip()
    if not text:
        return ""

    # 去掉以@开头的账号ID（不适合作为演员名）
    if text.startswith("@"):
        return ""

    # 去掉常见频道后缀
    text = re.sub(
        r"\s*(?:official(?:\s*channel)?|channel|公式(?:チャンネル)?|オフィシャル)\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    # 去掉尾部括号中的品牌性注记（如【HoneyWorks】）
    text = re.sub(
        r"\s*[【\[\(（](?:official|公式|honeyworks|channel|オフィシャル)[^】\]\)）]*[】\]\)）]\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    return text.strip(" \t-_|/")

def extract_actor_names(video_info):
    """提取演员名：频道主 + 结构化创作者字段，不从标题推断。"""
    original = video_info.get('original_info') or {}
    names = []

    def append_name(name):
        text = normalize_actor_name(name)
        if text and text not in names:
            names.append(text)

    def append_from_value(value):
        if isinstance(value, str):
            # 有些字段会以单字符串返回多个创作者，如 "A, B"
            parts = re.split(r"\s*(?:,|，|、|;|；|/|／|\|)\s*", value)
            for part in parts:
                append_name(part)
        elif isinstance(value, dict):
            append_name(value.get('name') or value.get('title') or "")
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                append_from_value(item)

    # 仅从频道主相关字段提取（优先channel，再uploader）
    append_name(original.get('channel'))
    append_name(video_info.get('uploader'))
    append_name(original.get('uploader'))

    # 补充结构化创作者信息（例如 creators: ['KAWAII LAB.', 'CANDY TUNE']）
    for key in ("creators", "creator", "artists", "artist"):
        append_from_value(original.get(key))

    # 你要求演员必须有：提取不到时给占位值
    if not names:
        names = ["未知演员"]
    return names[:10]

def normalize_youtube_url(url):
    """统一YouTube链接为watch?v=VIDEO_ID格式，避免短链提取失败。"""
    text = clean_xml_text(url).strip()
    if not text:
        return text
    try:
        parsed = urlparse(text)
        host = parsed.netloc.lower()
        path = parsed.path or ""

        if "youtu.be" in host:
            video_id = path.lstrip("/").split("/")[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"

        if "youtube.com" in host:
            query = parse_qs(parsed.query or "")
            if query.get("v"):
                return f"https://www.youtube.com/watch?v={query['v'][0]}"

            short_match = re.match(r"^/(?:shorts|live|embed)/([^/?#]+)", path)
            if short_match:
                return f"https://www.youtube.com/watch?v={short_match.group(1)}"
    except Exception:
        pass

    # 兜底兼容旧逻辑
    if 'youtube.com/watch?v=' in text:
        video_id = text.split('watch?v=')[-1].split('&')[0]
        return f'https://www.youtube.com/watch?v={video_id}'
    return text

def sanitize_filename(title):
    # 移除不允许的字符（Linux中主要是斜杠和空字符）
    sanitized = "".join(c for c in title if c not in '/\0').strip()
    
    # 在Linux中，文件名限制是255字节，需要考虑UTF-8编码
    max_bytes = 200  # 保守估计，为扩展名留空间
    
    # 确保字节长度不超过限制
    encoded = sanitized.encode('utf-8')
    if len(encoded) > max_bytes:
        # 逐字符截断直到字节长度合适
        while len(sanitized.encode('utf-8')) > max_bytes - 3:
            sanitized = sanitized[:-1]
        sanitized += "..."
    
    # 移除末尾的点和空格
    sanitized = sanitized.rstrip('. ')
    
    # 如果截断后为空，使用默认名称
    if not sanitized:
        sanitized = "video"
    
    return sanitized

def has_playable_formats(formats):
    """判断格式列表中是否存在可下载的音视频流（排除storyboard图片流）。"""
    if not formats:
        return False
    for f in formats:
        ext = (f.get('ext') or '').lower()
        vcodec = (f.get('vcodec') or '').lower()
        acodec = (f.get('acodec') or '').lower()
        # 排除 storyboard 图片格式
        if ext == 'mhtml' or vcodec == 'images':
            continue
        if vcodec != 'none' or (acodec and acodec != 'none'):
            return True
    return False

def build_ytdlp_base_opts():
    """构建yt-dlp通用参数，启用EJS能力以应对YouTube挑战。"""
    return {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ignore_no_formats_error': True,
        'force_ipv4': True,
        'socket_timeout': 60,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        'retries': 10,
        # 2026版yt-dlp默认仅启用deno。这里额外启用node，并允许拉取官方ejs远程组件
        'js_runtimes': {
            'deno': {},
            'node': {'path': 'node'},
        },
        'remote_components': {'ejs:github'},
    }

def get_video_info(url, cookie_file=None):
    if yt_dlp is None:
        raise ImportError("yt-dlp未安装，请运行: pip install --pre yt-dlp")
    
    # 统一链接格式，避免短链/分享链接触发提取差异
    url = normalize_youtube_url(url)
    base_opts = build_ytdlp_base_opts()
    try:
        YoutubeDL = yt_dlp.YoutubeDL

        def extract_info_with_cookie(cookie_candidate):
            opts = dict(base_opts)
            resolved_cookie = os.path.expandvars(cookie_candidate.strip('"')) if cookie_candidate else None
            opts['cookiefile'] = resolved_cookie
            with YoutubeDL(opts) as ydl:
                extracted = ydl.extract_info(url, download=False)
            return extracted, resolved_cookie

        resolved_cookie_display = os.path.expandvars(cookie_file.strip('"')) if cookie_file else None
        if cookie_file:
            print(f"ℹ️ Using cookie file: {resolved_cookie_display}")
        print(f"⌛ 正在获取视频信息: {url}")
        print("📋 获取可用格式列表...")

        info = None
        effective_cookie = os.path.expandvars(cookie_file.strip('"')) if cookie_file else None
        cookie_storyboard_only = False
        try:
            info, effective_cookie = extract_info_with_cookie(cookie_file)
        except Exception as first_error:
            # 某些视频在特定客户端策略下会出现“Requested format is not available”，回退到默认策略重试
            if "Requested format is not available" not in str(first_error):
                raise
            print("⚠️ 当前提取策略未返回可用格式，正在切换为默认策略重试...")
            info, effective_cookie = extract_info_with_cookie(cookie_file)

        if not info:
            raise Exception("无法获取视频信息")
        if info.get('_type') == 'playlist':
            entries = info.get('entries') or []
            info = next((entry for entry in entries if entry), None)
            if not info:
                raise Exception("无法从播放列表结果中提取视频信息")
        print(f"\n📺 视频标题: {info.get('title', 'Unknown')}")
        print(f"👤 上传者: {info.get('uploader', 'Unknown')}")
        formats = info.get('formats', [])

        # 某些环境在“带cookie”时只返回storyboard格式，尝试自动回退到不使用cookie
        if cookie_file and not has_playable_formats(formats):
            cookie_storyboard_only = True
            print("⚠️ 检测到当前 cookie 可能已失效、权限不足或导出不完整（仅返回 storyboard）。")
            print("⚠️ 建议重新导出 cookies.txt（需包含 youtube.com 且保持登录状态）。")
            print("⚠️ 使用 cookie 仅获取到 storyboard 格式，尝试不使用 cookie 重试...")
            try:
                retry_info, _ = extract_info_with_cookie(None)
                if retry_info and retry_info.get('_type') == 'playlist':
                    entries = retry_info.get('entries') or []
                    retry_info = next((entry for entry in entries if entry), None)
                retry_formats = retry_info.get('formats', []) if retry_info else []
                if retry_info and has_playable_formats(retry_formats):
                    info = retry_info
                    formats = retry_formats
                    effective_cookie = None
                    cookie_storyboard_only = False
                    print("✅ 不使用 cookie 获取到了可下载格式，后续将按无 cookie 继续。")
            except Exception as retry_error:
                print(f"⚠️ 无 cookie 重试失败: {retry_error}")

        if not formats:
            print("⚠️ 没有找到可用的视频格式")
        else:
            print("\n🎥 可用的视频格式：")
            for f in formats:
                format_id = f.get('format_id', 'N/A')
                ext = f.get('ext', 'N/A')
                resolution = f.get('resolution', 'N/A')
                filesize = f.get('filesize', 0)
                if filesize:
                    filesize = f"{filesize/1024/1024:.1f}MB"
                else:
                    filesize = 'N/A'
                print(f"ID: {format_id}, 格式: {ext}, 分辨率: {resolution}, 大小: {filesize}")

        if not has_playable_formats(formats):
            if cookie_storyboard_only:
                raise Exception(
                    "仅检测到 storyboard 图片格式。当前 cookie 可能已失效、权限不足或导出不完整，"
                    "请重新导出 cookies.txt 后重试。"
                )
            raise Exception(
                "仅检测到storyboard图片格式，未检测到可下载音视频流。"
                "这通常是yt-dlp在当前环境缺少JS runtime/challenge solver导致。"
            )

        upload_date = info.get('upload_date', '')
        return {
            'title': sanitize_filename(info.get('title', 'No Title')),
            'description': info.get('description', ''),
            'uploader': info.get('uploader', 'Unknown'),
            'publish_date': f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}" if upload_date else "",
            'year': upload_date[:4] if upload_date else "",
            'thumbnail_url': info.get('thumbnail', ''),
            'tags': info.get('tags', []),
            'url': url,
            'formats': formats,
            'cookiefile': effective_cookie,
            'original_info': info
        }
    except Exception as e:
        print(f"❌ 下载失败: {str(e)}")
        print("\n💡 提示：")
        print("1. 检查视频 URL 是否完整")
        print("2. 确认视频是否可以正常访问")
        print("3. 尝试更新 yt-dlp:")
        print("   python -m pip install -U yt-dlp")
        print("4. 手动测试视频格式:")
        print(f"   yt-dlp --list-formats {url}")
        print("5. 若只出现 sb0/sb1/sb2/sb3(mhtml)，请安装 JS runtime 和 challenge solver：")
        print("   https://github.com/yt-dlp/yt-dlp/wiki/EJS")
        if cookie_file:
            print("6. 若使用了 cookie 且仅返回 storyboard，cookie 可能已失效，请重新导出 cookies.txt。")
        return None

def download_video(info, output_dir):
    if yt_dlp is None:
        raise ImportError("yt-dlp未安装，请运行: pip install --pre yt-dlp")
    
    try:
        YoutubeDL = yt_dlp.YoutubeDL
        video_format = info.get('video_format', 'mp4')
        cookie_candidates = [info.get('cookiefile')]
        if info.get('cookiefile'):
            cookie_candidates.append(None)

        base_opts = build_ytdlp_base_opts()
        base_opts.update({
            'merge_output_format': video_format,
            'socket_timeout': 60,  # 增加超时时间
            'force_ipv4': True,  # 强制使用 IPv4
            'http_chunk_size': 10485760,  # 分块下载，优化网络请求（10MB）
            'outtmpl': os.path.join(output_dir, f"{sanitize_filename(info['title'])}.%(ext)s"),
            'sleep_interval': 2,  # 每次请求间隔 2 秒
            'max_sleep_interval': 5,  # 最大随机间隔 5 秒
            'quiet': True,  # 安静模式
            'no_warnings': True,  # 禁用警告以隐藏PO Token警告
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            'prefer_ffmpeg': True,  # 优先使用ffmpeg进行合并
        })
        print(f"⌛ Downloading video as {video_format} ...")
        download_errors = []
        format_candidates = [
            'bestvideo*+bestaudio/best',
            'bestvideo+bestaudio/best',
            'best'
        ]
        download_success = False
        for cookie_idx, cookie_candidate in enumerate(cookie_candidates):
            if cookie_idx > 0:
                print("⚠️ 带 cookie 下载失败，正在回退为不使用 cookie 重试...")
            for idx, format_expr in enumerate(format_candidates):
                try:
                    trial_opts = dict(base_opts)
                    trial_opts['cookiefile'] = cookie_candidate
                    trial_opts['format'] = format_expr
                    with YoutubeDL(trial_opts) as ydl:
                        ydl.download([info['url']])
                    download_success = True
                    break
                except Exception as e:
                    download_errors.append(str(e))
                    if idx < len(format_candidates) - 1:
                        print(f"⚠️ 下载格式 {format_expr} 不可用，尝试下一个格式...")
            if download_success:
                break
        if not download_success:
            raise Exception(download_errors[-1] if download_errors else "视频下载失败")

        downloaded_files = [
            f for f in os.listdir(output_dir)
            if f.startswith(sanitize_filename(info['title']))
            and os.path.splitext(f)[1].lower() in {'.mp4', '.mkv', '.webm', '.mov', '.m4v'}
        ]
        if not downloaded_files:
            raise Exception("No video file found after download")
        preferred = [f for f in downloaded_files if f.lower().endswith(f".{video_format.lower()}")]
        return preferred[0] if preferred else downloaded_files[0]
    except Exception as e:
        print(f"❌ Video download failed: {str(e)}")
        return None

def download_subtitles(info, output_dir):
    if yt_dlp is None:
        raise ImportError("yt-dlp未安装，请运行: pip install --pre yt-dlp")
    
    try:
        YoutubeDL = yt_dlp.YoutubeDL
        ydl_opts = build_ytdlp_base_opts()
        ydl_opts.update({
            'writesubtitles': True,  # 启用字幕下载
            'subtitleslangs': ['ja', 'zh-Hans', 'zh-Hant'],  # 优先下载日语和中文字幕
            'subtitlesformat': 'ass/srt/vtt',  # 下载字幕格式，优先 ASS
            'skip_download': True,  # 仅下载字幕，不下载视频
            'force_ipv4': True,  # 强制使用 IPv4
            'http_chunk_size': 10485760,  # 分块下载，优化网络请求（10MB）
            'cookiefile': info.get('cookiefile'),  # 使用 cookie 文件绕过人机验证
            'outtmpl': os.path.join(output_dir, f"{sanitize_filename(info['title'])}.%(ext)s"),
            'quiet': True,
            'no_warnings': True,
            'sleep_interval': 2,  # 每次请求间隔 2 秒
            'max_sleep_interval': 5,  # 最大随机间隔 5 秒
        })
        print("⌛ Downloading subtitles...")
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([info['url']])
        found = False
        sanitized_title = sanitize_filename(info['title'])
        for file in os.listdir(output_dir):
            if file.startswith(sanitized_title) and file.endswith(('.ass', '.srt', '.vtt')):
                subtitle_path = os.path.join(output_dir, file)
                subtitle_ext = os.path.splitext(file)[1]
                m = re.match(rf"^{re.escape(sanitized_title)}\.([a-zA-Z\-]+){subtitle_ext}$", file)
                lang = m.group(1) if m else None
                if subtitle_ext == '.vtt':
                    converted_file = os.path.splitext(subtitle_path)[0] + '.ass'
                    vtt_to_ass(subtitle_path, converted_file)
                    os.remove(subtitle_path)
                    subtitle_path = converted_file
                    subtitle_ext = '.ass'
                if lang:
                    new_name = f"{os.path.splitext(sanitized_title)[0]}.{lang}{subtitle_ext}"
                else:
                    new_name = f"{os.path.splitext(sanitized_title)[0]}{subtitle_ext}"
                os.rename(subtitle_path, os.path.join(output_dir, new_name))
                print(f"✅ Subtitle saved as: {new_name}")
                found = True
        if not found:
            print("⚠️ No subtitles found for this video.")
        return None
    except Exception as e:
        print(f"⚠️ Failed to download subtitles: {str(e)}")
        return None

def vtt_to_ass(vtt_path, ass_path):
    """将 VTT 格式字幕转换为 ASS 格式"""
    try:
        import webvtt
        from pysubs2 import SSAFile, SSAEvent
        import subprocess
        from . import get_ffmpeg_path

        print(f"⌛ Converting {vtt_path} to ASS format...")
        subs = SSAFile()
        for caption in webvtt.read(vtt_path):
            start = caption.start_in_seconds * 1000  # 转换为毫秒
            end = caption.end_in_seconds * 1000  # 转换为毫秒
            text = caption.text.replace('\n', '\\N')  # 替换换行符为 ASS 格式的换行符
            event = SSAEvent(start=start, end=end, text=text)
            subs.events.append(event)  # 添加字幕事件
        subs.save(ass_path)
        print(f"✅ Converted to ASS: {ass_path}")
    except ImportError as e:
        print("⚠️ Missing required module. Please install dependencies:")
        print("   pip install webvtt-py pysubs2")
        raise e
    except Exception as e:
        print(f"⚠️ Failed to convert VTT to ASS: {str(e)}")
        raise e

def generate_metadata_files(video_info, output_dir):
    base_name = os.path.splitext(video_info['title'])[0]
    thumbnail_path = os.path.join(output_dir, f"{base_name}-poster.jpg")
    if video_info['thumbnail_url']:
        try:
            print(f"⌛ Downloading thumbnail from {video_info['thumbnail_url']}")
            # 增加重试机制和超时设置
            for attempt in range(3):  # 尝试最多 3 次
                try:
                    response = requests.get(video_info['thumbnail_url'], timeout=10)
                    response.raise_for_status()
                    with open(thumbnail_path, 'wb') as f:
                        f.write(response.content)
                    print(f"✅ Thumbnail saved to {thumbnail_path}")
                    break
                except requests.exceptions.RequestException as e:
                    print(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")
                    if attempt == 2:  # 最后一次尝试失败
                        raise
        except Exception as e:
            print(f"❌ Thumbnail download failed: {str(e)}")
    try:
        original = video_info.get('original_info') or {}
        video_id = original.get('id', '')
        webpage_url = original.get('webpage_url') or video_info.get('url', '')
        duration_seconds = original.get('duration')
        runtime_minutes = ""
        if isinstance(duration_seconds, (int, float)) and duration_seconds > 0:
            runtime_minutes = str(max(1, int(round(duration_seconds / 60.0))))

        root = ET.Element("movie")
        # 字段顺序尽量贴近Emby/Kodi movie.nfo惯例
        add_text_element(root, "title", video_info.get('title'))
        add_text_element(root, "originaltitle", video_info.get('title'))
        add_text_element(root, "plot", video_info.get('description'))
        add_text_element(root, "outline", description_outline(video_info.get('description')))
        add_text_element(root, "year", video_info.get('year'))
        add_text_element(root, "premiered", video_info.get('publish_date'))
        add_text_element(root, "aired", video_info.get('publish_date'))
        add_text_element(root, "runtime", runtime_minutes)
        add_text_element(root, "studio", "YouTube")
        add_text_element(root, "trailer", webpage_url)
        add_text_element(root, "id", video_id)
        if clean_xml_text(video_id):
            uniqueid = ET.SubElement(root, "uniqueid", {"type": "youtube", "default": "true"})
            uniqueid.text = clean_xml_text(video_id)
        # 为海报保留显式引用，便于媒体库快速识别
        if os.path.exists(thumbnail_path):
            add_text_element(root, "thumb", os.path.basename(thumbnail_path))

        # 默认类型标签
        add_text_element(root, "genre", "YouTube")

        for actor_name in extract_actor_names(video_info):
            actor = ET.SubElement(root, "actor")
            ET.SubElement(actor, "name").text = actor_name
        
        for tag in video_info.get('tags', [])[:10]:
            tag_text = clean_xml_text(tag)
            if tag_text:
                ET.SubElement(root, "tag").text = tag_text
                ET.SubElement(root, "genre").text = tag_text
        nfo_path = os.path.join(output_dir, f"{base_name}.nfo")
        indent_xml(root)
        ET.ElementTree(root).write(
            nfo_path,
            encoding='utf-8',
            xml_declaration=True,
            short_empty_elements=False
        )
        print(f"✅ NFO file generated: {nfo_path}")
    except Exception as e:
        print(f"❌ NFO generation failed: {str(e)}")

def get_ffmpeg_path():
    # 优先使用项目内的ffmpeg.exe
    local_ffmpeg = os.path.join(os.path.dirname(__file__), "tools", "ffmpeg.exe")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    # 退回到系统PATH
    return shutil.which("ffmpeg.exe" if os.name == "nt" else "ffmpeg")

def check_ffmpeg_installed():
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        print("❌ ffmpeg is not installed or not in PATH or tools/ffmpeg.exe.")
        print("ℹ️ You can download it from: https://ffmpeg.org/download.html")
        return False
    return True

def get_current_ytdlp_version():
    """获取当前pip安装的yt-dlp版本"""
    try:
        # 检查yt_dlp是否可用
        if yt_dlp is None:
            return "未安装"
        
        # 方法1：使用importlib.metadata (Python 3.8+) - 最可靠
        try:
            from importlib.metadata import version
            ver = version('yt-dlp')
            print(f"✓ importlib.metadata获取版本: {ver}")
            return ver
        except Exception as e:
            print(f"importlib.metadata失败: {e}")
        
        # 方法2：使用pkg_resources
        try:
            import pkg_resources
            ver = pkg_resources.get_distribution('yt-dlp').version
            print(f"✓ pkg_resources获取版本: {ver}")
            return ver
        except Exception as e:
            print(f"pkg_resources失败: {e}")
        
        # 方法3：使用subprocess调用yt-dlp --version
        try:
            result = subprocess.run([sys.executable, '-m', 'yt_dlp', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                ver = result.stdout.strip()
                print(f"✓ 命令行获取版本: {ver}")
                return ver
            else:
                print(f"命令行调用失败: {result.stderr}")
        except Exception as e:
            print(f"命令行调用异常: {e}")
        
        # 方法4：直接从模块获取（通常不可用）
        if hasattr(yt_dlp, '__version__'):
            ver = yt_dlp.__version__
            print(f"✓ 模块属性获取版本: {ver}")
            return ver
        
        # 方法5：尝试从version模块获取
        try:
            from yt_dlp import version as ytdlp_version
            if hasattr(ytdlp_version, '__version__'):
                ver = ytdlp_version.__version__
                print(f"✓ version模块获取版本: {ver}")
                return ver
        except Exception as e:
            print(f"version模块失败: {e}")
        
        print("所有版本获取方法都失败了")
        return "版本获取失败"
    except Exception as e:
        print(f"获取版本异常: {e}")
        return "版本获取失败"

def update_ytdlp_nightly(log_func=print):
    """更新yt-dlp到nightly版本"""
    try:
        log_func("正在更新yt-dlp到nightly版本...")
        
        # 使用pip安装nightly版本
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "--upgrade", "--pre", "yt-dlp"
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            log_func("✓ yt-dlp nightly版本更新成功")
            
            # 重新导入模块以获取新版本
            import importlib
            importlib.reload(yt_dlp)
            
            new_version = get_current_ytdlp_version()
            log_func(f"新版本: {new_version}")
            return True
        else:
            log_func(f"❌ 更新失败: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        log_func("❌ 更新超时")
        return False
    except Exception as e:
        log_func(f"❌ 更新失败: {e}")
        return False

def update_ytdlp():
    print("是否需要检查并自动更新 yt-dlp nightly版本？")
    choice = input("输入 y 进行更新，直接回车跳过: ").strip().lower()
    if choice == "y":
        try:
            print("⌛ 正在通过 pip 更新 yt-dlp nightly版本...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "--pre", "yt-dlp"])
            print("✅ yt-dlp nightly版本已更新")
        except Exception as e:
            print(f"❌ yt-dlp 更新失败: {e}")

def main():
    update_ytdlp()
    print("====== YouTube to Emby Metadata Tool ======")
    # 检查 ffmpeg 是否已安装
    if not check_ffmpeg_installed():
        return
    print("请选择输入方式：")
    print("1. 单个链接")
    print("2. 批量链接（txt文件，每行一个链接）")
    input_mode = input("输入 1 或 2（默认1）: ").strip() or "1"

    if input_mode == "2":
        default_links_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "links.txt")
        txt_path = input(f"请输入包含链接的txt文件路径 (默认: {default_links_path}): ").strip() or default_links_path
        if not os.path.exists(txt_path):
            print("❌ 文件不存在")
            return
        with open(txt_path, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
    else:
        youtube_url = input("Enter YouTube URL: ").strip()
        urls = [youtube_url]

    base_output_dir = input("Base output directory (default: ./downloads): ").strip() or "./downloads"
    os.makedirs(base_output_dir, exist_ok=True)
    # 默认 cookie 文件路径（本项目根目录下）
    default_cookie_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    print(f"1. 使用默认 cookie 文件: {default_cookie_path}")
    print("2. 手动输入 cookie 文件路径")
    print("3. 不使用 cookie 文件")
    cookie_choice = input("请选择 cookie 文件方式（1/2/3，默认1，也可直接输入路径）: ").strip() or "1"
    cookie_path = None
    if cookie_choice == "1":
        cookie_path = default_cookie_path
        if not os.path.exists(cookie_path):
            print(f"⚠️ Cookie file not found: {cookie_path}")
            cookie_path = None
    elif cookie_choice == "2":
        cookie_path = os.path.expandvars(input("请输入 cookie 文件的完整路径: ").strip().strip('"'))
        if not os.path.exists(cookie_path):
            print("⚠️ 所选文件不存在")
            cookie_path = None
        else:
            print(f"✅ 已选择 cookie 文件: {cookie_path}")
    elif cookie_choice == "3":
        cookie_path = None
    else:
        # 兼容用户直接在这里粘贴 cookie 文件路径
        direct_cookie_path = os.path.expandvars(cookie_choice.strip('"'))
        if os.path.exists(direct_cookie_path):
            cookie_path = direct_cookie_path
            print(f"✅ 已选择 cookie 文件: {cookie_path}")
        else:
            print(f"⚠️ 无效输入或文件不存在: {cookie_choice}")
            cookie_path = None

    if not cookie_path:
        print("ℹ️ 当前不使用 cookie 文件")

    # 新增：选择视频保存格式
    print("请选择保存视频的格式：")
    print("1. mp4（默认）")
    print("2. mkv")
    format_choice = input("输入 1 或 2（默认1）: ").strip() or "1"
    if format_choice == "2":
        video_format = "mkv"
    else:
        video_format = "mp4"

    for youtube_url in urls:
        if not youtube_url.startswith(('http://', 'https://')):
            print(f"❌ Invalid URL format: {youtube_url}")
            continue

        video_info = get_video_info(youtube_url, cookie_path)
        if not video_info:
            print("❌ Failed to fetch metadata")
            continue
        # 优先使用get_video_info中判定的有效cookie策略（可能自动回退为None）
        video_info['cookiefile'] = video_info.get('cookiefile', cookie_path)
        video_info['video_format'] = video_format   # 传递格式信息

        output_dir = os.path.join(base_output_dir, video_info['title'])
        os.makedirs(output_dir, exist_ok=True)
        print(f"📁 Created output folder: {output_dir}")

        video_filename = download_video(video_info, output_dir)
        if not video_filename:
            print("❌ Failed to download video")
            continue

        # 下载字幕
        download_subtitles(video_info, output_dir)

        generate_metadata_files(video_info, output_dir)
        print("\n🎉 Success! Files created:")
        print(f"- Video: {os.path.join(output_dir, video_filename)}")
        print(f"- Metadata: {os.path.join(output_dir, video_info['title'])}.nfo")
        print(f"- Thumbnail: {os.path.join(output_dir, video_info['title'])}-poster.jpg")

if __name__ == "__main__":
    main()

