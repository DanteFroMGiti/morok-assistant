from __future__ import annotations

from html import escape
from shutil import which

from PySide6.QtCore import QProcess, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from morok_assistant.ai.local_models import available_ollama_models, ollama_running
from morok_assistant.ai.providers import (
    DEFAULT_MODELS,
    KEY_ENVIRONMENTS,
    KEY_URLS,
    MODEL_OPTIONS,
    PROVIDER_NAMES,
)
from morok_assistant.ai.settings import AISettings, AISettingsStore
from morok_assistant.system.autostart import AutostartManager
from morok_assistant.system.behavior_settings import BehaviorSettings, BehaviorSettingsStore
from morok_assistant.system.local_actions import ApplicationIndex
from morok_assistant.system.startup_apps import (
    StartupApplication,
    StartupApplicationsStore,
)
from morok_assistant.ui.gesture_settings import (
    DOUBLE_CLICK_ACTIONS,
    HOVER_ACTIONS,
    GestureSettings,
    GestureSettingsStore,
)


class AISettingsDialog(QDialog):
    interacted = Signal()

    def __init__(
        self,
        store: AISettingsStore,
        parent: QWidget | None = None,
        gesture_store: GestureSettingsStore | None = None,
        behavior_store: BehaviorSettingsStore | None = None,
        autostart: AutostartManager | None = None,
        startup_apps_store: StartupApplicationsStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.gesture_store = gesture_store or GestureSettingsStore(
            store.path.with_name("gestures.json")
        )
        self.behavior_store = behavior_store or BehaviorSettingsStore(
            store.path.with_name("behavior.json")
        )
        self.autostart_manager = autostart or AutostartManager()
        self.startup_apps_store = startup_apps_store or StartupApplicationsStore(
            store.path.with_name("startup-apps.json")
        )
        self._initial_autostart = self.autostart_manager.enabled
        settings = store.load()
        gestures = self.gesture_store.load()
        behavior = self.behavior_store.load()
        self._provider_keys = dict(settings.api_keys)
        self._provider_models = dict(settings.models)
        self._current_provider = settings.provider
        self.setWindowTitle("Настройки Морока")
        self.setMinimumSize(500, 570)

        self.enabled = QCheckBox("Подключить Морока к ИИ")
        self.enabled.setChecked(settings.enabled)
        self.enabled.toggled.connect(self.interacted)

        self.provider = QComboBox()
        for identifier, name in PROVIDER_NAMES.items():
            self.provider.addItem(name, identifier)
        self.provider.setCurrentIndex(self.provider.findData(settings.provider))
        self.provider.currentIndexChanged.connect(self._on_provider_changed)

        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.currentTextChanged.connect(self.interacted)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.textChanged.connect(self.interacted)

        self.endpoint = QLineEdit(settings.endpoint_url)
        self.endpoint.setPlaceholderText("http://127.0.0.1:1234/v1/chat/completions")
        self.endpoint.textChanged.connect(self.interacted)

        form = QFormLayout()
        form.addRow("Сервис:", self.provider)
        form.addRow("Модель:", self.model)
        form.addRow("Ключ API:", self.api_key)
        form.addRow("Адрес API:", self.endpoint)
        self._endpoint_label = form.labelForField(self.endpoint)

        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setOpenExternalLinks(True)

        self.local_button = QPushButton("Запустить Ollama")
        self.local_button.clicked.connect(self._start_or_refresh_ollama)

        self.double_click = QComboBox()
        for action, label in DOUBLE_CLICK_ACTIONS.items():
            self.double_click.addItem(label, action)
        self.double_click.setCurrentIndex(self.double_click.findData(gestures.double_click))
        self.double_click.currentIndexChanged.connect(self.interacted)

        self.hover = QComboBox()
        for action, label in HOVER_ACTIONS.items():
            self.hover.addItem(label, action)
        self.hover.setCurrentIndex(self.hover.findData(gestures.hover))
        self.hover.currentIndexChanged.connect(self.interacted)

        self.hover_cooldown = QComboBox()
        for label, seconds in (("Часто · 8 с", 8), ("Обычно · 30 с", 30),
                               ("Редко · 90 с", 90), ("Очень редко · 5 мин", 300)):
            self.hover_cooldown.addItem(label, seconds)
        self.hover_cooldown.setCurrentIndex(
            self.hover_cooldown.findData(gestures.hover_cooldown_seconds)
        )
        self.hover_cooldown.currentIndexChanged.connect(self.interacted)

        gesture_group = QGroupBox("Жесты")
        gesture_form = QFormLayout(gesture_group)
        gesture_form.addRow("Двойной клик:", self.double_click)
        gesture_form.addRow("Наведение мыши:", self.hover)
        gesture_form.addRow("Повтор реакции:", self.hover_cooldown)

        self.personality_mode = QComboBox()
        for label, value in (("Тихий — сидит и ждёт", "quiet"),
                             ("Активный — гуляет и осматривается", "active"),
                             ("Любознательный — спрашивает и помнит", "curious")):
            self.personality_mode.addItem(label, value)
        self.personality_mode.setCurrentIndex(
            self.personality_mode.findData(behavior.personality_mode)
        )
        self.personality_mode.currentIndexChanged.connect(self.interacted)
        self.reaction_frequency = QComboBox()
        for label, value in (("Выключены", "off"), ("Редко", "rare"),
                             ("Обычно", "normal"), ("Часто", "often")):
            self.reaction_frequency.addItem(label, value)
        self.reaction_frequency.setCurrentIndex(
            self.reaction_frequency.findData(behavior.reaction_frequency)
        )
        self.reaction_frequency.currentIndexChanged.connect(self.interacted)

        self.autostart = QCheckBox("Запускать Морока при входе в систему")
        self.autostart.setChecked(self._initial_autostart)
        self.autostart.toggled.connect(self.interacted)
        self.watch_videos = QCheckBox("Садиться у окна с видео и смотреть вместе")
        self.watch_videos.setChecked(behavior.watch_videos)
        self.watch_videos.toggled.connect(self.interacted)
        self.react_to_games = QCheckBox("Не отвлекать во время игр")
        self.react_to_games.setChecked(behavior.react_to_games)
        self.react_to_games.toggled.connect(self.interacted)
        self.react_to_music = QCheckBox("Реагировать на музыкальные проигрыватели")
        self.react_to_music.setChecked(behavior.react_to_music)
        self.react_to_music.toggled.connect(self.interacted)
        self.react_to_code = QCheckBox("Замечать ошибки из буфера в редакторах кода")
        self.react_to_code.setChecked(behavior.react_to_code)
        self.react_to_code.toggled.connect(self.interacted)
        self.break_reminders = QCheckBox("Напоминать о перерыве при долгом чтении")
        self.break_reminders.setChecked(behavior.break_reminders)
        self.break_reminders.toggled.connect(self.interacted)

        self.wayland_mode = QComboBox()
        self.wayland_mode.addItem("Авто (XWayland при наличии)", "auto")
        self.wayland_mode.addItem("XWayland", "xwayland")
        self.wayland_mode.addItem("Нативный Wayland (ограничено)", "native")
        self.wayland_mode.setCurrentIndex(self.wayland_mode.findData(behavior.wayland_mode))
        self.wayland_mode.currentIndexChanged.connect(self.interacted)
        wayland_hint = QLabel(
            "Режим применяется после перезапуска. Нативный Wayland пока не позволяет "
            "свободно перемещать Морока и выглядывать из-за края."
        )
        wayland_hint.setWordWrap(True)

        behavior_group = QGroupBox("Поведение")
        behavior_layout = QVBoxLayout(behavior_group)
        behavior_layout.addWidget(QLabel("Характер Морока:"))
        behavior_layout.addWidget(self.personality_mode)
        behavior_layout.addWidget(QLabel("Редкие анимации и реакции:"))
        behavior_layout.addWidget(self.reaction_frequency)
        behavior_layout.addWidget(self.autostart)
        behavior_layout.addWidget(self.watch_videos)
        behavior_layout.addWidget(self.react_to_games)
        behavior_layout.addWidget(self.react_to_music)
        behavior_layout.addWidget(self.react_to_code)
        behavior_layout.addWidget(self.break_reminders)
        behavior_layout.addWidget(QLabel("Режим Wayland:"))
        behavior_layout.addWidget(self.wayland_mode)
        behavior_layout.addWidget(wayland_hint)

        self.application_index = ApplicationIndex()
        self.startup_app_picker = QComboBox()
        self.startup_app_picker.setEditable(True)
        self.startup_app_picker.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.startup_app_picker.setPlaceholderText("Найдите установленное приложение")
        for application in self.application_index.applications():
            if application.name.casefold() == "морок":
                continue
            self.startup_app_picker.addItem(application.name, str(application.desktop_file))
        self.startup_app_picker.setCurrentIndex(-1)
        completer = self.startup_app_picker.completer()
        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)

        add_startup_app = QPushButton("Добавить")
        add_startup_app.clicked.connect(self._add_startup_application)
        picker_row = QHBoxLayout()
        picker_row.addWidget(self.startup_app_picker, 1)
        picker_row.addWidget(add_startup_app)

        self.startup_apps = QListWidget()
        self.startup_apps.setMinimumHeight(105)
        for application in self.startup_apps_store.load():
            self._append_startup_application(application)
        remove_startup_app = QPushButton("Убрать выбранное")
        remove_startup_app.clicked.connect(self._remove_startup_application)

        startup_group = QGroupBox("Приложения вместе с Мороком")
        startup_layout = QVBoxLayout(startup_group)
        startup_hint = QLabel(
            "При запуске Морока откроются только те из отмеченных приложений, "
            "которые ещё не запущены."
        )
        startup_hint.setWordWrap(True)
        startup_layout.addWidget(startup_hint)
        startup_layout.addLayout(picker_row)
        startup_layout.addWidget(self.startup_apps)
        startup_layout.addWidget(remove_startup_app)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        ai_page = QWidget()
        ai_layout = QVBoxLayout(ai_page)
        ai_layout.addWidget(self.enabled)
        ai_layout.addLayout(form)
        ai_layout.addWidget(self.info)
        ai_layout.addWidget(self.local_button)
        ai_layout.addStretch()

        behavior_page = QWidget()
        behavior_page_layout = QVBoxLayout(behavior_page)
        behavior_page_layout.addWidget(gesture_group)
        behavior_page_layout.addWidget(behavior_group)
        behavior_page_layout.addStretch()
        behavior_scroll = QScrollArea()
        behavior_scroll.setWidgetResizable(True)
        behavior_scroll.setWidget(behavior_page)

        startup_page = QWidget()
        startup_page_layout = QVBoxLayout(startup_page)
        startup_page_layout.addWidget(startup_group)
        startup_page_layout.addStretch()

        tabs = QTabWidget()
        tabs.addTab(ai_page, "ИИ")
        tabs.addTab(behavior_scroll, "Поведение")
        tabs.addTab(startup_page, "Запуск программ")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

        self._fill_provider(settings.provider, settings.model, settings.api_key)

    def _append_startup_application(self, application: StartupApplication) -> None:
        item = QListWidgetItem(application.name)
        item.setData(Qt.ItemDataRole.UserRole, application.desktop_file)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        check_state = Qt.CheckState.Checked if application.enabled else Qt.CheckState.Unchecked
        item.setCheckState(check_state)
        self.startup_apps.addItem(item)

    def _add_startup_application(self) -> None:
        desktop_file = self.startup_app_picker.currentData()
        name = self.startup_app_picker.currentText().strip()
        if not desktop_file or not name:
            QMessageBox.information(
                self,
                "Приложение не выбрано",
                "Выберите приложение из списка установленных программ.",
            )
            return
        for row in range(self.startup_apps.count()):
            if self.startup_apps.item(row).data(Qt.ItemDataRole.UserRole) == desktop_file:
                self.startup_apps.setCurrentRow(row)
                return
        self._append_startup_application(StartupApplication(name, str(desktop_file)))
        self.interacted.emit()

    def _remove_startup_application(self) -> None:
        for item in self.startup_apps.selectedItems():
            self.startup_apps.takeItem(self.startup_apps.row(item))
        self.interacted.emit()

    def _selected_startup_applications(self) -> list[StartupApplication]:
        return [
            StartupApplication(
                self.startup_apps.item(row).text(),
                str(self.startup_apps.item(row).data(Qt.ItemDataRole.UserRole)),
                self.startup_apps.item(row).checkState() == Qt.CheckState.Checked,
            )
            for row in range(self.startup_apps.count())
        ]

    def _remember_current_provider(self) -> None:
        key = self.api_key.text().strip()
        if key:
            self._provider_keys[self._current_provider] = key
        else:
            self._provider_keys.pop(self._current_provider, None)
        model = self.model.currentText().strip()
        if model:
            self._provider_models[self._current_provider] = model

    def _on_provider_changed(self) -> None:
        self._remember_current_provider()
        provider = self.provider.currentData()
        self._current_provider = provider
        self._fill_provider(
            provider,
            self._provider_models.get(provider, DEFAULT_MODELS[provider]),
            self._provider_keys.get(provider, ""),
        )
        self.interacted.emit()

    def _fill_provider(self, provider: str, model: str, key: str) -> None:
        self.model.blockSignals(True)
        self.model.clear()
        choices = available_ollama_models() if provider == "ollama" else MODEL_OPTIONS[provider]
        self.model.addItems(choices)
        self.model.setCurrentText(model or (choices[0] if choices else ""))
        self.model.blockSignals(False)
        self.api_key.setText(key)
        self.api_key.setEnabled(provider != "ollama")
        environment = KEY_ENVIRONMENTS.get(provider)
        self.api_key.setPlaceholderText(
            f"Ключ API или переменная {environment}" if environment else "Ключ не нужен"
        )
        self.local_button.setVisible(provider == "ollama")
        if provider == "ollama":
            self.local_button.setText(
                "Обновить список моделей" if ollama_running() else "Запустить Ollama"
            )
        custom = provider == "compatible"
        self.endpoint.setVisible(custom)
        self._endpoint_label.setVisible(custom)
        if provider == "ollama":
            self.info.setText(
                "Морок подключается к Ollama на этом компьютере. Если список моделей пуст, "
                "запустите <code>ollama serve</code> и установите модель командой "
                "<code>ollama pull llama3.2</code>."
            )
        elif custom:
            self.info.setText(
                "Укажите полный адрес Chat Completions API локального сервера или другого "
                "совместимого сервиса. Ключ можно оставить пустым для локального сервера."
            )
        else:
            key_url = KEY_URLS.get(provider)
            link = (
                f"<a href='{escape(key_url)}'>Создать ключ API</a><br>"
                if key_url is not None
                else ""
            )
            billing = (
                "<a href='https://platform.openai.com/settings/organization/billing/'>"
                "Баланс OpenAI API</a><br>"
                if provider == "openai"
                else ""
            )
            self.info.setText(
                link
                + billing
                + "Ключи разных сервисов хранятся на этом компьютере с доступом только для вас. "
                "Сообщения отправляются выбранному сервису."
            )

    def _start_or_refresh_ollama(self) -> None:
        if ollama_running():
            self._refresh_ollama_models()
            return
        executable = which("ollama")
        if executable is None:
            QMessageBox.warning(self, "Ollama не установлен", "Установите Ollama на компьютер.")
            return
        started, _pid = QProcess.startDetached(executable, ["serve"])
        if not started:
            QMessageBox.warning(self, "Ollama не запущен", "Не удалось запустить Ollama.")
            return
        self.local_button.setText("Подключаемся к Ollama…")
        QTimer.singleShot(1200, self._refresh_ollama_models)

    def _refresh_ollama_models(self) -> None:
        if self._current_provider != "ollama":
            return
        choices = available_ollama_models()
        current = self.model.currentText().strip()
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(choices)
        self.model.setCurrentText(current or (choices[0] if choices else ""))
        self.model.blockSignals(False)
        self.local_button.setText(
            "Обновить список моделей" if ollama_running() else "Запустить Ollama"
        )

    def _save(self) -> None:
        self._remember_current_provider()
        provider = self._current_provider
        settings = AISettings(
            enabled=self.enabled.isChecked(),
            provider=provider,
            model=self.model.currentText().strip(),
            api_key=self.api_key.text().strip(),
            api_keys=self._provider_keys,
            models=self._provider_models,
            endpoint_url=self.endpoint.text().strip(),
        )
        if settings.enabled and not settings.ready:
            reason = (
                "Укажите модель ИИ и адрес API."
                if provider == "compatible"
                else "Укажите модель ИИ и ключ API."
            )
            QMessageBox.warning(self, "Не хватает настроек ИИ", reason)
            return
        gestures = GestureSettings(
            double_click=self.double_click.currentData(),
            hover=self.hover.currentData(),
            hover_cooldown_seconds=self.hover_cooldown.currentData(),
        )
        behavior = BehaviorSettings(
            watch_videos=self.watch_videos.isChecked(),
            react_to_games=self.react_to_games.isChecked(),
            react_to_music=self.react_to_music.isChecked(),
            react_to_code=self.react_to_code.isChecked(),
            break_reminders=self.break_reminders.isChecked(),
            wayland_mode=self.wayland_mode.currentData(),
            personality_mode=self.personality_mode.currentData(),
            reaction_frequency=self.reaction_frequency.currentData(),
        )
        try:
            self.store.save(settings)
            self.gesture_store.save(gestures)
            self.behavior_store.save(behavior)
            self.startup_apps_store.save(self._selected_startup_applications())
            if self.autostart.isChecked() != self._initial_autostart:
                self.autostart_manager.set_enabled(self.autostart.isChecked())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Настройки не сохранены", str(error))
            return
        self.accept()
