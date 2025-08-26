import sys
import os
import re
import time
import logging
import configparser
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, Any, List, Union
from urllib.parse import urlparse
from croniter import croniter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QListWidget, QTabWidget, QMessageBox, QFileDialog, QInputDialog,
    QPlainTextEdit, QGroupBox, QListWidgetItem
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QIcon
from io import StringIO
from GithubDownload.github import GithubDownloader

def get_app_path():
    """获取应用程序所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

class LogHandler(logging.Handler, QObject):
    """自定义日志处理器，将日志发送到Qt信号"""
    log_signal = Signal(str)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)

class OutputRedirector(QObject):
    """重定向标准输出和错误输出到Qt信号"""
    text_written = Signal(str)

    def __init__(self):
        super().__init__()
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._string_io = StringIO()

    def write(self, text):
        self._string_io.write(text)
        self.text_written.emit(text)
        self._stdout.write(text)

    def flush(self):
        self._string_io.flush()
        self._stdout.flush()

    def restore(self):
        sys.stdout = self._stdout
        sys.stderr = self._stderr

class TaskExecutor(QThread):
    """任务执行器线程"""
    task_complete = Signal(dict, bool, str)

    def __init__(self, configs: List[Dict[str, Any]], global_config: Dict[str, Any], max_workers: int = 4):
        super().__init__()
        self.configs = configs
        self.global_config = global_config
        self.max_workers = max_workers
        self._stop_flag = False
        self.downloaders = {}  # 存储所有下载器实例

    def stop(self):
        """停止所有下载任务"""
        self._stop_flag = True
        for downloader in self.downloaders.values():
            downloader.stop_download()

    def run(self):
        """执行所有任务"""
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.execute_task, config): config
                for config in self.configs
            }

            for future in concurrent.futures.as_completed(futures):
                if self._stop_flag:
                    executor.shutdown(wait=False)
                    return

                config = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"任务执行错误: {str(e)}")

    def execute_task(self, config: Dict[str, Any]):
        """执行单个任务"""
        if self._stop_flag:
            return

        project_name = config['name']
        action_type = config.get('action_type', 'download').lower()

        proxies = {
            'http': self.global_config.get('proxies.http') if self.global_config.get('proxies.http') else None,
            'https': self.global_config.get('proxies.https') if self.global_config.get('proxies.https') else None,
        }

        if not proxies or not self.global_config.get('enable_proxy'):
            proxies = None

        try:
            downloader = GithubDownloader(
                url=config['url'],
                output=config.get('output'),
                dingtalk_webhook=self.global_config['dingtalk_webhook'],
                dingtalk_secret=self.global_config['dingtalk_secret'],
                project_name=project_name,
                only_latest=config['only_latest'],
                threads=config['threads'],
                log_file=config['log'],
                verify=not config['ignore_ssl'],
                proxies=proxies
            )

            # 存储下载器实例以便后续停止
            self.downloaders[project_name] = downloader

            if action_type == 'download':
                version_info = downloader.request()
                downloader.download(version_info)

            elif action_type == 'update':
                downloader.check_updates()

            # 任务完成后移除下载器引用
            self.downloaders.pop(project_name, None)

        except Exception as e:
            msg = f"处理项目 {project_name} 时发生错误: {e}"
            self.task_complete.emit(config, False, msg)
            raise

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

    def save_config(self):
        """保存更新后的配置"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)

class GitHubDownloaderGUI(QMainWindow):
    """GitHub下载器GUI主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitHub 下载器")
        self.setGeometry(100, 100, 1400, 700)

        self.app_path = get_app_path()
        self.config_file = os.path.join(self.app_path, "config.ini")
        self.config_manager = ConfigManager(self.config_file)
        self.task_executor = None
        self.timer = QTimer(self)

        self.init_ui()
        self.setup_output_redirection()
        self.load_config()

    def setup_output_redirection(self):
        """设置输出重定向和日志处理"""
        self.output_redirector = OutputRedirector()
        self.output_redirector.text_written.connect(self.append_log)
        sys.stdout = self.output_redirector
        sys.stderr = self.output_redirector

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        self.log_handler = LogHandler()
        self.log_handler.log_signal.connect(self.append_log)
        root_logger.addHandler(self.log_handler)

    def init_ui(self):
        """初始化UI界面"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        # 左侧项目列表区域
        left_area = QWidget()
        left_layout = QVBoxLayout(left_area)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 项目列表（多选模式）
        self.project_list = QListWidget()
        self.project_list.setSelectionMode(QListWidget.MultiSelection)
        self.project_list.currentItemChanged.connect(self.load_project_data)

        # 项目操作按钮
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("新增项目")
        self.add_btn.clicked.connect(self.add_project)
        btn_layout.addWidget(self.add_btn)

        self.delete_btn = QPushButton("删除项目")
        self.delete_btn.clicked.connect(self.delete_project)
        btn_layout.addWidget(self.delete_btn)

        left_layout.addWidget(QLabel("项目列表"))
        left_layout.addWidget(self.project_list)
        left_layout.addLayout(btn_layout)

        # 中间日志区域
        center_area = QWidget()
        center_layout = QVBoxLayout(center_area)

        # 执行控制按钮
        control_layout = QHBoxLayout()

        # 选择控制按钮
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all_projects)
        control_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("取消选择")
        self.deselect_all_btn.clicked.connect(self.deselect_all_projects)
        control_layout.addWidget(self.deselect_all_btn)

        # 执行控制按钮
        self.execute_btn = QPushButton("执行勾选项目")
        self.execute_btn.clicked.connect(self.execute_checked_projects)
        control_layout.addWidget(self.execute_btn)

        self.execute_all_btn = QPushButton("执行所有项目")
        self.execute_all_btn.clicked.connect(self.execute_all_projects)
        control_layout.addWidget(self.execute_all_btn)

        self.stop_btn = QPushButton("停止执行")
        self.stop_btn.clicked.connect(self.stop_execution)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        center_layout.addLayout(control_layout)

        # 日志显示
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        center_layout.addWidget(self.log_display)

        # 状态栏
        self.status_label = QLabel("就绪")
        center_layout.addWidget(self.status_label)

        # 右侧配置区域
        right_area = QWidget()
        right_layout = QVBoxLayout(right_area)

        # 配置选项卡
        self.tabs = QTabWidget()

        # 项目设置选项卡
        project_tab = QWidget()
        self.init_project_tab(project_tab)
        self.tabs.addTab(project_tab, "项目设置")

        # 全局设置选项卡
        global_tab = QWidget()
        self.init_global_tab(global_tab)
        self.tabs.addTab(global_tab, "全局设置")

        # 计划任务选项卡
        schedule_tab = QWidget()
        self.init_schedule_tab(schedule_tab)
        self.tabs.addTab(schedule_tab, "计划任务")

        right_layout.addWidget(self.tabs)

        # 保存按钮
        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self.save_config)
        right_layout.addWidget(self.save_btn)

        # 添加左右区域到主布局
        main_layout.addWidget(left_area, stretch=1)
        main_layout.addWidget(center_area, stretch=2)
        main_layout.addWidget(right_area, stretch=1)

    def init_global_tab(self, tab):
        """初始化全局设置选项卡"""
        layout = QVBoxLayout(tab)

        # 钉钉机器人设置
        dingtalk_group = QGroupBox("钉钉机器人设置")
        dingtalk_layout = QVBoxLayout(dingtalk_group)

        self.dingtalk_webhook = QLineEdit()
        self.dingtalk_webhook.setPlaceholderText("钉钉机器人Webhook地址")
        dingtalk_layout.addWidget(QLabel("Webhook地址:"))
        dingtalk_layout.addWidget(self.dingtalk_webhook)

        self.dingtalk_secret = QLineEdit()
        self.dingtalk_secret.setPlaceholderText("钉钉机器人Secret")
        dingtalk_layout.addWidget(QLabel("Secret:"))
        dingtalk_layout.addWidget(self.dingtalk_secret)

        layout.addWidget(dingtalk_group)

        # 代理设置
        proxy_group = QGroupBox("代理设置")
        proxy_layout = QVBoxLayout(proxy_group)

        http_layout = QHBoxLayout()
        http_layout.addWidget(QLabel("HTTP代理:"))
        self.global_proxy_http = QLineEdit()
        self.global_proxy_http.setPlaceholderText("例如: http://127.0.0.1:8080")
        http_layout.addWidget(self.global_proxy_http)
        proxy_layout.addLayout(http_layout)

        https_layout = QHBoxLayout()
        https_layout.addWidget(QLabel("HTTPS代理:"))
        self.global_proxy_https = QLineEdit()
        self.global_proxy_https.setPlaceholderText("例如: https://127.0.0.1:8080")
        https_layout.addWidget(self.global_proxy_https)
        proxy_layout.addLayout(https_layout)

        self.enable_proxy = QCheckBox("应用代理")
        self.enable_proxy.setChecked(True)
        proxy_layout.addWidget(self.enable_proxy)

        layout.addWidget(proxy_group)
        layout.addStretch()

    def init_project_tab(self, tab):
        """初始化项目设置选项卡"""
        layout = QVBoxLayout(tab)

        # 基本信息
        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("项目名称")
        layout.addWidget(QLabel("项目名称:"))
        layout.addWidget(self.project_name)

        self.project_url = QLineEdit()
        self.project_url.setPlaceholderText("GitHub项目URL")
        layout.addWidget(QLabel("GitHub URL:"))
        layout.addWidget(self.project_url)

        # 输出路径
        output_layout = QHBoxLayout()
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("输出路径")
        output_layout.addWidget(self.output_path)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self.browse_output_path)
        output_layout.addWidget(browse_btn)
        layout.addWidget(QLabel("输出路径:"))
        layout.addLayout(output_layout)

        # 日志文件路径
        log_layout = QHBoxLayout()
        self.log_path = QLineEdit()
        self.log_path.setPlaceholderText("日志文件路径")
        log_layout.addWidget(self.log_path)

        log_browse_btn = QPushButton("浏览...")
        log_browse_btn.clicked.connect(self.browse_log_path)
        log_layout.addWidget(log_browse_btn)
        layout.addWidget(QLabel("日志文件路径:"))
        layout.addLayout(log_layout)

        # 操作类型
        layout.addWidget(QLabel("操作类型:"))
        self.action_type = QComboBox()
        self.action_type.addItems(["download", "update"])
        layout.addWidget(self.action_type)

        # 其他选项
        options_layout = QHBoxLayout()
        self.only_latest = QCheckBox("仅最新版本")
        self.only_latest.setChecked(True)
        options_layout.addWidget(self.only_latest)

        self.ignore_ssl = QCheckBox("忽略SSL验证")
        options_layout.addWidget(self.ignore_ssl)
        layout.addLayout(options_layout)

        # 线程数
        layout.addWidget(QLabel("线程数:"))
        self.threads = QComboBox()
        self.threads.addItems(["1", "2", "4", "8", "16"])
        self.threads.setCurrentIndex(2)  # 默认选择4线程
        layout.addWidget(self.threads)

        # 备注
        layout.addWidget(QLabel("备注:"))
        self.remarks = QLineEdit()
        self.remarks.setPlaceholderText("项目描述/备注")
        layout.addWidget(self.remarks)

        layout.addStretch()

    def init_schedule_tab(self, tab):
        """初始化计划任务选项卡"""
        layout = QVBoxLayout(tab)

        # 计划任务设置组
        schedule_group = QGroupBox("计划任务设置")
        schedule_layout = QVBoxLayout(schedule_group)

        # Cron表达式设置
        cron_layout = QHBoxLayout()
        cron_layout.addWidget(QLabel("Cron表达式:"))
        self.cron_expression = QLineEdit()
        self.cron_expression.setPlaceholderText("例如: 0 9 * * * (每天9点)")
        self.cron_expression.textChanged.connect(self.update_next_executions)
        cron_layout.addWidget(self.cron_expression)
        schedule_layout.addLayout(cron_layout)

        # 下次执行时间显示
        self.next_executions = QPlainTextEdit()
        self.next_executions.setReadOnly(True)
        self.next_executions.setMaximumHeight(100)
        schedule_layout.addWidget(QLabel("下次执行时间:"))
        schedule_layout.addWidget(self.next_executions)

        # 定时任务控制按钮
        timer_btn_layout = QHBoxLayout()
        self.start_timer_btn = QPushButton("启动定时")
        self.start_timer_btn.clicked.connect(self.start_timer)
        timer_btn_layout.addWidget(self.start_timer_btn)

        self.stop_timer_btn = QPushButton("停止定时")
        self.stop_timer_btn.clicked.connect(self.stop_timer)
        self.stop_timer_btn.setEnabled(False)
        timer_btn_layout.addWidget(self.stop_timer_btn)
        schedule_layout.addLayout(timer_btn_layout)

        # 计划任务项目选择组
        project_group = QGroupBox("选择定时执行的项目")
        project_layout = QVBoxLayout(project_group)

        # 项目列表（多选模式）
        self.schedule_project_list = QListWidget()
        self.schedule_project_list.setSelectionMode(QListWidget.MultiSelection)
        project_layout.addWidget(self.schedule_project_list)

        # 选择控制按钮
        select_btn_layout = QHBoxLayout()
        self.select_all_schedule_btn = QPushButton("全选")
        self.select_all_schedule_btn.clicked.connect(self.select_all_schedule_projects)
        select_btn_layout.addWidget(self.select_all_schedule_btn)

        self.deselect_all_schedule_btn = QPushButton("取消选择")
        self.deselect_all_schedule_btn.clicked.connect(self.deselect_all_schedule_projects)
        select_btn_layout.addWidget(self.deselect_all_schedule_btn)
        project_layout.addLayout(select_btn_layout)

        # 高亮显示已选项目
        self.highlight_schedule_projects()

        schedule_layout.addWidget(project_group)
        layout.addWidget(schedule_group)
        layout.addStretch()

    def update_schedule_project_list(self):
        """更新计划任务项目列表"""
        self.schedule_project_list.clear()
        for section in self.config_manager.config.sections():
            if section != 'global':
                item = QListWidgetItem(section)
                self.schedule_project_list.addItem(item)

                # 从全局配置中获取已选项目
                scheduled_projects = self.config_manager.get_global_config().get('scheduled_projects', '').split(',')
                if section in scheduled_projects:
                    item.setSelected(True)
                    item.setBackground(Qt.yellow)

    def select_all_schedule_projects(self):
        """全选所有计划任务项目"""
        for i in range(self.schedule_project_list.count()):
            item = self.schedule_project_list.item(i)
            item.setSelected(True)
            item.setBackground(Qt.yellow)

    def deselect_all_schedule_projects(self):
        """取消全选所有计划任务项目"""
        for i in range(self.schedule_project_list.count()):
            item = self.schedule_project_list.item(i)
            item.setSelected(False)
            item.setBackground(Qt.white)

    def highlight_schedule_projects(self):
        """高亮显示已选计划任务项目"""
        for i in range(self.schedule_project_list.count()):
            item = self.schedule_project_list.item(i)
            if item.isSelected():
                item.setBackground(Qt.yellow)
            else:
                item.setBackground(Qt.white)

    def get_scheduled_projects(self):
        """获取勾选的需要定时执行的项目"""
        return [item.text() for item in self.schedule_project_list.selectedItems()]

    def calculate_next_executions(self, cron_expr: str, count: int = 3) -> List[datetime]:
        """计算下次执行时间"""
        if not cron_expr:
            return []

        try:
            now = datetime.now()
            cron = croniter(cron_expr, now)
            return [cron.get_next(datetime) for _ in range(count)]
        except Exception:
            return []

    def update_next_executions(self):
        """更新下次执行时间显示"""
        cron_expr = self.cron_expression.text().strip()
        next_times = self.calculate_next_executions(cron_expr)

        self.next_executions.clear()
        if not next_times:
            self.next_executions.appendPlainText("无效的cron表达式")
            return

        for i, dt in enumerate(next_times, 1):
            self.next_executions.appendPlainText(f"{i}. {dt.strftime('%Y-%m-%d %H:%M:%S')}")

    def start_timer(self):
        """启动定时执行"""
        cron_expr = self.cron_expression.text().strip()
        if not cron_expr:
            QMessageBox.warning(self, "警告", "请输入有效的cron表达式!")
            return

        try:
            now = datetime.now()
            cron = croniter(cron_expr, now)
            next_time = cron.get_next(datetime)

            delay = (next_time - now).total_seconds() * 1000
            self.timer.start(delay)

            self.append_log(f"定时任务已启动: {cron_expr}")
            self.append_log(f"第一次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")

            self.status_label.setText("定时任务已启动")
            self.timer.timeout.connect(self.execute_scheduled_projects)
            self.timer.timeout.connect(lambda: self.timer.start(self.calculate_next_delay(cron_expr)))

            self.start_timer_btn.setEnabled(False)
            self.stop_timer_btn.setEnabled(True)

        except Exception as e:
            QMessageBox.warning(self, "警告", f"无效的cron表达式: {str(e)}")

    def calculate_next_delay(self, cron_expr: str) -> int:
        """计算下次执行的延迟时间(毫秒)"""
        now = datetime.now()
        cron = croniter(cron_expr, now)
        next_time = cron.get_next(datetime)
        return int((next_time - now).total_seconds() * 1000)

    def stop_timer(self):
        """停止定时执行"""
        if self.timer.isActive():
            self.timer.stop()
            self.append_log("定时任务已停止")
            self.status_label.setText("定时任务已停止")
            self.start_timer_btn.setEnabled(True)
            self.stop_timer_btn.setEnabled(False)

    def execute_scheduled_projects(self):
        """执行计划任务中选中的项目"""
        scheduled_projects = self.get_scheduled_projects()
        if not scheduled_projects:
            self.append_log("没有选择要定时执行的项目")
            return

        configs = []
        for project in scheduled_projects:
            if project in self.config_manager.config:
                config = dict(self.config_manager.config[project])
                config['name'] = project
                configs.append(config)

        if configs:
            self.execute_tasks(configs)

    def select_all_projects(self):
        """全选所有项目"""
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            item.setSelected(True)

    def deselect_all_projects(self):
        """取消全选所有项目"""
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            item.setSelected(False)

    def get_checked_projects(self):
        """获取勾选的项目"""
        return [item.text() for item in self.project_list.selectedItems()]

    def execute_checked_projects(self):
        """执行勾选的项目"""
        checked_projects = self.get_checked_projects()
        if not checked_projects:
            QMessageBox.warning(self, "警告", "请先勾选要执行的项目!")
            return

        configs = []
        for project in checked_projects:
            if project in self.config_manager.config:
                config = dict(self.config_manager.config[project])
                config['name'] = project
                configs.append(config)

        if configs:
            self.execute_tasks(configs)

    def execute_all_projects(self):
        """执行所有项目"""
        configs = self.config_manager.get_project_configs()
        if not configs:
            QMessageBox.warning(self, "警告", "没有可执行的项目!")
            return

        self.execute_tasks(configs)

    def execute_tasks(self, configs: List[Dict[str, Any]]):
        """执行任务"""
        if self.task_executor and self.task_executor.isRunning():
            # QMessageBox.warning(self, "警告", "已有任务正在执行!")
            return

        self.log_display.clear()
        global_config = self.config_manager.get_global_config()

        self.task_executor = TaskExecutor(configs, global_config)
        self.task_executor.task_complete.connect(self.handle_task_complete)
        self.task_executor.finished.connect(self.handle_tasks_finished)

        self.execute_btn.setEnabled(False)
        self.execute_all_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("任务执行中...")

        self.task_executor.start()

    def handle_task_complete(self, config: Dict[str, Any], success: bool, message: str):
        """处理单个任务完成"""
        project_name = config['name']
        status = "成功" if success else "失败"
        self.append_log(f"项目 {project_name} 执行{status}: {message}")

    def handle_tasks_finished(self):
        """所有任务完成处理"""
        self.execute_btn.setEnabled(True)
        self.execute_all_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("任务执行完成")
        self.task_executor = None

    def stop_execution(self):
        """停止执行任务"""
        if self.task_executor and self.task_executor.isRunning():
            self.task_executor.stop()
            self.status_label.setText("正在停止任务...")
            self.append_log("正在停止所有下载任务...")

    def append_log(self, message: str):
        """追加日志消息"""
        self.log_display.appendPlainText(message)
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                self.config_manager.config.read(self.config_file, encoding='utf-8')
                self.update_project_list()
                self.update_schedule_project_list()

                # 加载全局设置
                global_config = self.config_manager.get_global_config()
                self.dingtalk_webhook.setText(global_config.get('dingtalk_webhook', ''))
                self.dingtalk_secret.setText(global_config.get('dingtalk_secret', ''))
                self.global_proxy_http.setText(global_config.get('proxies.http', ''))
                self.global_proxy_https.setText(global_config.get('proxies.https', ''))
                self.enable_proxy.setChecked(global_config.get('enable_proxy', 'true').lower() == 'true')
                self.cron_expression.setText(global_config.get('cron_expression', ''))

                # 如果配置中有定时任务设置，自动启动
                if global_config.get('cron_expression'):
                    self.start_timer()

            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载配置文件失败: {str(e)}")
        else:
            self.config_manager.create_default_config()

    def update_project_list(self):
        """更新项目列表"""
        self.project_list.clear()
        for section in self.config_manager.config.sections():
            if section != 'global':
                self.project_list.addItem(section)

    def load_project_data(self, current, previous):
        """加载选中项目的配置数据"""
        if not current:
            return

        section = current.text()
        if section in self.config_manager.config:
            project_data = dict(self.config_manager.config[section])

            self.project_name.setText(section)
            self.project_url.setText(project_data.get('url', ''))
            self.output_path.setText(project_data.get('output', ''))
            self.log_path.setText(project_data.get('log', ''))

            action_type = project_data.get('action_type', 'download')
            if action_type in ["download", "update"]:
                self.action_type.setCurrentText(action_type)

            self.only_latest.setChecked(project_data.get('only_latest', 'true').lower() == 'true')
            self.ignore_ssl.setChecked(project_data.get('ignore_ssl', 'false').lower() == 'true')

            threads = project_data.get('threads', '4')
            if threads in ["1", "2", "4", "8", "16"]:
                self.threads.setCurrentText(threads)

            self.remarks.setText(project_data.get('remarks', ''))

    def add_project(self):
        """添加新项目"""
        name, ok = QInputDialog.getText(
            self, '新增项目', '请输入项目名称:'
        )

        if ok and name:
            name = name.strip()
            if not name:
                QMessageBox.warning(self, "警告", "项目名称不能为空!")
                return

            if name in self.config_manager.config:
                QMessageBox.warning(self, "警告", "项目已存在!")
                return

            self.config_manager.config[name] = {
                'url': '',
                'output': '',
                'action_type': 'download',
                'only_latest': 'true',
                'threads': '4',
                'ignore_ssl': 'false',
                'proxies.http': '',
                'proxies.https': '',
                'remarks': '',
                'log': ''
            }

            self.update_project_list()
            self.update_schedule_project_list()
            self.project_list.setCurrentRow(self.project_list.count() - 1)

    def delete_project(self):
        """删除当前选中的项目"""
        current_item = self.project_list.currentItem()
        if not current_item:
            return

        reply = QMessageBox.question(
            self, '确认删除',
            f'确定要删除项目 "{current_item.text()}" 吗?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            section = current_item.text()
            self.config_manager.config.remove_section(section)
            self.update_project_list()
            self.update_schedule_project_list()

    def browse_output_path(self):
        """浏览输出路径"""
        current_path = self.output_path.text()
        if not current_path or not os.path.exists(current_path):
            current_path = self.app_path

        path = QFileDialog.getExistingDirectory(self, "选择输出目录", current_path)
        if path:
            self.output_path.setText(path)

    def browse_log_path(self):
        """浏览日志文件路径"""
        current_path = self.log_path.text()
        if not current_path or not os.path.exists(os.path.dirname(current_path)):
            current_path = os.path.join(self.app_path, 'logs')

        path, _ = QFileDialog.getSaveFileName(
            self, "选择日志文件", current_path,
            filter="日志文件 (*.log);;所有文件 (*)"
        )
        if path:
            self.log_path.setText(path)

    def save_config(self):
        """保存配置"""
        try:
            # 确保有global部分
            if not self.config_manager.config.has_section('global'):
                self.config_manager.config.add_section('global')

            # 保存全局设置
            self.config_manager.config['global']['dingtalk_webhook'] = self.dingtalk_webhook.text().strip()
            self.config_manager.config['global']['dingtalk_secret'] = self.dingtalk_secret.text().strip()
            self.config_manager.config['global']['proxies.http'] = self.global_proxy_http.text().strip()
            self.config_manager.config['global']['proxies.https'] = self.global_proxy_https.text().strip()
            self.config_manager.config['global']['enable_proxy'] = 'true' if self.enable_proxy.isChecked() else 'false'
            self.config_manager.config['global']['cron_expression'] = self.cron_expression.text().strip()

            # 保存计划任务项目选择
            scheduled_projects = ','.join(self.get_scheduled_projects())
            self.config_manager.config['global']['scheduled_projects'] = scheduled_projects

            # 保存当前项目设置
            current_item = self.project_list.currentItem()
            if current_item:
                old_section = current_item.text().strip()
                new_section = self.project_name.text().strip()

                # 检查项目名称是否被修改
                if old_section != new_section:
                    if not new_section:
                        QMessageBox.warning(self, "警告", "项目名称不能为空!")
                        return

                    if new_section in self.config_manager.config and new_section != old_section:
                        QMessageBox.warning(self, "警告", "项目名称已存在!")
                        return

                    # 复制旧项目配置到新项目
                    if old_section in self.config_manager.config:
                        self.config_manager.config[new_section] = {}
                        for key, value in self.config_manager.config[old_section].items():
                            self.config_manager.config[new_section][key] = value.strip() if isinstance(value, str) else value

                        # 删除旧项目
                        self.config_manager.config.remove_section(old_section)
                        current_item.setText(new_section)

                # 更新当前项目配置
                section = new_section
                if not self.config_manager.config.has_section(section):
                    self.config_manager.config.add_section(section)

                self.config_manager.config[section]['url'] = self.project_url.text().strip()
                self.config_manager.config[section]['output'] = self.output_path.text().strip()
                self.config_manager.config[section]['log'] = self.log_path.text().strip()
                self.config_manager.config[section]['action_type'] = self.action_type.currentText().strip()
                self.config_manager.config[section]['only_latest'] = 'true' if self.only_latest.isChecked() else 'false'
                self.config_manager.config[section]['ignore_ssl'] = 'true' if self.ignore_ssl.isChecked() else 'false'
                self.config_manager.config[section]['threads'] = self.threads.currentText().strip()
                self.config_manager.config[section]['remarks'] = self.remarks.text().strip()

            # 写入文件
            self.config_manager.save_config()

            # 保存后刷新GUI显示
            self.refresh_ui()

            # 如果cron表达式有变化，重新设置定时器
            if self.timer.isActive():
                self.stop_timer()
            if self.cron_expression.text().strip():
                self.start_timer()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置失败: {str(e)}")

    def refresh_ui(self):
        """刷新UI显示"""
        # 重新加载配置
        self.load_config()

        # 更新项目列表
        self.update_project_list()
        self.update_schedule_project_list()

        # 如果当前有选中的项目，重新加载其数据
        current_item = self.project_list.currentItem()
        if current_item:
            self.load_project_data(current_item, None)

        # 更新下次执行时间显示
        self.update_next_executions()

        # 高亮显示已选计划任务项目
        self.highlight_schedule_projects()

    def closeEvent(self, event):
        """窗口关闭事件处理"""
        if self.task_executor and self.task_executor.isRunning():
            reply = QMessageBox.question(
                self, '确认关闭',
                '有任务正在执行，确定要关闭窗口吗?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        self.output_redirector.restore()
        self.save_config()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GitHubDownloaderGUI()
    window.show()
    sys.exit(app.exec())
