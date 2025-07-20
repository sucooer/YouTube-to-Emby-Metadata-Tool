import sys
import os
import io
import re
import json

def get_app_dir():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.abspath(os.path.dirname(__file__))

sys.path.insert(0, get_app_dir())

CONFIG_FILE = os.path.join(get_app_dir(), "config.json")

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import queue
from nfo import (
    get_video_info,
    download_video,
    download_subtitles,
    generate_metadata_files,
    check_ffmpeg_installed,
    update_ytdlp,
    update_ytdlp_nightly
)

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"保存配置失败: {e}")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载配置失败: {e}")
        return {}

class ConsoleRedirector(io.TextIOBase):
    def __init__(self, log_widget, message_queue):
        self._log_widget = log_widget
        self._message_queue = message_queue

    def write(self, s):
        # 只处理非空字符串，避免Tkinter的IdleError
        if s and s.strip():
            self._message_queue.put(s.strip()) # strip()移除可能的空白行

    def flush(self):
        # flush操作，对于这种简单的文本输出器，通常不需要做什么
        pass

    def isatty(self):
        return False # 不是交互式终端

def restart_program():
    """自动重启当前应用"""
    python = sys.executable
    os.execl(python, python, *sys.argv)

class YouTubeToEmbyApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 配置窗口
        self.title("YouTube to Emby 元数据工具")
        self.geometry("1000x750")
        
        # 设置主题
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 创建消息队列用于线程间通信
        self.message_queue = queue.Queue()
        self.process_messages()

        # 创建主框架
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # URL输入
        self.url_label = ctk.CTkLabel(self.main_frame, text="YouTube URL:")
        self.url_label.pack(pady=(0, 2))
        self.url_entry = ctk.CTkEntry(self.main_frame, width=600)
        self.url_entry.pack(pady=(0, 6))

        # 输出目录选择
        self.output_frame = ctk.CTkFrame(self.main_frame)
        self.output_frame.pack(fill="x", pady=6)
        
        self.output_label = ctk.CTkLabel(self.output_frame, text="输出目录:")
        self.output_label.pack(side="left", padx=5)
        
        self.output_entry = ctk.CTkEntry(self.output_frame, width=400)
        self.output_entry.pack(side="left", padx=5)
        self.output_entry.insert(0, "./downloads")
        
        self.browse_button = ctk.CTkButton(
            self.output_frame,
            text="浏览",
            command=self.browse_output_dir,
            width=100
        )
        self.browse_button.pack(side="left", padx=5)

        # Cookie文件选择
        self.cookie_frame = ctk.CTkFrame(self.main_frame)
        self.cookie_frame.pack(fill="x", pady=6)
        
        self.cookie_label = ctk.CTkLabel(self.cookie_frame, text="Cookie文件:")
        self.cookie_label.pack(side="left", padx=5)
        
        self.cookie_entry = ctk.CTkEntry(self.cookie_frame, width=400)
        self.cookie_entry.pack(side="left", padx=5)
        
        config = load_config()
        saved_cookie_path = config.get("cookie_file")
        if saved_cookie_path and os.path.exists(saved_cookie_path):
            self.cookie_entry.insert(0, saved_cookie_path)
        
        self.cookie_button = ctk.CTkButton(
            self.cookie_frame,
            text="选择",
            command=self.browse_cookie_file,
            width=100
        )
        self.cookie_button.pack(side="left", padx=5)

        # 视频格式选择
        self.format_frame = ctk.CTkFrame(self.main_frame)
        self.format_frame.pack(fill="x", pady=6)
        
        self.format_label = ctk.CTkLabel(self.format_frame, text="视频格式:")
        self.format_label.pack(side="left", padx=5)
        
        self.format_var = tk.StringVar(value="mp4")
        self.mp4_radio = ctk.CTkRadioButton(
            self.format_frame,
            text="MP4",
            variable=self.format_var,
            value="mp4"
        )
        self.mp4_radio.pack(side="left", padx=20)
        
        self.mkv_radio = ctk.CTkRadioButton(
            self.format_frame,
            text="MKV",
            variable=self.format_var,
            value="mkv"
        )
        self.mkv_radio.pack(side="left", padx=20)

        # 进度显示
        self.progress_frame = ctk.CTkFrame(self.main_frame)
        self.progress_frame.pack(fill="x", pady=6)
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.pack(fill="x", padx=5, pady=5)
        self.progress_bar.set(0)
        
        self.status_label = ctk.CTkLabel(
            self.progress_frame,
            text="准备就绪",
            wraplength=700
        )
        self.status_label.pack(pady=2)

        # 日志显示
        self.log_frame = ctk.CTkFrame(self.main_frame)
        self.log_frame.pack(fill="both", expand=True, pady=6)
        
        self.log_text = ctk.CTkTextbox(
            self.log_frame,
            wrap="word",
            height=200
        )
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

        # 将重定向代码移动到这里
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._redirector = ConsoleRedirector(self.log_text, self.message_queue)
        sys.stdout = self._redirector
        sys.stderr = self._redirector

        # 开始按钮
        self.start_button = ctk.CTkButton(
            self.main_frame,
            text="开始下载",
            command=self.start_download,
            width=200
        )
        self.start_button.pack(pady=10)

        # yt-dlp 版本信息与更新
        self.ytdlp_frame = ctk.CTkFrame(self.main_frame)
        self.ytdlp_frame.pack(fill="x", pady=6)

        self.ytdlp_label = ctk.CTkLabel(self.ytdlp_frame, text="yt-dlp:")
        self.ytdlp_label.pack(side="left", padx=5)

        self.ytdlp_update_btn = ctk.CTkButton(
            self.ytdlp_frame,
            text="更新yt-dlp",
            command=self.update_ytdlp_gui,
            width=120
        )
        self.ytdlp_update_btn.pack(side="left", padx=5)

        self.ytdlp_info_label = ctk.CTkLabel(
            self.ytdlp_frame,
            text="版本信息加载中...",
            wraplength=400
        )
        self.ytdlp_info_label.pack(side="left", padx=5)

        # 应用程序启动后显示当前版本
        self.after(100, self.show_current_version)

        # 检查ffmpeg
        if not check_ffmpeg_installed():
            messagebox.showerror("错误", "未检测到ffmpeg，请安装ffmpeg并添加到系统PATH中。")

    def browse_output_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, directory)

    def browse_cookie_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if file_path:
            self.cookie_entry.delete(0, tk.END)
            self.cookie_entry.insert(0, file_path)
            config = load_config()
            config["cookie_file"] = file_path
            save_config(config)

    def log_message(self, message):
        self.message_queue.put(message)

    def process_messages(self):
        try:
            while True:
                message = self.message_queue.get_nowait()
                self.log_text.insert("end", message + "\n")
                self.log_text.see("end")
        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_messages)

    def update_status(self, message):
        self.status_label.configure(text=message)
        self.log_message(message)

    def start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "请输入YouTube URL")
            return

        output_dir = self.output_entry.get().strip()
        if not output_dir:
            messagebox.showerror("错误", "请选择输出目录")
            return

        cookie_path = self.cookie_entry.get().strip()
        if cookie_path and not os.path.exists(cookie_path):
            messagebox.showerror("错误", "Cookie文件不存在")
            return

        video_format = self.format_var.get()

        # 禁用开始按钮
        self.start_button.configure(state="disabled")
        
        # 在新线程中执行下载
        thread = threading.Thread(
            target=self.download_process,
            args=(url, output_dir, cookie_path, video_format)
        )
        thread.daemon = True
        thread.start()

    def download_process(self, url, output_dir, cookie_path, video_format):
        try:
            # 使用nightly版本
            self.update_status("正在获取视频信息...")
            video_info = get_video_info(url, cookie_path)
            
            if not video_info:
                self.update_status("获取视频信息失败")
                return

            video_info['cookiefile'] = cookie_path
            video_info['video_format'] = video_format

            output_dir = os.path.join(output_dir, video_info['title'])
            os.makedirs(output_dir, exist_ok=True)
            self.update_status(f"创建输出目录: {output_dir}")

            self.update_status("开始下载视频...")
            video_filename = download_video(video_info, output_dir, ytdlp_version)
            if not video_filename:
                self.update_status("视频下载失败")
                return

            self.update_status("开始下载字幕...")
            download_subtitles(video_info, output_dir, ytdlp_version)

            self.update_status("生成元数据文件...")
            generate_metadata_files(video_info, output_dir)

            self.update_status("下载完成！")
            messagebox.showinfo("成功", "文件下载和元数据生成完成！")

        except Exception as e:
            self.update_status(f"发生错误: {str(e)}")
            messagebox.showerror("错误", str(e))
        finally:
            # 重新启用开始按钮
            self.start_button.configure(state="normal")

    def show_ytdlp_version(self, selected_version=None):
        try:
            from nfo import get_current_ytdlp_version

            # 获取当前选中的版本类型
            if selected_version:
                version_type = selected_version
                # 同时更新下拉菜单的显示值，因为 command 触发时只传递值，不改变 StringVar
                self.ytdlp_version_var.set(version_type)
            else:
                # 在启动时调用时，直接获取 StringVar 的值
                version_type = self.ytdlp_version_var.get()

            # 获取当前版本的 yt-dlp 版本号
            # 在获取当前版本前，先确保清除了可能的旧模块缓存（import_yt_dlp 函数内部已处理）
            ytdlp_current_version = get_current_ytdlp_version(version_type)

            # 从已存储的最新版本数据中获取对应版本的最新版本号
            ytdlp_latest_version = self.latest_versions_data.get(version_type, "检测中...") # 如果还没获取到，显示"检测中..."

            # 构建要显示的文本
            current_text = f"当前: {ytdlp_current_version if ytdlp_current_version else '未加载'}"
            latest_text = f"最新: {ytdlp_latest_version}"

            # 更新主版本信息标签，增加当前版本和最新版本之间的间隔
            self.ytdlp_info_label.configure(text=f"{version_type.capitalize()}: {current_text}           {latest_text}")

        except Exception as e:
            # 如果获取当前版本或更新标签失败
            self.ytdlp_info_label.configure(text=f"{version_type.capitalize()}: 获取失败")
            self.log_message(f"显示 {version_type} 版本失败: {e}")

    def update_ytdlp_gui(self):
        self.log_message("准备更新yt-dlp到nightly版本...")
        self.ytdlp_update_btn.configure(state="disabled")
        self.ytdlp_info_label.configure(text="正在更新...")
        
        def log_func(msg):
            self.log_message(msg)
            
        def do_update():
            ok = update_ytdlp_nightly(log_func)
            self.ytdlp_update_btn.configure(state="normal")
            
            if ok:
                self.log_message("yt-dlp已更新成功！")
                # 更新版本信息显示
                self.after(1000, self.show_current_version)
            else:
                self.log_message("yt-dlp更新失败，请检查网络连接")
                self.ytdlp_info_label.configure(text="更新失败")

        threading.Thread(target=do_update, daemon=True).start()

    def show_current_version(self):
        """显示当前yt-dlp版本"""
        try:
            from nfo import get_current_ytdlp_version
            current_version = get_current_ytdlp_version()
            self.ytdlp_info_label.configure(text=f"当前版本: {current_version}")
            self.log_message(f"当前yt-dlp版本: {current_version}")
        except Exception as e:
            self.ytdlp_info_label.configure(text="版本获取失败")
            self.log_message(f"获取版本信息失败: {e}")

if __name__ == "__main__":
    app = YouTubeToEmbyApp()
    app.mainloop() 