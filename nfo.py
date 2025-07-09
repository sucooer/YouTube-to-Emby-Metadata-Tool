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
import yt_dlp

def sanitize_filename(title):
    return "".join(c for c in title if c not in '\\/*?:"<>|').strip()

def get_video_info(url, cookie_file=None):
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
        YoutubeDL = yt_dlp.YoutubeDL
        if cookie_file:
            print(f"ℹ️ Using cookie file: {ydl_opts['cookiefile']}")
        print(f"⌛ 正在获取视频信息: {url}")
        with YoutubeDL(ydl_opts) as ydl:
            print("📋 获取可用格式列表...")
            info = ydl.extract_info(url, download=False)
            if not info:
                raise Exception("无法获取视频信息")
            print(f"\n📺 视频标题: {info.get('title', 'Unknown')}")
            print(f"👤 上传者: {info.get('uploader', 'Unknown')}")
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

def download_video(info, output_dir):
    try:
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
        downloaded_files = [f for f in os.listdir(output_dir) if f.startswith(info['title']) and f.endswith(f".{video_format}")]
        if not downloaded_files:
            raise Exception("No video file found after download")
        return downloaded_files[0]
    except Exception as e:
        print(f"❌ Video download failed: {str(e)}")
        return None

def download_subtitles(info, output_dir):
    try:
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
        found = False
        for file in os.listdir(output_dir):
            if file.startswith(info['title']) and file.endswith(('.ass', '.srt', '.vtt')):
                subtitle_path = os.path.join(output_dir, file)
                subtitle_ext = os.path.splitext(file)[1]
                m = re.match(rf"^{re.escape(info['title'])}\.([a-zA-Z\-]+){subtitle_ext}$", file)
                lang = m.group(1) if m else None
                if subtitle_ext == '.vtt':
                    converted_file = os.path.splitext(subtitle_path)[0] + '.ass'
                    vtt_to_ass(subtitle_path, converted_file)
                    os.remove(subtitle_path)
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
            print("⌛ 正在通过 pip 更新 yt-dlp ...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
            print("✅ yt-dlp 已通过 pip 更新")
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
    cookie_choice = input("请选择 cookie 文件方式（1/2/3，默认1）: ").strip() or "1"
    cookie_path = None
    if cookie_choice == "1":
        cookie_path = default_cookie_path
        if not os.path.exists(cookie_path):
            print(f"⚠️ Cookie file not found: {cookie_path}")
            cookie_path = None
    elif cookie_choice == "2":
        cookie_path = input("请输入 cookie 文件的完整路径: ").strip()
        if not os.path.exists(cookie_path):
            print("⚠️ 所选文件不存在")
            cookie_path = None
        else:
            print(f"✅ 已选择 cookie 文件: {cookie_path}")
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

    for youtube_url in urls:
        if not youtube_url.startswith(('http://', 'https://')):
            print(f"❌ Invalid URL format: {youtube_url}")
            continue

        video_info = get_video_info(youtube_url, cookie_path)
        if not video_info:
            print("❌ Failed to fetch metadata")
            continue
        video_info['cookiefile'] = cookie_path
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

