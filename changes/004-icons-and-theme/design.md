# Change 004 — Design: Custom icons & theme switcher

> Decisões de **como** o ícone e theming são estruturados.

---

## 1. `qtawesome` por que e como

`qtawesome` é o padrão de fato pra ícones em apps Qt Python. Wraps
FontAwesome 5 (free) e Material Design Icons (community edition) como
`QIcon` prontos pra usar, com suporte a coloração via parâmetro ou
via QSS (`color: red` propaga).

```python
import qtawesome as qta

qta.icon("mdi.folder")             # ícone MDI default
qta.icon("mdi.language_python",     # ícone colorido
         color="#3776ab")
qta.icon("fa5s.file-code")          # FontAwesome alternative
```

Vantagens:
- 7000+ ícones disponíveis (MDI + FA5 free)
- Cor por chamada (consistente com tema dark/light)
- Funciona com PySide6 (detectado automaticamente)
- Ativo, mantido

## 2. CustomIconProvider

`QFileIconProvider` é a interface que o `QFileSystemModel` consulta para
ícones. Subclassando e injetando:

```python
class CustomIconProvider(QFileIconProvider):
    EXTENSION_ICONS: dict[str, str] = {
        ".py": "mdi.language_python",
        ".ts": "mdi.language_typescript",
        ".tsx": "mdi.language_typescript",
        ".js": "mdi.language_javascript",
        ".jsx": "mdi.language_javascript",
        ".java": "mdi.language_java",
        ".json": "mdi.code_json",
        ".md": "mdi.language_markdown",
        ".txt": "mdi.file_document",
        ".toml": "mdi.file_cog",
        ".yaml": "mdi.file_cog",
        ".yml": "mdi.file_cog",
    }
    FILENAME_ICONS: dict[str, str] = {
        "license": "mdi.license",
        "readme.md": "mdi.book_open_variant",
        ".gitignore": "mdi.git",
    }
    DEFAULT_FILE_ICON = "mdi.file"
    DEFAULT_DIR_ICON = "mdi.folder"

    def __init__(self, color: str | None = None) -> None:
        super().__init__()
        self._cache: dict[str, QIcon] = {}
        self._color = color or "#cccccc"  # will be themed later

    def icon(self, argument) -> QIcon:
        # QFileIconProvider.icon can take either QFileInfo or QFileIconProvider.IconType
        if isinstance(argument, QFileInfo):
            return self._icon_for_path(Path(argument.filePath()))
        if argument == QFileIconProvider.IconType.Folder:
            return self._cached(self.DEFAULT_DIR_ICON)
        return self._cached(self.DEFAULT_FILE_ICON)

    def _icon_for_path(self, path: Path) -> QIcon:
        if path.is_dir():
            return self._cached(self.DEFAULT_DIR_ICON)
        name = path.name.lower()
        if name in self.FILENAME_ICONS:
            return self._cached(self.FILENAME_ICONS[name])
        if path.suffix.lower() in self.EXTENSION_ICONS:
            return self._cached(self.EXTENSION_ICONS[path.suffix.lower()])
        return self._cached(self.DEFAULT_FILE_ICON)

    def _cached(self, mdi_name: str) -> QIcon:
        if mdi_name not in self._cache:
            self._cache[mdi_name] = qta.icon(mdi_name, color=self._color)
        return self._cache[mdi_name]
```

**Cores dinâmicas**: a cor pode ser atualizada via `set_color()` quando
o tema muda. Os ícones já cacheados precisam ser regenerados:

```python
def set_color(self, color: str) -> None:
    self._color = color
    self._cache.clear()  # força recriação no próximo acesso
```

(No Change 004, cor fica fixa; mudança fica para change futuro que
integrar com `QPalette` do tema corrente.)

## 3. ThemeManager

```python
from enum import Enum
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"

    @classmethod
    def from_string(cls, s: str) -> "Theme":
        try:
            return cls(s.lower())
        except ValueError:
            return cls.SYSTEM

    def to_string(self) -> str:
        return self.value


class ThemeManager:
    _QSS_DIR = Path(__file__).parent / "qss"

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._settings = QSettings()  # uses QApplication's org/app names
        persisted = self._settings.value("theme", Theme.SYSTEM.value, type=str)
        self._selected = Theme.from_string(persisted)

    def current(self) -> Theme:
        return self._selected

    def effective(self) -> Theme:
        if self._selected == Theme.SYSTEM:
            return self.detect_system_theme()
        return self._selected

    def apply(self, theme: Theme) -> None:
        self._selected = theme
        self._settings.setValue("theme", theme.to_string())
        effective = self.effective()
        qss_file = self._QSS_DIR / f"{effective.value}.qss"
        if qss_file.exists():
            self._app.setStyleSheet(qss_file.read_text(encoding="utf-8"))
        else:
            self._app.setStyleSheet("")  # fallback: tema do sistema

    def cycle(self) -> Theme:
        order = [Theme.DARK, Theme.LIGHT, Theme.SYSTEM]
        next_idx = (order.index(self._selected) + 1) % len(order)
        self.apply(order[next_idx])
        return self._selected

    @staticmethod
    def detect_system_theme() -> Theme:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return Theme.LIGHT if value == 1 else Theme.DARK
        except (OSError, ImportError):
            return Theme.DARK
```

**Por que `QSettings` direto**: built-in do PySide6, sem dep nova.
Usa `QApplication.organizationName()` e `applicationName()` para o path
(que setamos no `main.py` para `ArchExplorer` / `ArchExplorer AI`).

## 4. QSS (dark.qss e light.qss)

Cada um ~60-80 linhas. Estiliza apenas widgets que temos:

```css
/* dark.qss */
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

QTreeView {
    background-color: #252525;
    alternate-background-color: #2a2a2a;
    selection-background-color: #264f78;
    selection-color: #ffffff;
    border: none;
}

QTreeView::item:hover {
    background-color: #2a2a2a;
}

QSplitter::handle {
    background-color: #3a3a3a;
}

QSplitter::handle:hover {
    background-color: #007acc;
}

QPlainTextEdit {
    background-color: #1e1e1e;
    color: #d4d4d4;
    selection-background-color: #264f78;
    selection-color: #ffffff;
    border: none;
}

QMenuBar {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border-bottom: 1px solid #3a3a3a;
}

QMenuBar::item:selected {
    background-color: #3a3a3a;
}

QMenu {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3a3a3a;
}

QMenu::item:selected {
    background-color: #094771;
}

QStatusBar {
    background-color: #007acc;
    color: #ffffff;
}
```

```css
/* light.qss */
QMainWindow, QWidget {
    background-color: #fafafa;
    color: #1e1e1e;
}

QTreeView {
    background-color: #ffffff;
    alternate-background-color: #f5f5f5;
    selection-background-color: #cce8ff;
    selection-color: #1e1e1e;
    border: 1px solid #e0e0e0;
}

QTreeView::item:hover {
    background-color: #e8f0fe;
}

QSplitter::handle {
    background-color: #d0d0d0;
}

QSplitter::handle:hover {
    background-color: #007acc;
}

QPlainTextEdit {
    background-color: #ffffff;
    color: #1e1e1e;
    selection-background-color: #cce8ff;
    selection-color: #1e1e1e;
    border: 1px solid #e0e0e0;
}

QMenuBar {
    background-color: #f0f0f0;
    color: #1e1e1e;
    border-bottom: 1px solid #d0d0d0;
}

QMenuBar::item:selected {
    background-color: #d0d0d0;
}

QMenu {
    background-color: #ffffff;
    color: #1e1e1e;
    border: 1px solid #d0d0d0;
}

QMenu::item:selected {
    background-color: #cce8ff;
}

QStatusBar {
    background-color: #007acc;
    color: #ffffff;
}
```

**Notas QSS**:
- `QWebEngineView` (painel direito) **não** é estilizado pelo QSS — o conteúdo
  dele é HTML que tem seu próprio theming (via `github-markdown-dark` ou
  -light CSS). Para suporte light no visualizer, muda o CSS do template
  (de `github-markdown-dark` para `-light` quando o tema é light).
- Splitter handle: cinza neutro no estado normal, **azul** no hover (feedback visual)

## 5. HTML template — light variant

`build_html_template(markdown_text, theme: str = "dark")`:

```python
def build_html_template(markdown_text: str, theme: str = "dark") -> str:
    css_file = "github-markdown-dark" if theme == "dark" else "github-markdown-light"
    css_url = f"https://cdn.jsdelivr.net/npm/github-markdown-css@{VERSION}/{css_file}.min.css"
    # ... rest same as before
```

O `MainWindow` passa o tema efetivo para o `VisualizerPanel.show_markdown()`:

```python
def show_markdown(self, text: str, theme: str = "dark") -> None:
    self.last_markdown = text
    self._web.setHtml(build_html_template(text, theme=theme))
```

Worker continua emitindo só o markdown; `MainWindow` injeta o tema no
callback de `finished`:

```python
worker.signals.finished.connect(
    lambda text: self._visualizer.show_markdown(text, theme=self._theme_manager.effective().value)
)
```

## 6. App icon (SVG)

`assets/app-icon.svg` — letter "A" estilizada num hexágono:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0e7490"/>
      <stop offset="100%" stop-color="#06b6d4"/>
    </linearGradient>
  </defs>
  <polygon points="32,4 56,18 56,46 32,60 8,46 8,18"
           fill="url(#g)" stroke="#0e7490" stroke-width="2"/>
  <text x="32" y="44" text-anchor="middle"
        font-family="-apple-system, Segoe UI, sans-serif"
        font-weight="700" font-size="38" fill="#ffffff">A</text>
</svg>
```

64x64 viewBox, scalable, com gradiente cyan para combinar com o tema.

`assets/app-icon.ico` — gerado do SVG com Pillow (script manual):

```python
# scripts/build_app_icon.py (not part of repo; run once when SVG changes)
from PIL import Image
from pathlib import Path
svg_path = Path("assets/app-icon.svg")
img = Image.open(svg_path)  # requires cairosvg or similar
img.save("assets/app-icon.ico", sizes=[(16,16), (32,32), (48,48), (256,256)])
```

Na primeira execução, eu gero o `.ico` e commito. Pra mudanças futuras do SVG,
o usuário (ou eu) reroda o script.

## 7. Menu wiring no MainWindow

```python
class MainWindow(QMainWindow):
    def __init__(self, services=None, theme_manager=None, parent=None):
        super().__init__(parent)
        self._services = services or {}
        self._theme_manager = theme_manager
        # ... existing setup ...
        if self._theme_manager is not None:
            self._build_menu()

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        view_menu = menubar.addMenu("&View")
        theme_menu = view_menu.addMenu("&Theme")
        self._theme_actions = {}
        for theme in (Theme.DARK, Theme.LIGHT, Theme.SYSTEM):
            action = QAction(theme.value.title(), self)
            action.setCheckable(True)
            action.setChecked(theme == self._theme_manager.current())
            action.triggered.connect(lambda _checked, t=theme: self._on_theme_changed(t))
            self._theme_actions[theme] = action
            theme_menu.addAction(action)
        # Sync with current
        self._theme_action_group = QActionGroup(self)
        for a in self._theme_actions.values():
            self._theme_action_group.addAction(a)
        self._theme_action_group.setExclusive(True)
        # Toggle shortcut
        view_menu.addSeparator()
        toggle_action = QAction("&Toggle Theme", self)
        toggle_action.setShortcut("Ctrl+Shift+T")
        toggle_action.triggered.connect(self._on_toggle_theme)
        view_menu.addAction(toggle_action)

    def _on_theme_changed(self, theme: Theme) -> None:
        self._theme_manager.apply(theme)

    def _on_toggle_theme(self) -> None:
        self._theme_manager.cycle()
        # Update the checked state
        for theme, action in self._theme_actions.items():
            action.setChecked(theme == self._theme_manager.current())
```

## 8. Estrutura de arquivos (final)

```
app/ui/
├── icons.py             # CustomIconProvider
├── theme.py             # ThemeManager, Theme, detect_system_theme
├── qss/
│   ├── dark.qss
│   └── light.qss
└── main_window.py       # modificado: menu bar, theme manager injection

assets/
├── app-icon.svg         # letter A in hexagon
└── app-icon.ico         # multi-res from SVG

scripts/
└── build_app_icon.py    # (NEW, opt) regenerate .ico from .svg

tests/unit/
├── test_icons.py
├── test_theme.py
└── test_menu.py
```

## 9. Compatibilidade com Changes anteriores

- `app/main.py` ganha 2 novas responsabilidades: set icon, set theme
- `MainWindow` ganha `theme_manager` kwarg (opcional, default None)
- `VisualizerPanel.show_markdown()` ganha `theme` kwarg (default "dark")
- `app/ui/html_template.py` ganha `theme` kwarg em `build_html_template`
- `services={"ai_engine": ...}` continua igual
- Todos os 157 testes anteriores continuam passando (mudanças aditivas)

## 10. O que **NÃO** está neste design

- Ícones em menus de contexto (sem context menus ainda)
- Ícones em botões (sem botões ainda além de QMenuBar)
- Animações de transição entre temas
- Light/dark para o conteúdo do `QWebEngineView` (parcialmente coberto — só CSS base)
- Custom fonts
- Ícones em `.exe`, `.dll` (raros no contexto)

## 11. Trade-offs

| Decisão | Custo | Benefício |
|---|---|---|
| `qtawesome` (em vez de SVGs custom) | +1 dep | 7000+ ícones prontos, coloração dinâmica |
| 2 QSS files completos (em vez de 1 + vars) | ~80 linhas duplicadas | Qt não suporta CSS vars; duplicação é honesta |
| App icon SVG commitado + .ico commitado | usuário edita o .svg, precisa rerodar script | App icon aparece no taskbar do Windows desde a 1ª execução |
| Cor fixa nos ícones (não segue tema) | ícones sempre da mesma cor | Simplicidade; cor dinâmica fica para change futuro |
| QSettings (registry) | persistência vai pro registry | Standard Qt, sem dep |
| Theme enum no Python (em vez de constants) | Boilerplate leve | Type-safe, autocompleta |
| `QActionGroup` exclusive para radio behavior | +5 LOC | Comportamento correto de radio buttons no menu |
