import os
import re
import shutil

import dateutil
import requests
import hashlib
import urllib3
import logging
import pefile
import hmac
import base64
import sys
import platform
from datetime import datetime
import time
import pywintypes
import win32file
import win32con
from abc import ABC, abstractmethod
from urllib.parse import unquote, urlparse
from typing import Optional, Dict, Any, List, Union
from urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from colorama import Fore, Style, init
init(autoreset=True)

# Rich 相关导入
from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    TextColumn
)




ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

class DingTalkNotifier:
    """钉钉机器人通知类"""

    def __init__(self, webhook_url: str = None, secret: str = None):
        """初始化钉钉通知器"""
        self.webhook_url = webhook_url
        self.secret = secret
        self.enabled = bool(webhook_url)

        if self.enabled:
            from dingtalkchatbot.chatbot import DingtalkChatbot
            self.chatbot = DingtalkChatbot(webhook_url, secret)

    def send_message(self, title: str, text: str, is_at_all: bool = False) -> bool:
        """发送钉钉消息

        Args:
            title: 消息标题(纯文本)
            text: 消息内容(Markdown格式)
            is_at_all: 是否@所有人

        Returns:
            bool: 是否发送成功update
        """
        if not self.enabled:
            return False

        try:
            # 确保标题是纯文本，不含Markdown格式
            clean_title = re.sub(r'[#*_`~]', '', title)

            # 构建消息体
            message = {
                "msgtype": "markdown",
                "markdown": {
                    "title": clean_title,  # 标题必须是纯文本
                    "text": f"#### {clean_title}\n\n{text}"  # 在内容中显示格式化标题
                },
                "at": {
                    "isAtAll": is_at_all
                }
            }

            # 添加签名(如果有secret)
            params = {}
            if self.secret:
                timestamp = int(time.time() * 1000)
                sign = self._get_signature(timestamp)
                params = {
                    "timestamp": timestamp,
                    "sign": sign
                }

            response = requests.post(
                self.webhook_url,
                params=params,
                json=message,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logging.error(f"钉钉消息发送失败: {e}")
            return False

    def _get_signature(self, timestamp: int) -> str:
        """生成签名"""
        if not self.secret:
            return ""

        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()

        return base64.b64encode(hmac_code).decode('utf-8')


class ColoredFormatter(logging.Formatter):
    """自定义带颜色的日志格式化器。"""

    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT
    }

    def format(self, record):
        """格式化日志记录。"""
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{Style.RESET_ALL}"
            record.msg = f"{self.COLORS[levelname]}{record.msg}{Style.RESET_ALL}"
        return super().format(record)


class DownloaderBase(ABC):
    """下载器基类，使用rich实现进度显示。"""

    logger = logging.getLogger('DownloaderBase')
    _project_lock = Lock()
    _logger_configured = False
    _logger_lock = Lock()

    def __init__(self, url: Optional[str] = None, output: str = None,
                 dingtalk_webhook: str = None, dingtalk_secret: str = None,
                 project_name: str = "项目更新监控",
                 only_latest: bool = True,
                 threads: int = 4,
                 log_file: str = None,
                 **kwargs):
        """初始化下载基类。"""
        # Rich 控制台和进度条初始化
        self.console = Console()
        self.progress = Progress(
            TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            console=self.console
        )

        # 日志文件处理
        self.log_filename = log_file if log_file else os.path.join(
            "logs", f"{time.strftime('%Y%m%d_%H%M%S')}_monitor.log"
        )

        # 确保日志目录存在
        log_dir = os.path.dirname(self.log_filename) if log_file else "logs"
        os.makedirs(log_dir, exist_ok=True)

        # 确保日志系统只配置一次
        self._configure_logger_once(log_dir)

        # 禁用SSL错误告警
        urllib3.disable_warnings(InsecureRequestWarning)

        self.only_latest = bool(only_latest)
        self.url = url if url and url.endswith("/") else url + "/" if url else ""
        self.output_path = output if output else os.path.join(ROOT_PATH, 'output')
        self.project_name = project_name
        self.dingtalk_notifier = DingTalkNotifier(dingtalk_webhook, dingtalk_secret)
        self.threads = int(threads)

        self._abort_flag = False
        self._last_progress = 0

        self.kwargs = kwargs
        self.kwargs["verify"] = True if bool(self.kwargs.get("verify")) else False
        self.kwargs["timeout"] = self.kwargs.get("timeout", 10)
        self.kwargs['headers'] = self.kwargs.get('headers', {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/136.0.7103.48 Safari/537.36'
        })

        try:
            if not os.path.exists(self.output_path):
                os.makedirs(self.output_path, exist_ok=True)
                self.logger.info(f"已创建输出目录: {self.output_path}")
        except Exception as e:
            self.logger.error(f"创建输出目录失败: {e}")
            self._send_dingtalk_alert(f"{self.project_name} - 初始化失败", f"创建输出目录失败: {e}")
            raise

        # 显示启动横幅
        self._show_startup_banner()

    def _show_startup_banner(self):
        """显示启动横幅"""
        table = Table(title="项目下载器", show_header=True, header_style="bold magenta")
        table.add_column("项目名称", style="cyan")
        table.add_column("URL", style="green")
        table.add_column("输出路径", style="yellow")
        table.add_column("线程数", style="red")

        table.add_row(
            self.project_name,
            self.url,
            self.output_path,
            str(self.threads)
        )

        self.console.print(table)

    def _configure_logger_once(self, log_dir: str):
        """确保日志系统只配置一次"""
        with self._logger_lock:
            if not DownloaderBase._logger_configured:
                # 配置根logger
                logger = logging.getLogger()
                logger.setLevel(logging.INFO)

                # 移除所有现有handler（避免重复）
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)

                # 控制台处理器（带颜色）
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(ColoredFormatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                ))
                logger.addHandler(console_handler)

                # 文件处理器
                file_handler = logging.FileHandler(
                    self.log_filename,
                    encoding='utf-8'
                )
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                ))
                logger.addHandler(file_handler)

                DownloaderBase._logger_configured = True

    def get_log_filename(self) -> str:
        """获取当前日志文件名"""
        return self.log_filename

    def _check_abort(self):
        """检查是否请求中止"""
        if self._abort_flag:
            raise RuntimeError("Download aborted by user")

    def request_abort(self):
        """请求中止下载"""
        self._abort_flag = True

    def _send_dingtalk_alert(self, title: str, message: str, msg_type: str = 'info') -> None:
        """发送钉钉告警。"""
        self.logger.info(f"发送钉钉消息: 标题: {title}, 信息: {message}")
        if not message and not title:
            self.logger.warning("⚠空标题，空消息，跳过发送")
            return

        if msg_type == 'success':
            title = f"✅ {title}\n\n"
            message = f"### \n\n{message}\n\n"
        elif msg_type == 'error':
            title = f"❌ {title}\n\n"
            message = f"### \n\n{message}\n\n"
        elif msg_type == 'warning':
            title = f"⚠ {title}\n\n"
            message = f"### \n\n{message}\n\n"
        elif msg_type == 'critical':
            title = f"❗ {title}\n\n"
            message = f"### \n\n{message}\n\n"
        elif msg_type == 'info':
            title = f"✉️ {title}\n\n"
            message = f"### \n\n{message}\n\n"
        else:
            title = f"{title}\n\n"
            message = f"### \n\n{message}\n\n"
        self.dingtalk_notifier.send_message(title, message)

    def _send_download_success_notification(self, version: str, file_count: str) -> None:
        """发送下载成功通知。"""
        self.console.print(f"[bold green]✓ {self.project_name} 下载成功[/]")
        self.console.print(f"版本: [cyan]{version}[/]")
        self.console.print(f"文件数量: [yellow]{file_count}[/]")
        self.console.print(f"下载时间: [magenta]{time.strftime('%Y-%m-%d %H:%M:%S')}[/]")

        # 同时发送钉钉通知
        title = f"{self.project_name} 下载成功"
        message = (f"**项目**: {self.project_name}\n\n"
                   f"**版本**: {version}</br>\n\n"
                   f"**文件数量**: {file_count}</br>\n\n"
                   f"**下载时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}</br>")
        self._send_dingtalk_alert(title, message, msg_type='success')

    def _send_download_failure_notification(self, version: str, file_name: str, error: str) -> None:
        """发送下载失败通知。"""
        self.console.print(f"[bold red]✗ {self.project_name} 下载失败[/]")
        self.console.print(f"文件: [yellow]{file_name}[/]")
        self.console.print(f"错误: [red]{error}[/]")

        title = f"{self.project_name} 下载失败"
        message = (f"**项目**: {self.project_name}\n\n"
                   f"**版本**: {version}\n\n"
                   f"**文件**: {file_name}\n\n"
                   f"**错误**: {error}\n\n"
                   f"**时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._send_dingtalk_alert(title, message, msg_type='error')

    def _send_update_notification(self, version_information: List[Dict]) -> None:
        """发送更新发现通知。"""
        self.console.print(f"[bold green]✓ 发现 {len(version_information)} 个新版本[/]")
        table = Table(title="新版本", show_header=True, header_style="bold blue")
        table.add_column("版本", style="cyan")
        table.add_column("更新时间", style="magenta")
        table.add_column("描述", style="green")

        for info in version_information:
            table.add_row(
                info.get("file_version", "未知"),
                info.get("data", [{}])[0].get("update_time", "未知"),
                info.get("about", "无描述")[:50] + "..."
            )

        self.console.print(table)

        # 同时发送钉钉通知
        for info in version_information:
            title = f"{self.project_name} 发现新版本"
            about = info.get('about', '无描述')
            change = info.get('change', '无描述')
            update_time = [ f"{_['update_time']}\n\n" for _ in info.get('data', [])][0]
            file_list = "- " + ("- ".join([ f"[{_['file_name']}]({_['file_url']})\n\n" for _ in info.get('data', [])]))
            message = (f"**项目**: {self.project_name}\n\n"
                       f"**项目描述:**\n\n: {about}\n\n"
                       f"**更新时间**: {update_time}\n\n"
                       f"**文件列表**:\n\n\n{file_list}"
                       )

            self._send_dingtalk_alert(title, message, msg_type='info')
            message = f"{change}\n"
            self._send_dingtalk_alert("版本变化", message, msg_type='info')

    def _send_other_msg(self, title: str, message: str, msg_type='info') -> None:
        """发送其他信息"""
        return self._send_dingtalk_alert(title, message, msg_type=msg_type)

    @classmethod
    def get_exe_version(cls, exe_path: str) -> Optional[str]:
        """获取EXE文件的版本信息。"""
        try:
            pe = pefile.PE(exe_path)
            if not hasattr(pe, 'VS_VERSIONINFO'):
                return ""

            version_info = {}
            for entry in pe.FileInfo:
                if entry.Key.decode() == 'StringFileInfo':
                    for st in entry.StringTable:
                        for str_entry in st.entries.items():
                            version_info[str_entry[0].decode()] = str_entry[1].decode()
            return version_info.get('FileVersion', '')
        except Exception as e:
            cls.logger.error(f"获取exe版本信息失败: {e}")
            return ""
        finally:
            if 'pe' in locals():
                pe.close()

    @staticmethod
    def _get_file_hash(file_path: str, hash_type: str = 'md5', chunk_size: int = 8192) -> str:
        """获取文件的哈希值。"""
        if hash_type.lower() == 'md5':
            hash_obj = hashlib.md5()
        elif hash_type.lower() == 'sha256':
            hash_obj = hashlib.sha256()
        else:
            raise ValueError(f"不支持的哈希类型: {hash_type}")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"需要验证的文件 {str(file_path)} 不存在")

        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hash_obj.update(chunk)
        return hash_obj.hexdigest().lower().strip()

    @classmethod
    def verify_hash(cls, file_path: str, file_hash: str = None, hash_type: str = 'md5') -> bool:
        """验证文件哈希值是否符合预期。"""
        if not file_path or not file_hash:
            cls.logger.error("验证哈希失败, 参数不完整")
            raise ValueError("验证哈希失败, 参数不完整")

        if not os.path.exists(file_path):
            cls.logger.error(f"验证哈希失败, 原始文件: {file_path} 不存在")
            raise FileNotFoundError(f"验证哈希失败, 原始文件: {file_path} 不存在")

        if os.path.isfile(file_hash):
            with open(file_hash, 'r') as f:
                hash_str = f.read().strip()
        else:
            hash_str = file_hash.lower().strip()

        local_file_hash = DownloaderBase._get_file_hash(file_path, hash_type)
        is_same = local_file_hash.lower().strip() == hash_str

        if is_same:
            cls.logger.info(f"✅文件 {file_path}, 验证hash通过")
        else:
            cls.logger.error(f"❌文件 {file_path} 验证hash不通过")

        return is_same

    @staticmethod
    def get_filename_from_response(url: str) -> Optional[str]:
        """从URL响应中获取文件名。"""
        try:
            response = requests.head(url, allow_redirects=True)
            response.raise_for_status()

            content_disposition = response.headers.get('Content-Disposition', '')
            if content_disposition:
                filename_match = re.findall('filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disposition)
                if filename_match:
                    return unquote(filename_match[0][0].strip('"\''))

            parsed_url = urlparse(url)
            path = parsed_url.path
            if path:
                return unquote(path.split('/')[-1]).replace('@', '-')

            return None
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            return None

    @staticmethod
    def _convert_to_timestamp(time_input: Union[datetime, float, str]) -> float:
        """
        将各种时间格式转换为Unix时间戳

        参数:
            time_input: 接受以下格式：
                - datetime对象
                - Unix时间戳
                - ISO 8601字符串（如：2024-10-08T01:24:03.000+08:00）
                - 简单时间字符串（YYYY-MM-DD HH:MM:SS）

        返回:
            float: Unix时间戳

        异常:
            ValueError: 当输入格式不支持时抛出
        """
        if isinstance(time_input, datetime):
            return time_input.timestamp()
        elif isinstance(time_input, (int, float)):
            return float(time_input)
        elif isinstance(time_input, str):
            try:
                # 尝试解析ISO 8601格式
                dt = dateutil.parser.isoparse(time_input)
                return dt.timestamp()
            except ValueError:
                try:
                    # 尝试解析简单格式
                    dt = datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
                    return dt.timestamp()
                except ValueError:
                    raise ValueError("时间格式不支持，请使用ISO 8601或YYYY-MM-DD HH:MM:SS格式")
        else:
            raise ValueError("不支持的时间格式类型")

    @staticmethod
    def set_modification_time(file_path: str, modification_time: Union[datetime, float, str]) -> bool:
        """
        设置文件的修改时间

        参数:
            file_path: 文件路径
            modification_time: 接受多种时间格式（由_convert_to_timestamp处理）

        返回:
            bool: 操作是否成功
        """
        try:
            timestamp = DownloaderBase._convert_to_timestamp(modification_time)
            current_system = platform.system()

            if current_system == 'Windows':
                import pywintypes
                import win32file
                import win32con

                win32_time = pywintypes.Time(timestamp)
                handle = win32file.CreateFile(
                    file_path,
                    win32file.GENERIC_WRITE,
                    win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
                    None,
                    win32con.OPEN_EXISTING,
                    0,
                    None
                )

                try:
                    ctime, atime, mtime = win32file.GetFileTime(handle)
                    win32file.SetFileTime(handle, ctime, atime, win32_time)
                finally:
                    win32file.CloseHandle(handle)

            elif current_system in ('Linux', 'Darwin'):
                atime = os.path.getatime(file_path)
                os.utime(file_path, (atime, timestamp))

            else:
                raise OSError(f"不支持的操作系统: {current_system}")

            return True

        except Exception as e:
            logging.error(f"修改文件时间失败: {str(e)}")
            return False

    @staticmethod
    def get_modification_time(file_path: str) -> Optional[datetime]:
        """
        获取文件的修改时间

        参数:
            file_path: 文件路径

        返回:
            datetime对象表示的修改时间，失败返回None
        """
        try:
            mtime = os.path.getmtime(file_path)
            return datetime.fromtimestamp(mtime)
        except Exception as e:
            logging.error(f"获取文件修改时间失败: {str(e)}")
            return None

    def _generate_markdown(self, version_information: Dict[str, Any], file_output_path: str) -> None:
        """生成Markdown说明文件。"""
        version = version_information["file_version"]
        about = version_information["about"]
        change = version_information["change"]

        data_markdown_list = """| 名称 | hash | 更新时间 |
| ----------- | ----------- |-----------|"""
        for data in version_information["data"]:
            data_markdown_list += f"""\n|{data['file_name']} | {data['file_hash']} | {data['update_time']} |"""

        markdown_info = f""" 
## 版本: 
{version}
## 简介:
{about}
## 文件:
{data_markdown_list}
## 版本更新变化:
{change}
"""
        with open(os.path.join(file_output_path, "说明.md"), 'w', encoding='utf-8') as f:
            f.write(markdown_info)

    def check_updates(self) -> List[Dict[str, Any]]:
        """检查是否有新版本可用（只检查不下载）。"""
        self.console.print(f"[bold]正在检查 {self.project_name} 的更新...[/]")

        try:
            version_information = self.request()
            if not version_information:
                self.console.print("[yellow]⚠ 未获取到下载信息[/]")
                return []

            new_versions = []
            for version_info in version_information:
                version = version_info.get("file_version")
                if not version:
                    continue

                version_path = os.path.join(self.output_path, version)

                # 版本路径不存在 - 直接判断为存在新的版本
                if not os.path.exists(version_path):
                    new_versions.append(version_info)
                else:
                    # 版本路路径存在，检测内部文件（检测其余版本的本的无意义，因为通过是否存在版本路径，即可判断是否存在新版本）
                    if version == 'latest':
                        for data in version_info['data']:
                            output_file = os.path.join(version_path, data['file_name'])
                            # 已经存在，检测版本 (只要检测到一个文件存在新的版本，就判定为存在新的版本）
                            if os.path.exists(output_file):
                                if self._convert_to_timestamp(self.get_modification_time(output_file)) < self._convert_to_timestamp(data['update_time']):
                                    new_versions.append(version_info)
                                    break
            if new_versions:
                self.console.print(f"[green]✓ 发现 {len(new_versions)} 个新版本[/]")
                self._send_update_notification(new_versions)
            else:
                self.console.print("[yellow]✓ 未发现新版本[/]")
            return new_versions
        except Exception as e:
            self.console.print(f"[red]✗ 检查更新失败: {e}[/]")
            self._send_dingtalk_alert(f"{self.project_name} - 检查更新失败", f"检查更新失败: {e}")
            return []

    def _output_download(self, version_information: List[Dict[str, Any]],
                         threads: int = None, chunk_size: int = 1024 * 1024) -> None:
        try:
            for download in version_information:
                self._check_abort()

                # 创建对应的版本目录
                with self._project_lock:
                    version = download["file_version"]
                    file_output_path = os.path.join(self.output_path, version)
                    os.makedirs(file_output_path, exist_ok=True)

                # 执行下载前的预处理，文件的校验等
                with self._project_lock:
                    download_tasks = self._prepare_download_tasks(download, file_output_path)

                if download_tasks:
                    self._execute_downloads(download_tasks, threads, chunk_size)

                    with self._project_lock:
                        self._process_download_results(download, file_output_path)

        except Exception as e:
            self.logger.error(f"下载过程中出错: {str(e)}")
            raise

    def _prepare_download_tasks(self, download: Dict, output_path: str) -> List[tuple]:
        """准备下载任务（线程安全）"""
        tasks = []
        for data in download["data"]:
            self._check_abort()

            file_name = data["file_name"]
            file_hash = data.get("file_hash")
            file_url = data["file_url"]
            file_version = download["file_version"]
            file_update_time = data["update_time"]
            file_is_source_code = data["source_code"]

            if data['source_code']:
                output_file = os.path.join(output_path, 'source', file_name)
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
            else:
                output_file = os.path.join(output_path, file_name)

            if os.path.exists(output_file):
                if file_hash and not self.check_file(output_file, file_hash):
                    self.logger.warning(f"文件 {file_name} 校验不通过，重新下载")
                else:
                    # 版本是最新的，且更新的时间发生了变动，则将任务也添加进去
                    if (file_version == 'latest'
                            and self._convert_to_timestamp(self.get_modification_time(output_file)) < self._convert_to_timestamp(data['update_time'])):
                        self.logger.info(f"源码文件 {file_name} 版本更新了")
                    else:
                        self.logger.info(f"文件 {file_name} 通过，跳过下载")
                        continue

            tasks.append((file_url, output_file, file_name, file_version, file_update_time, file_is_source_code))
        return tasks

    def _process_download_results(self, download: Dict, output_path: str):
        """处理下载结果（线程安全）"""
        version = download["file_version"]
        total_count = len(download["data"])

        success_count = 0
        for data in download["data"]:
            if data['source_code']:
                output_file = os.path.join(output_path, 'source', data['file_name'])
            else:
                output_file = os.path.join(output_path, data['file_name'])
            if os.path.exists(output_file):
                success_count += 1

        self._generate_markdown(download, output_path)
        self._send_download_success_notification(version, f"{success_count} / {total_count}")

        self.logger.info(f"成功下载 {success_count} / {total_count} 个文件")

    def stop_download(self):
        """安全停止所有下载线程"""
        # 设置中止标志
        self._abort_flag = True

        # 关闭线程池
        if hasattr(self, '_executor') and self._executor:
            self._executor.shutdown(wait=False)

        # 停止进度条
        if hasattr(self, '_progress'):
            self._progress.stop()

        self.logger.info("下载已停止")
        self._send_dingtalk_alert(f"{self.project_name} - 下载已停止", "用户请求停止下载", msg_type='warning')

    def _execute_downloads(self, download_tasks: List[tuple],
                           threads: int = None, chunk_size: int = 8192) -> int:
        """执行下载任务并返回成功数量"""
        threads = threads if threads else self.threads
        success_count = 0
        lock = Lock()

        with self.progress:
            # 保存executor引用以便停止
            self._executor = ThreadPoolExecutor(max_workers=threads)
            with self._executor as executor:
                futures = {}
                for file_url, output_file, file_name, file_version, update_time, is_source_code in download_tasks:
                    self._check_abort()
                    future = executor.submit(
                        self._download_file,
                        file_url, output_file, file_name, file_version, update_time, is_source_code, chunk_size
                    )
                    futures[future] = file_name

                for future in as_completed(futures):
                    self._check_abort()
                    file_name = futures[future]
                    try:
                        if future.result():
                            with lock:
                                success_count += 1
                            self.logger.info(f"文件 {file_name} 下载成功")
                    except Exception as e:
                        self.logger.error(f"文件 {file_name} 下载失败: {str(e)}")

        # 清除executor引用
        self._executor = None
        return success_count

    def _download_file(self, url: str, output_file: str,
                       file_name: str, version: str, update_time, is_source_code, chunk_size: int = 8192) -> bool:
        """下载单个文件"""
        task_id = self.progress.add_task("download", filename=file_name, start=False)

        try:
            temp_file = output_file + '.tmp'
            downloaded_size = 0

            if os.path.exists(temp_file):
                downloaded_size = os.path.getsize(temp_file)
                headers = self.kwargs.get('headers', {}).copy()
                headers['Range'] = f'bytes={downloaded_size}-'
                self.kwargs['headers'] = headers

            response = requests.get(url, stream=True, **self.kwargs)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0)) + downloaded_size

            # 开始进度条
            self.progress.start_task(task_id)
            self.progress.update(task_id, total=total_size, completed=downloaded_size)

            mode = 'ab' if downloaded_size > 0 else 'wb'
            with open(temp_file, mode) as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    self._check_abort()
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        self.progress.update(task_id, advance=len(chunk))


            # 处理特殊情况的 latest 版本的 (是最新版本，且更新时间发生了变化，且本地文件已经存在，且文件修改时间不一样)
            if (version == 'latest' and os.path.exists(output_file) and
                    self._convert_to_timestamp(self.get_modification_time(output_file)) < self._convert_to_timestamp(update_time)):
                old_file_time = self.get_modification_time(output_file)
                dst_dir = os.path.join(os.path.split(output_file)[0], 'history', str(self._convert_to_timestamp(old_file_time)))
                self.logger.info(f"创建目录 {dst_dir} 存放历史版本")
                os.makedirs(dst_dir, exist_ok=True)
                self.logger.info(f"移动旧版本 -> {dst_dir}")
                shutil.move(output_file, dst_dir)


            os.rename(temp_file, output_file)
            # 下载的修改文件的修改时间为commit时间
            self.set_modification_time(file_path=output_file, modification_time=self._convert_to_timestamp(update_time))

            self.progress.remove_task(task_id)
            return True

        except Exception as e:
            self.progress.stop()
            self.logger.error(f"下载文件 {file_name} 版本: {version} 失败: {str(e)}")
            self._send_download_failure_notification(version, file_name, str(e))
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

    @abstractmethod
    def request(self) -> List[Dict[str, Any]]:
        """获取每个版本的下载信息。"""
        return []

    @abstractmethod
    def check_file(self, *args, **kwargs) -> bool:
        """检测文件完整性。"""
        pass

    @abstractmethod
    def filter(self, version_information: List[Dict[str, Any]], *args, **kwargs) -> List[Dict[str, Any]]:
        """过滤下载信息。"""
        pass

    @abstractmethod
    def download(self, version_information: List[Dict[str, Any]]) -> None:
        """下载方法，子类必须实现"""
        pass