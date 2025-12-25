"""
SpeiiKhiev Video Downloader v1.0.0

A powerful multi-platform video downloader supporting:
- Instagram (via instaloader & URL scraper)
- TikTok
- YouTube
- Facebook
- 1000+ other sites via yt-dlp

Features:
- Individual URL downloads
- Profile/Channel fetching
- Instagram URL scraper
- Batch downloads
- 4 filename formats
- Visual selection
- Download tracking
- Auto-update system

Author: SpeiiKhiev
Version: 1.0.0
Release Date: December 2024
"""

import sys
import os
import re
import json
import time
import string
import shutil
import logging
import subprocess
from urllib.parse import urlparse
from threading import Lock
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QProgressBar, QFileDialog, QMessageBox, QTextEdit,
                             QScrollArea, QCheckBox, QFrame, QGridLayout, QPlainTextEdit,
                             QTabWidget, QComboBox, QDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt5.QtGui import QFont, QPixmap, QDesktopServices
import yt_dlp
import requests
from io import BytesIO

# Current version
CURRENT_VERSION = "1.0.0"
VERSION_CHECK_URL = "https://raw.githubusercontent.com/SpeiiKhiev12/speiikhievdownloader/main/version.json"
DOWNLOAD_PAGE_URL = "https://github.com/SpeiiKhiev12/speiikhievdownloader/releases/latest"

# Configure logging
logging.basicConfig(
    filename='video_downloader.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class Config:
    """Configuration manager for persistent settings"""
    def __init__(self):
        self.config_file = 'downloader_config.json'
        self.state_file = 'download_state.json'
        self.load()

    def load(self):
        try:
            with open(self.config_file, 'r') as f:
                self.data = json.load(f)
        except:
            self.data = {
                'save_directory': os.path.expanduser("~/Downloads"),
                'max_videos': 50,
                'filename_format': 0,
                'rate_limit_delay': 2,
                'check_updates': True,
                'last_update_check': 0
            }
            self.save()

    def save(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save config: {e}")

    def save_state(self, videos, downloaded_ids):
        """Save current download state"""
        try:
            state = {
                'videos': videos,
                'downloaded': downloaded_ids,
                'timestamp': time.time()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    def load_state(self):
        """Load previous download state"""
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except:
            return None


class SecurityUtils:
    """Security utilities for input validation and sanitization"""

    @staticmethod
    def is_valid_url(url):
        """Validate URL format and scheme"""
        try:
            result = urlparse(url)
            if result.scheme not in ['http', 'https']:
                return False
            if not result.netloc:
                return False
            if '..' in url or url.count('/') > 10:
                return False
            return True
        except Exception as e:
            logging.warning(f"URL validation failed: {e}")
            return False

    @staticmethod
    def sanitize_filename(filename):
        """Remove invalid filename characters and prevent path traversal"""
        if not filename:
            return "video"

        filename = filename.replace('..', '').replace('/', '').replace('\\', '')
        valid_chars = f"-_.() {string.ascii_letters}{string.digits}"
        sanitized = ''.join(c if c in valid_chars else '_' for c in filename)
        sanitized = sanitized.strip('. ')
        sanitized = os.path.basename(sanitized)

        if len(sanitized) > 100:
            sanitized = sanitized[:100]

        return sanitized if sanitized else "video"

    @staticmethod
    def sanitize_path(filepath):
        """Ensure filepath is safe and within intended directory"""
        abs_path = os.path.abspath(filepath)
        real_path = os.path.realpath(abs_path)
        return real_path

    @staticmethod
    def check_disk_space(path, required_mb=100):
        """Check if enough disk space is available"""
        try:
            stat = shutil.disk_usage(path)
            free_mb = stat.free / (1024 * 1024)
            return free_mb > required_mb, free_mb
        except Exception as e:
            logging.error(f"Disk space check failed: {e}")
            return True, 0


class VersionCheckThread(QThread):
    """Thread to check for updates"""
    update_available = pyqtSignal(str, str, str)  # new_version, download_url, changelog
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version

    def run(self):
        try:
            # Check version from GitHub or your server
            response = requests.get(VERSION_CHECK_URL, timeout=10)

            if response.status_code == 200:
                version_data = response.json()
                latest_version = version_data.get('version', '1.0.0')
                download_url = version_data.get('download_url', DOWNLOAD_PAGE_URL)
                changelog = version_data.get('changelog', 'New version available!')

                # Compare versions
                if self.is_newer_version(latest_version, self.current_version):
                    self.update_available.emit(latest_version, download_url, changelog)
                else:
                    self.no_update.emit()
            else:
                self.error.emit("Failed to check for updates")

        except Exception as e:
            logging.error(f"Version check failed: {e}")
            self.error.emit(str(e))

    def is_newer_version(self, latest, current):
        """Compare version strings (e.g., '2.0.0' > '1.0.0')"""
        try:
            latest_parts = [int(x) for x in latest.split('.')]
            current_parts = [int(x) for x in current.split('.')]
            return latest_parts > current_parts
        except:
            return False


class UpdateDialog(QDialog):
    """Dialog to show update information and download"""
    def __init__(self, new_version, download_url, changelog, parent=None):
        super().__init__(parent)
        self.new_version = new_version
        self.download_url = download_url
        self.changelog = changelog
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Update Available")
        self.setFixedSize(500, 400)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QPushButton {
                background-color: #0095f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0081d8;
            }
            QPushButton#secondaryBtn {
                background-color: #3d3d3d;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #4d4d4d;
            }
            QTextEdit {
                background-color: #2d2d2d;
                border: 2px solid #3d3d3d;
                border-radius: 8px;
                padding: 10px;
                color: #ffffff;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Title
        title = QLabel(f"🎉 New Version Available: v{self.new_version}")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet("color: #00d26a;")
        layout.addWidget(title)

        # Current version
        current_label = QLabel(f"Current version: v{CURRENT_VERSION}")
        current_label.setStyleSheet("color: #8e8e8e; font-size: 11px;")
        layout.addWidget(current_label)

        # Changelog
        changelog_label = QLabel("What's New:")
        changelog_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(changelog_label)

        changelog_text = QTextEdit()
        changelog_text.setReadOnly(True)
        changelog_text.setMaximumHeight(200)
        changelog_text.setPlainText(self.changelog)
        layout.addWidget(changelog_text)

        # Buttons
        button_layout = QHBoxLayout()

        self.download_btn = QPushButton("Download Update")
        self.download_btn.clicked.connect(self.download_update)
        button_layout.addWidget(self.download_btn)

        self.later_btn = QPushButton("Remind Me Later")
        self.later_btn.setObjectName("secondaryBtn")
        self.later_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.later_btn)

        layout.addLayout(button_layout)

        # Info
        info_label = QLabel("💡 You can also download manually from GitHub")
        info_label.setStyleSheet("color: #8e8e8e; font-size: 9px; font-style: italic;")
        layout.addWidget(info_label)

        self.setLayout(layout)

    def download_update(self):
        """Open download page in browser"""
        try:
            QDesktopServices.openUrl(QUrl(self.download_url))
            QMessageBox.information(
                self,
                "Opening Browser",
                "The download page will open in your browser.\n\n"
                "After downloading:\n"
                "1. Close this application\n"
                "2. Replace the old file with the new one\n"
                "3. Run the new version"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open browser: {e}")


class ProfileFetchThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str, list)
    status_update = pyqtSignal(str)

    def __init__(self, url, max_videos=50):
        super().__init__()
        self.url = url
        self.max_videos = max_videos
        self._is_running = True

    def stop(self):
        self._is_running = False

    def detect_platform(self, url):
        url_lower = url.lower()
        if 'tiktok.com' in url_lower:
            return 'TikTok'
        elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'YouTube'
        elif 'instagram.com' in url_lower:
            return 'Instagram'
        elif 'facebook.com' in url_lower or 'fb.com' in url_lower:
            return 'Facebook'
        return 'Unknown'

    def extract_instagram_username(self, url):
        patterns = [
            r'instagram\.com/([^/\?]+)',
            r'instagram\.com/@([^/\?]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                username = match.group(1)
                username = username.split('?')[0].strip('/')
                return username
        return None

    def scrape_instagram_with_instaloader(self, username):
        try:
            import instaloader

            self.status_update.emit("Using instaloader for Instagram...")

            L = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
            )

            profile = instaloader.Profile.from_username(L.context, username)

            self.status_update.emit(f"Found profile: {profile.full_name}")
            self.status_update.emit(f"Total posts: {profile.mediacount}")

            videos = []
            count = 0

            for post in profile.get_posts():
                if not self._is_running:
                    break

                if count >= self.max_videos:
                    break
                count += 1

                if post.is_video:
                    video_url = f"https://www.instagram.com/p/{post.shortcode}/"

                    video_info = {
                        'id': post.shortcode,
                        'title': (post.caption[:100] if post.caption else 'Untitled'),
                        'url': video_url,
                        'thumbnail': post.url,
                        'duration': post.video_duration if hasattr(post, 'video_duration') else 0,
                        'view_count': post.video_view_count if hasattr(post, 'video_view_count') else 0,
                        'like_count': post.likes,
                    }
                    videos.append(video_info)
                    self.status_update.emit(f"Found video {len(videos)}: {post.shortcode}")

                progress = 60 + int((count / self.max_videos) * 30)
                self.progress.emit(progress)
                time.sleep(0.5)

            return videos

        except Exception as e:
            raise e

    def run(self):
        try:
            if not self._is_running:
                return

            platform = self.detect_platform(self.url)
            self.status_update.emit(f"Detected platform: {platform}")
            self.progress.emit(10)

            if platform == 'Instagram':
                try:
                    import instaloader
                    instagram_available = True
                except ImportError:
                    instagram_available = False

                if instagram_available:
                    username = self.extract_instagram_username(self.url)
                    if not username:
                        self.finished.emit(False, "Could not extract Instagram username from URL", [])
                        return

                    self.status_update.emit(f"Fetching Instagram profile: @{username}")
                    self.progress.emit(30)

                    try:
                        videos = self.scrape_instagram_with_instaloader(username)

                        if videos and self._is_running:
                            self.progress.emit(100)
                            self.finished.emit(True, f"Found {len(videos)} videos from Instagram", videos)
                        else:
                            self.finished.emit(False, "No videos found in this Instagram profile", [])
                        return

                    except Exception as e:
                        error_msg = str(e)
                        logging.error(f"Instagram fetch error: {error_msg}")
                        if "private" in error_msg.lower():
                            self.finished.emit(False, "This Instagram profile is private.\n\nPlease use Tab 1 (Individual URLs) instead.", [])
                        elif "429" in error_msg or "rate" in error_msg.lower():
                            self.finished.emit(False, "Instagram rate limit reached.\n\nPlease wait 10-15 minutes.", [])
                        else:
                            self.finished.emit(False, f"Instagram error: {error_msg}", [])
                        return
                else:
                    self.finished.emit(False, "Instagram scraping requires 'instaloader'.\n\nInstall: pip install instaloader", [])
                    return

            if not self._is_running:
                return

            self.status_update.emit(f"Fetching {platform} profile...")
            self.progress.emit(30)

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'playlistend': self.max_videos,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)

                if not info:
                    self.finished.emit(False, "Could not fetch profile information", [])
                    return

                self.progress.emit(60)

                videos = []
                entries = info.get('entries', [])

                if not entries:
                    self.finished.emit(False, f"No videos found in this {platform} profile.", [])
                    return

                for idx, entry in enumerate(entries):
                    if not self._is_running:
                        break

                    if entry:
                        video_id = entry.get('id', f'video_{idx}')
                        title = entry.get('title', 'Untitled')
                        video_url = entry.get('url') or entry.get('webpage_url', '')

                        if not video_url.startswith('http'):
                            if platform == 'TikTok':
                                video_url = f"https://www.tiktok.com/@user/video/{video_id}"
                            elif platform == 'YouTube':
                                video_url = f"https://www.youtube.com/watch?v={video_id}"

                        video_info = {
                            'id': video_id,
                            'title': title[:100],
                            'url': video_url,
                            'thumbnail': entry.get('thumbnail', ''),
                            'duration': entry.get('duration', 0),
                            'view_count': entry.get('view_count', 0),
                            'like_count': entry.get('like_count', 0),
                        }
                        videos.append(video_info)

                    progress = 60 + int((idx / len(entries)) * 30)
                    self.progress.emit(progress)

                self.progress.emit(100)

                if videos and self._is_running:
                    self.finished.emit(True, f"Found {len(videos)} videos from {platform}", videos)
                else:
                    self.finished.emit(False, "No videos found in profile", [])

        except Exception as e:
            error_msg = str(e)
            logging.error(f"Profile fetch error: {error_msg}")
            self.finished.emit(False, f"Error: {error_msg}", [])


class VideoInfoThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str, list)
    status_update = pyqtSignal(str)

    def __init__(self, urls):
        super().__init__()
        self.urls = urls
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            videos = []
            total = len(self.urls)

            for idx, url in enumerate(self.urls, 1):
                if not self._is_running:
                    break

                try:
                    if not SecurityUtils.is_valid_url(url):
                        self.status_update.emit(f"⚠️ Invalid URL {idx}: Skipping")
                        logging.warning(f"Invalid URL rejected: {url}")
                        continue

                    self.status_update.emit(f"Extracting info {idx}/{total}...")
                    self.progress.emit(int((idx / total) * 90))

                    ydl_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'skip_download': True,
                    }

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)

                        if info:
                            title = info.get('title', '')
                            description = info.get('description', '')

                            if 'instagram.com' in url:
                                if description and description != title:
                                    caption_lines = description.split('\n')
                                    title = caption_lines[0] if caption_lines else title
                                    if len(title) > 100:
                                        title = title[:100]

                            if not title or title == 'Untitled':
                                uploader = info.get('uploader', info.get('channel', 'unknown'))
                                upload_date = info.get('upload_date', '')
                                if upload_date:
                                    title = f"{uploader}_{upload_date}"
                                else:
                                    title = f"{uploader}_video"

                            video_info = {
                                'id': info.get('id', '') or info.get('display_id', f'video_{idx}'),
                                'title': title,
                                'url': url,
                                'thumbnail': info.get('thumbnail', ''),
                                'duration': info.get('duration', 0),
                                'view_count': info.get('view_count', 0),
                                'like_count': info.get('like_count', 0),
                            }
                            videos.append(video_info)

                except Exception as e:
                    self.status_update.emit(f"⚠️ Failed: {str(e)[:50]}")
                    logging.error(f"Failed to extract info from {url}: {e}")

            self.progress.emit(100)

            if videos and self._is_running:
                self.finished.emit(True, f"Loaded {len(videos)} videos", videos)
            else:
                self.finished.emit(False, "No valid URLs found", [])

        except Exception as e:
            logging.error(f"VideoInfoThread error: {e}")
            self.finished.emit(False, f"Error: {str(e)}", [])


class DownloadThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, str)
    status_update = pyqtSignal(str)

    def __init__(self, videos, save_path, filename_format=0, rate_limit_delay=2):
        super().__init__()
        self.videos = videos
        self.save_path = save_path
        self.filename_format = filename_format
        self.rate_limit_delay = rate_limit_delay
        self._is_running = True

    def stop(self):
        self._is_running = False

    def is_already_downloaded(self, video_id, save_path):
        try:
            for filename in os.listdir(save_path):
                if str(video_id) in filename:
                    return True
        except:
            pass
        return False

    def progress_hook(self, d, video_id):
        if not self._is_running:
            raise Exception("Download cancelled")

        if d['status'] == 'downloading':
            if 'downloaded_bytes' in d and 'total_bytes' in d:
                percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                self.progress.emit(int(percent), video_id)
        elif d['status'] == 'finished':
            self.progress.emit(100, video_id)

    def run(self):
        try:
            total = len(self.videos)
            success_count = 0
            failed_count = 0

            for idx, video in enumerate(self.videos, 1):
                if not self._is_running:
                    break

                try:
                    video_id = video['id']
                    title = video['title']
                    url = video['url']

                    if self.is_already_downloaded(video_id, self.save_path):
                        success_count += 1
                        self.finished.emit(True, f"✓ Already exists: {title[:50]}", video_id)
                        continue

                    clean_title = SecurityUtils.sanitize_filename(title)

                    if self.filename_format == 0:
                        final_filename = f'{idx:02d}_{clean_title}'
                    elif self.filename_format == 1:
                        safe_id = SecurityUtils.sanitize_filename(str(video_id))[:30]
                        final_filename = safe_id
                    elif self.filename_format == 2:
                        safe_id = SecurityUtils.sanitize_filename(str(video_id))[:10]
                        final_filename = f'{idx:02d}_{clean_title}_{safe_id}'
                    else:
                        final_filename = clean_title

                    final_filename = SecurityUtils.sanitize_filename(final_filename)

                    self.status_update.emit(f"[{idx}/{total}] Downloading: {title[:50]}...")

                    output_template = os.path.join(self.save_path, f'{final_filename}.%(ext)s')
                    output_template = SecurityUtils.sanitize_path(output_template)

                    ydl_opts = {
                        'format': 'best',
                        'outtmpl': output_template,
                        'progress_hooks': [lambda d, vid=video_id: self.progress_hook(d, vid)],
                        'quiet': True,
                        'no_warnings': True,
                    }

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])

                    success_count += 1
                    self.finished.emit(True, f"✓ Downloaded: {title[:50]}", video_id)

                    if idx < total and self.rate_limit_delay > 0:
                        time.sleep(self.rate_limit_delay)

                except Exception as e:
                    failed_count += 1
                    self.finished.emit(False, f"✗ Failed: {title[:50]}", video_id)
                    logging.error(f"Download failed: {e}")

            if self._is_running:
                self.status_update.emit(f"\n🎉 Complete! Success: {success_count}, Failed: {failed_count}")

        except Exception as e:
            self.status_update.emit(f"Error: {str(e)}")


class InstagramScraperThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, list)

    def __init__(self, username, max_posts=50):
        super().__init__()
        self.username = username
        self.max_posts = max_posts
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            import instaloader

            self.progress.emit(10, "Connecting...")

            L = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
            )

            self.progress.emit(30, f"Fetching: @{self.username}")

            profile = instaloader.Profile.from_username(L.context, self.username)

            self.progress.emit(50, f"Found: {profile.full_name}")

            video_urls = []
            count = 0

            for post in profile.get_posts():
                if not self._is_running or count >= self.max_posts:
                    break
                count += 1

                if post.is_video:
                    url = f"https://www.instagram.com/p/{post.shortcode}/"
                    video_urls.append(url)
                    self.progress.emit(50 + int((count / self.max_posts) * 40), f"Found {len(video_urls)} videos")

                time.sleep(0.5)

            self.progress.emit(100, "Complete!")

            if video_urls and self._is_running:
                self.finished.emit(True, f"Found {len(video_urls)} videos!", video_urls)
            else:
                self.finished.emit(False, "No videos found", [])

        except Exception as e:
            logging.error(f"Instagram scraper error: {e}")
            self.finished.emit(False, str(e), [])


class VideoWidget(QFrame):
    def __init__(self, video_info, parent=None):
        super().__init__(parent)
        self.video_info = video_info
        self.download_status = None
        self.thumbnail_pixmap = None
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setStyleSheet("""
            VideoWidget {
                background-color: #2d2d2d;
                border: 2px solid #3d3d3d;
                border-radius: 8px;
                padding: 10px;
            }
            VideoWidget:hover {
                border: 2px solid #0095f6;
            }
            VideoWidget[downloaded="true"] {
                background-color: #1a3a2a;
                border: 2px solid #00d26a;
            }
            VideoWidget[failed="true"] {
                background-color: #3a1a1a;
                border: 2px solid #ff4444;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(8)

        self.status_indicator = QLabel()
        self.status_indicator.setAlignment(Qt.AlignCenter)
        self.status_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.7);
                color: white;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
            }
        """)
        self.status_indicator.hide()

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(200, 200)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
        self.load_thumbnail()
        layout.addWidget(self.thumbnail_label, alignment=Qt.AlignCenter)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setStyleSheet("""
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 2px solid #0095f6;
                background-color: #2d2d2d;
            }
            QCheckBox::indicator:checked {
                background-color: #0095f6;
            }
        """)
        layout.addWidget(self.checkbox)
        layout.addWidget(self.status_indicator)

        title = self.video_info['title'][:60] + ('...' if len(self.video_info['title']) > 60 else '')
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")
        layout.addWidget(title_label)

        url_short = self.video_info['url'][:40] + '...' if len(self.video_info['url']) > 40 else self.video_info['url']
        url_label = QLabel(f"🔗 {url_short}")
        url_label.setStyleSheet("color: #8e8e8e; font-size: 10px;")
        layout.addWidget(url_label)

        self.setLayout(layout)

    def load_thumbnail(self):
        try:
            thumbnail_url = self.video_info.get('thumbnail', '')
            if thumbnail_url:
                response = requests.get(thumbnail_url, timeout=5)
                image_data = BytesIO(response.content)

                self.thumbnail_pixmap = QPixmap()
                self.thumbnail_pixmap.loadFromData(image_data.getvalue())

                scaled_pixmap = self.thumbnail_pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumbnail_label.setPixmap(scaled_pixmap)

                image_data.close()
                response.close()
            else:
                self.thumbnail_label.setText("📹")
                self.thumbnail_label.setStyleSheet("color: #666666; font-size: 48px; background-color: #1a1a1a;")
        except:
            self.thumbnail_label.setText("📹")
            self.thumbnail_label.setStyleSheet("color: #666666; font-size: 48px; background-color: #1a1a1a;")

    def is_selected(self):
        return self.checkbox.isChecked()

    def mark_downloaded(self):
        self.download_status = 'success'
        self.setProperty("downloaded", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        self.status_indicator.setText("✓ DOWNLOADED")
        self.status_indicator.setStyleSheet("background-color: #00d26a; color: white; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
        self.status_indicator.show()
        self.checkbox.setChecked(False)

    def mark_failed(self):
        self.download_status = 'failed'
        self.setProperty("failed", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        self.status_indicator.setText("✗ FAILED")
        self.status_indicator.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
        self.status_indicator.show()

    def cleanup(self):
        if self.thumbnail_pixmap:
            del self.thumbnail_pixmap


class InstagramBatchDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.video_widgets = []
        self.config = Config()
        self.save_directory = self.config.data['save_directory']
        self.info_thread = None
        self.download_thread = None
        self.profile_thread = None
        self.version_check_thread = None
        self.state_lock = Lock()
        self.init_ui()

        # Check for updates on startup
        self.check_for_updates_auto()

    def init_ui(self):
        self.setWindowTitle(f"SpeiiKhiev Video Downloader v{CURRENT_VERSION}")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1a1a1a;
                color: #ffffff;
                font-family: 'Segoe UI', Arial;
            }
            QLineEdit, QPlainTextEdit {
                background-color: #2d2d2d;
                border: 2px solid #3d3d3d;
                border-radius: 8px;
                padding: 12px;
                color: #ffffff;
            }
            QLineEdit:focus, QPlainTextEdit:focus { border: 2px solid #0095f6; }
            QPushButton {
                background-color: #0095f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0081d8; }
            QPushButton:disabled { background-color: #3d3d3d; color: #666666; }
            QPushButton#secondaryBtn { background-color: #3d3d3d; }
            QPushButton#secondaryBtn:hover { background-color: #4d4d4d; }
            QPushButton#updateBtn {
                background-color: #00d26a;
                color: white;
            }
            QPushButton#updateBtn:hover {
                background-color: #00b85a;
            }
            QProgressBar {
                border: 2px solid #3d3d3d;
                border-radius: 8px;
                background-color: #2d2d2d;
                text-align: center;
                height: 30px;
            }
            QProgressBar::chunk { background-color: #0095f6; border-radius: 6px; }
            QTextEdit {
                background-color: #2d2d2d;
                border: 2px solid #3d3d3d;
                border-radius: 8px;
                padding: 10px;
                color: #ffffff;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(30, 30, 30, 30)

        # Title with version (clickable)
        title_layout = QHBoxLayout()

        title = QLabel("SpeiiKhiev")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title_layout.addWidget(title)

        title_layout.addStretch()

        # Clickable version label
        self.version_label = QPushButton(f"V{CURRENT_VERSION}")
        self.version_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.version_label.setObjectName("secondaryBtn")
        self.version_label.setToolTip("Click to check for updates")
        self.version_label.clicked.connect(self.check_for_updates_manual)
        self.version_label.setCursor(Qt.PointingHandCursor)
        title_layout.addWidget(self.version_label)

        # Update button (hidden by default)
        self.update_btn = QPushButton("Update Available!")
        self.update_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.update_btn.setObjectName("updateBtn")
        self.update_btn.hide()
        self.update_btn.clicked.connect(self.show_update_dialog)
        title_layout.addWidget(self.update_btn)

        main_layout.addLayout(title_layout)

        subtitle = QLabel("Download from Instagram, TikTok, YouTube & more • Auto-detects platform")
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setStyleSheet("color: #8e8e8e; margin-bottom: 10px;")
        main_layout.addWidget(subtitle)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #3d3d3d;
                border-radius: 8px;
                background-color: #1a1a1a;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #ffffff;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background-color: #0095f6;
            }
            QTabBar::tab:hover {
                background-color: #3d3d3d;
            }
        """)

        # Tab 1: Individual URLs
        urls_tab = QWidget()
        urls_layout = QVBoxLayout()
        urls_layout.setSpacing(10)
        urls_layout.setContentsMargins(10, 10, 10, 10)

        url_label = QLabel("📝 Paste Video URLs (one per line):")
        url_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        urls_layout.addWidget(url_label)

        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText(
            "Example:\n"
            "https://www.instagram.com/p/ABC123/\n"
            "https://www.youtube.com/watch?v=...\n"
            "https://www.tiktok.com/@user/video/..."
        )
        self.url_input.setMinimumHeight(100)
        self.url_input.setMaximumHeight(150)
        urls_layout.addWidget(self.url_input)

        url_button_layout = QHBoxLayout()
        self.clear_btn = QPushButton("Clear URLs")
        self.clear_btn.setObjectName("secondaryBtn")
        self.clear_btn.clicked.connect(lambda: self.url_input.clear())
        url_button_layout.addWidget(self.clear_btn)
        url_button_layout.addStretch()
        self.load_btn = QPushButton("Load Videos")
        self.load_btn.setMinimumWidth(150)
        self.load_btn.clicked.connect(self.load_videos)
        url_button_layout.addWidget(self.load_btn)
        urls_layout.addLayout(url_button_layout)

        urls_tab.setLayout(urls_layout)
        self.tab_widget.addTab(urls_tab, "📝 Individual URLs")

        # Tab 2: Profile/Channel
        profile_tab = QWidget()
        profile_layout = QVBoxLayout()
        profile_layout.setSpacing(10)
        profile_layout.setContentsMargins(10, 10, 10, 10)

        profile_label = QLabel("👤 Fetch Entire Profile/Channel:")
        profile_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        profile_layout.addWidget(profile_label)

        self.profile_input = QLineEdit()
        self.profile_input.setPlaceholderText("Paste profile URL")
        self.profile_input.setMinimumHeight(45)
        profile_layout.addWidget(self.profile_input)

        limit_layout = QHBoxLayout()
        limit_label = QLabel("Max videos:")
        limit_layout.addWidget(limit_label)

        self.limit_input = QLineEdit()
        self.limit_input.setText(str(self.config.data.get('max_videos', 50)))
        self.limit_input.setMaximumWidth(80)
        limit_layout.addWidget(self.limit_input)

        limit_layout.addStretch()

        self.fetch_btn = QPushButton("Fetch Profile Videos")
        self.fetch_btn.setMinimumWidth(180)
        self.fetch_btn.clicked.connect(self.fetch_profile)
        limit_layout.addWidget(self.fetch_btn)

        profile_layout.addLayout(limit_layout)
        profile_layout.addStretch()

        profile_tab.setLayout(profile_layout)
        self.tab_widget.addTab(profile_tab, "👤 Profile/Channel")

        main_layout.addWidget(self.tab_widget)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(30)
        main_layout.addWidget(self.progress_bar)

        # Controls
        controls_layout = QHBoxLayout()
        self.video_count_label = QLabel("Videos: 0 | Selected: 0")
        self.video_count_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        controls_layout.addWidget(self.video_count_label)
        controls_layout.addStretch()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setObjectName("secondaryBtn")
        self.select_all_btn.clicked.connect(self.select_all)
        self.select_all_btn.setEnabled(False)
        controls_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.setObjectName("secondaryBtn")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        self.deselect_all_btn.setEnabled(False)
        controls_layout.addWidget(self.deselect_all_btn)
        main_layout.addLayout(controls_layout)

        # Videos grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(250)
        self.videos_container = QWidget()
        self.videos_layout = QGridLayout()
        self.videos_layout.setSpacing(15)
        self.videos_container.setLayout(self.videos_layout)
        self.scroll_area.setWidget(self.videos_container)
        main_layout.addWidget(self.scroll_area)

        # Download controls
        download_layout = QHBoxLayout()

        format_label = QLabel("Filename format:")
        format_label.setStyleSheet("font-weight: bold;")
        download_layout.addWidget(format_label)

        self.filename_format = QComboBox()
        self.filename_format.addItems([
            "Number_Filename (01_Filename)",
            "Video ID (Caption TXT file)",
            "Number_Filename_ID (unique)",
            "Title only"
        ])
        self.filename_format.setCurrentIndex(0)
        self.filename_format.setMinimumWidth(250)
        download_layout.addWidget(self.filename_format)

        download_layout.addStretch()

        self.location_input = QLineEdit()
        self.location_input.setText(self.save_directory)
        self.location_input.setReadOnly(True)
        self.location_input.setMinimumHeight(45)
        download_layout.addWidget(self.location_input)

        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self.browse_directory)
        download_layout.addWidget(browse_btn)

        self.download_btn = QPushButton("Download Selected")
        self.download_btn.setMinimumHeight(45)
        self.download_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setEnabled(False)
        download_layout.addWidget(self.download_btn)
        main_layout.addLayout(download_layout)

        # Counters
        counters_layout = QHBoxLayout()
        self.reset_btn = QPushButton("Reset Selection")
        self.reset_btn.setObjectName("secondaryBtn")
        self.reset_btn.clicked.connect(self.reset_selection)
        self.reset_btn.setEnabled(False)
        counters_layout.addWidget(self.reset_btn)
        counters_layout.addStretch()

        self.downloaded_label = QLabel("Downloaded: 0")
        self.downloaded_label.setStyleSheet("color: #8e8e8e; font-weight: bold;")
        counters_layout.addWidget(self.downloaded_label)

        self.failed_label = QLabel("Failed: 0")
        self.failed_label.setStyleSheet("color: #8e8e8e; font-weight: bold;")
        counters_layout.addWidget(self.failed_label)

        self.disk_space_label = QLabel()
        self.disk_space_label.setStyleSheet("color: #8e8e8e; font-size: 10px;")
        counters_layout.addWidget(self.disk_space_label)
        self.update_disk_space()

        main_layout.addLayout(counters_layout)

        # Status log
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(100)
        self.status_text.append("✓ Ready - Paste video URLs and click Load Videos")
        self.status_text.append("💡 Works with Instagram, YouTube, TikTok, and 1000+ sites!")
        main_layout.addWidget(self.status_text)

        central_widget.setLayout(main_layout)

    def check_for_updates_auto(self):
        """Check for updates automatically on startup"""
        # Check only once per day
        last_check = self.config.data.get('last_update_check', 0)
        if time.time() - last_check < 86400:  # 24 hours
            return

        if self.config.data.get('check_updates', True):
            self.check_for_updates(silent=True)

    def check_for_updates_manual(self):
        """Check for updates when user clicks version"""
        self.check_for_updates(silent=False)

    def check_for_updates(self, silent=False):
        """Check for updates"""
        if not silent:
            self.log_status("\n🔍 Checking for updates...")

        # Clean up existing thread
        if self.version_check_thread and self.version_check_thread.isRunning():
            return

        self.version_check_thread = VersionCheckThread(CURRENT_VERSION)
        self.version_check_thread.update_available.connect(
            lambda v, u, c: self.on_update_available(v, u, c, silent)
        )
        self.version_check_thread.no_update.connect(
            lambda: self.on_no_update(silent)
        )
        self.version_check_thread.error.connect(
            lambda e: self.on_update_error(e, silent)
        )
        self.version_check_thread.start()

        # Update last check time
        self.config.data['last_update_check'] = time.time()
        self.config.save()

    def on_update_available(self, new_version, download_url, changelog, silent):
        """Handle update available"""
        self.latest_version = new_version
        self.download_url = download_url
        self.changelog = changelog

        # Show update button
        self.update_btn.setText(f"Update to v{new_version}")
        self.update_btn.show()
        self.version_label.setStyleSheet("color: #ff9500;")

        self.log_status(f"\n🎉 Update available: v{new_version}")

        if not silent:
            self.show_update_dialog()

    def on_no_update(self, silent):
        """Handle no update available"""
        if not silent:
            self.log_status("\n✓ You're using the latest version!")
            QMessageBox.information(
                self,
                "No Updates",
                f"You're using the latest version (v{CURRENT_VERSION})"
            )

    def on_update_error(self, error, silent):
        """Handle update check error"""
        if not silent:
            self.log_status(f"\n⚠️ Update check failed: {error}")

    def show_update_dialog(self):
        """Show update dialog"""
        if hasattr(self, 'latest_version'):
            dialog = UpdateDialog(
                self.latest_version,
                self.download_url,
                self.changelog,
                self
            )
            dialog.exec_()

    def update_disk_space(self):
        """Update disk space indicator"""
        try:
            has_space, free_mb = SecurityUtils.check_disk_space(self.save_directory)
            free_gb = free_mb / 1024

            if free_gb < 1:
                color = "#ff4444"
                text = f"⚠️ {free_mb:.0f}MB free"
            elif free_gb < 5:
                color = "#ff9500"
                text = f"💾 {free_gb:.1f}GB free"
            else:
                color = "#00d26a"
                text = f"💾 {free_gb:.1f}GB free"

            self.disk_space_label.setText(text)
            self.disk_space_label.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: bold;")
        except:
            pass

    def cleanup_thread(self, thread):
        """Safely cleanup a thread"""
        if thread:
            if thread.isRunning():
                thread.stop()
                thread.quit()
                thread.wait(5000)
            try:
                thread.deleteLater()
            except:
                pass
        return None

    def fetch_profile(self):
        """Fetch videos from profile"""
        url = self.profile_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a profile URL")
            return

        if not SecurityUtils.is_valid_url(url):
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid URL")
            return

        try:
            max_videos = int(self.limit_input.text() or "50")
        except:
            max_videos = 50

        has_space, free_mb = SecurityUtils.check_disk_space(self.save_directory)
        if not has_space:
            QMessageBox.warning(self, "Low Disk Space", f"Only {free_mb:.0f}MB free")
            return

        self.clear_videos()
        self.fetch_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_status(f"\n🔍 Fetching profile: {url}")

        self.profile_thread = ProfileFetchThread(url, max_videos)
        self.profile_thread.progress.connect(self.progress_bar.setValue)
        self.profile_thread.status_update.connect(self.log_status)
        self.profile_thread.finished.connect(self.profile_fetched)
        self.profile_thread.start()

    def profile_fetched(self, success, message, videos):
        """Handle profile fetch completion"""
        self.fetch_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.profile_thread = self.cleanup_thread(self.profile_thread)

        if success:
            self.log_status(f"✓ {message}")
            self.display_videos(videos)
            self.select_all_btn.setEnabled(True)
            self.deselect_all_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
        else:
            self.log_status(f"✗ {message}")
            QMessageBox.critical(self, "Error", message)

    def load_videos(self):
        """Load videos from URLs"""
        urls_text = self.url_input.toPlainText().strip()
        if not urls_text:
            QMessageBox.warning(self, "Error", "Please paste video URLs")
            return

        urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
        if not urls:
            return

        valid_urls = [url for url in urls if SecurityUtils.is_valid_url(url)]

        if len(valid_urls) < len(urls):
            QMessageBox.warning(
                self,
                "Invalid URLs",
                f"{len(urls) - len(valid_urls)} invalid URLs removed"
            )

        if not valid_urls:
            QMessageBox.warning(self, "No Valid URLs", "No valid URLs found")
            return

        self.clear_videos()
        self.load_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_status(f"\n📥 Loading {len(valid_urls)} video(s)...")

        self.info_thread = VideoInfoThread(valid_urls)
        self.info_thread.progress.connect(self.progress_bar.setValue)
        self.info_thread.status_update.connect(self.log_status)
        self.info_thread.finished.connect(self.videos_loaded)
        self.info_thread.start()

    def videos_loaded(self, success, message, videos):
        """Handle videos loaded"""
        self.load_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.info_thread = self.cleanup_thread(self.info_thread)

        if success:
            self.log_status(f"✓ {message}")
            self.display_videos(videos)
            self.select_all_btn.setEnabled(True)
            self.deselect_all_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
        else:
            self.log_status(f"✗ {message}")

    def display_videos(self, videos):
        """Display videos in grid"""
        for i in reversed(range(self.videos_layout.count())):
            widget = self.videos_layout.itemAt(i).widget()
            if widget:
                widget.cleanup()
                widget.setParent(None)

        self.video_widgets.clear()
        row, col = 0, 0

        for video in videos:
            widget = VideoWidget(video)
            widget.checkbox.stateChanged.connect(self.update_selection_count)
            self.video_widgets.append(widget)
            self.videos_layout.addWidget(widget, row, col)
            col += 1
            if col >= 3:
                col, row = 0, row + 1

        self.update_selection_count()

    def clear_videos(self):
        """Clear all videos"""
        for i in reversed(range(self.videos_layout.count())):
            widget = self.videos_layout.itemAt(i).widget()
            if widget:
                widget.cleanup()
                widget.setParent(None)
        self.video_widgets.clear()
        self.update_selection_count()

    def update_selection_count(self):
        """Update selection count"""
        total = len(self.video_widgets)
        selected = sum(1 for w in self.video_widgets if w.is_selected())
        self.video_count_label.setText(f"Videos: {total} | Selected: {selected}")
        self.download_btn.setEnabled(selected > 0)

    def select_all(self):
        for w in self.video_widgets:
            w.checkbox.setChecked(True)

    def deselect_all(self):
        for w in self.video_widgets:
            w.checkbox.setChecked(False)

    def reset_selection(self):
        for w in self.video_widgets:
            if w.download_status == 'success':
                w.checkbox.setChecked(False)

    def browse_directory(self):
        """Browse for save directory"""
        directory = QFileDialog.getExistingDirectory(self, "Select Directory", self.save_directory)
        if directory:
            self.save_directory = directory
            self.location_input.setText(directory)
            self.config.data['save_directory'] = directory
            self.config.save()
            self.update_disk_space()

    def start_download(self):
        """Start downloading selected videos"""
        selected = [w.video_info for w in self.video_widgets if w.is_selected()]
        if not selected:
            return

        has_space, free_mb = SecurityUtils.check_disk_space(self.save_directory, 500)
        if not has_space:
            reply = QMessageBox.warning(
                self,
                "Low Disk Space",
                f"Only {free_mb:.0f}MB free. Continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        self.download_thread = self.cleanup_thread(self.download_thread)

        self.download_btn.setEnabled(False)
        self.log_status(f"\n⬇️ Downloading {len(selected)} video(s)...")

        format_index = self.filename_format.currentIndex()
        self.download_thread = DownloadThread(selected, self.save_directory, format_index, 2)
        self.download_thread.status_update.connect(self.log_status)
        self.download_thread.finished.connect(self.video_downloaded)
        self.download_thread.start()

    def video_downloaded(self, success, message, video_id):
        """Handle video download completion"""
        self.log_status(message)

        for w in self.video_widgets:
            if w.video_info['id'] == video_id:
                w.mark_downloaded() if success else w.mark_failed()
                break

        self.update_counters()

        if "Complete!" in message:
            self.download_thread = self.cleanup_thread(self.download_thread)
            self.download_btn.setEnabled(True)
            self.update_selection_count()

            downloaded = sum(1 for w in self.video_widgets if w.download_status == 'success')
            failed = sum(1 for w in self.video_widgets if w.download_status == 'failed')

            QMessageBox.information(
                self,
                "Complete",
                f"✓ Downloaded: {downloaded}\n✗ Failed: {failed}"
            )

    def update_counters(self):
        """Update download counters"""
        downloaded = sum(1 for w in self.video_widgets if w.download_status == 'success')
        failed = sum(1 for w in self.video_widgets if w.download_status == 'failed')

        self.downloaded_label.setText(f"Downloaded: {downloaded}")
        self.downloaded_label.setStyleSheet(f"color: {'#00d26a' if downloaded > 0 else '#8e8e8e'}; font-weight: bold;")

        self.failed_label.setText(f"Failed: {failed}")
        self.failed_label.setStyleSheet(f"color: {'#ff4444' if failed > 0 else '#8e8e8e'}; font-weight: bold;")

        self.update_disk_space()

    def log_status(self, message):
        """Log status message"""
        self.status_text.append(message)
        self.status_text.verticalScrollBar().setValue(self.status_text.verticalScrollBar().maximum())

    def closeEvent(self, event):
        """Handle application close"""
        if self.info_thread and self.info_thread.isRunning():
            self.info_thread.stop()
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
        if self.profile_thread and self.profile_thread.isRunning():
            self.profile_thread.stop()

        for widget in self.video_widgets:
            widget.cleanup()

        self.config.save()
        event.accept()


def main():
    app = QApplication(sys.argv)

    try:
        window = InstagramBatchDownloader()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logging.critical(f"Application crashed: {e}")
        raise


if __name__ == "__main__":
    main()