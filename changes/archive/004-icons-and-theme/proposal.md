# Change 004 — Custom icons & theme switcher

> **Status:** Aguardando aprovação
> **Tipo:** UI/UX (visual polish)
> **Risco:** Médio (touch em todos os widgets via QSS, dep nova `qtawesome`)
> **Pré-requisito externo:** Nenhum

---

## 1. Contexto

O Change 003 entregou o pipeline funcional ponta-a-ponta (clique em arquivo
→ análise → markdown renderizado com Mermaid). Mas o visual ainda usa:

- **Ícones default do Windows** no `QFileSystemModel` (via `QFileIconProvider`
  implícito que delega pro Explorer)
- **Tema único** (segue o tema do sistema, sem opção de override)
- **Sem app icon próprio** (ícone genérico de executável no title bar)

A `docs/guidelines/diretriz.md` já tinha previsto: **"Não use emojis,
prefira ícones"**. Vamos cumprir isso neste change.

O usuário validou este escopo via questionário:
- `qtawesome` + Material Design Icons (Recomendado)
- App icon temporário (vou criar; usuário troca depois)
- Theme switcher dark/light/system

## 2. Mudança

### 2.1. Dependência nova

| Pacote | Versão | Por quê |
|---|---|---|
| `qtawesome` | `>=1.3` | Wrapper de FontAwesome + Material Design Icons como `QIcon`. Já lida com theming (colorir via QSS). |

Adiciona em `pyproject.toml` `[project.dependencies]` e `requirements.txt`.

### 2.2. Estrutura de arquivos

```
app/ui/
├── icons.py             # NOVO — CustomIconProvider(QFileIconProvider)
├── theme.py             # NOVO — Theme enum, ThemeManager, detect_system_theme()
└── qss/
    ├── dark.qss         # NOVO — dark theme stylesheet
    └── light.qss        # NOVO — light theme stylesheet

assets/
├── app-icon.svg         # NOVO — temporary app icon (letter "A" in hexagon)
└── app-icon.ico         # NOVO — same icon, Windows ICO format (16/32/48/256 px)
```

Arquivos modificados:
- `app/main.py` — seta `QApplication.setWindowIcon()` + aplica tema inicial
- `app/ui/main_window.py` — menu bar `View > Theme > Dark/Light/System` + `setIconProvider` no file explorer
- `pyproject.toml` + `requirements.txt` — adiciona `qtawesome`

### 2.3. CustomIconProvider

Subclasse de `QFileIconProvider` que retorna ícones MDI/FontAwesome
baseado em extensão/nome. Caching interno (cada ícone criado 1x).

Mapeamento (Material Design Icons):

| Tipo | MDI | Exemplo |
|---|---|---|
| Diretório | `mdi.folder` | `app/`, `docs/` |
| Python | `mdi.language_python` | `app/main.py` |
| TypeScript | `mdi.language_typescript` | `foo.ts`, `foo.tsx` |
| JavaScript | `mdi.language_javascript` | `foo.js`, `foo.jsx` |
| JSON | `mdi.code_json` | `package.json` |
| Markdown | `mdi.language_markdown` | `README.md` |
| Texto | `mdi.file_document` | `notes.txt` |
| TOML/YAML | `mdi.file_settings` | `pyproject.toml` |
| LICENSE | `mdi.license` | `LICENSE` |
| `.gitignore` | `mdi.git` | `.gitignore` |
| Outros | `mdi.file` | `requirements.txt`, etc. |

### 2.4. ThemeManager

```python
class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"

class ThemeManager:
    def __init__(self, app: QApplication, settings: QSettings) -> None: ...
    def apply(self, theme: Theme) -> None: ...           # carrega QSS + aplica
    def current(self) -> Theme: ...                      # efetivo (resolve SYSTEM → DARK ou LIGHT)
    def detect_system_theme(self) -> Theme: ...         # lê Windows registry
    def toggle(self) -> None: ...                       # cycla DARK → LIGHT → SYSTEM
```

QSettings (built-in PySide6) persiste a escolha do usuário:
- `HKEY_CURRENT_USER\Software\ArchExplorer\ArchExplorer AI\theme`

System detection (Windows 10+):
- Lê `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme`
- `0` = DARK, `1` = LIGHT, ausente = DARK (default)

### 2.5. QSS (dark + light)

Dois arquivos de stylesheet. Cada um estiliza:
- `QMainWindow` background
- `QSplitter::handle` (cor do separador)
- `QTreeView` (background, item hover/selection)
- `QPlainTextEdit` (background, selection)
- `QMenuBar` + `QMenu` (cores consistentes com o tema)
- `QLabel` (cor de texto padrão)

CSS variables não são suportados oficialmente pelo Qt — em vez disso, dois
arquivos `.qss` completos. Cada um ~60-80 linhas.

### 2.6. Menu bar

```
View
├── Theme
│   ├── ● Dark
│   ├── ○ Light
│   └── ○ System (default)
└── (separator)
└── Toggle Theme   Ctrl+Shift+T
```

`●`/`○` indicam seleção atual. Implementado com `QActionGroup` (exclusive).

### 2.7. App icon (temporário)

`assets/app-icon.svg` — letra "A" estilizada num hexágono, em azul/cyan
(mesma família dos gradientes do Mermaid). Versão `.ico` gerada a partir
do SVG (Python `pillow` ou `pyinstaller`-like), com sizes 16/32/48/256.

**Substituível**: o usuário fornecerá um SVG próprio depois; basta
substituir `assets/app-icon.svg` e regenerar o `.ico`.

## 3. Fora do escopo

- Custom fonts (Roboto/Inter/etc.)
- Animações/transitions
- Light/dark para áreas que já são desenhadas pelo Chromium (QWebEngineView)
- Ícones em menus de contexto (mudança futura quando tivermos context menus)
- Splash screen
- Ícones para `.exe`, `.dll`, etc. (raros no contexto de projeto Python)
- Auto-switch com base em horário (day/night)
- Customização granular de cores (color pickers)

## 4. Critérios de aceitação

- [ ] `pip install -r requirements.txt` instala `qtawesome` sem erro
- [ ] Árvore de arquivos mostra ícones MDI distintos para `.py`, `.md`, `.json`, etc. (não mais ícones genéricos do Windows)
- [ ] Cada extensão tem um ícone próprio (verificável visualmente)
- [ ] Pastas usam `mdi.folder`
- [ ] `LICENSE` usa `mdi.license`, `.gitignore` usa `mdi.git`
- [ ] App icon aparece no title bar (e no taskbar do Windows quando `.ico` for gerado)
- [ ] `View > Theme > Dark` aplica tema dark
- [ ] `View > Theme > Light` aplica tema light
- [ ] `View > Theme > System` detecta o tema do Windows
- [ ] `Ctrl+Shift+T` cicla entre Dark → Light → System
- [ ] Preferência do usuário persiste entre execuções (QSettings)
- [ ] Tema dark: fundo escuro, texto claro, seleção visível
- [ ] Tema light: fundo claro, texto escuro, seleção visível
- [ ] `py -m pytest` verde (todos os 157 testes anteriores + novos)
- [ ] Cobertura `app/ui/icons.py` ≥ 90% e `app/ui/theme.py` ≥ 85%
- [ ] Type hints em todas as funções públicas
- [ ] Nenhuma referência a `PyQt6`

## 5. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| `qtawesome` em Windows precisa de `PyQt5` ou `PySide2` ou `PySide6` instalado | Já temos PySide6 6.11 — qtawesome detecta automaticamente |
| QSS pode quebrar algum widget específico (ex: `QFileDialog`) | Mudança só estiliza widgets que **já temos**; dialogs default ficam com tema do SO (aceitável) |
| `QSettings` no Windows grava no registry — usuário pode achar estranho | Documentado no README; standard para Qt apps |
| Detecção de tema do sistema via `winreg` falha em versões antigas do Windows | Fallback: se a chave não existe, assume DARK; o usuário pode escolher manualmente |
| Ícones MDI coloridos podem destoar do tema dark | `qtawesome` aceita cor via parâmetro; usa cor padrão do tema Qt (`QPalette.Text`) para ícones genéricos |
| App icon `.ico` multi-resolution é chato de gerar | Script Python com `Pillow` no `setup` (opcional) ou usar `pyside6-assistant` para gerar do SVG |
| `CustomIconProvider` chamado várias vezes pelo `QFileSystemModel` | Cache interno: 1 `QIcon()` por `(name, ext)` |

## 6. Definição de Pronto

- [ ] 4 artefatos revisados e aprovados
- [ ] Implementação completa, todos os blocos A–H do `tasks.md` marcados
- [ ] `py -m pytest` verde (≥ 170 testes)
- [ ] Cobertura: `app/ui/icons.py` ≥ 90%, `app/ui/theme.py` ≥ 85%
- [ ] Henrique confirma visualmente:
  - Ícones MDI no file tree
  - Theme switcher funciona (dark ↔ light ↔ system)
  - App icon no title bar
  - Preferência persiste após fechar/reabrir o app
- [ ] 1 screenshot de cada tema (dark + light) — opcional mas recomendado
- [ ] Commit no `main` + arquivado

## 7. Rollback

`git revert <commit>` remove o change. UI volta aos ícones do Windows +
tema do sistema. Sem perda de funcionalidade.
