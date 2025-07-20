from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import os
import threading
import queue
import json
from datetime import datetime
import uuid
from nfo import (
    get_video_info,
    download_video,
    download_subtitles,
    generate_metadata_files,
    check_ffmpeg_installed,
    update_ytdlp,
    update_ytdlp_nightly,
    get_current_ytdlp_version
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# 存储活动的下载任务
active_downloads = {}

class WebLogger:
    """Web版本的日志记录器，通过WebSocket发送日志"""
    def __init__(self, session_id):
        self.session_id = session_id
    
    def log(self, message):
        """发送日志消息到前端"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        socketio.emit('log_message', {
            'message': f"[{timestamp}] {message}",
            'session_id': self.session_id
        })

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/api/check_ffmpeg')
def check_ffmpeg():
    """检查ffmpeg是否可用"""
    return jsonify({'available': check_ffmpeg_installed()})

@app.route('/api/ytdlp_info')
def get_ytdlp_info():
    """获取yt-dlp版本信息"""
    try:
        print("API: 开始获取yt-dlp版本信息")
        current_version = get_current_ytdlp_version()
        print(f"API: 获取到版本: {current_version}")
        
        if current_version == "未安装":
            status = "未安装 - 请运行 pip install --pre yt-dlp"
        elif current_version == "版本获取失败":
            status = "已安装但版本获取失败"
        else:
            status = "pip安装的nightly版本"
        
        result = {
            'current': current_version,
            'status': status
        }
        print(f"API: 返回结果: {result}")
        
        return jsonify(result)
    except Exception as e:
        print(f"API: 发生错误: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_ytdlp', methods=['POST'])
def update_ytdlp_api():
    """更新yt-dlp nightly版本"""
    data = request.get_json()
    session_id = data.get('session_id', str(uuid.uuid4()))
    
    logger = WebLogger(session_id)
    
    def update_process():
        try:
            logger.log("开始更新yt-dlp nightly版本...")
            success = update_ytdlp_nightly(logger.log)
            
            if success:
                logger.log("yt-dlp nightly版本更新成功！")
                # 获取新版本号
                new_version = get_current_ytdlp_version()
                logger.log(f"新版本: {new_version}")
                socketio.emit('update_complete', {
                    'success': True,
                    'new_version': new_version,
                    'session_id': session_id
                })
            else:
                logger.log("yt-dlp更新失败！")
                socketio.emit('update_complete', {
                    'success': False,
                    'session_id': session_id
                })
        except Exception as e:
            logger.log(f"更新过程中出错: {str(e)}")
            socketio.emit('update_complete', {
                'success': False,
                'error': str(e),
                'session_id': session_id
            })
    
    thread = threading.Thread(target=update_process)
    thread.daemon = True
    thread.start()
    
    return jsonify({'session_id': session_id, 'status': 'started'})

@app.route('/api/upload_cookie', methods=['POST'])
def upload_cookie():
    """上传Cookie文件"""
    try:
        if 'cookie_file' not in request.files:
            return jsonify({'error': '没有选择文件'}), 400
        
        file = request.files['cookie_file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 创建临时目录存储Cookie文件
        temp_dir = os.path.join(os.path.dirname(__file__), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # 保存文件
        filename = f"cookies_{uuid.uuid4().hex[:8]}.txt"
        filepath = os.path.join(temp_dir, filename)
        file.save(filepath)
        
        return jsonify({
            'success': True,
            'filepath': filepath,
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def start_download():
    """开始下载任务"""
    data = request.get_json()
    
    url = data.get('url', '').strip()
    output_dir = data.get('output_dir', './downloads').strip()
    cookie_file = data.get('cookie_file', '').strip()
    video_format = data.get('video_format', 'mp4')
    
    # 验证输入
    if not url:
        return jsonify({'error': '请输入YouTube URL'}), 400
    
    # 检查Cookie文件（可能是上传的临时文件）
    if cookie_file and not os.path.exists(cookie_file):
        # 如果是相对路径，尝试在temp目录中查找
        if not os.path.isabs(cookie_file):
            temp_cookie_path = os.path.join(os.path.dirname(__file__), 'temp', cookie_file)
            if os.path.exists(temp_cookie_path):
                cookie_file = temp_cookie_path
            else:
                return jsonify({'error': 'Cookie文件不存在'}), 400
    
    # 生成任务ID
    task_id = str(uuid.uuid4())
    session_id = data.get('session_id', task_id)
    
    # 创建日志记录器
    logger = WebLogger(session_id)
    
    # 存储任务信息
    active_downloads[task_id] = {
        'status': 'starting',
        'progress': 0,
        'session_id': session_id
    }
    
    def download_process():
        try:
            # 更新任务状态
            active_downloads[task_id]['status'] = 'getting_info'
            socketio.emit('download_status', {
                'task_id': task_id,
                'status': 'getting_info',
                'message': '正在获取视频信息...',
                'session_id': session_id
            })
            
            logger.log("正在获取视频信息...")
            video_info = get_video_info(url, cookie_file if cookie_file else None)
            
            if not video_info:
                raise Exception("获取视频信息失败")
            
            video_info['cookiefile'] = cookie_file if cookie_file else None
            video_info['video_format'] = video_format
            
            # 创建输出目录
            final_output_dir = os.path.join(output_dir, video_info['title'])
            os.makedirs(final_output_dir, exist_ok=True)
            logger.log(f"创建输出目录: {final_output_dir}")
            
            # 下载视频
            active_downloads[task_id]['status'] = 'downloading_video'
            socketio.emit('download_status', {
                'task_id': task_id,
                'status': 'downloading_video',
                'message': '正在下载视频...',
                'session_id': session_id
            })
            
            logger.log("开始下载视频...")
            video_filename = download_video(video_info, final_output_dir)
            
            if not video_filename:
                raise Exception("视频下载失败")
            
            # 下载字幕
            active_downloads[task_id]['status'] = 'downloading_subtitles'
            socketio.emit('download_status', {
                'task_id': task_id,
                'status': 'downloading_subtitles',
                'message': '正在下载字幕...',
                'session_id': session_id
            })
            
            logger.log("开始下载字幕...")
            download_subtitles(video_info, final_output_dir)
            
            # 生成元数据
            active_downloads[task_id]['status'] = 'generating_metadata'
            socketio.emit('download_status', {
                'task_id': task_id,
                'status': 'generating_metadata',
                'message': '正在生成元数据文件...',
                'session_id': session_id
            })
            
            logger.log("生成元数据文件...")
            generate_metadata_files(video_info, final_output_dir)
            
            # 完成
            active_downloads[task_id]['status'] = 'completed'
            socketio.emit('download_status', {
                'task_id': task_id,
                'status': 'completed',
                'message': '下载完成！',
                'output_dir': final_output_dir,
                'session_id': session_id
            })
            
            logger.log("下载完成！")
            
        except Exception as e:
            error_msg = str(e)
            logger.log(f"发生错误: {error_msg}")
            active_downloads[task_id]['status'] = 'error'
            socketio.emit('download_status', {
                'task_id': task_id,
                'status': 'error',
                'message': f'错误: {error_msg}',
                'session_id': session_id
            })
    
    # 启动下载线程
    thread = threading.Thread(target=download_process)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'task_id': task_id,
        'session_id': session_id,
        'status': 'started'
    })

@app.route('/api/download_status/<task_id>')
def get_download_status(task_id):
    """获取下载任务状态"""
    if task_id in active_downloads:
        return jsonify(active_downloads[task_id])
    else:
        return jsonify({'error': '任务不存在'}), 404

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print('客户端已连接')

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开连接"""
    print('客户端已断开连接')

if __name__ == '__main__':
    # 确保模板和静态文件目录存在
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # 检查ffmpeg
    if not check_ffmpeg_installed():
        print("警告: 未检测到ffmpeg，某些功能可能无法正常工作")
    
    print("启动YouTube to Emby Web界面...")
    print("访问 http://localhost:5000 来使用web界面")
    
    # 检查Python版本，Python 3.13+禁用调试模式以避免兼容性问题
    import sys
    debug_mode = sys.version_info < (3, 13)
    if not debug_mode:
        print("检测到Python 3.13+，已禁用调试模式以确保兼容性")
    
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=5000)