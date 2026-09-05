# Change 004 — Tasks: Custom icons & theme switcher

> Checklist executável. Marcar `[x]` conforme conclusão.

---

## Bloco A — Dependência

- [ ] A1. Adicionar `qtawesome>=1.3` em `pyproject.toml` `[project.dependencies]`
- [ ] A2. Adicionar `qtawesome>=1.3` em `requirements.txt`
- [ ] A3. `pip install qtawesome` (ou `pip install -r requirements.txt`)
- [ ] A4. `python -c "import qtawesome; print(qtawesome.__version__)"` → funciona

## Bloco B — App icon

- [ ] B1. Criar `assets/app-icon.svg` (letra "A" estilizada num hexágono, gradiente cyan)
- [ ] B2. Gerar `assets/app-icon.ico` (multi-resolution 16/32/48/256) — script manual com Pillow
- [ ] B3. `app/main.py` carrega o ícone via `QIcon(str(icon_path))` e chama `app.setWindowIcon(...)`

## Bloco C — CustomIconProvider

- [ ] C1. Criar `app/ui/icons.py` com:
  - Constantes `EXTENSION_ICONS`, `FILENAME_ICONS`, `DEFAULT_FILE_ICON`, `DEFAULT_DIR_ICON`
  - `CustomIconProvider(QFileIconProvider)` com cache interno
  - Override de `icon()` que recebe `QFileInfo` ou `IconType`
  - `set_color(color: str)` para invalidar cache (preparação futura)
- [ ] C2. `app/ui/file_explorer.py` instancia o provider e chama `self._model.setIconProvider(provider)` (ou faz via `MainWindow` injetando)

## Bloco D — Theme

- [ ] D1. Criar `app/ui/theme.py` com:
  - `class Theme(Enum)` com DARK, LIGHT, SYSTEM + `from_string()` / `to_string()`
  - `class ThemeManager` com `__init__`, `current`, `effective`, `apply`, `cycle`, `detect_system_theme`
  - `detect_system_theme` usa `winreg` (com try/except para fallback DARK)
- [ ] D2. Criar `app/ui/qss/dark.qss` (background `#1e1e1e`, texto `#e0e0e0`, etc.)
- [ ] D3. Criar `app/ui/qss/light.qss` (background `#fafafa`, texto `#1e1e1e`, etc.)
- [ ] D4. `app/main.py` instancia `ThemeManager(app)` e chama `theme_manager.apply(theme_manager.current())` antes de criar a janela

## Bloco E — HTML template (light variant)

- [ ] E1. `app/ui/html_template.py` ganha parâmetro `theme: str = "dark"` em `build_html_template(markdown_text, theme)`
- [ ] E2. Quando `theme == "light"`, usa `github-markdown-light` no link CSS
- [ ] E3. `app/ui/visualizer.py` `show_markdown(text, theme="dark")` passa o tema para o template

## Bloco F — MainWindow wiring

- [ ] F1. `app/ui/main_window.py` aceita `theme_manager: ThemeManager | None` no construtor
- [ ] F2. Se `theme_manager is not None`, chama `_build_menu()` que cria o menu `View > Theme > Dark/Light/System` (checkable, com `QActionGroup` exclusive) e o atalho `Ctrl+Shift+T`
- [ ] F3. Conectar ações ao `theme_manager.apply(theme)`
- [ ] F4. No callback de `worker.signals.finished`, passar o tema efetivo para `visualizer.show_markdown(text, theme=...)`
- [ ] F5. Sincronizar o check state do menu quando o tema muda (via signal ou callback)

## Bloco G — Testes

- [ ] G1. `tests/unit/test_icons.py`:
  - `test_provider_returns_qicon_for_file` (10+ extensions via parametrize)
  - `test_provider_returns_qicon_for_directory`
  - `test_provider_caches_icons` (mesma chamada = mesmo QIcon instance)
  - `test_provider_handles_unknown_extension` (fallback para mdi.file)
  - `test_provider_handles_known_filenames` (LICENSE, .gitignore, README.md)
- [ ] G2. `tests/unit/test_theme.py`:
  - `test_theme_enum_string_roundtrip`
  - `test_theme_manager_loads_persisted_preference`
  - `test_theme_manager_defaults_to_system`
  - `test_theme_manager_effective_resolves_system`
  - `test_theme_manager_apply_calls_setstylesheet`
  - `test_theme_manager_cycle_through_all_themes`
  - `test_detect_system_theme_returns_dark_or_light` (mock do winreg)
- [ ] G3. `tests/unit/test_menu.py`:
  - `test_view_menu_has_theme_submenu`
  - `test_theme_submenu_has_dark_light_system_actions`
  - `test_exactly_one_theme_action_is_checked`
  - `test_ctrl_shift_t_shortcut_is_registered`
- [ ] G4. `tests/integration/test_ui_flow.py` (update): verificar que `MainWindow` aceita `theme_manager` e não quebra
- [ ] G5. `py -m pytest` — todos verdes (≥ 170 testes)
- [ ] G6. `py -m pytest --cov=app.ui.icons --cov=app.ui.theme --cov-report=term-missing` — `icons.py` ≥ 90%, `theme.py` ≥ 85%

## Bloco H — Verificações finais

- [ ] H1. `py -m pytest` verde
- [ ] H2. `py -m app.main` (ou `.\run.ps1`) abre:
  - Com ícone "A" no title bar
  - Com ícones MDI no file tree
  - Com menu `View > Theme`
- [ ] H3. Trocar tema via menu → todos os painéis mudam
- [ ] H4. Fechar, reabrir → tema persistido
- [ ] H5. `Ctrl+Shift+T` cicla
- [ ] H6. Screenshot dark + light (opcional mas recomendado)
- [ ] H7. `git status` mostra apenas arquivos do change 004

## Bloco I — Commit + arquivamento

- [ ] I1. `git add .` e revisar
- [ ] I2. `git commit -F .git/COMMIT_EDITMSG.tmp` com mensagem "feat: custom icons (qtawesome) + theme switcher (dark/light/system)"
- [ ] I3. `git log --oneline` → 9+ commits no `main`
- [ ] I4. Mover `changes/004-icons-and-theme/` para `changes/archive/004-icons-and-theme/`
- [ ] I5. Commit `chore: archive change 004`

## Bloco J — Comunicação

- [ ] J1. Reportar pytest verde + novos testes
- [ ] J2. Pedir screenshot dark + light
- [ ] J3. Listar próximos candidates (syntax highlight, edit/save, QSettings para última pasta)

---

## Definition of Done (DoD)

Todos os blocos A–I marcados, H2–H4 confirmados pelo Henrique, J1–J2
reportados. Só então o `TodoWrite` é marcado como completo.
