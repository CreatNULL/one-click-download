import sys
import os
import shutil
import logging
import configparser
import concurrent.futures
from datetime import datetime
from typing import Dict, Any, List
from croniter import croniter
from pathvalidate import sanitize_filename
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QListWidget, QTabWidget, QMessageBox, QFileDialog, QInputDialog,
    QPlainTextEdit, QGroupBox, QListWidgetItem, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
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

    def __init__(self, configs: List[Dict[str, Any]], max_workers: int = 4):
        super().__init__()
        self.configs = configs
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

        try:
            downloader = GithubDownloader(
                url=config['url'],
                output=config.get('output'),
                dingtalk_webhook=config['dingtalk_webhook'],
                dingtalk_secret=config['dingtalk_secret'],
                project_name=project_name,
                only_latest=config['only_latest'],
                threads=4,
                log_file=config['log_file'],
                verify=not config['ignore_ssl'],
                proxies=config['proxies'],
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
    """配置文件管理器（添加分组支持）"""
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        if not os.path.exists(config_file):
            self.create_default_config()
        self.config.read(config_file, encoding='utf-8')

    def create_default_config(self):
        """创建默认配置文件（添加分组支持）"""
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
            f.write("threads = \n")
            f.write("groups = 默认\n")  # 添加默认分组

    def get_global_config(self) -> Dict[str, str]:
        """获取全局配置"""
        return dict(self.config['global']) if 'global' in self.config else {}

    def get_groups(self) -> List[str]:
        """获取所有分组"""
        groups = self.config.get('global', 'groups', fallback='默认')
        return [g.strip() for g in groups.split(',') if g.strip()]

    def add_group(self, group_name: str):
        """添加新分组"""
        groups = self.get_groups()
        if group_name not in groups:
            groups.append(group_name)
            self.config.set('global', 'groups', ','.join(groups))

    def rename_group(self, old_name: str, new_name: str):
        """重命名分组"""
        groups = self.get_groups()
        if old_name in groups and new_name not in groups:
            index = groups.index(old_name)
            groups[index] = new_name
            self.config.set('global', 'groups', ','.join(groups))

            # 更新所有属于该分组的项目
            for section in self.config.sections():
                if section != 'global':
                    if self.config[section].get('group', '默认') == old_name:
                        self.config[section]['group'] = new_name

    def delete_group(self, group_name: str, default_group: str = '默认'):
        """删除分组并将项目移动到默认分组"""
        groups = self.get_groups()
        if group_name in groups and group_name != default_group:
            groups.remove(group_name)
            self.config.set('global', 'groups', ','.join(groups))

            # 将所有属于该分组的项目移动到默认分组
            for section in self.config.sections():
                if section != 'global':
                    if self.config[section].get('group', '默认') == group_name:
                        self.config[section]['group'] = default_group

    def get_project_configs(self) -> List[Dict[str, Any]]:
        """获取所有项目配置（添加分组支持）"""
        projects = []
        for section in self.config.sections():
            if section != 'global':
                project = dict(self.config[section])
                project['name'] = section
                project['group'] = project.get('group', '默认')
                projects.append(project)
        return projects

    def get_projects_by_group(self, group_name: str) -> List[Dict[str, Any]]:
        """获取指定分组的项目"""
        return [p for p in self.get_project_configs() if p.get('group', '默认') == group_name]

    def save_config(self):
        """保存更新后的配置"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)

class GitHubDownloaderGUI(QMainWindow):
    """GitHub下载器GUI主窗口（完整实现）"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitHub 下载器")
        self.setGeometry(100, 100, 1400, 700)

        self.app_path = get_app_path()
        self.config_file = os.path.join(self.app_path, "config.ini")
        self.config_manager = ConfigManager(self.config_file)
        self.task_executor = None
        self.output_redirector = OutputRedirector()
        self.log_handler = LogHandler()

        # 初始化UI组件
        self.init_ui_components()
        self.init_ui_layout()
        self.setup_output_redirection()

        # 加载配置
        self.load_config()

    def init_ui_components(self):
        """初始化UI组件"""
        # 分组管理组件
        self.group_combo = QComboBox()
        self.add_group_btn = QPushButton("添加分组")
        self.rename_group_btn = QPushButton("重命名分组")
        self.delete_group_btn = QPushButton("删除分组")

        # 项目列表组件
        self.project_list = QListWidget()
        self.project_list.setSelectionMode(QListWidget.MultiSelection)

        # 项目操作按钮
        self.add_btn = QPushButton("新增项目")
        self.delete_btn = QPushButton("删除项目")
        self.select_all_btn = QPushButton("全选")
        self.deselect_all_btn = QPushButton("取消选择")
        self.execute_btn = QPushButton("执行勾选项目")
        self.execute_all_btn = QPushButton("执行所有项目")
        self.stop_btn = QPushButton("停止执行")

        # 项目配置组件
        self.project_name = QLineEdit()
        self.project_url = QLineEdit()
        self.output_path = QLineEdit()
        self.action_type = QComboBox()
        self.action_type.addItems(["download", "update"])
        self.only_latest = QCheckBox("仅最新版本")
        self.ignore_ssl = QCheckBox("忽略SSL验证")
        self.remarks = QLineEdit()

        # 全局配置组件
        self.dingtalk_webhook = QLineEdit()
        self.dingtalk_secret = QLineEdit()
        self.global_proxy_http = QLineEdit()
        self.global_proxy_https = QLineEdit()
        self.enable_proxy = QCheckBox("应用代理")
        self.global_log_file = QLineEdit()
        self.threads = QComboBox()
        self.threads.addItems(["1", "2", "4", "8", "16"])

        # 定时任务组件
        self.cron_expression = QLineEdit()
        self.next_executions = QPlainTextEdit()
        self.start_timer_btn = QPushButton("启动定时")
        self.stop_timer_btn = QPushButton("停止定时")
        self.schedule_project_list = QListWidget()
        self.schedule_project_list.setSelectionMode(QListWidget.MultiSelection)

        # 日志和状态组件
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.status_label = QLabel("就绪")

    def init_ui_layout(self):
        """初始化UI布局"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        # 左侧区域 - 分组和项目列表
        left_area = QWidget()
        left_layout = QVBoxLayout(left_area)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 分组管理控件
        group_control_layout = QHBoxLayout()
        group_control_layout.addWidget(QLabel("分组:"))
        group_control_layout.addWidget(self.group_combo)
        left_layout.addLayout(group_control_layout)

        group_btn_layout = QHBoxLayout()
        group_btn_layout.addWidget(self.add_group_btn)
        group_btn_layout.addWidget(self.rename_group_btn)
        group_btn_layout.addWidget(self.delete_group_btn)
        left_layout.addLayout(group_btn_layout)

        # 项目列表
        left_layout.addWidget(QLabel("项目列表"))
        left_layout.addWidget(self.project_list)

        # 项目操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.delete_btn)
        left_layout.addLayout(btn_layout)

        select_btn_layout = QHBoxLayout()
        select_btn_layout.addWidget(self.select_all_btn)
        select_btn_layout.addWidget(self.deselect_all_btn)
        left_layout.addLayout(select_btn_layout)

        execute_btn_layout = QHBoxLayout()
        execute_btn_layout.addWidget(self.execute_btn)
        execute_btn_layout.addWidget(self.execute_all_btn)
        execute_btn_layout.addWidget(self.stop_btn)
        left_layout.addLayout(execute_btn_layout)

        # 中间区域 - 日志显示
        center_area = QWidget()
        center_layout = QVBoxLayout(center_area)
        center_layout.addWidget(QLabel("日志输出"))
        center_layout.addWidget(self.log_display)
        center_layout.addWidget(self.status_label)

        # 右侧区域 - 配置选项卡
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
        right_layout.addWidget(self.save_btn)

        # 添加左右区域到主布局
        main_layout.addWidget(left_area, stretch=1)
        main_layout.addWidget(center_area, stretch=2)
        main_layout.addWidget(right_area, stretch=1)

        # 连接信号槽
        self.connect_signals()

    def init_project_tab(self, tab):
        """初始化项目设置选项卡"""
        layout = QVBoxLayout(tab)

        # 基本信息
        layout.addWidget(QLabel("项目名称:"))
        layout.addWidget(self.project_name)

        layout.addWidget(QLabel("GitHub URL:"))
        layout.addWidget(self.project_url)

        # 输出路径
        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_path)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self.browse_output_path)
        output_layout.addWidget(browse_btn)
        layout.addWidget(QLabel("输出路径:"))
        layout.addLayout(output_layout)

        # 操作类型
        layout.addWidget(QLabel("操作类型:"))
        layout.addWidget(self.action_type)

        # 其他选项
        options_layout = QHBoxLayout()
        options_layout.addWidget(self.only_latest)
        options_layout.addWidget(self.ignore_ssl)
        layout.addLayout(options_layout)

        # 备注
        layout.addWidget(QLabel("备注:"))
        layout.addWidget(self.remarks)

        layout.addStretch()

    def init_global_tab(self, tab):
        """初始化全局设置选项卡"""
        layout = QVBoxLayout(tab)

        # 钉钉机器人设置
        dingtalk_group = QGroupBox("钉钉机器人设置")
        dingtalk_layout = QVBoxLayout(dingtalk_group)

        dingtalk_layout.addWidget(QLabel("Webhook地址:"))
        dingtalk_layout.addWidget(self.dingtalk_webhook)

        dingtalk_layout.addWidget(QLabel("Secret:"))
        dingtalk_layout.addWidget(self.dingtalk_secret)

        layout.addWidget(dingtalk_group)

        # 日志文件设置
        log_group = QGroupBox("日志设置")
        log_layout = QVBoxLayout(log_group)

        log_file_layout = QHBoxLayout()
        log_file_layout.addWidget(self.global_log_file)
        log_browse_btn = QPushButton("浏览...")
        log_browse_btn.clicked.connect(self.browse_global_log_path)
        log_file_layout.addWidget(log_browse_btn)
        log_layout.addWidget(QLabel("日志文件路径:"))
        log_layout.addLayout(log_file_layout)

        layout.addWidget(log_group)

        # 代理设置
        proxy_group = QGroupBox("代理设置")
        proxy_layout = QVBoxLayout(proxy_group)

        http_layout = QHBoxLayout()
        http_layout.addWidget(QLabel("HTTP代理:"))
        http_layout.addWidget(self.global_proxy_http)
        proxy_layout.addLayout(http_layout)

        https_layout = QHBoxLayout()
        https_layout.addWidget(QLabel("HTTPS代理:"))
        https_layout.addWidget(self.global_proxy_https)
        proxy_layout.addLayout(https_layout)

        proxy_layout.addWidget(self.enable_proxy)
        layout.addWidget(proxy_group)

        # 线程数
        layout.addWidget(QLabel("线程数:"))
        layout.addWidget(self.threads)

        layout.addStretch()

    def init_schedule_tab(self, tab):
        """初始化计划任务选项卡"""
        layout = QVBoxLayout(tab)

        # Cron表达式设置
        cron_layout = QHBoxLayout()
        cron_layout.addWidget(QLabel("Cron表达式:"))
        cron_layout.addWidget(self.cron_expression)
        layout.addLayout(cron_layout)

        # 下次执行时间显示
        layout.addWidget(QLabel("下次执行时间:"))
        layout.addWidget(self.next_executions)

        # 定时任务控制按钮
        timer_btn_layout = QHBoxLayout()
        timer_btn_layout.addWidget(self.start_timer_btn)
        timer_btn_layout.addWidget(self.stop_timer_btn)
        layout.addLayout(timer_btn_layout)

        # 计划任务项目选择
        layout.addWidget(QLabel("选择定时执行的项目:"))
        layout.addWidget(self.schedule_project_list)

        # 选择控制按钮
        select_btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(self.select_all_schedule_projects)
        deselect_all_btn = QPushButton("取消选择")
        deselect_all_btn.clicked.connect(self.deselect_all_schedule_projects)
        select_btn_layout.addWidget(select_all_btn)
        select_btn_layout.addWidget(deselect_all_btn)
        layout.addLayout(select_btn_layout)

        layout.addStretch()

    def connect_signals(self):
        """连接信号槽"""
        # 分组管理
        self.group_combo.currentTextChanged.connect(self.filter_projects_by_group)
        self.add_group_btn.clicked.connect(self.add_group)
        self.rename_group_btn.clicked.connect(self.rename_group)
        self.delete_group_btn.clicked.connect(self.delete_group)

        # 项目列表
        self.project_list.currentItemChanged.connect(self.load_project_data)
        self.project_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.project_list.customContextMenuRequested.connect(self.show_project_context_menu)

        # 项目操作
        self.add_btn.clicked.connect(self.add_project)
        self.delete_btn.clicked.connect(self.delete_project)
        self.select_all_btn.clicked.connect(self.select_all_projects)
        self.deselect_all_btn.clicked.connect(self.deselect_all_projects)
        self.execute_btn.clicked.connect(self.execute_checked_projects)
        self.execute_all_btn.clicked.connect(self.execute_all_projects)
        self.stop_btn.clicked.connect(self.stop_execution)

        # 定时任务
        self.cron_expression.textChanged.connect(self.update_next_executions)
        self.start_timer_btn.clicked.connect(self.start_timer)
        self.stop_timer_btn.clicked.connect(self.stop_timer)

        # 保存配置
        self.save_btn.clicked.connect(self.save_config)

        # 日志处理
        self.log_handler.log_signal.connect(self.append_log)
        self.output_redirector.text_written.connect(self.append_log)

    def setup_output_redirection(self):
        """设置输出重定向和日志处理"""
        sys.stdout = self.output_redirector
        sys.stderr = self.output_redirector

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(self.log_handler)

    def append_log(self, message: str):
        """追加日志消息"""
        self.log_display.appendPlainText(message)
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_group_combo(self):
        """更新分组下拉框"""
        current_group = self.group_combo.currentText()
        self.group_combo.clear()
        groups = self.config_manager.get_groups()
        self.group_combo.addItems(groups)

        if current_group in groups:
            self.group_combo.setCurrentText(current_group)

    def filter_projects_by_group(self, group_name: str):
        """根据分组过滤项目"""
        self.update_project_list()

    def update_project_list(self):
        """更新项目列表"""
        current_group = self.group_combo.currentText()
        self.project_list.clear()

        for section in self.config_manager.config.sections():
            if section != 'global':
                group = self.config_manager.config[section].get('group', '默认')
                if group == current_group:
                    self.project_list.addItem(section)

    def show_project_context_menu(self, position):
        """显示项目右键菜单"""
        selected_items = self.project_list.selectedItems()
        if not selected_items:
            return

        menu = QMenu()

        # 添加移动到分组的子菜单
        move_to_menu = menu.addMenu("移动到分组")

        # 添加所有分组选项
        for group in self.config_manager.get_groups():
            if group != self.group_combo.currentText():  # 不显示当前分组
                action = move_to_menu.addAction(group)
                action.triggered.connect(lambda _, g=group: self.move_projects_to_group(g))

        # 添加从分组删除选项（移动到默认分组）
        if self.group_combo.currentText() != '默认':
            remove_action = menu.addAction("从分组删除")
            remove_action.triggered.connect(lambda: self.move_projects_to_group('默认'))

        menu.exec_(self.project_list.viewport().mapToGlobal(position))

    def move_projects_to_group(self, group_name: str):
        """移动项目到指定分组"""
        selected_items = self.project_list.selectedItems()
        if not selected_items:
            return

        for item in selected_items:
            project_name = item.text()
            if project_name in self.config_manager.config:
                self.config_manager.config[project_name]['group'] = group_name

        self.config_manager.save_config()
        self.update_project_list()

    def add_group(self):
        """添加新分组"""
        name, ok = QInputDialog.getText(
            self, '添加分组', '请输入分组名称:'
        )

        if ok and name:
            name = name.strip()
            if not name:
                QMessageBox.warning(self, "警告", "分组名称不能为空!")
                return

            if name in self.config_manager.get_groups():
                QMessageBox.warning(self, "警告", "分组已存在!")
                return

            self.config_manager.add_group(name)
            self.config_manager.save_config()
            self.update_group_combo()
            self.group_combo.setCurrentText(name)

    def rename_group(self):
        """重命名分组"""
        current_group = self.group_combo.currentText()
        if current_group == '默认':
            QMessageBox.warning(self, "警告", "不能重命名默认分组!")
            return

        new_name, ok = QInputDialog.getText(
            self, '重命名分组', '请输入新的分组名称:', text=current_group
        )

        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, "警告", "分组名称不能为空!")
                return

            if new_name in self.config_manager.get_groups():
                QMessageBox.warning(self, "警告", "分组已存在!")
                return

            self.config_manager.rename_group(current_group, new_name)
            self.config_manager.save_config()
            self.update_group_combo()
            self.group_combo.setCurrentText(new_name)

    def delete_group(self):
        """删除分组"""
        current_group = self.group_combo.currentText()
        if current_group == '默认':
            QMessageBox.warning(self, "警告", "不能删除默认分组!")
            return

        reply = QMessageBox.question(
            self, '确认删除',
            f'确定要删除分组 "{current_group}" 吗?\n该分组下的项目将被移动到默认分组',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.config_manager.delete_group(current_group)
            self.config_manager.save_config()
            self.update_group_combo()

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
            self.action_type.setCurrentText(project_data.get('action_type', 'download'))
            self.only_latest.setChecked(project_data.get('only_latest', 'true').lower() == 'true')
            self.ignore_ssl.setChecked(project_data.get('ignore_ssl', 'false').lower() == 'true')
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

            current_group = self.group_combo.currentText()
            self.config_manager.config[name] = {
                'url': '',
                'output': f"./output/{sanitize_filename(name, replacement_text='-')}",
                'action_type': 'download',
                'only_latest': 'true',
                'ignore_ssl': 'false',
                'remarks': '',
                'group': current_group
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

    def select_all_schedule_projects(self):
        """全选所有计划任务项目"""
        for i in range(self.schedule_project_list.count()):
            item = self.schedule_project_list.item(i)
            item.setSelected(True)

    def deselect_all_schedule_projects(self):
        """取消全选所有计划任务项目"""
        for i in range(self.schedule_project_list.count()):
            item = self.schedule_project_list.item(i)
            item.setSelected(False)

    def browse_output_path(self):
        """浏览输出路径"""
        current_path = self.output_path.text()
        if not current_path or not os.path.exists(current_path):
            current_path = self.app_path

        path = QFileDialog.getExistingDirectory(self, "选择输出目录", current_path)
        if path:
            self.output_path.setText(path)

    def browse_global_log_path(self):
        """浏览全局日志文件路径"""
        current_path = self.global_log_file.text()
        if not current_path:
            current_path = os.path.join(self.app_path, 'logs', 'github_download.log')

        path, _ = QFileDialog.getSaveFileName(
            self, "选择日志文件", current_path,
            filter="日志文件 (*.log);;所有文件 (*)",
        )
        if path:
            self.global_log_file.setText(path)

    def update_schedule_project_list(self):
        """更新计划任务项目列表"""
        self.schedule_project_list.clear()
        for section in self.config_manager.config.sections():
            if section != 'global':
                item = QListWidgetItem(section)
                self.schedule_project_list.addItem(item)

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
            self.timer = QTimer(self)
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

    def stop_timer(self):
        """停止定时执行"""
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
            self.append_log("定时任务已停止")
            self.status_label.setText("定时任务已停止")
            self.start_timer_btn.setEnabled(True)
            self.stop_timer_btn.setEnabled(False)

    def calculate_next_delay(self, cron_expr: str) -> int:
        """计算下次执行的延迟时间(毫秒)"""
        now = datetime.now()
        cron = croniter(cron_expr, now)
        next_time = cron.get_next(datetime)
        return int((next_time - now).total_seconds() * 1000)

    def execute_scheduled_projects(self):
        """执行计划任务中选中的项目"""
        selected_items = self.schedule_project_list.selectedItems()
        if not selected_items:
            self.append_log("没有选择要定时执行的项目")
            return

        configs = []
        for item in selected_items:
            project = item.text()
            if project in self.config_manager.config:
                config = dict(self.config_manager.config[project])
                config['name'] = project
                configs.append(config)

        if configs:
            self.execute_tasks(configs)

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
            return

        self.log_display.clear()
        if not self.save_config():
            return

        for config in configs:
            if self.enable_proxy.isChecked():
                proxies = {
                    'http': self.global_proxy_http.text() if self.global_proxy_http.text() else None,
                    'https': self.global_proxy_https.text() if self.global_proxy_https.text() else None
                }
                if not proxies.get('http') and not proxies.get('https'):
                    proxies = None
            else:
                proxies = None
            config['proxies'] = proxies
            config['log_file'] = self.global_log_file.text() if self.global_log_file.text() else None
            config['dingtalk_webhook'] = self.dingtalk_webhook.text() if self.dingtalk_webhook.text() else None
            config['dingtalk_secret'] = self.dingtalk_secret.text() if self.dingtalk_secret.text() else None

        self.task_executor = TaskExecutor(
            configs=configs,
            max_workers=int(self.threads.currentText()) if self.threads.currentText() else 4
        )
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

    def load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                self.config_manager.config.read(self.config_file, encoding='utf-8')

                # 加载分组
                self.update_group_combo()

                # 加载全局设置
                global_config = self.config_manager.get_global_config()
                self.dingtalk_webhook.setText(global_config.get('dingtalk_webhook', ''))
                self.dingtalk_secret.setText(global_config.get('dingtalk_secret', ''))
                self.global_proxy_http.setText(global_config.get('proxies.http', ''))
                self.global_proxy_https.setText(global_config.get('proxies.https', ''))
                self.enable_proxy.setChecked(global_config.get('enable_proxy', 'true').lower() == 'true')
                self.cron_expression.setText(global_config.get('cron_expression', ''))
                self.global_log_file.setText(global_config.get('log_file', './logs/github_download.log'))
                self.threads.setCurrentText(global_config.get('threads', '4'))

                # 更新项目列表
                self.update_project_list()
                self.update_schedule_project_list()

                # 如果配置中有定时任务设置，自动启动
                if global_config.get('cron_expression'):
                    self.start_timer()

            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载配置文件失败: {str(e)}")
        else:
            self.config_manager.create_default_config()

    def save_config(self):
        """保存配置（添加验证功能）"""
        try:
            # 执行保存前的验证
            if not self._validate_before_save():
                return False

            # 保存前记录当前选中状态
            selected_items = [item.text() for item in self.project_list.selectedItems()]
            current_item = self.project_list.currentItem()
            current_item_text = current_item.text() if current_item else None
            current_group = self.group_combo.currentText()

            # 保存全局设置
            if not self.config_manager.config.has_section('global'):
                self.config_manager.config.add_section('global')

            self.config_manager.config['global'].update({
                'dingtalk_webhook': self.dingtalk_webhook.text().strip(),
                'dingtalk_secret': self.dingtalk_secret.text().strip(),
                'proxies.http': self.global_proxy_http.text().strip(),
                'proxies.https': self.global_proxy_https.text().strip(),
                'enable_proxy': 'true' if self.enable_proxy.isChecked() else 'false',
                'cron_expression': self.cron_expression.text().strip(),
                'log_file': self.global_log_file.text().strip(),
                'threads': self.threads.currentText(),
                'groups': ','.join(self.config_manager.get_groups())
            })

            # 保存当前项目配置
            if current_item:
                old_section = current_item.text().strip()
                new_section = self.project_name.text().strip()

                # 处理项目重命名
                if old_section != new_section:
                    if not new_section:
                        QMessageBox.warning(self, "警告", "项目名称不能为空!")
                        return False

                    if new_section in self.config_manager.config and new_section != old_section:
                        QMessageBox.warning(self, "警告", "项目名称已存在!")
                        return False

                    # 复制旧配置到新项目
                    if old_section in self.config_manager.config:
                        self.config_manager.config[new_section] = dict(self.config_manager.config[old_section])
                        self.config_manager.config.remove_section(old_section)
                        current_item.setText(new_section)

                # 更新项目配置
                section = new_section
                if not self.config_manager.config.has_section(section):
                    self.config_manager.config.add_section(section)

                self.config_manager.config[section].update({
                    'url': self.project_url.text().strip(),
                    'output': self.output_path.text().strip(),
                    'action_type': self.action_type.currentText().strip(),
                    'only_latest': 'true' if self.only_latest.isChecked() else 'false',
                    'ignore_ssl': 'true' if self.ignore_ssl.isChecked() else 'false',
                    'remarks': self.remarks.text().strip(),
                    'group': current_group
                })

            # 写入配置文件
            self.config_manager.save_config()

            # 刷新UI并恢复选中状态
            self.update_group_combo()
            self.group_combo.setCurrentText(current_group)
            self.update_project_list()
            self.update_schedule_project_list()

            # 恢复选中状态
            if current_item_text:
                for i in range(self.project_list.count()):
                    if self.project_list.item(i).text() == current_item_text:
                        self.project_list.setCurrentRow(i)
                        break

            return True
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置失败: {str(e)}")
            return False

    def _validate_before_save(self):
        """保存前的验证 - 验证所有项目（包含当前编辑的项目）"""
        errors = []

        # 验证全局设置
        if self.dingtalk_webhook.text() and not self.dingtalk_webhook.text().strip().startswith('https://oapi.dingtalk.com/robot/'):
            errors.append("钉钉webhookURL格式错误")

        if self.dingtalk_webhook.text() and not self.dingtalk_secret.text().strip():
            errors.append("钉钉secret不能为空")

        if self.global_proxy_http.text() and not self.global_proxy_http.text().startswith('http') and not self.global_proxy_http.text().startswith('socks'):
            errors.append("HTTP代理格式错误")

        if self.global_proxy_https.text() and not self.global_proxy_https.text().startswith('http') and not self.global_proxy_http.text().startswith('socks'):
            errors.append("HTTPS代理格式错误")

        # 获取当前编辑的项目数据（如果有）
        current_project = None
        if self.project_list.currentItem():
            current_project = {
                'name': self.project_name.text(),
                'url': self.project_url.text(),
                'output': self.output_path.text(),
                'action_type': self.action_type.currentText(),
                'only_latest': 'true' if self.only_latest.isChecked() else 'false',
                'ignore_ssl': 'true' if self.ignore_ssl.isChecked() else 'false',
                'group': self.group_combo.currentText()
            }

        # 验证所有项目
        for section in self.config_manager.config.sections():
            if section == 'global':
                continue

            # 如果是当前编辑的项目，使用界面上的最新值
            if current_project and section == current_project['name']:
                project_data = current_project
            else:
                project_data = dict(self.config_manager.config[section])

            # 验证项目URL
            if not project_data.get('url'):
                errors.append(f"项目 {section} 的GitHub URL不能为空")
                continue

            if not project_data.get('url').startswith('https://github.com/'):
                errors.append(f"项目 {section} 的GitHub URL格式错误")

            # 验证输出路径
            if not project_data.get('output'):
                errors.append(f"项目 {section} 的输出路径不能为空")

            # 验证操作类型
            action_type = project_data.get('action_type', 'download')
            if action_type not in ['download', 'update']:
                errors.append(f"项目 {section} 的操作类型无效")

            # 验证分组
            group = project_data.get('group', '默认')
            if group not in self.config_manager.get_groups():
                errors.append(f"项目 {section} 的分组 '{group}' 不存在")

        if errors:
            QMessageBox.critical(
                self,
                "验证错误",
                "发现以下配置问题:\n\n• " + "\n• ".join(errors)
            )
            return False

        return True

    def closeEvent(self, event):
        """窗口关闭事件处理"""
        if self.task_executor and self.task_executor.isRunning():
            reply = QMessageBox.question(
                self, '确认关闭',
                '有任务正在执行，确定要关闭窗口吗?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        try:
            if not self.save_config():
                event.ignore()
                return

            self.output_redirector.restore()
            event.accept()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"关闭窗口时发生错误: {str(e)}")
            event.ignore()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GitHubDownloaderGUI()
    window.show()
    sys.exit(app.exec())
