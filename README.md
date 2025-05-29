# YouTube to Emby Metadata Tool (Integrated yt-dlp Nightly Version)

This is a desktop GUI application that integrates the latest yt-dlp nightly version. No local Python or yt-dlp environment is required. It supports one-click updates, automatic restart, and all download and metadata features are based on the nightly version of yt-dlp.

## Main Features

- Built-in yt-dlp nightly version, always up-to-date
- One-click automatic update of yt-dlp, no command line needed
- Automatic application restart after update
- Supports YouTube video download, subtitle download, and Emby NFO metadata generation
- Integrated ffmpeg (no separate installation required)
- Modern Material Design style interface
- No local Python/yt-dlp/ffmpeg dependencies, ready to use after packaging

## System Requirements

- Windows 10/11
- No local Python environment required
- No local yt-dlp/ffmpeg required

## Installation & Usage

1. Download the release or source code of this project
2. Make sure `tools/ffmpeg.exe` and the `yt_dlp/` source folder are in the project root directory
3. Install dependencies (only needed for development/packaging):
   ```bash
   pip install -r requirements.txt
   ```
4. Package as a standalone desktop app (recommended: `--onedir`):
   ```bash
   pyinstaller --noconsole --add-data "tools/ffmpeg.exe;tools" --add-data "yt_dlp;yt_dlp" --add-data "nfo.py;." --hidden-import requests --hidden-import customtkinter --onedir youtube_to_emby_gui.py
   ```
5. Run `dist/youtube_to_emby_gui/youtube_to_emby_gui.exe`

## How to Use

1. Enter the YouTube video URL
2. Select the output directory (default: ./downloads)
3. (Optional) Select a cookie file
4. Choose the video format (MP4/MKV)
5. Click "Start Download"
6. To update yt-dlp, click the "Update yt-dlp" button; the app will restart automatically after updating

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