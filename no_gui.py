import sys
import os
import re
import time
import threading
import shutil
import logging
import configparser
import concurrent.futures
import argparse
from datetime import datetime, timedelta
import os
import time
import concurrent.futures
from typing import Dict, Any, List
from croniter import croniter
from pathvalidate import sanitize_filename
from GithubDownload.github import GithubDownloader

def get_app_path():
    """获取应用程序所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

import os
import time
import threading
import concurrent.futures
from typing import Dict, Any, List


# class TaskExecutor:
#     """任务执行器"""
#     def __init__(self, configs: List[Dict[str, Any]], max_workers: int = 4):
#         """
#         初始化任务执行器
#
#         :param configs: 任务配置列表
#         :param max_workers: 最大工作线程数
#         """
#         self.configs = configs
#         self.max_workers = max_workers
#         self._stop_flag = threading.Event()
#         self.downloaders = {}
#         self.status_files = {}
#         self.monitor_thread = None
#         self.executor = None
#         self.lock = threading.Lock()
#         self.task_complete_events = {}  # 新增：任务完成事件字典
#
#         # 创建运行状态目录
#         self.status_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.run_status')
#         os.makedirs(self.status_dir, exist_ok=True)
#         self.global_stop_file = os.path.join(self.status_dir, '.stop_all')
#
#     def _create_status_file(self, project_name: str) -> str:
#         """创建运行状态文件"""
#         status_file = os.path.join(self.status_dir, f"{project_name}.run")
#         with open(status_file, 'w') as f:
#             f.write(str(os.getpid()))
#         with self.lock:
#             self.status_files[project_name] = status_file
#             # 为每个任务创建完成事件
#             self.task_complete_events[project_name] = threading.Event()
#         return status_file
#
#     def _remove_status_file(self, project_name: str):
#         """删除运行状态文件"""
#         with self.lock:
#             if project_name in self.status_files:
#                 try:
#                     os.unlink(self.status_files[project_name])
#                     del self.status_files[project_name]
#                 except:
#                     pass
#             # 清理任务完成事件
#             if project_name in self.task_complete_events:
#                 del self.task_complete_events[project_name]
#
#     def _check_global_stop(self) -> bool:
#         """检查全局停止文件是否存在"""
#         return os.path.exists(self.global_stop_file)
#
#     def _monitor_stop_signals(self):
#         """监控停止信号的独立线程"""
#         while not self._stop_flag.is_set():
#             try:
#                 if self._stop_flag.is_set() or self._check_global_stop():
#                     self._stop_flag.set()
#                     break
#
#                 with self.lock:
#                     for project_name, downloader in list(self.downloaders.items()):
#                         if project_name in self.status_files:
#                             status_file = self.status_files[project_name]
#                             if not os.path.exists(status_file):
#                                 print(f"检测到停止信号，正在停止项目: {project_name}")
#                                 downloader.stop_download()
#                                 self._remove_status_file(project_name)
#                                 self.downloaders.pop(project_name, None)
#                                 # 设置任务完成事件
#                                 if project_name in self.task_complete_events:
#                                     self.task_complete_events[project_name].set()
#
#                 time.sleep(0.5)
#             except Exception as e:
#                 print(f"监控线程出错: {str(e)}")
#                 time.sleep(1)
#
#     def stop(self, all_tasks=False):
#         """
#         停止下载任务
#
#         :param all_tasks: 是否停止所有任务(包括未开始的)
#         """
#         self._stop_flag.set()
#
#         # 设置所有任务完成事件
#         with self.lock:
#             for event in self.task_complete_events.values():
#                 event.set()
#
#         # 停止监控线程
#         if self.monitor_thread and self.monitor_thread.is_alive():
#             self.monitor_thread.join(timeout=1)
#
#         # 停止所有下载器
#         with self.lock:
#             for downloader in self.downloaders.values():
#                 downloader.stop_download()
#
#         # 清理所有状态文件
#         with self.lock:
#             for project_name in list(self.status_files.keys()):
#                 self._remove_status_file(project_name)
#
#         # 如果停止所有任务，则关闭线程池
#         if all_tasks and self.executor:
#             self.executor.shutdown(wait=False)
#
#     def execute(self):
#         """执行所有任务"""
#         if self._stop_flag.is_set() or self._check_global_stop():
#             print("任务执行已停止")
#             return
#
#         self.monitor_thread = threading.Thread(
#             target=self._monitor_stop_signals,
#             daemon=True
#         )
#         self.monitor_thread.start()
#
#         self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
#         futures = {}
#
#         try:
#             for config in self.configs:
#                 if self._stop_flag.is_set() or self._check_global_stop():
#                     break
#
#                 future = self.executor.submit(self.execute_task, config)
#                 futures[future] = config
#
#             for future in concurrent.futures.as_completed(futures):
#                 if self._stop_flag.is_set() or self._check_global_stop():
#                     self.executor.shutdown(wait=False)
#                     return
#
#                 config = futures[future]
#                 try:
#                     future.result()
#                 except Exception as e:
#                     print(f"任务执行错误: {str(e)}")
#         finally:
#             if not self._stop_flag.is_set() and not self._check_global_stop():
#                 self.executor.shutdown()
#
#     def execute_task(self, config: Dict[str, Any]):
#         """
#         执行单个任务
#
#         :param config: 任务配置字典
#         """
#         if self._stop_flag.is_set() or self._check_global_stop():
#             return
#
#         project_name = config['name']
#         action_type = config.get('action_type', 'download').lower()
#         status_file = self._create_status_file(project_name)
#
#         try:
#             # 获取任务完成事件
#             with self.lock:
#                 task_complete_event = self.task_complete_events.get(project_name)
#
#             # 确保代理设置正确
#             proxies = config.get('proxies', {})
#             if not isinstance(proxies, dict):
#                 proxies = {}
#             if not proxies.get('http') and not proxies.get('https'):
#                 proxies = None
#             else:
#                 print(f"使用代理设置: {proxies}")
#
#             downloader = GithubDownloader(
#                 url=config['url'],
#                 output=config.get('output'),
#                 dingtalk_webhook=config.get('dingtalk_webhook'),
#                 dingtalk_secret=config.get('dingtalk_secret'),
#                 project_name=project_name,
#                 only_latest=config.get('only_latest', True),
#                 threads=config.get('threads', 4),
#                 log_file=config.get('log_file'),
#                 verify=not config.get('ignore_ssl', True),
#                 proxies=proxies,
#                 timeout=30
#             )
#
#             # 存储下载器实例以便后续停止
#             with self.lock:
#                 self.downloaders[project_name] = downloader
#
#             if action_type == 'download':
#                 try:
#                     version_info = downloader.request()
#                     # 定期检查是否应该停止
#                     if not self._stop_flag.is_set() and not self._check_global_stop():
#                         downloader.download(version_info)
#                         # 检查是否被停止
#                         if task_complete_event and task_complete_event.is_set():
#                             print(f"项目 {project_name} 下载被中断")
#                             return
#                         print(f"项目 {project_name} 下载完成")
#                 except Exception as e:
#                     print(f"下载项目 {project_name} 时发生错误: {e}")
#                     if config.get('dingtalk_webhook'):
#                         downloader._send_other_msg(
#                             f"下载项目 {project_name} 失败",
#                             f"URL: {config['url']}\n错误信息: {str(e)}"
#                         )
#
#             elif action_type == 'update':
#                 try:
#                     updates = downloader.check_updates()
#                     if updates:
#                         print(f"项目 {project_name} 有更新可用:")
#                         for update in updates:
#                             print(f"  - {update}")
#                     else:
#                         print(f"项目 {project_name} 已是最新版本")
#                 except Exception as e:
#                     print(f"检查项目 {project_name} 更新时发生错误: {e}")
#                     if config.get('dingtalk_webhook'):
#                         downloader._send_other_msg(
#                             f"检查项目 {project_name} 更新失败",
#                             f"URL: {config['url']}\n错误信息: {str(e)}"
#                         )
#
#         except Exception as e:
#             print(f"处理项目 {project_name} 时发生错误: {e}")
#         finally:
#             # 任务完成后移除状态文件和下载器引用
#             self._remove_status_file(project_name)
#             with self.lock:
#                 self.downloaders.pop(project_name, None)


class TaskExecutor:
    """任务执行器"""
    def __init__(self, configs: List[Dict[str, Any]], max_workers: int = 4):
        """
        初始化任务执行器

        :param configs: 任务配置列表
        :param max_workers: 最大工作线程数
        """
        self.configs = configs
        self.max_workers = max_workers
        self._stop_flag = threading.Event()
        self.downloaders = {}
        self.status_files = {}
        self.monitor_thread = None
        self.executor = None
        self.lock = threading.Lock()
        self.task_complete_events = {}
        self.completed_tasks = 0
        self.all_tasks_completed = threading.Event()

        # 创建运行状态目录
        self.status_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.run_status')
        os.makedirs(self.status_dir, exist_ok=True)
        self.global_stop_file = os.path.join(self.status_dir, '.stop_all')

    def _create_status_file(self, project_name: str) -> str:
        """创建运行状态文件"""
        status_file = os.path.join(self.status_dir, f"{project_name}.run")
        with open(status_file, 'w') as f:
            f.write(str(os.getpid()))
        with self.lock:
            self.status_files[project_name] = status_file
            self.task_complete_events[project_name] = threading.Event()
        return status_file

    def _remove_status_file(self, project_name: str):
        """删除运行状态文件"""
        with self.lock:
            if project_name in self.status_files:
                try:
                    os.unlink(self.status_files[project_name])
                    del self.status_files[project_name]
                except:
                    pass
            if project_name in self.task_complete_events:
                del self.task_complete_events[project_name]

    def _check_global_stop(self) -> bool:
        """检查全局停止文件是否存在"""
        return os.path.exists(self.global_stop_file)

    def stop(self):
        """
        停止所有下载任务
        """
        self._stop_flag.set()

        # 设置所有任务完成事件
        with self.lock:
            for event in self.task_complete_events.values():
                event.set()

        # 停止监控线程
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)

        # 停止所有下载器
        with self.lock:
            for downloader in self.downloaders.values():
                downloader.stop_download()

        # 清理所有状态文件
        with self.lock:
            for project_name in list(self.status_files.keys()):
                self._remove_status_file(project_name)

        # 关闭线程池
        if self.executor:
            self.executor.shutdown(wait=False)

    def _monitor_stop_signals(self):
        """监控停止信号的独立线程"""
        while not self._stop_flag.is_set():
            try:
                if self._stop_flag.is_set() or os.path.exists(self.global_stop_file):
                    self._stop_flag.set()
                    break

                time.sleep(0.5)
            except Exception as e:
                print(f"监控线程出错: {str(e)}")
                time.sleep(1)

    def execute(self):
        """执行所有任务"""
        if self._stop_flag.is_set() or self._check_global_stop():
            print("任务执行已停止")
            return

        self.monitor_thread = threading.Thread(
            target=self._monitor_stop_signals,
            daemon=True
        )
        self.monitor_thread.start()

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
        futures = {}

        try:
            # 提交所有任务
            for config in self.configs:
                if self._stop_flag.is_set() or self._check_global_stop():
                    break

                future = self.executor.submit(self.execute_task, config)
                futures[future] = config

            # 等待所有任务完成或停止信号
            while not self._stop_flag.is_set() and not self._check_global_stop():
                with self.lock:
                    if self.completed_tasks >= len(self.configs):
                        self.all_tasks_completed.set()
                        break

                time.sleep(0.5)

        finally:
            if not self._stop_flag.is_set() and not self._check_global_stop():
                self.executor.shutdown()

    def execute_task(self, config: Dict[str, Any]):
        """
        执行单个任务

        :param config: 任务配置字典
        """
        if self._stop_flag.is_set() or self._check_global_stop():
            return

        project_name = config['name']
        action_type = config.get('action_type', 'download').lower()
        status_file = self._create_status_file(project_name)

        try:
            # 获取任务完成事件
            with self.lock:
                task_complete_event = self.task_complete_events.get(project_name)

            # 确保代理设置正确
            proxies = config.get('proxies', {})
            if not isinstance(proxies, dict):
                proxies = {}
            if not proxies.get('http') and not proxies.get('https'):
                proxies = None
            else:
                print(f"使用代理设置: {proxies}")

            downloader = GithubDownloader(
                url=config['url'],
                output=config.get('output'),
                dingtalk_webhook=config.get('dingtalk_webhook'),
                dingtalk_secret=config.get('dingtalk_secret'),
                project_name=project_name,
                only_latest=config.get('only_latest', True),
                threads=config.get('threads', 4),
                log_file=config.get('log_file'),
                verify=not config.get('ignore_ssl', True),
                proxies=proxies,
                timeout=30
            )

            # 存储下载器实例以便后续停止
            with self.lock:
                self.downloaders[project_name] = downloader

            if action_type == 'download':
                try:
                    version_info = downloader.request()
                    # 执行下载任务
                    if not self._stop_flag.is_set() and not self._check_global_stop():
                        downloader.download(version_info)
                        # 检查是否被停止
                        if task_complete_event and task_complete_event.is_set():
                            print(f"项目 {project_name} 下载被中断")
                            return
                        print(f"项目 {project_name} 下载完成")
                except Exception as e:
                    print(f"下载项目 {project_name} 时发生错误: {e}")
                    if config.get('dingtalk_webhook'):
                        downloader._send_other_msg(
                            f"下载项目 {project_name} 失败",
                            f"URL: {config['url']}\n错误信息: {str(e)}"
                        )

            elif action_type == 'update':
                try:
                    updates = downloader.check_updates()
                    if updates:
                        print(f"项目 {project_name} 有更新可用:")
                        for update in updates:
                            print(f"  - {update}")
                    else:
                        print(f"项目 {project_name} 已是最新版本")
                except Exception as e:
                    print(f"检查项目 {project_name} 更新时发生错误: {e}")
                    if config.get('dingtalk_webhook'):
                        downloader._send_other_msg(
                            f"检查项目 {project_name} 更新失败",
                            f"URL: {config['url']}\n错误信息: {str(e)}"
                        )

        except Exception as e:
            print(f"处理项目 {project_name} 时发生错误: {e}")
        finally:
            # 任务完成后移除状态文件和下载器引用
            self._remove_status_file(project_name)
            with self.lock:
                self.downloaders.pop(project_name, None)
                self.completed_tasks += 1
                # 检查是否所有任务都已完成
                if self.completed_tasks >= len(self.configs):
                    self.all_tasks_completed.set()


class ConfigManager:
    """配置文件管理器"""
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        if not os.path.exists(config_file):
            self.create_default_config()
        self.config.read(config_file, encoding='utf-8')

    def create_default_config(self):
        """创建默认配置文件"""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            f.write("[global]\n")
            f.write("dingtalk_webhook = \n")
            f.write("dingtalk_secret = \n")
            f.write("proxies.http = \n")
            f.write("proxies.https = \n")
            f.write("cron_expression = \n")
            f.write("scheduled_projects = \n")
            f.write("log_file = \n")
            f.write("threads = 4\n")

    def get_global_config(self) -> Dict[str, str]:
        """获取全局配置"""
        return dict(self.config['global']) if 'global' in self.config else {}

    def get_project_configs(self) -> List[Dict[str, Any]]:
        """获取所有项目配置"""
        projects = []
        for section in self.config.sections():
            if section != 'global':
                project = dict(self.config[section])
                project['name'] = section
                projects.append(project)
        return projects

    def get_project_config(self, name: str) -> Dict[str, str]:
        """获取单个项目配置"""
        if name in self.config:
            return dict(self.config[name])
        return {}

    def set_global_config(self, key: str, value: str):
        """设置全局配置"""
        if not self.config.has_section('global'):
            self.config.add_section('global')
        self.config['global'][key] = value
        self.save_config()

    def set_project_config(self, project: str, key: str, value: str):
        """设置项目配置"""
        if not self.config.has_section(project):
            self.config.add_section(project)
        self.config[project][key] = value
        self.save_config()

    def save_config(self):
        """保存更新后的配置"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)

class GitHubDownloaderCLI:
    """GitHub下载器命令行版"""
    def __init__(self):
        self.app_path = get_app_path()
        self.config_file = os.path.join(self.app_path, "config.ini")
        self.config_manager = ConfigManager(self.config_file)
        self.task_executor = None
        self.setup_logging()

    def add_project(self):
        """交互式添加项目(默认方式)"""
        return self.interactive_add_project()

    def setup_logging(self):
        """设置日志记录"""
        global_config = self.config_manager.get_global_config()
        log_file = global_config.get('log_file', os.path.join(self.app_path, 'logs', 'github_downloader.log'))

        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

    def execute_tasks(self, configs: List[Dict[str, Any]]):
        """执行任务"""
        global_config = self.config_manager.get_global_config()

        for config in configs:
            # 应用全局配置
            if 'proxies' not in config:
                proxies = {
                    'http': global_config.get('proxies.http'),
                    'https': global_config.get('proxies.https')
                }
                if not proxies['http'] and not proxies['https']:
                    proxies = None
                config['proxies'] = proxies

            config['log_file'] = global_config.get('log_file')
            config['dingtalk_webhook'] = global_config.get('dingtalk_webhook')
            config['dingtalk_secret'] = global_config.get('dingtalk_secret')

        max_workers = int(global_config.get('threads', 4))
        self.task_executor = TaskExecutor(configs=configs, max_workers=max_workers)
        self.task_executor.execute()

    def list_projects(self):
        """列出所有项目"""
        projects = self.config_manager.get_project_configs()
        if not projects:
            print("没有配置任何项目")
            return

        print("\n已配置的项目:")
        for i, project in enumerate(projects, 1):
            print(f"{i}. {project['name']}")
            print(f"   URL: {project['url']}")
            print(f"   输出路径: {project.get('output', '未设置')}")
            print(f"   操作类型: {project.get('action_type', 'download')}")
            print(f"   仅最新版本: {project.get('only_latest', 'true')}")
            print(f"   忽略SSL验证: {project.get('ignore_ssl', 'true')}")
            print(f"   备注: {project.get('remarks', '无')}\n")

    def show_project_config(self, name):
        """查看单个项目的所有配置"""
        if name not in self.config_manager.config:
            print(f"错误: 项目 '{name}' 不存在")
            return False

        config = self.config_manager.get_project_config(name)
        print(f"\n项目 '{name}' 的配置:")
        for key, value in config.items():
            print(f"  {key}: {value}")
        print()
        return True

    def interactive_add_project(self):
        """交互式添加项目"""
        print("\n交互式添加项目")
        print("="*30)

        # 获取项目名称
        while True:
            name = input("请输入项目名称: ").strip()
            if not name:
                print("错误: 项目名称不能为空")
                continue
            if name in self.config_manager.config:
                print(f"错误: 项目 '{name}' 已存在")
                continue
            break

        # 获取GitHub URL
        while True:
            url = input("请输入GitHub项目URL: ").strip()
            if not url.startswith('https://github.com/'):
                print("错误: GitHub URL必须以 'https://github.com/' 开头")
                continue
            break

        # 获取输出路径
        output = input("请输入输出路径(留空使用默认路径): ").strip()
        if not output:
            output = os.path.join(self.app_path, 'downloads', sanitize_filename(name, replacement_text='-'))
            print(f"将使用默认输出路径: {output}")

        # 获取操作类型
        while True:
            action_type = input("请选择操作类型(download/update)[默认:download]: ").strip().lower()
            if not action_type:
                action_type = 'download'
            if action_type in ['download', 'update']:
                break
            print("错误: 操作类型必须是 'download' 或 'update'")

        # 获取其他选项
        only_latest = input("是否仅下载最新版本(y/n)[默认:y]: ").strip().lower()
        only_latest = True if only_latest in ('', 'y', 'yes') else False

        ignore_ssl = input("是否忽略SSL验证(y/n)[默认:y]: ").strip().lower()
        ignore_ssl = False if ignore_ssl in ('n', 'no') else True

        remarks = input("请输入备注信息(可选): ").strip()

        # 保存配置
        self.config_manager.config[name] = {
            'url': url,
            'output': output,
            'action_type': action_type,
            'only_latest': 'true' if only_latest else 'false',
            'ignore_ssl': 'true' if ignore_ssl else 'false',
            'remarks': remarks,
        }

        self.config_manager.save_config()
        print(f"\n项目 '{name}' 已添加")
        return True

    def add_project_non_interactive(self, name, url, output=None, action_type='download',
                                    only_latest=True, ignore_ssl=False, remarks=''):
        """非交互式添加项目"""
        name = name.strip()
        if not name:
            print("错误: 项目名称不能为空")
            return False

        if name in self.config_manager.config:
            print(f"错误: 项目 '{name}' 已存在")
            return False

        if not url.startswith('https://github.com/'):
            print("错误: GitHub URL必须以 'https://github.com/' 开头")
            return False

        if not output:
            output = os.path.join(self.app_path, 'downloads', sanitize_filename(name, replacement_text='-'))

        self.config_manager.config[name] = {
            'url': url,
            'output': output,
            'action_type': action_type,
            'only_latest': 'true' if only_latest else 'false',
            'ignore_ssl': 'true' if ignore_ssl else 'false',
            'remarks': remarks,
        }

        self.config_manager.save_config()
        print(f"项目 '{name}' 已添加")
        return True

    def remove_project(self, name):
        """删除项目"""
        if name not in self.config_manager.config:
            print(f"错误: 项目 '{name}' 不存在")
            return False

        confirm = input(f"确定要删除项目 '{name}' 吗? (y/n): ").lower()
        if confirm != 'y':
            print("取消删除")
            return False

        try:
            if os.path.exists(self.config_manager.config[name]['output']):
                shutil.rmtree(self.config_manager.config[name]['output'])
            self.config_manager.config.remove_section(name)
            self.config_manager.save_config()
            print(f"项目 '{name}' 已删除")
            return True
        except Exception as e:
            print(f"删除项目 '{name}' 失败: {str(e)}")
            return False

    def execute_project(self, name):
        """执行单个项目"""
        if name not in self.config_manager.config:
            print(f"错误: 项目 '{name}' 不存在")
            return False

        config = dict(self.config_manager.config[name])
        config['name'] = name
        self.execute_tasks([config])
        return True

    def execute_all_projects(self):
        """执行所有项目"""
        configs = self.config_manager.get_project_configs()
        if not configs:
            print("没有可执行的项目")
            return False

        self.execute_tasks(configs)
        return True

    def schedule_tasks(self):
        """定时执行任务"""
        global_config = self.config_manager.get_global_config()
        cron_expr = global_config.get('cron_expression')
        scheduled_projects = global_config.get('scheduled_projects', '').split(',')

        if not cron_expr:
            print("没有配置定时任务")
            return

        if not scheduled_projects:
            print("没有选择要定时执行的项目")
            return

        configs = []
        for project in scheduled_projects:
            if project in self.config_manager.config:
                config = dict(self.config_manager.config[project])
                config['name'] = project
                configs.append(config)

        if not configs:
            print("没有找到有效的项目配置")
            return

        print(f"定时任务已启动: {cron_expr}")
        print(f"将执行的项目: {', '.join(scheduled_projects)}")

        while True:
            try:
                now = datetime.now()
                cron = croniter(cron_expr, now)
                next_time = cron.get_next(datetime)
                delay = (next_time - now).total_seconds()

                print(f"下一次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"等待 {delay:.0f} 秒...")
                time.sleep(delay)

                print(f"开始执行任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                self.execute_tasks(configs)
                print(f"任务执行完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            except KeyboardInterrupt:
                print("\n定时任务已停止")
                break
            except Exception as e:
                print(f"定时任务执行错误: {str(e)}")
                time.sleep(60)  # 出错后等待1分钟再重试

    def config_global_set(self, key, value):
        """设置全局配置"""
        if not self.config_manager.config.has_section('global'):
            self.config_manager.config.add_section('global')

        self.config_manager.config['global'][key] = value
        self.config_manager.save_config()
        print(f"全局配置 '{key}' 已设置为 '{value}'")

    def config_project_set(self, project, key, value):
        """设置项目配置"""
        if project not in self.config_manager.config:
            print(f"错误: 项目 '{project}' 不存在")
            return False

        if not self.config_manager.config.has_section(project):
            self.config_manager.config.add_section(project)

        self.config_manager.config[project][key] = value
        self.config_manager.save_config()
        print(f"项目 '{project}' 的配置 '{key}' 已设置为 '{value}'")
        return True

    def stop(self):
        """停止所有正在执行的任务"""
        status_dir = os.path.join(get_app_path(), '.run_status')
        if not os.path.exists(status_dir):
            print("没有正在执行的项目")
            return

        # 写入全局停止标志
        with open("./.run_status/.stop_all", "w", encoding="utf-8") as f:
            f.write("")

        print("已发送停止所有任务的信号")

def main():
    """命令行主函数"""
    parser = argparse.ArgumentParser(description='GitHub下载器命令行版')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # 列出项目
    list_parser = subparsers.add_parser('list', help='列出所有项目')

    # 添加项目
    add_parser = subparsers.add_parser('add', help='添加新项目')
    add_parser.add_argument('--non-interactive', action='store_true', help='使用非交互式模式')
    add_parser.add_argument('--name', help='项目名称(非交互式模式需要)')
    add_parser.add_argument('--url', help='GitHub项目URL(非交互式模式需要)')
    add_parser.add_argument('--output', help='输出路径', default=None)
    add_parser.add_argument('--action', choices=['download', 'update'], default='download', help='操作类型')
    add_parser.add_argument('--latest', action='store_true', help='仅下载最新版本')
    add_parser.add_argument('--ignore-ssl', action='store_true', help='忽略SSL验证')
    add_parser.add_argument('--remarks', help='备注信息', default='')

    # 删除项目
    remove_parser = subparsers.add_parser('remove', help='删除项目')
    remove_parser.add_argument('name', help='项目名称')

    # 执行项目
    execute_parser = subparsers.add_parser('execute', help='执行项目')
    execute_parser.add_argument('names', nargs='*', help='项目名称(不指定则执行所有项目)')

    # 定时任务
    schedule_parser = subparsers.add_parser('schedule', help='启动定时任务')

    # 配置管理
    config_parser = subparsers.add_parser('config', help='配置管理')
    config_subparsers = config_parser.add_subparsers(dest='config_command', required=True)

    # 全局配置
    global_parser = config_subparsers.add_parser('global', help='全局配置')
    global_subparsers = global_parser.add_subparsers(dest='global_action', required=True)

    # 查看全局配置
    global_show_parser = global_subparsers.add_parser('show', help='查看全局所有配置')

    # 获取单个全局配置
    global_get_parser = global_subparsers.add_parser('get', help='获取单个全局配置')
    global_get_parser.add_argument('key', help='配置键')

    # 设置全局配置
    global_set_parser = global_subparsers.add_parser('set', help='设置全局配置')
    global_set_parser.add_argument('key', help='配置键')
    global_set_parser.add_argument('value', help='配置值')

    # 项目配置
    project_parser = config_subparsers.add_parser('project', help='项目配置')
    project_parser.add_argument('name', help='项目名称')
    project_subparsers = project_parser.add_subparsers(dest='project_action', required=True)

    # 查看项目配置
    project_show_parser = project_subparsers.add_parser('show', help='查看项目所有配置')

    # 获取单个项目配置
    project_get_parser = project_subparsers.add_parser('get', help='获取单个项目配置')
    project_get_parser.add_argument('key', help='配置键')

    # 设置项目配置
    project_set_parser = project_subparsers.add_parser('set', help='设置项目配置')
    project_set_parser.add_argument('key', help='配置键')
    project_set_parser.add_argument('value', help='配置值')

    # 停止命令
    stop_parser = subparsers.add_parser('stop', help='停止所有正在执行的任务')

    args = parser.parse_args()
    downloader = GitHubDownloaderCLI()

    try:
        if args.command == 'list':
            downloader.list_projects()
        elif args.command == 'add':
            if args.non_interactive:
                if not args.name or not args.url:
                    print("错误: 非交互式添加需要指定 --name 和 --url")
                    return 1

                downloader.add_project_non_interactive(
                    name=args.name,
                    url=args.url,
                    output=args.output,
                    action_type=args.action,
                    only_latest=args.latest,
                    ignore_ssl=args.ignore_ssl,
                    remarks=args.remarks
                )
            else:
                downloader.interactive_add_project()
        elif args.command == 'remove':
            downloader.remove_project(args.name)
        elif args.command == 'execute':
            # 删除全局停止标志文件
            if os.path.exists('./.run_status/.stop_all'):
                os.remove('./.run_status/.stop_all')

            if args.names:
                # 执行指定的多个项目
                configs = []
                for name in args.names:
                    if name in downloader.config_manager.config:
                        config = dict(downloader.config_manager.config[name])
                        config['name'] = name
                        configs.append(config)
                    else:
                        print(f"警告: 项目 '{name}' 不存在，已跳过")

                if configs:
                    downloader.execute_tasks(configs)
                else:
                    print("没有找到有效的项目配置")
            else:
                # 执行所有项目
                downloader.execute_all_projects()
        elif args.command == 'schedule':
            # 删除全局停止标志文件
            if os.path.exists('./.run_status/.stop_all'):
                os.remove('./.run_status/.stop_all')
            downloader.schedule_tasks()
        elif args.command == 'config':
            if args.config_command == 'global':
                if args.global_action == 'show':
                    global_config = downloader.config_manager.get_global_config()
                    print("\n全局配置:")
                    for key, value in global_config.items():
                        print(f"  {key}: {value}")
                elif args.global_action == 'get':
                    global_config = downloader.config_manager.get_global_config()
                    value = global_config.get(args.key, "未设置")
                    print(f"\n全局配置 {args.key}: {value}")
                elif args.global_action == 'set':
                    downloader.config_global_set(args.key, args.value)
            elif args.config_command == 'project':
                if args.project_action == 'show':
                    downloader.show_project_config(args.name)
                elif args.project_action == 'get':
                    project_config = downloader.config_manager.get_project_config(args.name)
                    value = project_config.get(args.key, "未设置")
                    print(f"\n项目 {args.name} 的配置 {args.key}: {value}")
                elif args.project_action == 'set':
                    downloader.config_project_set(args.name, args.key, args.value)
        elif args.command == 'stop':
            downloader.stop()

    except Exception as e:
        print(f"错误: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())


