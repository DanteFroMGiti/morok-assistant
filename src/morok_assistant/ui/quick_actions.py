from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from morok_assistant.system.local_actions import ApplicationIndex


class QuickActionsDialog(QDialog):
    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.index = ApplicationIndex()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_files)
        self.process.finished.connect(self._search_finished)
        self._file_buffer = ""
        self._file_count = 0
        self.setWindowTitle("Команды и поиск")
        self.setMinimumSize(580, 420)

        self.query = QLineEdit()
        self.query.setPlaceholderText("Название приложения или файла")
        self.query.returnPressed.connect(self.search_applications)
        apps = QPushButton("Найти приложение")
        apps.clicked.connect(self.search_applications)
        files = QPushButton("Найти файл")
        files.clicked.connect(self.search_files)

        controls = QHBoxLayout()
        controls.addWidget(self.query, 1)
        controls.addWidget(apps)
        controls.addWidget(files)
        self.status = QLabel(
            "Можно ввести «Telegram», «браузер» или часть имени файла. Двойной клик открывает результат."
        )
        self.status.setWordWrap(True)
        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(self._activate)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(self.results, 1)

    def search_applications(self) -> None:
        self._stop_search()
        query = self._normalized_query(("открой", "запусти", "open", "run"))
        self.results.clear()
        matches = self.index.search(query)
        for application in matches:
            item = QListWidgetItem(application.name)
            item.setData(Qt.ItemDataRole.UserRole, str(application.desktop_file))
            item.setData(Qt.ItemDataRole.UserRole + 1, "application")
            self.results.addItem(item)
        self.status.setText(
            f"Найдено приложений: {len(matches)}" if matches else "Приложение не найдено"
        )

    def search_files(self) -> None:
        self._stop_search()
        query = self._normalized_query(("найди", "find", "search"))
        self.results.clear()
        if not query:
            self.status.setText("Введите часть имени файла")
            return
        self._file_buffer = ""
        self._file_count = 0
        home = str(Path.home())
        arguments = [
            home,
            "(",
            "-path",
            f"{home}/.cache",
            "-o",
            "-path",
            "*/.git",
            ")",
            "-prune",
            "-o",
            "-type",
            "f",
            "-iname",
            f"*{query}*",
            "-print",
        ]
        self.status.setText("Ищу файлы…")
        self.process.start("find", arguments)

    def _read_files(self) -> None:
        self._file_buffer += bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        lines = self._file_buffer.split("\n")
        self._file_buffer = lines.pop()
        for path in lines:
            if not path or self._file_count >= 50:
                continue
            item = QListWidgetItem(path.replace(str(Path.home()), "~", 1))
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setData(Qt.ItemDataRole.UserRole + 1, "file")
            self.results.addItem(item)
            self._file_count += 1
        if self._file_count >= 50:
            self.process.kill()

    def _search_finished(self) -> None:
        self._read_files()
        self.status.setText(
            f"Найдено файлов: {self._file_count}"
            if self._file_count
            else "Подходящих файлов не найдено"
        )

    def _activate(self, item: QListWidgetItem) -> None:
        path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        kind = item.data(Qt.ItemDataRole.UserRole + 1)
        if kind == "application":
            application = next(
                (app for app in self.index.applications() if app.desktop_file == path), None
            )
            if application is not None and self.index.launch(application):
                self.status.setText(f"Запускаю: {application.name}")
            else:
                self.status.setText("Не удалось запустить приложение")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.status.setText("Не удалось открыть файл")

    def _normalized_query(self, prefixes: tuple[str, ...]) -> str:
        query = self.query.text().strip()
        lowered = query.casefold()
        for prefix in prefixes:
            if lowered.startswith(prefix + " "):
                return query[len(prefix) :].strip()
        return query

    def _stop_search(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
