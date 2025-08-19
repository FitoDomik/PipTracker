import sys
import os
import json
import subprocess
import pkg_resources
import datetime
import matplotlib
matplotlib.use('QtAgg')  
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QTableWidget, QTableWidgetItem, QTabWidget, QPushButton, 
                           QLabel, QLineEdit, QComboBox, QMessageBox, QGroupBox, 
                           QSplitter, QProgressBar, QHeaderView, QDialog, QTextEdit,
                           QListWidget, QListWidgetItem, QPushButton, QDateEdit)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QIcon, QFont, QColor
ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PipTracker.ico")
APP_ICON = None
class PackageInstaller(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    def __init__(self, package_name, upgrade=False):
        super().__init__()
        self.package_name = package_name
        self.upgrade = upgrade
    def run(self):
        try:
            cmd = ["pip", "install"]
            if self.upgrade:
                cmd.append("--upgrade")
            cmd.append(self.package_name)
            self.progress.emit(f"Установка {self.package_name}...")
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                self.finished.emit(True, f"Успешно установлен {self.package_name}")
            else:
                self.finished.emit(False, f"Ошибка: {stderr}")
        except Exception as e:
            self.finished.emit(False, f"Ошибка: {str(e)}")
class PackageUninstaller(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    def __init__(self, package_name):
        super().__init__()
        self.package_name = package_name
    def run(self):
        try:
            self.progress.emit(f"Проверка зависимостей для {self.package_name}...")
            deps_process = subprocess.Popen(
                ["pip", "show", self.package_name], 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = deps_process.communicate()
            if deps_process.returncode != 0:
                self.finished.emit(False, f"Пакет {self.package_name} не найден")
                return
            required_by = None
            for line in stdout.split('\n'):
                if line.startswith("Required-by:"):
                    required_by = line[len("Required-by:"):].strip()
                    break
            if required_by and required_by != "":
                self.finished.emit(False, f"Внимание! Пакет {self.package_name} требуется для: {required_by}. Удаление отменено.")
                return
            self.progress.emit(f"Удаление {self.package_name}...")
            process = subprocess.Popen(
                ["pip", "uninstall", "-y", self.package_name], 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                self.finished.emit(True, f"Успешно удален {self.package_name}")
            else:
                self.finished.emit(False, f"Ошибка при удалении: {stderr}")
        except Exception as e:
            self.finished.emit(False, f"Ошибка: {str(e)}")
class OutdatedPackagesFinder(QThread):
    finished = pyqtSignal(list)
    def run(self):
        try:
            process = subprocess.Popen(
                ["pip", "list", "--outdated", "--format=json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                outdated = json.loads(stdout)
                self.finished.emit(outdated)
            else:
                self.finished.emit([])
        except Exception:
            self.finished.emit([])
class CategoryLibraryView(QWidget):
    install_requested = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)  
        self.layout.setSpacing(2)  
        search_layout = QHBoxLayout()
        search_layout.setSpacing(2)  
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск библиотек...")
        self.search_input.textChanged.connect(self.filter_libraries)
        search_layout.addWidget(QLabel("Поиск:"))
        search_layout.addWidget(self.search_input)
        self.layout.addLayout(search_layout)
        category_layout = QHBoxLayout()
        category_layout.setSpacing(2)  
        category_label = QLabel("Категория:")
        self.category_combo = QComboBox()
        self.category_combo.setMinimumHeight(25)  
        self.category_combo.currentIndexChanged.connect(self.load_category)
        category_layout.addWidget(category_label)
        category_layout.addWidget(self.category_combo)
        self.layout.addLayout(category_layout)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Название", "Активность", "Простота", "Размер", "Поддержка"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(22)  
        self.layout.addWidget(self.table)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(2)  
        self.install_button = QPushButton("Установить библиотеку")
        self.install_button.clicked.connect(self.request_install)
        self.install_button.setEnabled(False)
        self.docs_button = QPushButton("Документация")
        self.docs_button.clicked.connect(self.open_docs)
        self.docs_button.setEnabled(False)
        self.table.itemSelectionChanged.connect(self.enable_buttons)
        button_layout.addWidget(self.install_button)
        button_layout.addWidget(self.docs_button)
        self.layout.addLayout(button_layout)
        self.categories_data = {}
        self.all_libraries = []  
        self.current_libraries = []  
        self.load_categories()
    def load_categories(self):
        try:
            with open('category.JSON', 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.categories_data = data
                self.category_combo.clear()
                for category in data['categories']:
                    self.category_combo.addItem(category['name'])
                    for lib in category.get('libraries', []):
                        lib_info = lib.copy()
                        lib_info['category'] = category['name']
                        self.all_libraries.append(lib_info)
                if self.category_combo.count() > 0:
                    self.load_category(0)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить категории: {str(e)}")
    def load_category(self, index):
        if index < 0 or index >= len(self.categories_data.get('categories', [])):
            return
        category = self.categories_data['categories'][index]
        libraries = category.get('libraries', [])
        search_text = self.search_input.text().lower()
        if search_text:
            libraries = [lib for lib in libraries if search_text in lib.get('name', '').lower()]
        self.current_libraries = libraries
        self.update_table(libraries)
    def update_table(self, libraries):
        self.table.setRowCount(0)
        size_translation = {
            "light": "легкий",
            "small": "малый",
            "medium": "средний",
            "large": "большой",
            "very-large": "очень большой",
            "module": "модуль",
            "built-in": "встроенный"
        }
        support_translation = {
            "built-in": "встроенная",
            "powerful": "мощная",
            "active": "активная",
            "stable": "стабильная",
            "gpu": "GPU",
            "standard": "стандартная",
            "good": "хорошая",
            "interactive": "интерактивная",
            "declarative": "декларативная",
            "popular": "популярная",
            "modern": "современная",
            "async": "асинхронная",
            "micro": "микро",
            "low-level": "низкоуровневая",
            "basic": "базовая",
            "fast": "быстрая",
            "excel": "Excel",
            "yaml": "YAML",
            "convenient": "удобная",
            "advanced": "продвинутая",
            "distributed": "распределенная",
            "specialized": "специализированная",
            "nlp": "NLP",
            "usb": "USB",
            "bluetooth": "Bluetooth",
            "raspberry-pi": "Raspberry Pi",
            "camera": "камера",
            "lightweight": "легковесная",
            "orm": "ORM",
            "nosql": "NoSQL",
            "cache": "кэш",
            "postgresql": "PostgreSQL",
            "mysql": "MySQL",
            "ml": "ML",
            "deep-learning": "глубокое обучение",
            "high-level": "высокоуровневая",
            "gradient-boosting": "градиентный бустинг",
            "2d": "2D",
            "3d": "3D",
            "opengl": "OpenGL",
            "cross-platform": "кросс-платформенная",
            "windows": "Windows",
            "multi": "мульти"
        }
        for i, lib in enumerate(libraries):
            self.table.insertRow(i)
            name = lib.get('name', '')
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 0, name_item)
            activity = lib.get('activity', 0)
            activity_text = "★" * activity
            activity_item = QTableWidgetItem(activity_text)
            activity_item.setFlags(activity_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 1, activity_item)
            simplicity = lib.get('simplicity', 0)
            simplicity_text = "★" * simplicity
            simplicity_item = QTableWidgetItem(simplicity_text)
            simplicity_item.setFlags(simplicity_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 2, simplicity_item)
            size = lib.get('size', '')
            size_ru = size_translation.get(size, size)
            size_item = QTableWidgetItem(size_ru)
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 3, size_item)
            support = lib.get('support', '')
            support_ru = support_translation.get(support, support)
            support_item = QTableWidgetItem(support_ru)
            support_item.setFlags(support_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 4, support_item)
        self.enable_buttons()
    def filter_libraries(self, text):
        search_text = text.lower()
        if not search_text:
            current_index = self.category_combo.currentIndex()
            self.load_category(current_index)
            return
        filtered_libraries = []
        for lib in self.all_libraries:
            if search_text in lib.get('name', '').lower():
                filtered_libraries.append(lib)
        self.current_libraries = filtered_libraries
        self.update_table(filtered_libraries)
    def enable_buttons(self):
        selected_items = self.table.selectedItems()
        has_selection = len(selected_items) > 0
        selected_row = self.table.currentRow()
        install_enabled = False
        if has_selection and selected_row >= 0 and selected_row < len(self.current_libraries):
            library = self.current_libraries[selected_row]
            install_name = library.get('install_name', '')
            install_enabled = bool(install_name)
            if not install_enabled:
                self.install_button.setText("Встроенная библиотека")
            else:
                self.install_button.setText("Установить библиотеку")
        self.install_button.setEnabled(install_enabled)
        self.docs_button.setEnabled(has_selection)
    def request_install(self):
        selected_row = self.table.currentRow()
        if selected_row >= 0 and selected_row < len(self.current_libraries):
            library = self.current_libraries[selected_row]
            install_name = library.get('install_name', '')
            if install_name:
                self.install_requested.emit(install_name)
            else:
                QMessageBox.information(
                    self, 
                    "Информация", 
                    "Эта библиотека встроена в Python и не требует установки."
                )
    def open_docs(self):
        selected_row = self.table.currentRow()
        if selected_row >= 0 and selected_row < len(self.current_libraries):
            library = self.current_libraries[selected_row]
            library_name = library.get('name', '')
            install_name = library.get('install_name', '')
            if not install_name:
                if library_name == "time_module":
                    library_name = "time"
                url = f"https://docs.python.org/3/library/{library_name}.html"
            else:
                url = f"https://pypi.org/project/{install_name}/"
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось открыть документацию: {str(e)}")
class InstalledPackagesView(QWidget):
    update_requested = pyqtSignal(str)
    uninstall_requested = pyqtSignal(str)
    show_details_requested = pyqtSignal(str)
    update_selected_requested = pyqtSignal(list)
    uninstall_selected_requested = pyqtSignal(list)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)  
        self.layout.setSpacing(2)  
        search_layout = QHBoxLayout()
        search_layout.setSpacing(2)  
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск пакетов...")
        self.search_input.textChanged.connect(self.filter_packages)
        search_layout.addWidget(QLabel("Поиск:"))
        search_layout.addWidget(self.search_input)
        self.layout.addLayout(search_layout)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Название", "Версия", "Обновление", "Статус"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.table.verticalHeader().setDefaultSectionSize(22)  
        self.layout.addWidget(self.table)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(2)  
        self.info_button = QPushButton("Информация")
        self.info_button.clicked.connect(self.request_show_details)
        self.info_button.setEnabled(False)
        self.update_button = QPushButton("Обновить")
        self.update_button.clicked.connect(self.request_update)
        self.update_button.setEnabled(False)
        self.update_selected_button = QPushButton("Обновить выбранные")
        self.update_selected_button.clicked.connect(self.request_update_selected)
        self.update_selected_button.setEnabled(False)
        self.uninstall_button = QPushButton("Удалить")
        self.uninstall_button.clicked.connect(self.request_uninstall)
        self.uninstall_button.setEnabled(False)
        self.uninstall_selected_button = QPushButton("Удалить выбранные")
        self.uninstall_selected_button.clicked.connect(self.request_uninstall_selected)
        self.uninstall_selected_button.setEnabled(False)
        self.refresh_button = QPushButton("Обновить список")
        self.refresh_button.clicked.connect(self.refresh_packages)
        button_layout.addWidget(self.info_button)
        button_layout.addWidget(self.update_button)
        button_layout.addWidget(self.update_selected_button)
        button_layout.addWidget(self.uninstall_button)
        button_layout.addWidget(self.uninstall_selected_button)
        button_layout.addWidget(self.refresh_button)
        self.layout.addLayout(button_layout)
        self.packages = []
        self.outdated = []
        self.table.itemSelectionChanged.connect(self.enable_buttons)
        self.refresh_packages()
    def refresh_packages(self):
        try:
            self.packages = list(pkg_resources.working_set)
            self.outdated_finder = OutdatedPackagesFinder()
            self.outdated_finder.finished.connect(self.update_outdated_info)
            self.outdated_finder.start()
            self.update_table()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить список пакетов: {str(e)}")
    def update_outdated_info(self, outdated_list):
        self.outdated = outdated_list
        self.update_table()
    def update_table(self):
        search_text = self.search_input.text().lower()
        self.table.setRowCount(0)
        row = 0
        for pkg in self.packages:
            if search_text and search_text not in pkg.key.lower():
                continue
            self.table.insertRow(row)
            name_item = QTableWidgetItem(pkg.key)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            version_item = QTableWidgetItem(pkg.version)
            version_item.setFlags(version_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, version_item)
            update_info = ""
            update_color = None
            for outdated_pkg in self.outdated:
                if outdated_pkg.get('name', '').lower() == pkg.key.lower():
                    current_version = outdated_pkg.get('version', '')
                    latest_version = outdated_pkg.get('latest_version', '')
                    update_info = f"{current_version} → {latest_version}"
                    try:
                        current_parts = current_version.split('.')
                        latest_parts = latest_version.split('.')
                        if len(current_parts) > 0 and len(latest_parts) > 0:
                            if current_parts[0] != latest_parts[0]:
                                update_color = QColor(255, 165, 0)  
                            else:
                                update_color = QColor(0, 128, 0)  
                    except:
                        pass
                    break
            update_item = QTableWidgetItem(update_info)
            update_item.setFlags(update_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if update_color:
                update_item.setForeground(update_color)
            self.table.setItem(row, 2, update_item)
            status = "Установлен"
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, status_item)
            row += 1
    def filter_packages(self):
        self.update_table()
    def enable_buttons(self):
        selected_items = self.table.selectedItems()
        has_selection = len(selected_items) > 0
        selected_rows = self.table.selectionModel().selectedRows()
        has_multiple_selection = len(selected_rows) > 1
        self.uninstall_button.setEnabled(has_selection)
        self.info_button.setEnabled(has_selection)
        self.uninstall_selected_button.setEnabled(has_multiple_selection)
        if has_selection:
            row = self.table.currentRow()
            update_info = self.table.item(row, 2).text()
            self.update_button.setEnabled(bool(update_info))
            has_updates = False
            for row_index in selected_rows:
                if row_index.row() < self.table.rowCount():
                    update_info = self.table.item(row_index.row(), 2).text()
                    if update_info:
                        has_updates = True
                        break
            self.update_selected_button.setEnabled(has_multiple_selection and has_updates)
        else:
            self.update_button.setEnabled(False)
            self.update_selected_button.setEnabled(False)
    def request_update(self):
        selected_row = self.table.currentRow()
        if selected_row >= 0:
            package_name = self.table.item(selected_row, 0).text()
            self.update_requested.emit(package_name)
    def request_uninstall(self):
        selected_row = self.table.currentRow()
        if selected_row >= 0:
            package_name = self.table.item(selected_row, 0).text()
            self.uninstall_requested.emit(package_name)
    def request_update_selected(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if len(selected_rows) > 1:
            packages_to_update = []
            for row_index in selected_rows:
                if row_index.row() < self.table.rowCount():
                    package_name = self.table.item(row_index.row(), 0).text()
                    update_info = self.table.item(row_index.row(), 2).text()
                    if update_info:
                        packages_to_update.append(package_name)
            if packages_to_update:
                self.update_selected_requested.emit(packages_to_update)
    def request_uninstall_selected(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if len(selected_rows) > 1:
            packages_to_uninstall = []
            for row_index in selected_rows:
                if row_index.row() < self.table.rowCount():
                    package_name = self.table.item(row_index.row(), 0).text()
                    packages_to_uninstall.append(package_name)
            if packages_to_uninstall:
                self.uninstall_selected_requested.emit(packages_to_uninstall)
    def request_show_details(self):
        selected_row = self.table.currentRow()
        if selected_row >= 0:
            package_name = self.table.item(selected_row, 0).text()
            self.show_details_requested.emit(package_name)
    def on_item_double_clicked(self, item):
        row = item.row()
        package_name = self.table.item(row, 0).text()
        self.show_details_requested.emit(package_name)
class StatusDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Статус операции")
        self.setMinimumWidth(400)
        if APP_ICON:
            self.setWindowIcon(APP_ICON)
        layout = QVBoxLayout(self)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        layout.addWidget(self.status_text)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  
        layout.addWidget(self.progress_bar)
        self.close_button = QPushButton("Закрыть")
        self.close_button.clicked.connect(self.accept)
        self.close_button.setEnabled(False)
        layout.addWidget(self.close_button)
    def add_message(self, message):
        self.status_text.append(message)
    def operation_finished(self):
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.close_button.setEnabled(True)
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PipTracker - Менеджер библиотек Python")
        self.setMinimumSize(1200, 800)
        if APP_ICON:
            self.setWindowIcon(APP_ICON)
        self.history_manager = PackageHistoryManager()
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)  
        main_layout.setSpacing(2)  
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.installed_packages = InstalledPackagesView()
        self.installed_packages.update_requested.connect(self.update_package)
        self.installed_packages.uninstall_requested.connect(self.uninstall_package)
        self.installed_packages.show_details_requested.connect(self.show_package_details)
        self.installed_packages.update_selected_requested.connect(self.update_selected_packages)
        self.installed_packages.uninstall_selected_requested.connect(self.uninstall_selected_packages)
        installed_group = QGroupBox("Установленные пакеты")
        installed_layout = QVBoxLayout(installed_group)
        installed_layout.setContentsMargins(2, 2, 2, 2)  
        installed_layout.setSpacing(2)  
        installed_layout.addWidget(self.installed_packages)
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(2)  
        history_button = QPushButton("История операций")
        history_button.clicked.connect(self.show_history)
        size_analysis_button = QPushButton("Анализ размеров")
        size_analysis_button.clicked.connect(self.show_size_analysis)
        buttons_layout.addWidget(history_button)
        buttons_layout.addWidget(size_analysis_button)
        installed_layout.addLayout(buttons_layout)
        splitter.addWidget(installed_group)
        self.category_view = CategoryLibraryView()
        self.category_view.install_requested.connect(self.install_package)
        library_group = QGroupBox("Библиотеки по категориям")
        library_layout = QVBoxLayout(library_group)
        library_layout.setContentsMargins(2, 2, 2, 2)  
        library_layout.setSpacing(2)  
        library_layout.addWidget(self.category_view)
        splitter.addWidget(library_group)
        splitter.setSizes([400, 500])
        main_layout.addWidget(splitter)
        self.setCentralWidget(central_widget)
        self.check_updates_on_startup()
    def show_size_analysis(self):
        size_dialog = PackageSizeChartDialog(self)
        size_dialog.exec()
    def check_updates_on_startup(self):
        self.installed_packages.refresh_packages()
        self.startup_outdated_finder = OutdatedPackagesFinder()
        self.startup_outdated_finder.finished.connect(self.show_update_notification)
        self.startup_outdated_finder.start()
    def show_update_notification(self, outdated_packages):
        if not outdated_packages:
            return
        update_dialog = UpdateNotifierDialog(outdated_packages, self)
        update_dialog.update_all_requested.connect(lambda: self.update_all_packages(outdated_packages))
        update_dialog.exec()
    def update_all_packages(self, outdated_packages):
        dialog = StatusDialog(self)
        dialog.setWindowTitle("Массовое обновление пакетов")
        updater = BulkPackageUpdater(outdated_packages)
        updater.progress.connect(dialog.add_message)
        updater.package_updated.connect(self.package_updated_in_bulk)
        updater.finished.connect(dialog.operation_finished)
        updater.finished.connect(self.installed_packages.refresh_packages)
        updater.start()
        dialog.exec()
    def package_updated_in_bulk(self, package_name, success, message, previous_version):
        self.history_manager.add_operation(
            "update",
            package_name,
            previous_version,
            success,
            message
        )
    def show_package_details(self, package_name):
        detail_dialog = PackageDetailDialog(package_name, self)
        detail_dialog.exec()
    def show_history(self):
        history_dialog = PackageHistoryDialog(self.history_manager, self)
        history_dialog.rollback_requested.connect(self.rollback_operation)
        history_dialog.exec()
    def install_package(self, package_name):
        dialog = StatusDialog(self)
        dialog.setWindowTitle(f"Установка {package_name}")
        try:
            current_version = None
            for pkg in pkg_resources.working_set:
                if pkg.key == package_name.lower():
                    current_version = pkg.version
                    break
        except:
            current_version = None
        installer = PackageInstaller(package_name)
        installer.progress.connect(dialog.add_message)
        installer.finished.connect(lambda success, message: 
                                  self.installation_finished(success, message, dialog, package_name, current_version))
        installer.start()
        dialog.exec()
    def installation_finished(self, success, message, dialog, package_name, previous_version):
        dialog.add_message(message)
        dialog.operation_finished()
        installed_version = None
        if success:
            try:
                for pkg in pkg_resources.working_set:
                    if pkg.key == package_name.lower():
                        installed_version = pkg.version
                        break
            except:
                pass
        operation_type = "install"
        if previous_version:
            operation_type = "update"
            version_for_history = previous_version
        else:
            version_for_history = installed_version
        self.history_manager.add_operation(
            operation_type,
            package_name,
            version_for_history,
            success,
            message
        )
        if success:
            self.installed_packages.refresh_packages()
    def update_package(self, package_name):
        dialog = StatusDialog(self)
        dialog.setWindowTitle(f"Обновление {package_name}")
        current_version = None
        try:
            for pkg in pkg_resources.working_set:
                if pkg.key == package_name.lower():
                    current_version = pkg.version
                    break
        except:
            pass
        installer = PackageInstaller(package_name, upgrade=True)
        installer.progress.connect(dialog.add_message)
        installer.finished.connect(lambda success, message: 
                                  self.update_finished(success, message, dialog, package_name, current_version))
        installer.start()
        dialog.exec()
    def update_finished(self, success, message, dialog, package_name, previous_version):
        dialog.add_message(message)
        dialog.operation_finished()
        self.history_manager.add_operation(
            "update",
            package_name,
            previous_version,  
            success,
            message
        )
        if success:
            self.installed_packages.refresh_packages()
    def uninstall_package(self, package_name):
        current_version = None
        try:
            for pkg in pkg_resources.working_set:
                if pkg.key == package_name.lower():
                    current_version = pkg.version
                    break
        except:
            pass
        reply = QMessageBox.question(
            self, 
            "Подтверждение удаления", 
            f"Вы уверены, что хотите удалить пакет {package_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            dialog = StatusDialog(self)
            dialog.setWindowTitle(f"Удаление {package_name}")
            uninstaller = PackageUninstaller(package_name)
            uninstaller.progress.connect(dialog.add_message)
            uninstaller.finished.connect(lambda success, message: 
                                       self.uninstallation_finished(success, message, dialog, package_name, current_version))
            uninstaller.start()
            dialog.exec()
    def uninstallation_finished(self, success, message, dialog, package_name, version):
        dialog.add_message(message)
        dialog.operation_finished()
        self.history_manager.add_operation(
            "uninstall",
            package_name,
            version,  
            success,
            message
        )
        if success:
            self.installed_packages.refresh_packages()
    def update_selected_packages(self, package_names):
        if not package_names:
            return
        dialog = StatusDialog(self)
        dialog.setWindowTitle(f"Обновление {len(package_names)} пакетов")
        packages_with_versions = []
        for package_name in package_names:
            current_version = None
            try:
                for pkg in pkg_resources.working_set:
                    if pkg.key == package_name.lower():
                        current_version = pkg.version
                        break
            except:
                pass
            packages_with_versions.append({"name": package_name, "version": current_version})
        updater = BulkPackageUpdater(packages_with_versions)
        updater.progress.connect(dialog.add_message)
        updater.package_updated.connect(lambda name, success, message, prev_version: 
                                      self.package_updated_in_bulk(name, success, message, prev_version))
        updater.finished.connect(dialog.operation_finished)
        updater.finished.connect(self.installed_packages.refresh_packages)
        updater.start()
        dialog.exec()
    def uninstall_selected_packages(self, package_names):
        if not package_names:
            return
        packages_text = "\n".join([f"• {name}" for name in package_names])
        reply = QMessageBox.question(
            self, 
            "Подтверждение удаления", 
            f"Вы уверены, что хотите удалить следующие пакеты?\n\n{packages_text}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            dialog = StatusDialog(self)
            dialog.setWindowTitle(f"Удаление {len(package_names)} пакетов")
            uninstaller = BulkPackageUninstaller(package_names)
            uninstaller.progress.connect(dialog.add_message)
            uninstaller.package_uninstalled.connect(lambda name, success, message, version: 
                                                  self.package_uninstalled_in_bulk(name, success, message, version))
            uninstaller.finished.connect(dialog.operation_finished)
            uninstaller.finished.connect(self.installed_packages.refresh_packages)
            uninstaller.start()
            dialog.exec()
    def package_updated_in_bulk(self, package_name, success, message, previous_version):
        self.history_manager.add_operation(
            "update",
            package_name,
            previous_version,
            success,
            message
        )
    def package_uninstalled_in_bulk(self, package_name, success, message, version):
        self.history_manager.add_operation(
            "uninstall",
            package_name,
            version,
            success,
            message
        )
    def rollback_operation(self, operation):
        dialog = StatusDialog(self)
        dialog.setWindowTitle(f"Откат операции для {operation.get('package')}")
        class RollbackThread(QThread):
            finished = pyqtSignal(bool, str)
            progress = pyqtSignal(str)
            def __init__(self, history_manager, operation):
                super().__init__()
                self.history_manager = history_manager
                self.operation = operation
            def run(self):
                self.progress.emit(f"Выполняется откат операции...")
                success, message = self.history_manager.rollback_operation(self.operation)
                self.finished.emit(success, message)
        rollback_thread = RollbackThread(self.history_manager, operation)
        rollback_thread.progress.connect(dialog.add_message)
        rollback_thread.finished.connect(lambda success, message: self.rollback_finished(success, message, dialog))
        rollback_thread.start()
        dialog.exec()
    def rollback_finished(self, success, message, dialog):
        dialog.add_message(message)
        dialog.operation_finished()
        if success:
            self.installed_packages.refresh_packages()
class PackageHistoryManager:
    def __init__(self, history_file="package_history.json"):
        self.history_file = history_file
        self.history = self._load_history()
    def _load_history(self):
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {"operations": []}
        except Exception as e:
            print(f"Ошибка при загрузке истории: {e}")
            return {"operations": []}
    def _save_history(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка при сохранении истории: {e}")
    def add_operation(self, operation_type, package_name, version=None, success=True, details=None):
        timestamp = datetime.datetime.now().isoformat()
        operation = {
            "timestamp": timestamp,
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": operation_type,
            "package": package_name,
            "version": version,
            "success": success,
            "details": details or ""
        }
        self.history["operations"].append(operation)
        self._save_history()
        return operation
    def get_operations(self, package_name=None, operation_type=None, limit=None):
        operations = self.history["operations"]
        if package_name:
            operations = [op for op in operations if op["package"] == package_name]
        if operation_type:
            operations = [op for op in operations if op["type"] == operation_type]
        operations = sorted(operations, key=lambda x: x["timestamp"], reverse=True)
        if limit and isinstance(limit, int) and limit > 0:
            operations = operations[:limit]
        return operations
    def can_rollback(self, operation):
        if not operation or not isinstance(operation, dict):
            return False
        op_type = operation.get("type")
        success = operation.get("success", False)
        if not success:
            return False
        if op_type == "install":
            return True
        elif op_type == "uninstall":
            return operation.get("version") is not None
        elif op_type == "update":
            return operation.get("version") is not None
        return False
    def rollback_operation(self, operation):
        if not self.can_rollback(operation):
            return False, "Невозможно откатить эту операцию"
        op_type = operation.get("type")
        package = operation.get("package")
        version = operation.get("version")
        cmd = ["pip"]
        if op_type == "install":
            cmd.extend(["uninstall", "-y", package])
            rollback_type = "uninstall_rollback"
        elif op_type == "uninstall":
            cmd.extend(["install", f"{package}=={version}"])
            rollback_type = "install_rollback"
        elif op_type == "update":
            cmd.extend(["install", f"{package}=={version}"])
            rollback_type = "downgrade_rollback"
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()
            success = process.returncode == 0
            details = stdout if success else stderr
            self.add_operation(
                rollback_type,
                package,
                version,
                success,
                f"Откат операции от {operation.get('date')}: {details}"
            )
            return success, "Откат выполнен успешно" if success else f"Ошибка отката: {stderr}"
        except Exception as e:
            return False, f"Ошибка при откате: {str(e)}"
class PackageHistoryDialog(QDialog):
    rollback_requested = pyqtSignal(dict)
    def __init__(self, history_manager, parent=None):
        super().__init__(parent)
        self.history_manager = history_manager
        self.operations = []
        self.setWindowTitle("История операций с пакетами")
        self.setMinimumSize(800, 500)
        if APP_ICON:
            self.setWindowIcon(APP_ICON)
        self.init_ui()
        self.load_operations()
    def init_ui(self):
        layout = QVBoxLayout(self)
        filter_layout = QHBoxLayout()
        self.operation_type_combo = QComboBox()
        self.operation_type_combo.addItem("Все операции", "")
        self.operation_type_combo.addItem("Установка", "install")
        self.operation_type_combo.addItem("Удаление", "uninstall")
        self.operation_type_combo.addItem("Обновление", "update")
        self.operation_type_combo.addItem("Откат", "rollback")
        self.operation_type_combo.currentIndexChanged.connect(self.load_operations)
        filter_layout.addWidget(QLabel("Тип операции:"))
        filter_layout.addWidget(self.operation_type_combo)
        self.package_search = QLineEdit()
        self.package_search.setPlaceholderText("Поиск по имени пакета...")
        self.package_search.textChanged.connect(self.load_operations)
        filter_layout.addWidget(QLabel("Пакет:"))
        filter_layout.addWidget(self.package_search)
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(self.load_operations)
        filter_layout.addWidget(self.refresh_button)
        layout.addLayout(filter_layout)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(["Дата", "Операция", "Пакет", "Версия", "Статус"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history_table.itemSelectionChanged.connect(self.update_rollback_button)
        layout.addWidget(self.history_table)
        details_group = QGroupBox("Детали операции")
        details_layout = QVBoxLayout(details_group)
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)
        layout.addWidget(details_group)
        buttons_layout = QHBoxLayout()
        self.rollback_button = QPushButton("Откатить операцию")
        self.rollback_button.clicked.connect(self.rollback_selected_operation)
        self.rollback_button.setEnabled(False)
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(self.rollback_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(close_button)
        layout.addLayout(buttons_layout)
    def load_operations(self):
        operation_type = self.operation_type_combo.currentData()
        package_name = self.package_search.text().strip()
        if not package_name:
            package_name = None
        self.operations = self.history_manager.get_operations(package_name, operation_type)
        self.history_table.setRowCount(0)
        for i, op in enumerate(self.operations):
            self.history_table.insertRow(i)
            date_item = QTableWidgetItem(op.get("date", ""))
            date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.history_table.setItem(i, 0, date_item)
            operation_type = op.get("type", "")
            operation_name = self.get_operation_name(operation_type)
            type_item = QTableWidgetItem(operation_name)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.history_table.setItem(i, 1, type_item)
            package_item = QTableWidgetItem(op.get("package", ""))
            package_item.setFlags(package_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.history_table.setItem(i, 2, package_item)
            version_item = QTableWidgetItem(op.get("version", "") or "")
            version_item.setFlags(version_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.history_table.setItem(i, 3, version_item)
            success = op.get("success", False)
            status_text = "Успешно" if success else "Ошибка"
            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item.setForeground(QColor(0, 128, 0) if success else QColor(255, 0, 0))
            self.history_table.setItem(i, 4, status_item)
        self.details_text.clear()
        self.update_rollback_button()
    def get_operation_name(self, operation_type):
        operation_names = {
            "install": "Установка",
            "uninstall": "Удаление",
            "update": "Обновление",
            "install_rollback": "Откат (установка)",
            "uninstall_rollback": "Откат (удаление)",
            "downgrade_rollback": "Откат (понижение)"
        }
        return operation_names.get(operation_type, operation_type)
    def update_rollback_button(self):
        selected_rows = self.history_table.selectionModel().selectedRows()
        if not selected_rows:
            self.rollback_button.setEnabled(False)
            self.details_text.clear()
            return
        row = selected_rows[0].row()
        if row < 0 or row >= len(self.operations):
            self.rollback_button.setEnabled(False)
            self.details_text.clear()
            return
        operation = self.operations[row]
        details = operation.get("details", "")
        self.details_text.setText(details)
        can_rollback = self.history_manager.can_rollback(operation)
        self.rollback_button.setEnabled(can_rollback)
        if can_rollback:
            self.rollback_button.setText("Откатить операцию")
        else:
            self.rollback_button.setText("Откат невозможен")
    def rollback_selected_operation(self):
        selected_rows = self.history_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if row < 0 or row >= len(self.operations):
            return
        operation = self.operations[row]
        reply = QMessageBox.question(
            self,
            "Подтверждение отката",
            f"Вы уверены, что хотите откатить операцию {self.get_operation_name(operation.get('type'))} "
            f"для пакета {operation.get('package')}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.rollback_requested.emit(operation)
            self.accept()  
class PackageDetailThread(QThread):
    finished = pyqtSignal(dict)
    def __init__(self, package_name):
        super().__init__()
        self.package_name = package_name
    def run(self):
        result = {
            "name": self.package_name,
            "version": "",
            "summary": "",
            "author": "",
            "author_email": "",
            "license": "",
            "home_page": "",
            "location": "",
            "requires": [],
            "required_by": [],
            "metadata": {}
        }
        try:
            process = subprocess.Popen(
                ["pip", "show", self.package_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                for line in stdout.splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower().replace("-", "_")
                        value = value.strip()
                        if key == "requires":
                            if value:
                                result["requires"] = [req.strip() for req in value.split(",")]
                            else:
                                result["requires"] = []
                        elif key == "required_by":
                            if value and value != "":
                                result["required_by"] = [req.strip() for req in value.split(",")]
                            else:
                                result["required_by"] = []
                        else:
                            result[key] = value
            try:
                dist = None
                for pkg in pkg_resources.working_set:
                    if pkg.key == self.package_name.lower():
                        dist = pkg
                        break
                if dist:
                    if hasattr(dist, "_get_metadata"):
                        for key in dist._get_metadata("PKG-INFO"):
                            if ":" in key:
                                meta_key, meta_value = key.split(":", 1)
                                result["metadata"][meta_key.strip()] = meta_value.strip()
            except:
                pass
        except Exception as e:
            print(f"Ошибка при получении информации о пакете: {e}")
        self.finished.emit(result)
class PackageDetailDialog(QDialog):
    def __init__(self, package_name, parent=None):
        super().__init__(parent)
        self.package_name = package_name
        self.setWindowTitle(f"Информация о пакете {package_name}")
        self.setMinimumSize(700, 500)
        if APP_ICON:
            self.setWindowIcon(APP_ICON)
        self.init_ui()
        self.load_package_info()
    def init_ui(self):
        layout = QVBoxLayout(self)
        header_layout = QHBoxLayout()
        self.package_title = QLabel(self.package_name)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.package_title.setFont(title_font)
        self.package_version = QLabel("")
        version_font = QFont()
        version_font.setPointSize(12)
        self.package_version.setFont(version_font)
        header_layout.addWidget(self.package_title)
        header_layout.addWidget(self.package_version)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        tab_widget = QTabWidget()
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        self.info_table = QTableWidget(0, 2)
        self.info_table.setHorizontalHeaderLabels(["Параметр", "Значение"])
        self.info_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.info_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.info_table.verticalHeader().setVisible(False)
        general_layout.addWidget(self.info_table)
        tab_widget.addTab(general_tab, "Общая информация")
        dependencies_tab = QWidget()
        dependencies_layout = QVBoxLayout(dependencies_tab)
        deps_label = QLabel("Зависимости (пакеты, необходимые для работы):")
        dependencies_layout.addWidget(deps_label)
        self.requires_list = QListWidget()
        dependencies_layout.addWidget(self.requires_list)
        deps_by_label = QLabel("Зависит от этого пакета:")
        dependencies_layout.addWidget(deps_by_label)
        self.required_by_list = QListWidget()
        dependencies_layout.addWidget(self.required_by_list)
        tab_widget.addTab(dependencies_tab, "Зависимости")
        metadata_tab = QWidget()
        metadata_layout = QVBoxLayout(metadata_tab)
        self.metadata_table = QTableWidget(0, 2)
        self.metadata_table.setHorizontalHeaderLabels(["Ключ", "Значение"])
        self.metadata_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.metadata_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.metadata_table.verticalHeader().setVisible(False)
        metadata_layout.addWidget(self.metadata_table)
        tab_widget.addTab(metadata_tab, "Метаданные")
        layout.addWidget(tab_widget)
        buttons_layout = QHBoxLayout()
        self.open_docs_button = QPushButton("Открыть документацию")
        self.open_docs_button.clicked.connect(self.open_docs)
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(self.open_docs_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(close_button)
        layout.addLayout(buttons_layout)
        self.loading_label = QLabel("Загрузка информации о пакете...")
        layout.addWidget(self.loading_label)
    def load_package_info(self):
        self.detail_thread = PackageDetailThread(self.package_name)
        self.detail_thread.finished.connect(self.update_package_info)
        self.detail_thread.start()
    def update_package_info(self, package_info):
        self.loading_label.setVisible(False)
        self.package_title.setText(package_info.get("name", ""))
        self.package_version.setText(f"v{package_info.get('version', '')}")
        self.summary_label.setText(package_info.get("summary", ""))
        self.info_table.setRowCount(0)
        info_items = [
            ("Автор", package_info.get("author", "")),
            ("Email автора", package_info.get("author_email", "")),
            ("Лицензия", package_info.get("license", "")),
            ("Домашняя страница", package_info.get("home_page", "")),
            ("Расположение", package_info.get("location", ""))
        ]
        for i, (key, value) in enumerate(info_items):
            self.info_table.insertRow(i)
            key_item = QTableWidgetItem(key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.info_table.setItem(i, 0, key_item)
            value_item = QTableWidgetItem(value)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.info_table.setItem(i, 1, value_item)
        self.requires_list.clear()
        for req in package_info.get("requires", []):
            self.requires_list.addItem(req)
        self.required_by_list.clear()
        for req_by in package_info.get("required_by", []):
            self.required_by_list.addItem(req_by)
        self.metadata_table.setRowCount(0)
        metadata = package_info.get("metadata", {})
        sorted_keys = sorted(metadata.keys())
        for i, key in enumerate(sorted_keys):
            value = metadata.get(key, "")
            self.metadata_table.insertRow(i)
            key_item = QTableWidgetItem(key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.metadata_table.setItem(i, 0, key_item)
            value_item = QTableWidgetItem(value)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.metadata_table.setItem(i, 1, value_item)
    def open_docs(self):
        url = f"https://pypi.org/project/{self.package_name}/"
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть документацию: {str(e)}")
class UpdateNotifierDialog(QDialog):
    update_all_requested = pyqtSignal()
    def __init__(self, outdated_packages, parent=None):
        super().__init__(parent)
        self.outdated_packages = outdated_packages
        self.setWindowTitle("Доступны обновления")
        self.setMinimumWidth(600)
        if APP_ICON:
            self.setWindowIcon(APP_ICON)
        self.init_ui()
    def init_ui(self):
        layout = QVBoxLayout(self)
        header_label = QLabel("Доступны обновления для следующих пакетов:")
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(14)
        header_label.setFont(header_font)
        layout.addWidget(header_label)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Пакет", "Текущая версия", "Доступная версия", "Уровень риска"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        for i, pkg in enumerate(self.outdated_packages):
            self.table.insertRow(i)
            name = pkg.get('name', '')
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 0, name_item)
            current_version = pkg.get('version', '')
            current_item = QTableWidgetItem(current_version)
            current_item.setFlags(current_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 1, current_item)
            latest_version = pkg.get('latest_version', '')
            latest_item = QTableWidgetItem(latest_version)
            latest_item.setFlags(latest_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 2, latest_item)
            risk_level = self.calculate_risk_level(current_version, latest_version)
            risk_item = QTableWidgetItem(risk_level)
            risk_item.setFlags(risk_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if risk_level == "Высокий":
                risk_item.setForeground(QColor(255, 0, 0))  
            elif risk_level == "Средний":
                risk_item.setForeground(QColor(255, 165, 0))  
            else:
                risk_item.setForeground(QColor(0, 128, 0))  
            self.table.setItem(i, 3, risk_item)
        buttons_layout = QHBoxLayout()
        update_all_button = QPushButton("Обновить все")
        update_all_button.clicked.connect(self.request_update_all)
        later_button = QPushButton("Позже")
        later_button.clicked.connect(self.reject)
        buttons_layout.addWidget(update_all_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(later_button)
        layout.addLayout(buttons_layout)
    def calculate_risk_level(self, current_version, latest_version):
        try:
            current_parts = current_version.split('.')
            latest_parts = latest_version.split('.')
            if len(current_parts) > 0 and len(latest_parts) > 0:
                if current_parts[0] != latest_parts[0]:
                    return "Высокий"
                if len(current_parts) > 1 and len(latest_parts) > 1:
                    if current_parts[1] != latest_parts[1]:
                        return "Средний"
            return "Низкий"
        except:
            return "Неизвестно"
    def request_update_all(self):
        self.update_all_requested.emit()
        self.accept()
class BulkPackageUpdater(QThread):
    progress = pyqtSignal(str)
    package_updated = pyqtSignal(str, bool, str, str)  
    finished = pyqtSignal()
    def __init__(self, packages):
        super().__init__()
        self.packages = packages
    def run(self):
        total = len(self.packages)
        self.progress.emit(f"Начало обновления {total} пакетов...")
        for i, pkg in enumerate(self.packages):
            package_name = pkg.get('name', '')
            current_version = pkg.get('version', '')
            if not package_name:
                continue
            self.progress.emit(f"[{i+1}/{total}] Обновление {package_name} ({current_version})...")
            cmd = ["pip", "install", "--upgrade", package_name]
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                stdout, stderr = process.communicate()
                success = process.returncode == 0
                message = stdout if success else stderr
                self.progress.emit(f"{'Успешно' if success else 'Ошибка'}: {message}")
                self.package_updated.emit(package_name, success, message, current_version)
            except Exception as e:
                self.progress.emit(f"Ошибка при обновлении {package_name}: {str(e)}")
                self.package_updated.emit(package_name, False, str(e), current_version)
        self.progress.emit(f"Обновление завершено.")
        self.finished.emit()
class BulkPackageUninstaller(QThread):
    progress = pyqtSignal(str)
    package_uninstalled = pyqtSignal(str, bool, str, str)
    finished = pyqtSignal()
    def __init__(self, package_names):
        super().__init__()
        self.package_names = package_names
    def run(self):
        total = len(self.package_names)
        self.progress.emit(f"Начало удаления {total} пакетов...")
        for i, package_name in enumerate(self.package_names):
            if not package_name:
                continue
            current_version = None
            try:
                for pkg in pkg_resources.working_set:
                    if pkg.key == package_name.lower():
                        current_version = pkg.version
                        break
            except:
                pass
            self.progress.emit(f"[{i+1}/{total}] Удаление {package_name} ({current_version or 'неизвестная версия'})...")
            try:
                deps_process = subprocess.Popen(
                    ["pip", "show", package_name], 
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                stdout, stderr = deps_process.communicate()
                if deps_process.returncode == 0:
                    required_by = None
                    for line in stdout.split('\n'):
                        if line.startswith("Required-by:"):
                            required_by = line[len("Required-by:"):].strip()
                            break
                    if required_by and required_by != "":
                        self.progress.emit(f"Пропуск {package_name}: требуется для {required_by}")
                        self.package_uninstalled.emit(package_name, False, f"Пакет требуется для: {required_by}", current_version)
                        continue
            except:
                pass
            cmd = ["pip", "uninstall", "-y", package_name]
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                stdout, stderr = process.communicate()
                success = process.returncode == 0
                message = stdout if success else stderr
                self.progress.emit(f"{'Успешно' if success else 'Ошибка'}: {message}")
                self.package_uninstalled.emit(package_name, success, message, current_version)
            except Exception as e:
                self.progress.emit(f"Ошибка при удалении {package_name}: {str(e)}")
                self.package_uninstalled.emit(package_name, False, str(e), current_version)
        self.progress.emit(f"Удаление завершено.")
        self.finished.emit()
class PackageSizeAnalyzer(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    def __init__(self, packages=None):
        super().__init__()
        self.packages = packages or []
    def run(self):
        result = []
        if not self.packages:
            self.packages = list(pkg_resources.working_set)
        total = len(self.packages)
        self.progress.emit(f"Анализ размеров {total} пакетов...")
        for i, pkg in enumerate(self.packages):
            if isinstance(pkg, dict):
                package_name = pkg.get('name', '')
            else:
                package_name = pkg.key
            if not package_name:
                continue
            self.progress.emit(f"[{i+1}/{total}] Анализ размера {package_name}...")
            try:
                process = subprocess.Popen(
                    ["pip", "show", "-f", package_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                stdout, stderr = process.communicate()
                if process.returncode == 0:
                    location = ""
                    files = []
                    in_files_section = False
                    for line in stdout.splitlines():
                        if line.startswith("Location:"):
                            location = line.split(":", 1)[1].strip()
                        elif line.startswith("Files:"):
                            in_files_section = True
                        elif in_files_section and line.strip():
                            files.append(line.strip())
                    total_size = 0
                    for file_path in files:
                        full_path = os.path.join(location, file_path)
                        if os.path.isfile(full_path):
                            total_size += os.path.getsize(full_path)
                    package_info = {
                        "name": package_name,
                        "size": total_size,
                        "size_mb": round(total_size / (1024 * 1024), 2),
                        "file_count": len(files),
                        "location": location
                    }
                    result.append(package_info)
            except Exception as e:
                self.progress.emit(f"Ошибка при анализе {package_name}: {str(e)}")
        result.sort(key=lambda x: x.get("size", 0), reverse=True)
        self.progress.emit(f"Анализ завершен.")
        self.finished.emit(result)
class PackageSizeChartDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Анализ размеров пакетов")
        self.setMinimumSize(800, 600)
        if APP_ICON:
            self.setWindowIcon(APP_ICON)
        self.init_ui()
        self.start_analysis()
    def init_ui(self):
        layout = QVBoxLayout(self)
        header_label = QLabel("Анализ размеров установленных пакетов")
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(14)
        header_label.setFont(header_font)
        layout.addWidget(header_label)
        self.tab_widget = QTabWidget()
        self.pie_tab = QWidget()
        pie_layout = QVBoxLayout(self.pie_tab)
        self.pie_figure = Figure(figsize=(6, 6), dpi=100)
        self.pie_canvas = FigureCanvas(self.pie_figure)
        pie_layout.addWidget(self.pie_canvas)
        self.tab_widget.addTab(self.pie_tab, "Круговая диаграмма")
        self.bar_tab = QWidget()
        bar_layout = QVBoxLayout(self.bar_tab)
        self.bar_figure = Figure(figsize=(8, 6), dpi=100)
        self.bar_canvas = FigureCanvas(self.bar_figure)
        bar_layout.addWidget(self.bar_canvas)
        self.tab_widget.addTab(self.bar_tab, "Гистограмма")
        self.table_tab = QWidget()
        table_layout = QVBoxLayout(self.table_tab)
        self.size_table = QTableWidget(0, 4)
        self.size_table.setHorizontalHeaderLabels(["Пакет", "Размер (МБ)", "Количество файлов", "Расположение"])
        self.size_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table_layout.addWidget(self.size_table)
        self.tab_widget.addTab(self.table_tab, "Таблица")
        layout.addWidget(self.tab_widget)
        self.status_label = QLabel("Анализ размеров пакетов...")
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  
        layout.addWidget(self.progress_bar)
        buttons_layout = QHBoxLayout()
        refresh_button = QPushButton("Обновить")
        refresh_button.clicked.connect(self.start_analysis)
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(refresh_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(close_button)
        layout.addLayout(buttons_layout)
    def start_analysis(self):
        self.status_label.setText("Анализ размеров пакетов...")
        self.progress_bar.setRange(0, 0)  
        self.size_table.setRowCount(0)
        self.analyzer = PackageSizeAnalyzer()
        self.analyzer.progress.connect(self.update_status)
        self.analyzer.finished.connect(self.update_charts)
        self.analyzer.start()
    def update_status(self, message):
        self.status_label.setText(message)
    def update_charts(self, size_data):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        if not size_data:
            self.status_label.setText("Не удалось получить данные о размерах пакетов")
            return
        self.update_pie_chart(size_data)
        self.update_bar_chart(size_data)
        self.update_size_table(size_data)
        self.status_label.setText(f"Анализ завершен. Проанализировано {len(size_data)} пакетов.")
    def update_pie_chart(self, size_data):
        self.pie_figure.clear()
        top_packages = size_data[:10]
        other_packages = size_data[10:]
        labels = [pkg["name"] for pkg in top_packages]
        sizes = [pkg["size_mb"] for pkg in top_packages]
        if other_packages:
            labels.append("Другие")
            other_size = sum(pkg["size_mb"] for pkg in other_packages)
            sizes.append(other_size)
        ax = self.pie_figure.add_subplot(111)
        ax.set_title("Распределение размеров пакетов (МБ)")
        wedges, texts, autotexts = ax.pie(
            sizes, 
            labels=labels, 
            autopct='%1.1f%%', 
            startangle=90
        )
        ax.legend(wedges, labels, title="Пакеты", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        ax.axis('equal')
        self.pie_canvas.draw()
    def update_bar_chart(self, size_data):
        self.bar_figure.clear()
        top_packages = size_data[:20]
        names = [pkg["name"] for pkg in top_packages]
        sizes = [pkg["size_mb"] for pkg in top_packages]
        ax = self.bar_figure.add_subplot(111)
        ax.set_title("Топ-20 пакетов по размеру (МБ)")
        bars = ax.bar(names, sizes)
        for bar in bars:
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.,
                height,
                f'{height:.1f}',
                ha='center', 
                va='bottom', 
                rotation=0
            )
        ax.set_xticklabels(names, rotation=45, ha='right')
        ax.set_xlabel("Пакет")
        ax.set_ylabel("Размер (МБ)")
        self.bar_figure.tight_layout()
        self.bar_canvas.draw()
    def update_size_table(self, size_data):
        self.size_table.setRowCount(0)
        for i, pkg in enumerate(size_data):
            self.size_table.insertRow(i)
            name_item = QTableWidgetItem(pkg.get("name", ""))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.size_table.setItem(i, 0, name_item)
            size_mb = pkg.get("size_mb", 0)
            size_item = QTableWidgetItem(f"{size_mb:.2f}")
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.size_table.setItem(i, 1, size_item)
            file_count = pkg.get("file_count", 0)
            files_item = QTableWidgetItem(str(file_count))
            files_item.setFlags(files_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.size_table.setItem(i, 2, files_item)
            location = pkg.get("location", "")
            location_item = QTableWidgetItem(location)
            location_item.setFlags(location_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.size_table.setItem(i, 3, location_item)
def main():
    app = QApplication(sys.argv)
    global APP_ICON
    if os.path.exists(ICON_PATH):
        APP_ICON = QIcon(ICON_PATH)
        app.setWindowIcon(APP_ICON)
    QMessageBox.Yes = QMessageBox.StandardButton.Yes
    QMessageBox.No = QMessageBox.StandardButton.No
    QMessageBox.Ok = QMessageBox.StandardButton.Ok
    QMessageBox.Cancel = QMessageBox.StandardButton.Cancel
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main() 