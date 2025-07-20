# YouTube to Emby Metadata Tool

A comprehensive YouTube video downloader with Emby media server integration. This tool provides both a modern web interface and a desktop GUI application, featuring automatic metadata generation, subtitle download, and seamless Emby NFO file creation.

## 🌟 Main Features

- **Dual Interface Options**: Modern web interface and desktop GUI application
- **Built-in yt-dlp nightly version**: Always up-to-date with latest features
- **One-click setup**: Easy installation with automated dependency management
- **Emby Integration**: Automatic NFO metadata file generation for Emby media server
- **Subtitle Support**: Automatic subtitle download and conversion
- **Multiple Formats**: Support for MP4/MKV video formats
- **Real-time Progress**: Live download progress monitoring
- **Cookie Support**: Login-required content download capability
- **Modern UI**: Material Design interface with responsive layout

## 🚀 Quick Start

### Option 1: Easy Launch (Recommended)
1. Download or clone this repository
2. Run `YouTube_to_Emby.bat` (Windows)
3. Select option `[3]` to install dependencies
4. Select option `[1]` to start the web interface

### Option 2: Manual Setup
1. Install Python 3.7+ if not already installed
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Choose your preferred interface:
   - **Web Interface**: `python app.py` then open http://localhost:5000
   - **Desktop GUI**: `python youtube_to_emby_gui.py`

## 💻 System Requirements

- **Operating System**: Windows 10/11, macOS, or Linux
- **Python**: 3.7 or higher (for source code usage)
- **Internet Connection**: Required for downloads and updates
- **Browser**: Modern web browser (for web interface)

## 🎯 How to Use

### Web Interface (Recommended)
1. Open http://localhost:5000 in your browser
2. Enter the YouTube video URL
3. Configure download settings:
   - Output directory
   - Video format (MP4/MKV)
   - Cookie file (optional)
4. Click "Start Download"
5. Monitor real-time progress in the web interface

### Desktop GUI
1. Launch the desktop application
2. Enter the YouTube video URL
3. Select output directory and format
4. Click "Start Download"
5. Use "Update yt-dlp" button to get latest features

## Version Information

- This tool **only integrates the yt-dlp nightly version**. All updates and usage are based on nightly; stable/master are not supported.
- The version label will show "Current version: xxxxx (nightly)"
- Avoids PyPI/GitHub rate limits and multi-version confusion

## FAQ

- **Update/network failure**: Please check your network or try again later
- **Auto-restart not working**: Please use `--onedir` packaging, do not use `--onefile`
- **Other missing dependencies**: Please install with `pip install -r requirements.txt`

## Development Notes

- The `tools/ffmpeg.exe` file is ignored in version control to reduce repository size
- When packaging the application, make sure to include the `tools/ffmpeg.exe` file in the project root directory
- The packaging command includes all necessary dependencies and data files

## License

MIT License 