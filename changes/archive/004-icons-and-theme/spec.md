# Change 004 — Spec: Custom icons & theme switcher

> Comportamento observável. Para **como** é implementado, veja `design.md`.

---

## 1. App icon

- `assets/app-icon.svg` existe no repo (entregue neste change)
- `assets/app-icon.ico` existe no repo (gerado do SVG, multi-resolution 16/32/48/256)
- `python -m app.main` mostra o ícone customizado no title bar da janela
- No Windows taskbar: ícone aparece (depende de o `.ico` ter sido gerado
  corretamente; se ausente, fallback pro ícone genérico do Qt)

## 2. File tree icons

Cada entrada do `QTreeView` exibe um ícone Material Design Icons
baseado no seu tipo:

| Tipo / Extensão | Ícone MDI | Cor |
|---|---|---|
| Diretório | `mdi.folder` | padrão |
| `.py` | `mdi.language_python` | accent |
| `.ts`, `.tsx` | `mdi.language_typescript` | accent |
| `.js`, `.jsx` | `mdi.language_javascript` | accent |
| `.java` | `mdi.language_java` | accent |
| `.json` | `mdi.code_json` | accent |
| `.md` | `mdi.language_markdown` | accent |
| `.txt` | `mdi.file_document` | padrão |
| `.toml`, `.yaml`, `.yml` | `mdi.file_cog` | padrão |
| `LICENSE` (case-insensitive) | `mdi.license` | accent |
| `.gitignore` | `mdi.git` | accent |
| `README.md` | `mdi.book_open_variant` | accent |
| outros arquivos | `mdi.file` | padrão |

`accent` = cor de destaque do tema atual (cyan/blue).

## 3. Theme switcher

### 3.1. Menu

```
View
├── Theme
│   ├── ● Dark
│   ├── ○ Light
│   └── ○ System (default)
└── Toggle Theme   Ctrl+Shift+T
```

Comportamento:
- `●` marca o tema ativo
- Selecionar um tema aplica imediatamente
- `Ctrl+Shift+T` cicla: Dark → Light → System → Dark
- Fechar o app, reabrir: tema persistido é restaurado

### 3.2. Temas disponíveis

| Tema | Background | Texto | Selection | Splitter |
|---|---|---|---|---|
| Dark | `#1e1e1e` | `#e0e0e0` | `#264f78` | `#3a3a3a` |
| Light | `#fafafa` | `#1e1e1e` | `#cce8ff` | `#d0d0d0` |

(Final values subject to design tuning — ver design.md)

### 3.3. System detection

- **Windows 10/11**: lê `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme`
  - `1` = Light, `0` = Dark, ausente = Dark (default)
- **Fallback** (outras plataformas ou erro de leitura): Dark
- Aplicado apenas quando `Theme.SYSTEM` está selecionado

## 4. Persistência (QSettings)

- **Key**: `theme` (string, valores: `"dark"`, `"light"`, `"system"`)
- **Localização no Windows**: `HKEY_CURRENT_USER\Software\ArchExplorer\ArchExplorer AI\theme`
- **Default**: `system`

Mudou o tema → `QSettings.setValue("theme", value)` chamado antes do `app.quit()`.

## 5. ThemeManager API

```python
class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"

class ThemeManager:
    def __init__(self, app: QApplication) -> None:
        """Loads persisted preference (or detects system theme) and applies it."""

    def current(self) -> Theme:
        """Returns the user's selected theme (may be SYSTEM)."""

    def effective(self) -> Theme:
        """Resolves SYSTEM to DARK or LIGHT based on the OS."""

    def apply(self, theme: Theme) -> None:
        """Loads the right QSS and calls app.setStyleSheet()."""

    def cycle(self) -> Theme:
        """Dark → Light → System → Dark; applies and returns new theme."""

    @staticmethod
    def detect_system_theme() -> Theme:
        """Reads the Windows registry (with fallback to DARK)."""
```

## 6. App-level integration

`app/main.py`:
```python
def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_ORG)
    app.setOrganizationDomain(APP_DOMAIN)

    # App icon (loads from assets/ relative to project root)
    icon_path = Path(__file__).parent.parent / "assets" / "app-icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Theme
    theme_manager = ThemeManager(app)
    theme_manager.apply(theme_manager.current())

    services = {"ai_engine": AIEngine(OllamaProvider())}
    window = MainWindow(services=services, theme_manager=theme_manager)
    window.show()
    return app.exec()
```

`MainWindow.__init__` accepts an optional `theme_manager: ThemeManager` and wires up the View menu.

## 7. CustomIconProvider API

```python
class CustomIconProvider(QFileIconProvider):
    """Returns qtawesome (Material Design Icons) icons for files and dirs."""

    EXTENSION_ICONS: Final[dict[str, str]] = {
        ".py": "mdi.language_python",
        ".ts": "mdi.language_typescript",
        # ...
    }

    FILENAME_ICONS: Final[dict[str, str]] = {
        "license": "mdi.license",
        "readme.md": "mdi.book_open_variant",
        ".gitignore": "mdi.git",
    }

    def __init__(self, color: str | None = None) -> None:
        self._cache: dict[str, QIcon] = {}
        self._color = color  # if None, uses default MDI color

    def icon(self, type_or_info) -> QIcon:
        """Override of QFileIconProvider.icon()."""
```

## 8. Test contracts

### 8.1. Unit (sem Qt graphics, só objetos `QIcon`)

- `test_icons.py`:
  - `CustomIconProvider().icon(QFileIconProvider.File)` is a `QIcon`
  - `CustomIconProvider().icon(QFileInfo(".gitignore"))` returns a `QIcon`
  - Caching: 2 calls for the same input return the same `QIcon` instance
  - All whitelisted extensions return non-null `QIcon`
  - Unknown extensions fall back to `mdi.file` (still a valid `QIcon`)

- `test_theme.py`:
  - `ThemeManager(app).current()` returns one of `DARK`, `LIGHT`, `SYSTEM`
  - `ThemeManager(app).effective()` never returns `SYSTEM`
  - `ThemeManager(app).apply(Theme.DARK)` calls `app.setStyleSheet()` with non-empty string
  - `ThemeManager(app).cycle()` cycles through all 3 themes
  - `detect_system_theme()` returns `DARK` or `LIGHT` (never raises)

- `test_menu.py`:
  - `View > Theme > Dark` is a checkable `QAction`
  - Exactly one of {Dark, Light, System} is checked at any time
  - `Ctrl+Shift+T` is bound to the cycle action

### 8.2. Smoke (with `qapp` fixture)

- `test_integration.py`:
  - Instantiating `MainWindow` with a `ThemeManager` does not crash
  - The menu bar has `View` with `Theme` submenu

### 8.3. Manual (Henrique)

- Visual: ícones MDI no tree
- Visual: tema dark + tema light + alterna
- Persistência: fechar, reabrir, tema preservado

## 9. Restrições

- Python 3.10–3.13 (sem mudança)
- Windows 11 (alvo principal; outros SOs funcionam mas system-detection só Windows)
- **Nova dep runtime**: `qtawesome>=1.3`
- **Sem novas deps dev**
- `QSettings` é built-in do PySide6
- `assets/app-icon.ico` é gerado uma vez (script manual) e commitado
