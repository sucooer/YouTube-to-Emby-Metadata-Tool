import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import shutil
import requests
import xml.etree.ElementTree as ET
import re  # 用于正则表达式解析
import tkinter as tk
from tkinter import filedialog
import subprocess
import importlib.util
import zipfile
import tarfile
import tempfile

def get_ytdlp_version_dir(version):
    import os
    folder_map = {
        'stable': 'yt_dlp_stable',
        'nightly': 'yt_dlp_nightly',
        'master': 'yt_dlp_master'
    }
    # 源码模式下，base_dir 就是当前 nfo.py 文件所在的目录
    base_dir = os.path.abspath(os.path.dirname(__file__))

    # 返回 yt-dlp 版本目录的路径 (例如: 项目根目录/yt_dlp_stable)
    return os.path.join(base_dir, folder_map.get(version, ''))

def import_yt_dlp(version='stable'):
    import sys, importlib.util, os

    # 获取目标版本的 yt_dlp 包所在的目录
    target_ytdlp_dir = get_ytdlp_version_dir(version)

    # 检查这个目录是否存在且确实看起来像一个 yt_dlp 源码目录
    init_file = os.path.join(target_ytdlp_dir, "__init__.py")
    version_file = os.path.join(target_ytdlp_dir, "version.py")

    print(f"import_yt_dlp: 尝试加载 {version} 版从目录: {target_ytdlp_dir}")
    print(f"import_yt_dlp: 检查 {init_file} 是否存在: {os.path.exists(init_file)}")
    print(f"import_yt_dlp: 检查 {version_file} 是否存在: {os.path.exists(version_file)}")

    if not os.path.isdir(target_ytdlp_dir) or not os.path.exists(init_file) or not os.path.exists(version_file):
         print(f"import_yt_dlp: 目录 {target_ytdlp_dir} 不存在或结构不正确")
         raise ImportError(f"未找到yt_dlp模块({version})，请确保目录结构正确且已下载：{target_ytdlp_dir}")

    # >>> 添加以下代码来清除 yt_dlp 模块及其子模块的缓存 <<<
    # 遍历 sys.modules，找到所有属于 yt_dlp 的模块并移除
    modules_to_remove = [module_name for module_name in sys.modules if module_name == "yt_dlp" or module_name.startswith("yt_dlp.")]
    for module_name in modules_to_remove:
        try:
            del sys.modules[module_name]
            print(f"import_yt_dlp: 清除缓存模块: {module_name}")
        except KeyError:
            pass # 模块可能已经被移除了
    # >>> 清除缓存代码结束 <<<

    try:
        # 使用 importlib.util 动态加载模块
        # 构建模块规格
        spec = importlib.util.spec_from_file_location("yt_dlp", init_file, submodule_search_locations=[target_ytdlp_dir])

        if spec is None:
             print(f"import_yt_dlp: 无法为 {target_ytdlp_dir} 创建模块规格")
             raise ImportError(f"无法创建yt_dlp模块规格({version})")

        # 从规格加载模块
        yt_dlp = importlib.util.module_from_spec(spec)

        # 将模块添加到 sys.modules
        sys.modules["yt_dlp"] = yt_dlp

        # 执行模块的代码 (__init__.py 的内容)
        spec.loader.exec_module(yt_dlp)

        print(f"import_yt_dlp: 成功加载 {version} 版 yt-dlp 从 {target_ytdlp_dir}")
        return yt_dlp

    except Exception as e:
        print(f"import_yt_dlp: 导入 {version} 版失败: {e}")
        # 导入失败，确保从 sys.modules 中移除，避免影响后续尝试
        # 这里的移除代码在前面的缓存清除中已经处理了大部分情况，但为了安全，可以保留。
        if "yt_dlp" in sys.modules:
             del sys.modules["yt_dlp"]
        raise ImportError(f"未找到yt_dlp模块({version})，请确保目录结构正确且已下载：{target_ytdlp_dir}")

def sanitize_filename(title):
    return "".join(c for c in title if c not in '\\/*?:"<>|').strip()

def get_video_info(url, cookie_file=None, ytdlp_version='stable'):
    # 确保 URL 格式正确
    if 'youtube.com/watch?v=' in url:
        video_id = url.split('watch?v=')[-1].split('&')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'force_ipv4': True,
        'socket_timeout': 30,  # 增加超时时间
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        },
        'format': 'best',  # 使用最佳格式
        'retries': 10,  # 增加重试次数
        'cookiefile': os.path.expandvars(cookie_file.strip('"')) if cookie_file else None
    }
    
    try:
        yt_dlp = import_yt_dlp(ytdlp_version)
        YoutubeDL = yt_dlp.YoutubeDL
        if cookie_file:
            print(f"ℹ️ Using cookie file: {ydl_opts['cookiefile']}")
        print(f"⌛ 正在获取视频信息: {url}")
        
        with YoutubeDL(ydl_opts) as ydl:
            print("📋 获取可用格式列表...")
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise Exception("无法获取视频信息")
                
            # 打印详细的调试信息
            print(f"\n📺 视频标题: {info.get('title', 'Unknown')}")
            print(f"👤 上传者: {info.get('uploader', 'Unknown')}")
            
            # 获取格式列表
            formats = info.get('formats', [])
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
            
            # 其余代码保持不变
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
        return None

def download_video(info, output_dir, ytdlp_version='stable'):
    """下载视频文件"""
    try:
        yt_dlp = import_yt_dlp(ytdlp_version)
        YoutubeDL = yt_dlp.YoutubeDL
        video_format = info.get('video_format', 'mp4')
        ydl_opts = {
            'format': f'bestvideo+bestaudio/best',
            'merge_output_format': video_format,
            'socket_timeout': 30,  # 增加超时时间
            'force_ipv4': True,  # 强制使用 IPv4
            'http_chunk_size': 10485760,  # 分块下载，优化网络请求（10MB）
            'cookiefile': info.get('cookiefile'),
            'outtmpl': os.path.join(output_dir, f"{info['title']}.%(ext)s"),
            'sleep_interval': 2,  # 每次请求间隔 2 秒
            'max_sleep_interval': 5,  # 最大随机间隔 5 秒
        }
        print(f"⌛ Downloading video as {video_format} ...")
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([info['url']])
        # 查找下载后的视频文件
        downloaded_files = [f for f in os.listdir(output_dir) if f.startswith(info['title']) and f.endswith(f".{video_format}")]
        if not downloaded_files:
            raise Exception("No video file found after download")
        return downloaded_files[0]
    except Exception as e:
        print(f"❌ Video download failed: {str(e)}")
        return None

def download_subtitles(info, output_dir, ytdlp_version='stable'):
    """下载字幕文件并保存到与视频文件相同的目录，优先下载日语和中文字幕，并转换为 ASS 格式"""
    try:
        yt_dlp = import_yt_dlp(ytdlp_version)
        YoutubeDL = yt_dlp.YoutubeDL
        ydl_opts = {
            'writesubtitles': True,  # 启用字幕下载
            'subtitleslangs': ['ja', 'zh-Hans', 'zh-Hant'],  # 优先下载日语和中文字幕
            'subtitlesformat': 'ass/srt/vtt',  # 下载字幕格式，优先 ASS
            'skip_download': True,  # 仅下载字幕，不下载视频
            'force_ipv4': True,  # 强制使用 IPv4
            'http_chunk_size': 10485760,  # 分块下载，优化网络请求（10MB）
            'cookiefile': info.get('cookiefile'),  # 使用 cookie 文件绕过人机验证
            'outtmpl': os.path.join(output_dir, f"{info['title']}.%(ext)s"),
            'quiet': True,
            'no_warnings': True,
            'sleep_interval': 2,  # 每次请求间隔 2 秒
            'max_sleep_interval': 5,  # 最大随机间隔 5 秒
        }
        print("⌛ Downloading subtitles...")
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([info['url']])

        # 重命名字幕文件以符合 Emby 刮削规则，按语言代码命名
        found = False
        for file in os.listdir(output_dir):
            if file.startswith(info['title']) and file.endswith(('.ass', '.srt', '.vtt')):
                subtitle_path = os.path.join(output_dir, file)
                subtitle_ext = os.path.splitext(file)[1]
                # 提取语言代码
                m = re.match(rf"^{re.escape(info['title'])}\.([a-zA-Z\-]+){subtitle_ext}$", file)
                lang = m.group(1) if m else None
                if subtitle_ext == '.vtt':
                    # 如果字幕是 VTT 格式，尝试转换为 ASS 格式
                    converted_file = os.path.splitext(subtitle_path)[0] + '.ass'
                    vtt_to_ass(subtitle_path, converted_file)
                    os.remove(subtitle_path)  # 删除原始 VTT 文件
                    subtitle_path = converted_file
                    subtitle_ext = '.ass'
                if lang:
                    new_name = f"{os.path.splitext(info['title'])[0]}.{lang}{subtitle_ext}"
                else:
                    new_name = f"{os.path.splitext(info['title'])[0]}{subtitle_ext}"
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
        root = ET.Element("movie")
        ET.SubElement(root, "title").text = video_info['title']
        ET.SubElement(root, "plot").text = video_info['description']
        ET.SubElement(root, "premiered").text = video_info['publish_date']
        ET.SubElement(root, "year").text = video_info['year']
        ET.SubElement(root, "studio").text = "YouTube"

        if video_info['uploader']:
            director = ET.SubElement(root, "director")
            director.text = video_info['uploader']
        
        for tag in video_info.get('tags', [])[:10]:
            ET.SubElement(root, "tag").text = tag
        nfo_path = os.path.join(output_dir, f"{base_name}.nfo")
        ET.ElementTree(root).write(nfo_path, encoding='utf-8', xml_declaration=True)
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

def update_ytdlp():
    print("是否需要检查并自动更新 yt-dlp？")
    choice = input("输入 y 进行更新，直接回车跳过: ").strip().lower()
    if choice == "y":
        try:
            # 优先尝试 pip 更新
            print("⌛ 正在通过 pip 更新 yt-dlp ...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
            print("✅ yt-dlp 已通过 pip 更新")
        except Exception as e:
            print(f"⚠️ pip 更新失败: {e}")
            # 如果 pip 失败，尝试 yt-dlp 自带更新（适用于 yt-dlp.exe）
            try:
                print("⌛ 正在尝试 yt-dlp 自带更新 ...")
                subprocess.check_call(["yt-dlp", "-U"])
                print("✅ yt-dlp 已自更新")
            except Exception as e2:
                print(f"❌ yt-dlp 更新失败: {e2}")

def get_yt_dlp_install_path():
    # 获取yt_dlp包的安装路径
    spec = importlib.util.find_spec("yt_dlp")
    if spec and spec.submodule_search_locations:
        return spec.submodule_search_locations[0]
    return None

def get_current_ytdlp_version(ytdlp_version='stable'):
    try:
        yt_dlp = import_yt_dlp(ytdlp_version)
        print("yt_dlp.version.__version__:", getattr(yt_dlp.version, '__version__', 'not found'))
        return yt_dlp.version.__version__
    except Exception as e:
        print("get_current_ytdlp_version error:", e)
        return None

def get_latest_stable_version():
    import requests
    r = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=10)
    return r.json()["info"]["version"]

def update_yt_dlp_in_app(version_type, log_func=print, github_token=None):
    import os, shutil, requests, tarfile, zipfile, tempfile
    yt_dlp_path = get_yt_dlp_dir()
    if not yt_dlp_path:
        log_func("未找到yt_dlp安装路径")
        return False

    repo = "yt-dlp-nightly-builds"
    api_url = f"https://api.github.com/repos/yt-dlp/{repo}/releases/latest"
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    try:
        # 先获取本地版本号
        local_version = get_current_ytdlp_version()
        if local_version:
            log_func(f"yt-dlp 当前版本为 {local_version}，如无特殊需求无需频繁更新。")
        try:
            r = requests.get(api_url, timeout=20, headers=headers)
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                log_func("GitHub API 限流，无法检测新版本。请稍后再试。")
                return False
            else:
                log_func(f"yt-dlp nightly 版更新失败: {e}")
                return False
        latest_version = r.json().get("tag_name")
        if local_version and latest_version and local_version == latest_version:
            log_func(f"yt-dlp 已经是最新版（{local_version}），无需更新。")
            return False
        assets = r.json().get("assets", [])
        url = None
        for asset in assets:
            if asset["name"].endswith(".tar.gz"):
                url = asset["browser_download_url"]
                break
        if not url:
            for asset in assets:
                if asset["name"].endswith(".zip"):
                    url = asset["browser_download_url"]
                    break
        if not url:
            log_func("未找到可用的源码包")
            return False
        log_func(f"正在下载 nightly 版 yt-dlp ...")
        tmp_dir = tempfile.mkdtemp()
        local_file = os.path.join(tmp_dir, os.path.basename(url))
        with requests.get(url, stream=True, timeout=60) as r2:
            r2.raise_for_status()
            with open(local_file, "wb") as f:
                for chunk in r2.iter_content(1024 * 1024):
                    f.write(chunk)
        # 解压
        if local_file.endswith(".tar.gz"):
            with tarfile.open(local_file, "r:gz") as tar:
                tar.extractall(tmp_dir)
        elif local_file.endswith(".zip"):
            with zipfile.ZipFile(local_file, "r") as zipf:
                zipf.extractall(tmp_dir)
        # 找到yt_dlp目录
        yt_dlp_src = None
        for root, dirs, files in os.walk(tmp_dir):
            if "yt_dlp" in dirs:
                yt_dlp_src = os.path.join(root, "yt_dlp")
                break
        if not yt_dlp_src:
            log_func("解压后未找到yt_dlp目录")
            return False
        # 目标目录应该是 _internal/yt_dlp_stable/yt_dlp
        target_dir = os.path.join(internal_path, "yt_dlp")
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        os.makedirs(internal_path, exist_ok=True)
        shutil.copytree(yt_dlp_src, target_dir)
        log_func(f"yt-dlp nightly 版已更新，请重启应用生效。")
        shutil.rmtree(tmp_dir)
        return True
    except Exception as e:
        log_func(f"yt-dlp nightly 版更新失败: {e}")
        return False

def get_yt_dlp_dir():
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, 'yt_dlp')
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), 'yt_dlp')

def download_and_extract_yt_dlp(version='stable', log_func=print):
    import requests, tarfile, zipfile, tempfile, os, shutil

    # 获取目标版本的 yt-dlp 应该存放的目录 (例如: 项目根目录/yt_dlp_stable)
    target_ytdlp_dir = get_ytdlp_version_dir(version)

    # 确保目标目录存在
    os.makedirs(target_ytdlp_dir, exist_ok=True)

    folder_map = {
        'stable': 'yt_dlp_stable',
        'nightly': 'yt_dlp_nightly',
        'master': 'yt_dlp_master'
    }

    # 静态下载地址 (直接下载 release asset)
    static_url_map = {
        'stable': 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.tar.gz',
        'nightly': 'https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.tar.gz',
        'master': 'https://github.com/yt-dlp/yt-dlp-master-builds/releases/latest/download/yt-dlp.tar.gz'
    }

    try:
        if version not in static_url_map:
             log_func(f"不支持的版本类型: {version}")
             return False

        url = static_url_map[version]
        log_func(f"下载 {version} 版 yt-dlp: {url}")

        # 后续下载和解压逻辑不变
        tmp_dir = tempfile.mkdtemp()
        local_file = os.path.join(tmp_dir, os.path.basename(url))
        with requests.get(url, stream=True, timeout=60) as r2:
            r2.raise_for_status()
            with open(local_file, "wb") as f:
                for chunk in r2.iter_content(1024 * 1024):
                    f.write(chunk)

        log_func(f"下载完成，解压中...")
        if local_file.endswith(".tar.gz"):
            with tarfile.open(local_file, "r:gz") as tar:
                tar.extractall(tmp_dir)
        elif local_file.endswith(".zip"):
            with zipfile.ZipFile(local_file, "r") as zipf:
                zipf.extractall(tmp_dir)

        # 找到解压后的 yt_dlp 包的目录 (在临时目录中)
        yt_dlp_src = None
        for root, dirs, files in os.walk(tmp_dir):
            # 寻找包含 __init__.py 的目录，这才是真正的 yt_dlp 包的根目录
            # 同时检查 version.py 和 downloader 目录，进一步确认是 yt_dlp 包
            if '__init__.py' in files and 'version.py' in files and 'downloader' in dirs:
                 # 如果解压出来就是 yt_dlp 包的根目录本身 (例如: tmp_dir/yt_dlp/...)
                 if os.path.basename(root) == 'yt_dlp':
                     yt_dlp_src = root
                     break
                 # 如果解压出来的内容直接就是 yt_dlp 包的内容 (例如: tmp_dir/__init__.py, tmp_dir/downloader/...)
                 # 并且 tmp_dir 目录下没有 yt_dlp 子目录
                 elif os.path.normpath(root) == os.path.normpath(tmp_dir) and 'yt_dlp' not in dirs:
                     yt_dlp_src = root
                     break
                 # 还有一种可能是解压后在 tmp_dir 下有一个额外的目录，其子目录才是 yt_dlp (例如: tmp_dir/yt-dlp-release/yt_dlp/...)
                 elif 'yt_dlp' in dirs and os.path.join(root, 'yt_dlp') == os.path.join(tmp_dir, [d for d in dirs if 'yt-dlp' in d][0], 'yt_dlp') if [d for d in dirs if 'yt-dlp' in d] else False: # 尝试识别中间目录
                      yt_dlp_src = os.path.join(root, 'yt_dlp')
                      break


        if not yt_dlp_src:
            log_func("解压后未找到yt_dlp源码目录")
            return False

        # 目标目录是 .../yt_dlp_stable 等
        # 我们要将找到的 yt_dlp 源码内容直接拷贝到 target_ytdlp_dir
        if os.path.exists(target_ytdlp_dir):
            shutil.rmtree(target_ytdlp_dir)
        os.makedirs(target_ytdlp_dir, exist_ok=True)

        # 拷贝 yt_dlp 源码文件到目标目录
        for item in os.listdir(yt_dlp_src):
             s = os.path.join(yt_dlp_src, item)
             d = os.path.join(target_ytdlp_dir, item)
             if os.path.isdir(s):
                  # 避免无限递归拷贝
                  if os.path.abspath(s) != os.path.abspath(target_ytdlp_dir):
                       shutil.copytree(s, d, False, None)
             else:
                  shutil.copy2(s, d)

        shutil.rmtree(tmp_dir)
        log_func(f"yt-dlp {version} 版已更新，目录：{target_ytdlp_dir}，请重启应用生效。")
        return True
    except Exception as e:
        log_func(f"yt-dlp {version} 版下载或解压失败: {e}")
        print(f"yt-dlp {version} 版下载或解压失败: {e}")
        return False

def get_nightly_download_url():
    # 直接返回nightly源码包的静态下载地址
    return "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.tar.gz"

def get_latest_versions(log_func=print):
    import requests
    latest_versions = {
        'stable': '获取失败',
        'nightly': '获取失败',
        'master': '获取失败'
    }

    # 获取 Stable 最新版本 (从 PyPI)
    try:
        log_func("获取 Stable 最新版本...")
        r = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=10)
        r.raise_for_status()
        latest_versions['stable'] = r.json()["info"]["version"]
        log_func(f"Stable 最新版本: {latest_versions['stable']}")
    except Exception as e:
        log_func(f"获取 Stable 最新版本失败: {e}")
        latest_versions['stable'] = f"获取失败 ({e})"

    # 获取 Nightly 最新版本 (从 GitHub Releases HTML 页面解析)
    # 直接从静态下载地址 URL 中提取版本信息可能不可靠，解析 Release 页面更稳定
    try:
        log_func("获取 Nightly 最新版本...")
        # 访问 Releases 页面
        r = requests.get("https://github.com/yt-dlp/yt-dlp-nightly-builds/releases", timeout=10)
        r.raise_for_status()
        # 简单的字符串查找或正则表达式来找到最新的 tag_name
        # 查找类似 <a href="/yt-dlp/yt-dlp-nightly-builds/releases/tag/2024.x.x">2024.x.x</a> 的模式
        match = re.search(r'/yt-dlp/yt-dlp-nightly-builds/releases/tag/(.*?)"', r.text)
        if match:
            latest_versions['nightly'] = match.group(1)
            log_func(f"Nightly 最新版本: {latest_versions['nightly']}")
        else:
            log_func("在 Nightly Releases 页面未找到版本信息")
            latest_versions['nightly'] = "未找到"

    except Exception as e:
        log_func(f"获取 Nightly 最新版本失败: {e}")
        latest_versions['nightly'] = f"获取失败 ({e})"


    # 获取 Master 最新版本 (从 GitHub Releases HTML 页面解析)
    try:
        log_func("获取 Master 最新版本...")
        # 访问 Releases 页面
        r = requests.get("https://github.com/yt-dlp/yt-dlp-master-builds/releases", timeout=10)
        r.raise_for_status()
         # 简单的字符串查找或正则表达式来找到最新的 tag_name
        match = re.search(r'/yt-dlp/yt-dlp-master-builds/releases/tag/(.*?)"', r.text)
        if match:
            latest_versions['master'] = match.group(1)
            log_func(f"Master 最新版本: {latest_versions['master']}")
        else:
            log_func("在 Master Releases 页面未找到版本信息")
            latest_versions['master'] = "未找到"

    except Exception as e:
        log_func(f"获取 Master 最新版本失败: {e}")
        latest_versions['master'] = f"获取失败 ({e})"

    return latest_versions

def main():
    update_ytdlp()
    print("====== YouTube to Emby Metadata Tool ======")
    # 检查 ffmpeg 是否已安装
    if not check_ffmpeg_installed():
        return
    youtube_url = input("Enter YouTube URL: ").strip()
    if not youtube_url.startswith(('http://', 'https://')):
        print("❌ Invalid URL format")
        return

    base_output_dir = input("Base output directory (default: ./downloads): ").strip() or "./downloads"
    os.makedirs(base_output_dir, exist_ok=True)
    # 默认 cookie 文件路径
    default_cookie_path = os.path.expanduser("~\\cookies.txt")
    print(f"1. 使用默认 cookie 文件: {default_cookie_path}")
    print("2. 手动选择 cookie 文件")
    print("3. 不使用 cookie 文件")
    cookie_choice = input("请选择 cookie 文件方式（1/2/3，默认1）: ").strip() or "1"
    cookie_path = None
    if cookie_choice == "1":
        cookie_path = default_cookie_path
        if not os.path.exists(cookie_path):
            print(f"⚠️ Cookie file not found: {cookie_path}")
            cookie_path = None
    elif cookie_choice == "2":
        try:
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            # 将窗口提升到最前
            root.attributes('-topmost', True)
            print("正在打开文件选择窗口...")
            cookie_path = filedialog.askopenfilename(
                title="选择 cookies.txt 文件",
                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
                parent=root  # 设置父窗口
            )
            if cookie_path:
                if not os.path.exists(cookie_path):
                    print("⚠️ 所选文件不存在")
                    cookie_path = None
                else:
                    print(f"✅ 已选择 cookie 文件: {cookie_path}")
            else:
                print("⚠️ 未选择任何文件")
                cookie_path = None
            root.destroy()  # 销毁 Tk 窗口
        except Exception as e:
            print(f"⚠️ 打开文件选择窗口失败: {str(e)}")
            cookie_path = None
    else:
        cookie_path = None

    # 新增：选择视频保存格式
    print("请选择保存视频的格式：")
    print("1. mp4（默认）")
    print("2. mkv")
    format_choice = input("输入 1 或 2（默认1）: ").strip() or "1"
    if format_choice == "2":
        video_format = "mkv"
    else:
        video_format = "mp4"

    video_info = get_video_info(youtube_url, cookie_path)
    if not video_info:
        print("❌ Failed to fetch metadata")
        return
    video_info['cookiefile'] = cookie_path
    video_info['video_format'] = video_format   # 传递格式信息

    output_dir = os.path.join(base_output_dir, video_info['title'])
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Created output folder: {output_dir}")

    video_filename = download_video(video_info, output_dir)
    if not video_filename:
        print("❌ Failed to download video")
        return

    # 下载字幕
    download_subtitles(video_info, output_dir)

    generate_metadata_files(video_info, output_dir)
    print("\n🎉 Success! Files created:")
    print(f"- Video: {os.path.join(output_dir, video_filename)}")
    print(f"- Metadata: {os.path.join(output_dir, video_info['title'])}.nfo")
    print(f"- Thumbnail: {os.path.join(output_dir, video_info['title'])}-poster.jpg")

    yt_dlp = import_yt_dlp('stable')
    print("yt_dlp.version:", yt_dlp.version.__version__)

if __name__ == "__main__":
    main()

