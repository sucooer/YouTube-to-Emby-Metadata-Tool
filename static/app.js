// YouTube to Emby Web界面 JavaScript

// 全局变量
let socket;
let currentSessionId = null;
let currentTaskId = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    console.log('初始化应用...');
    
    // 初始化Socket.IO连接
    initializeSocket();
    
    // 绑定事件监听器
    bindEventListeners();
    
    // 检查系统状态
    checkSystemStatus();
    
    // 获取yt-dlp版本信息
    setTimeout(() => {
        getYtdlpInfo();
    }, 1000); // 延迟1秒加载版本信息
    
    console.log('应用初始化完成');
}

function initializeSocket() {
    socket = io();
    
    socket.on('connect', function() {
        console.log('已连接到服务器');
        updateConnectionStatus('已连接', 'success');
    });
    
    socket.on('disconnect', function() {
        console.log('与服务器断开连接');
        updateConnectionStatus('已断开', 'danger');
    });
    
    socket.on('log_message', function(data) {
        if (!currentSessionId || data.session_id === currentSessionId) {
            addLogMessage(data.message);
        }
    });
    
    socket.on('download_status', function(data) {
        if (data.session_id === currentSessionId) {
            updateDownloadProgress(data);
        }
    });
    
    socket.on('update_complete', function(data) {
        if (data.session_id === currentSessionId) {
            handleUpdateComplete(data);
        }
    });
}

function bindEventListeners() {
    // 下载表单提交
    document.getElementById('download-form').addEventListener('submit', function(e) {
        console.log('表单提交事件触发');
        e.preventDefault();
        startDownload();
    });
    
    // 直接绑定下载按钮点击事件（备用）
    document.getElementById('start-download-btn').addEventListener('click', function(e) {
        console.log('下载按钮点击事件触发');
        e.preventDefault();
        startDownload();
    });
    
    // 更新yt-dlp按钮
    document.getElementById('update-ytdlp-btn').addEventListener('click', function() {
        updateYtdlp();
    });
    
    // 清空日志按钮
    document.getElementById('clear-log-btn').addEventListener('click', function() {
        clearLog();
    });
    
    // 输出目录选择按钮
    document.getElementById('select-output-dir').addEventListener('click', function() {
        selectOutputDirectory();
    });
    
    // Cookie文件选择按钮
    document.getElementById('select-cookie-file').addEventListener('click', function() {
        document.getElementById('cookie-file-input').click();
    });
    
    // Cookie文件选择处理
    document.getElementById('cookie-file-input').addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            uploadCookieFile(file);
        }
    });
}

function checkSystemStatus() {
    // 检查FFmpeg状态
    fetch('/api/check_ffmpeg')
        .then(response => response.json())
        .then(data => {
            const status = data.available ? '可用' : '不可用';
            const badgeClass = data.available ? 'bg-success' : 'bg-danger';
            document.getElementById('ffmpeg-status').textContent = status;
            document.getElementById('ffmpeg-status').className = `badge ${badgeClass}`;
        })
        .catch(error => {
            console.error('检查FFmpeg状态失败:', error);
            document.getElementById('ffmpeg-status').textContent = '检查失败';
            document.getElementById('ffmpeg-status').className = 'badge bg-warning';
        });
}

function getYtdlpInfo() {
    console.log('正在获取yt-dlp版本信息...');
    
    fetch('/api/ytdlp_info')
        .then(response => {
            console.log('API响应状态:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('API返回数据:', data);
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            document.getElementById('current-version').textContent = data.current || '未知';
            document.getElementById('latest-version').textContent = data.status || '未知';
            
            // 更新按钮状态
            const updateBtn = document.getElementById('update-ytdlp-btn');
            if (data.current === '未安装') {
                updateBtn.classList.remove('btn-primary', 'btn-success');
                updateBtn.classList.add('btn-warning');
                updateBtn.innerHTML = '<i class="bi bi-download"></i> 安装yt-dlp';
            } else if (data.current === '版本获取失败') {
                updateBtn.classList.remove('btn-warning', 'btn-success');
                updateBtn.classList.add('btn-primary');
                updateBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 重新检查';
            } else {
                // 已安装版本，显示为检查更新
                updateBtn.classList.remove('btn-warning', 'btn-primary');
                updateBtn.classList.add('btn-success');
                updateBtn.innerHTML = '<i class="bi bi-check-circle"></i> 检查更新';
            }
            
            console.log('版本信息更新完成');
        })
        .catch(error => {
            console.error('获取yt-dlp信息失败:', error);
            document.getElementById('current-version').textContent = '获取失败';
            document.getElementById('latest-version').textContent = '请检查控制台';
            
            // 显示错误详情
            addLogMessage(`版本信息获取失败: ${error.message}`);
        });
}

function updateYtdlp() {
    currentSessionId = generateSessionId();
    
    const updateBtn = document.getElementById('update-ytdlp-btn');
    updateBtn.disabled = true;
    updateBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 更新中...';
    
    fetch('/api/update_ytdlp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            session_id: currentSessionId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            throw new Error(data.error);
        }
        addLogMessage('开始更新yt-dlp nightly版本...');
    })
    .catch(error => {
        console.error('更新yt-dlp失败:', error);
        addLogMessage(`更新失败: ${error.message}`);
        resetUpdateButton();
    });
}

function handleUpdateComplete(data) {
    const updateBtn = document.getElementById('update-ytdlp-btn');
    
    if (data.success) {
        addLogMessage('yt-dlp更新成功！');
        if (data.new_version) {
            addLogMessage(`新版本: ${data.new_version}`);
        }
        updateBtn.classList.remove('btn-warning', 'btn-primary');
        updateBtn.classList.add('btn-success');
        updateBtn.innerHTML = '<i class="bi bi-check-circle"></i> 更新完成';
        
        // 立即刷新版本信息
        getYtdlpInfo();
        
        // 3秒后重置按钮
        setTimeout(() => {
            updateBtn.innerHTML = '<i class="bi bi-check-circle"></i> 已是最新版本';
            updateBtn.disabled = false;
        }, 3000);
    } else {
        addLogMessage(`yt-dlp更新失败: ${data.error || '未知错误'}`);
        resetUpdateButton();
    }
}

function resetUpdateButton() {
    const updateBtn = document.getElementById('update-ytdlp-btn');
    updateBtn.disabled = false;
    updateBtn.classList.remove('btn-warning', 'btn-primary');
    updateBtn.classList.add('btn-success');
    updateBtn.innerHTML = '<i class="bi bi-check-circle"></i> 检查更新';
}

function startDownload() {
    console.log('开始下载函数被调用');
    
    const url = document.getElementById('youtube-url').value.trim();
    const outputDir = document.getElementById('output-dir').value.trim();
    const cookieFile = document.getElementById('cookie-file').value.trim();
    const videoFormat = document.querySelector('input[name="video-format"]:checked').value;
    
    console.log('下载参数:', {
        url: url,
        outputDir: outputDir,
        cookieFile: cookieFile,
        videoFormat: videoFormat
    });
    
    if (!url) {
        alert('请输入YouTube URL');
        return;
    }
    
    currentSessionId = generateSessionId();
    console.log('生成会话ID:', currentSessionId);
    
    // 显示进度卡片
    document.getElementById('progress-card').style.display = 'block';
    
    // 禁用下载按钮
    const downloadBtn = document.getElementById('start-download-btn');
    downloadBtn.disabled = true;
    downloadBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 下载中...';
    
    // 重置进度
    updateProgressBar(0, '准备中...', 'info');
    
    addLogMessage('正在启动下载任务...');
    
    const requestData = {
        url: url,
        output_dir: outputDir,
        cookie_file: cookieFile,
        video_format: videoFormat,
        session_id: currentSessionId
    };
    
    console.log('发送请求数据:', requestData);
    
    fetch('/api/download', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData)
    })
    .then(response => {
        console.log('API响应状态:', response.status);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('API响应数据:', data);
        if (data.error) {
            throw new Error(data.error);
        }
        currentTaskId = data.task_id;
        addLogMessage('✓ 下载任务已启动');
        addLogMessage(`任务ID: ${data.task_id}`);
    })
    .catch(error => {
        console.error('启动下载失败:', error);
        addLogMessage(`❌ 下载失败: ${error.message}`);
        resetDownloadButton();
        document.getElementById('progress-card').style.display = 'none';
    });
}

function updateDownloadProgress(data) {
    const statusMessages = {
        'starting': '准备中...',
        'getting_info': '获取视频信息...',
        'downloading_video': '下载视频中...',
        'downloading_subtitles': '下载字幕中...',
        'generating_metadata': '生成元数据...',
        'completed': '下载完成！',
        'error': '下载失败'
    };
    
    const statusColors = {
        'starting': 'info',
        'getting_info': 'info',
        'downloading_video': 'primary',
        'downloading_subtitles': 'primary',
        'generating_metadata': 'warning',
        'completed': 'success',
        'error': 'danger'
    };
    
    const progressValues = {
        'starting': 10,
        'getting_info': 20,
        'downloading_video': 60,
        'downloading_subtitles': 80,
        'generating_metadata': 90,
        'completed': 100,
        'error': 0
    };
    
    const message = statusMessages[data.status] || data.message || '处理中...';
    const color = statusColors[data.status] || 'info';
    const progress = progressValues[data.status] || 0;
    
    updateProgressBar(progress, message, color);
    
    if (data.status === 'completed') {
        addLogMessage(`下载完成！文件保存在: ${data.output_dir}`);
        resetDownloadButton();
        
        // 3秒后隐藏进度卡片
        setTimeout(() => {
            document.getElementById('progress-card').style.display = 'none';
        }, 3000);
    } else if (data.status === 'error') {
        addLogMessage(`下载失败: ${data.message}`);
        resetDownloadButton();
    }
}

function updateProgressBar(progress, text, status) {
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const progressStatus = document.getElementById('progress-status');
    
    progressBar.style.width = progress + '%';
    progressBar.setAttribute('aria-valuenow', progress);
    progressText.textContent = text;
    
    // 更新状态徽章
    progressStatus.className = `badge bg-${status}`;
    progressStatus.textContent = text;
    
    // 更新进度条颜色
    progressBar.className = `progress-bar progress-bar-striped ${progress < 100 ? 'progress-bar-animated' : ''}`;
    if (status === 'success') {
        progressBar.classList.add('bg-success');
    } else if (status === 'danger') {
        progressBar.classList.add('bg-danger');
    } else if (status === 'warning') {
        progressBar.classList.add('bg-warning');
    }
}

function resetDownloadButton() {
    const downloadBtn = document.getElementById('start-download-btn');
    downloadBtn.disabled = false;
    downloadBtn.innerHTML = '<i class="bi bi-play-circle"></i> 开始下载';
}

function updateConnectionStatus(status, type) {
    const statusElement = document.getElementById('connection-status');
    statusElement.textContent = status;
    statusElement.className = `badge bg-${type}`;
}

function addLogMessage(message) {
    const logOutput = document.getElementById('log-output');
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = document.createElement('div');
    logEntry.textContent = `[${timestamp}] ${message}`;
    logOutput.appendChild(logEntry);
    
    // 自动滚动到底部
    logOutput.scrollTop = logOutput.scrollHeight;
}

function clearLog() {
    document.getElementById('log-output').innerHTML = '';
}

function selectOutputDirectory() {
    // 创建一个模态对话框来选择目录
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">选择输出目录</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">常用目录:</label>
                        <div class="list-group">
                            <button type="button" class="list-group-item list-group-item-action" data-dir="./downloads">
                                <i class="bi bi-folder"></i> ./downloads (默认)
                            </button>
                            <button type="button" class="list-group-item list-group-item-action" data-dir="./videos">
                                <i class="bi bi-folder"></i> ./videos
                            </button>
                            <button type="button" class="list-group-item list-group-item-action" data-dir="C:\\Downloads">
                                <i class="bi bi-folder"></i> C:\\Downloads
                            </button>
                            <button type="button" class="list-group-item list-group-item-action" data-dir="D:\\Downloads">
                                <i class="bi bi-folder"></i> D:\\Downloads
                            </button>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label for="custom-dir" class="form-label">或输入自定义路径:</label>
                        <input type="text" class="form-control" id="custom-dir" placeholder="例如: C:\\MyVideos">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="button" class="btn btn-primary" id="confirm-dir">确认</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // 绑定事件
    modal.querySelectorAll('[data-dir]').forEach(btn => {
        btn.addEventListener('click', function() {
            document.getElementById('custom-dir').value = this.dataset.dir;
        });
    });
    
    modal.querySelector('#confirm-dir').addEventListener('click', function() {
        const customDir = document.getElementById('custom-dir').value.trim();
        if (customDir) {
            document.getElementById('output-dir').value = customDir;
            addLogMessage(`已设置输出目录: ${customDir}`);
            bootstrap.Modal.getInstance(modal).hide();
        } else {
            alert('请选择或输入一个目录路径');
        }
    });
    
    // 显示模态框
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
    
    // 清理
    modal.addEventListener('hidden.bs.modal', function() {
        document.body.removeChild(modal);
    });
}

function uploadCookieFile(file) {
    addLogMessage(`正在上传Cookie文件: ${file.name}`);
    
    const formData = new FormData();
    formData.append('cookie_file', file);
    
    fetch('/api/upload_cookie', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('cookie-file').value = data.filepath;
            addLogMessage(`✓ Cookie文件上传成功: ${data.filename}`);
        } else {
            throw new Error(data.error);
        }
    })
    .catch(error => {
        console.error('Cookie文件上传失败:', error);
        addLogMessage(`❌ Cookie文件上传失败: ${error.message}`);
        document.getElementById('cookie-file').value = '';
    });
}

function generateSessionId() {
    return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
}

// 工具函数：格式化文件大小
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// 工具函数：格式化时间
function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
}