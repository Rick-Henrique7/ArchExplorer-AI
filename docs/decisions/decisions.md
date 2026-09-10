# Decisões Técnicas do ArchExplorer AI

> Por que cada peça do stack foi escolhida, o que foi rejeitado,
> e os trade-offs que aceitamos. Este documento complementa
> [`docs/visão-geral.md`](../visão-geral.md) (o QUÊ) e
> [`docs/backend/backend.md`](../backend/backend.md) (o COMO).

---

## Filosofia geral

Três princípios nortearam todas as decisões abaixo:

1. **Offline-first.** Nenhum byte do código do usuário sai da máquina.
   Sem telemetria, sem analytics, sem chamada pra API de LLM na
   nuvem. Isso **mata** várias opções (GitHub Copilot, Claude API,
   OpenAI, etc.) mas **garante** privacidade por design.

2. **Baixa fricção de adoção.** Python é a linguagem mais usada
   em times de software segundo todo survey relevante. PySide6 dá
   GUI nativa no Windows sem pedir pro usuário compilar Qt. Ollama
   é um único binário + um `ollama pull`. Cada peça do setup
   precisa ser uma decisão consciente **e justificável**.

3. **Boring tech > clever tech.** Quando duas opções resolvem o
   problema, escolhemos a que tem mais material publicado, mais
   gente usando, e menos surpresas escondidas. O sucesso do
   ArchExplorer AI depende de rodar no PC do Henrique 5 anos
   daqui, não de ser o mais inovador em 2026.

---

## GUI: PySide6 (Qt 6.8+)

### Decisão

Usamos **PySide6 6.8+** como toolkit de GUI.

### Por quê

| Critério               | PySide6                    | Alternativas (rejeitadas)                       |
|------------------------|----------------------------|-------------------------------------------------|
| Licença                | **LGPL** (uso livre, até proprietário) | PyQt6 (GPL comercial confusa)             |
| Bindings               | Oficiais do Qt Project     | PyQt (Riverbank, fork)                          |
| Manutenção             | **Mesma do Qt**            | PyQt (atraso nas releases)                      |
| Instalação Windows     | `pip install PySide6`      | Electron/Tauri (precisa Node/Rust)              |
| Look & feel            | Nativo (Win32, Cocoa, X11) | Tkinter (datado), wxPython (moribundo)          |
| Suporte a HiDPI        | Automático                 | Custom em quase tudo                            |
| Web render embutido    | `QWebEngineView` (Chromium) | `QTextBrowser` (sem JS), `WebKit` (deprecated) |

### O que isso **mata**

- **Impossível distribuir como um único `.exe`.** PySide6 empacota
  ~150 MB de DLLs Qt. Solução: o usuário roda via `python -m app.main`
  ou usa o `run.ps1` que abstrai isso.
- **Primeira inicialização é lenta** (1-2s) por causa do binding
  Python↔C++. Aceitável pra uma IDE desktop.

### Versão específica: Qt 6.8+

Pinned em `pyproject.toml` (`PySide6>=6.8,<7`). O `QWebEngineView`
que usamos pra renderizar o markdown/Mermaid só ficou utilizável
a partir do Qt 6.7, e o 6.8 trouxe correções importantes de
offscreen rendering que importam pros nossos testes (`tests/conftest.py`).

---

## Ícones: qtawesome 1.4 + Material Design Icons

### Decisão

Usamos **qtawesome 1.4** com a coleção **Material Design Icons (MDI)**
como provider de ícones pro file tree.

### Por quê

- **Vetorial** — escala em qualquer DPI sem perda.
- **Font-based** — não precisa de assets binários no repo
  (eram 4 MB de PNGs no projeto anterior).
- **MDI** é a coleção mais completa de ícones relacionados a
  desenvolvimento que existe (cada extensão de linguagem, cada
  arquivo de config, etc. tem ícone dedicado).
- **API simples** — `qta.icon("mdi.folder")` retorna um `QIcon` pronto.

### Nomes com hífen, não underscore

A versão 1.4 do qtawesome (que é a que suporta MDI 7+) **rejeita**
nomes com underscore: `mdi.language_python` lança
`Invalid icon name`. Usamos `mdi.language-python` consistentemente.
Tem teste de regressão em `tests/unit/test_icons.py` pra isso.

### Cores por tema

A primeira versão (Change 004) deixava os ícones na cor padrão do
qtawesome — que é **branca**. No tema light isso deixava pastas
e arquivos invisíveis sobre fundo branco. Adicionamos:

- `THEME_COLORS` no `CustomIconProvider` (dark `#c9d1d9` / light `#24292f`)
- `set_theme(name)` que limpa o cache e re-aplica
- `FileExplorerPanel.apply_theme(theme)` que re-define o icon
  provider no `QFileSystemModel` (que cacheia internamente)

---

## LLM: Ollama + Qwen 2.5 Coder 3B

### Decisão

- **Ollama** como servidor LLM local
- **qwen2.5-coder:3b** como modelo padrão

### Por quê Ollama

- **Um binário** (`ollama pull qwen2.5-coder:3b`) e o servidor
  HTTP já está rodando em `localhost:11434`.
- **API HTTP trivial** (`POST /api/generate`) com um único
  endpoint, JSON, sem streaming obrigatório.
- **Cross-platform** (Windows, macOS, Linux) com o mesmo binário.
- **Alibaba Qwen 2.5 Coder** é Apache 2.0, quantizado em
  4-bit pela Ollama — ~1.9 GB de download.

### Por quê 3B (e não 7B ou 70B)

| Modelo                       | Tamanho  | Velocidade CPU | Qualidade código | Memória RAM |
|------------------------------|----------|----------------|------------------|-------------|
| qwen2.5-coder:1.5b           | 1.0 GB   | **~2s/req**    | razoável         | 4 GB        |
| **qwen2.5-coder:3b**         | 1.9 GB   | **~5-15s/req** | bom              | 8 GB        |
| qwen2.5-coder:7b             | 4.5 GB   | ~30-60s/req    | ótimo            | 16 GB       |
| qwen2.5-coder:14b            | 9 GB     | ~2-3 min/req   | excelente        | 32 GB       |

Escolhemos **3B** como sweet-spot: roda no laptop médio do Henrique
(provavelmente 16 GB de RAM, sem GPU dedicada), resposta em
< 15s, qualidade suficiente pra detectar padrões arquiteturais.

A escolha do modelo é **configurável** — qualquer modelo Ollama
compatível com a API `/api/generate` pode ser passado pro
`OllamaProvider(model="...")`.

### Por que **não** cloud APIs (Copilot, Claude, GPT)

| API                        | Custo/mês (heavy use) | Privacidade        | Latência |
|----------------------------|-----------------------|--------------------|----------|
| OpenAI GPT-4               | $200+                 | ❌ código na nuvem | 1-3s     |
| Anthropic Claude           | $100+                 | ❌ código na nuvem | 1-3s     |
| GitHub Copilot             | $10-19/usuário        | ❌ treina em você  | <1s      |
| **Ollama local**           | **$0**                | ✅ **100% local**  | 5-15s    |

Pra uma ferramenta que promete "olhar seu código", mandar ele
pra uma API externa quebra a promessa. Optamos pelo trade-off
de latência em troca de privacidade.

---

## Renderização: QWebEngineView + marked + Mermaid

### Decisão

O painel direito (visualizer) é um `QWebEngineView` que carrega
HTML com:

- **marked 11.1.1** (markdown → HTML)
- **mermaid 10.9.1** (blocos `mermaid` → SVG/Canvas)
- **github-markdown-css** (estilo visual de issue do GitHub)

Ambos via **jsDelivr CDN** dentro do HTML gerado.

### Por quê Web e não QTextBrowser

| Critério                  | QTextBrowser             | QWebEngineView                |
|---------------------------|--------------------------|-------------------------------|
| Markdown                  | Precisa de lib externa   | ✅ nativo (marked)            |
| Mermaid / SVG             | ❌ sem JS                 | ✅ Chromium completo          |
| Code highlighting         | Limited                  | ✅ com Prism.js / hl.js       |
| Look & feel               | Desktop plain            | Idêntico ao GitHub            |
| Performance               | Rápido                   | ~50ms pra renderizar          |

A primeira versão (Change 003) tentou `QTextBrowser` + uma lib
de markdown caseira. O resultado era monstro, sem syntax
highlighting, sem diagramas. Trocar pra `QWebEngineView` foi
o divisor de águas do projeto — literalmente permitiu o Mermaid
funcionar.

### Custo

- ~200 MB de RAM por instância (Chromium embed).
- Primeira renderização ~200ms (cold start do Chromium).
- O `QWebEngineView` **não renderiza em offscreen mode** durante
  os testes — eles verificam o `last_markdown` exposto pelo
  panel sem inspecionar a página web.

---

## Persistência: QSettings (built-in do Qt)

### Decisão

Usamos `QSettings()` (registro no Windows, plist no macOS,
INI no Linux) para guardar a **pasta raiz** entre execuções.

### Por quê

- **Zero código de boilerplate.** Sem schema, sem migrations,
  sem dependência. `QSettings().setValue("workspace/root_dir", path)`
  e `QSettings().value("workspace/root_dir", "")` em 2 linhas.
- **Já é onde o Qt guarda state** (tamanho/janela, geometria
  dos splitters se quiséssemos). Unificar tudo no mesmo lugar
  é consistente.
- **Plataforma-correto automaticamente** — Windows usa o
  registro (`HKCU\Software\ArchExplorer\ArchExplorer AI\`),
  macOS usa ~/Library/Preferences, Linux usa ~/.config.

### Onde guardar o que

| Chave                         | Conteúdo              |
|-------------------------------|-----------------------|
| `workspace/root_dir`          | Última pasta aberta   |
| `theme`                       | `dark` / `light` / `system` |
| *(futuro: splitter sizes)*    | Tamanhos dos painéis  |
| *(futuro: window geometry)*   | Posição/tamanho da janela |

### Por que **não** um JSON em disco

- Windows users têm a expectativa de ver suas configs no
  `regedit`. Um `~/.archexplorer.json` esconde e parece "outro
  arquivo pra deletar quando algo dá errado".
- `QSettings` lida com platform paths (AppData no Windows,
  XDG_CONFIG_HOME no Linux) sem o nosso código ter que saber.

---

## Threading: QRunnable + QThreadPool

### Decisão

Toda chamada de IA roda num `QRunnable` agendado no
`QThreadPool.globalInstance()`. Três workers hoje:

- `AnalysisWorker` (analisa arquivo)
- `AIEditWorker` (edita arquivo com preview)
- `ChatWorker` (chat livre)

Cada um tem um companion `_WorkerSignals(QObject)` para emitir
`finished(str)` / `failed(str)` porque `QRunnable` não é
`QObject` e não pode declarar signals.

### Por quê QRunnable e não QThread

| Critério                  | QThread (subclass)         | QRunnable + QThreadPool    |
|---------------------------|----------------------------|----------------------------|
| Boilerplate               | Muito                      | Mínimo                     |
| Pool automático           | ❌ manual                   | ✅ built-in                |
| Cancelamento              | Manual                     | Manual                     |
| Reuso                     | ❌ uma vez só               | ✅ automático              |
| Signal/Slot cross-thread  | Manual                     | ✅ automático               |

`QThread` foi feito pra **loops longos** (timers, sockets).
Pra **tarefas one-shot** como chamar uma API, `QRunnable + Pool`
é 1/3 do código e o pool se vira com o paralelismo.

### Gotcha que virou teste de regressão

`QWebEngineView` e `QFileSystemModel` **não funcionam em
thread de pool** (precisam estar na main thread). Workers só
chamam o LLM e emitem signal; o slot que atualiza a UI roda
na main thread automaticamente (queued connection). Tem
teste explícito em `tests/unit/test_analysis_worker.py` que
valida essa separação.

---

## Provider Pattern: `Protocol` (structural) e não `ABC`

### Decisão

`IAIProvider` e `BaseDiagramRenderer` são `typing.Protocol`,
não `abc.ABC`. Qualquer classe com o método certo **é** o
provider, sem herança.

```python
class IAIProvider(Protocol):
    def generate(self, prompt, *, system=None, temperature=None) -> str: ...

class MockAIProvider:        # não herda de ninguém
    def generate(self, prompt, *, system=None, temperature=None) -> str:
        return "fixture"
```

### Por quê Protocol

- **Duck typing ganha.** Posso passar uma `lambda` (em testes)
  sem ter que criar uma subclasse de `MockAIProvider` que
  herda de `ABC` só pra ter 1 método.
- **Mypy valida o LSP** automaticamente: se o método muda
  de assinatura, mypy reclama em **todos** os call sites.
- **Zero acoplamento em tempo de execução.** Não tem metaclass
  ou `register()`.

### Por que não ABC

- Força herança, que em Python é raro e cada vez mais desaconselhado.
- `issubclass()` checks viram armadilhas em mock objects.
- Adiciona `abc.ABCMeta` que complica type narrowing.

A `tests/unit/test_ai_engine.py` tem um teste
(`test_mock_satisfies_iai_provider_protocol`) que valida
que o `MockAIProvider` satisfaz o Protocol mesmo sem herança.

---

## Workers: o pattern `_WorkerSignals` companion

### Decisão

Cada worker tem um `_WorkerSignals(QObject)` como atributo:

```python
class _WorkerSignals(QObject):
    finished = Signal(str)
    failed = Signal(str)

class AnalysisWorker(QRunnable):
    def __init__(self, ...):
        super().__init__()
        self.signals = _WorkerSignals()
```

### Por quê

`QRunnable.run()` não roda num `QObject` (é só uma `run()` em
qualquer thread). Pra emitir signals cross-thread, **precisa**
de um `QObject` companion. Esse é o pattern documentado pela
própria Qt.

### Gotcha PySide6: closures NÃO funcionam cross-thread

`worker.signals.finished.connect(lambda r, um=user_msg: ...)` —
isso **parece** funcionar mas o slot nunca é chamado em testes
de integração, porque PySide6 tem um bug sutil com closures
que capturam default-args em conexões cross-thread.

A solução (depois de perder 30 min debugando):

```python
# ❌ Não funciona cross-thread
worker.signals.finished.connect(
    lambda r, um=user_msg: self._handle(um, r)
)

# ✅ Funciona: bound method na main window
worker.signals.finished.connect(self._handle_chat_response)
# A main window stasheia o user_msg em self antes de startar o worker
```

Tem teste de regressão disso em `tests/integration/test_chat_sends_message.py`.

---

## Cache de análises: SHA-1 do conteúdo + LRU

### Decisão

`MainWindow._analysis_cache: dict[path, tuple[sha1, markdown]]`,
LRU cap 32. Invalidação:

- `Ctrl+S` no editor → `file_saved` signal → pop do cache
- AI-edit aplicado → conteúdo mudou → pop do cache
- LRU eviction quando passa de 32 entradas

### Por quê SHA-1 e não mtime

- `mtime` muda com `git checkout`, `cp`, downloads. SHA-1 do
  conteúdo só muda quando o **conteúdo** muda.
- Já tínhamos `hashlib` na stdlib, sem dependência nova.

### Por que LRU 32

- Trade-off entre memória (~50 KB por análise) e utilidade.
  32 arquivos = um projeto pequeno típico. Maior que isso
  e a maioria das entradas é fria.

### O que **não** cacheamos

- **Chat** — é conversacional, não tem sentido reusar.
- **UML extraction** — não está exposto na UI ainda (Change futuro).

---

## Testes: pytest + Protocol mocks + `qtawesome` offscreen

### Decisão

- **pytest 8** como runner (não unittest)
- **requests-mock** pra mockar Ollama HTTP
- **MockAIProvider** como mock default da `IAIProvider`
- **QT_QPA_PLATFORM=offscreen** em `tests/conftest.py` pra rodar
  PySide6 em CI sem display

### Por que pytest

- Output legível, fixtures reutilizáveis, parametrização nativa.
- `pytest-cov` dá relatório de cobertura por linha em HTML.
- 100% da comunidade Python usa.

### Por que `QT_QPA_PLATFORM=offscreen`

Permite que 200+ testes de UI rodem em **CI Linux sem display**.
Os 2 testes que pulamos (`test_ai_ollama_live.py`) precisam
do Ollama rodando de verdade e são marcados com `pytest.mark.integration`.

### Por que NÃO unittest

- Mais boilerplate, fixtures menos ergonômicas, sem parametrize.
- Unittest.mock funciona, mas o pattern `with patch(...)` é
  mais verboso que injetar via construtor (DI).

---

## Workflow: SDD + trunk-based + conventional commits

### Decisão

3 camadas sobrepostas:

1. **Spec-Driven Development (SDD)** — toda mudança (feature,
   fix grande, refactor) vira `changes/NNN-name/{proposal,spec,design,tasks}.md`.
   Após merge, vai pra `changes/archive/`.

2. **Trunk-based** — branch curta `00X-name` → PR → squash → merge em `main`.
   Sem `develop`, sem `release/*`, sem long-lived branches.

3. **Conventional commits** — `feat:`, `fix:`, `refactor:`, `docs:`,
   `test:`, `chore:`. Cada commit conta uma história.

### Por que SDD

- Força pensar **antes** de codar (a proposal pergunta "por quê?").
- O `tasks.md` é checklist executável — se está tudo `[x]`,
  a feature está pronta.
- O histórico em `changes/archive/` vira **documentação viva**
  de como o projeto evoluiu.

### Por que trunk-based (e não GitFlow)

- Projeto tem 1 dev (você). GitFlow foi feito pra times com
  10+ devs e múltiplas releases paralelas. Overhead puro aqui.
- Trunk-based = merge conflicts raros, "main is always shippable",
  CI roda em cada push.

### Por que conventional commits

- `git log --oneline` filtrável por tipo (`git log --grep="^fix:"`).
- CHANGELOG.md auto-gerável via `conventional-changelog`.
- GitHub release notes automáticas.

---

## Convenções de idioma

### Decisão

- **UI / strings visíveis:** Português (pt-BR) — "Salvar", "Editar com IA", "Análise", etc.
- **Prompts da IA:** Português com `SYSTEM_PROMPT` forçando pt-BR
- **Código / identificadores / CLI / mensagens de log:** Inglês
- **Docs:** Português (consistente com o resto do projeto)
- **Comentários em código:** Inglês (são meta, não UI)
- **Commits:** Inglês (padrão da indústria, melhor tooling)

### Por que

- O usuário é brasileiro, fala português. UI em inglês é barreira.
- Código em inglês é o **padrão da indústria Python** — `requests`,
  `qtawesome`, `pytest` etc. são todos em inglês. Misturar
  português em identificadores (`criar_pasta` ao lado de
  `create_file`) cria inconsistência que atrapalha.
- Prompts em pt-BR são essenciais: o Qwen 2.5 Coder **espelha**
  o idioma do input. Sem o `SYSTEM_PROMPT`, digitar "olá" em
  pt-BR resulta em resposta em pt-BR (bom), mas digitar "hello"
  em inglês resulta em resposta em inglês (ruim pra consistência).

---

## Decisões de UX que viraram código

### Análise manual (não automática)

**Decisão:** clicar num arquivo abre no editor mas **não** chama
a IA automaticamente. O usuário clica num botão **Analisar**
dedicado.

**Por que:** em iteração inicial a análise era auto-triggered.
Feedback: era barulhento (toda seleção de arquivo virava 5-15s
de espera), e o usuário perdia controle. Mudar pra manual
deu ao usuário a decisão de "esse arquivo vale análise?".

### Cache com hash de conteúdo

**Decisão:** voltar num arquivo já analisado é instantâneo,
sem chamar a IA.

**Por que:** análise boa custa tempo e tokens. 80% das vezes
o usuário volta num arquivo que ele já viu — não faz sentido
re-analisar. O cache invalida em `Ctrl+S` (mudou) e em
AI-edit aplicado (mudou).

### Tema escuro/claro com switcher

**Decisão:** `Ctrl+Shift+T` alterna dark/light/system,
e a escolha persiste entre execuções via QSettings.

**Por que:** o dev trabalha 14h/dia no PC. Cansaço ocular
muda. Light mode de manhã, dark mode à noite. "Sistema"
segue o Windows (que detecta sunrise/sunset em alguns casos).

### Resposta da IA em PT-BR forçada

**Decisão:** `SYSTEM_PROMPT` enviado em **toda** chamada diz
"Responda SEMPRE em português brasileiro, mesmo que a pergunta
esteja em outro idioma".

**Por que:** sem isso, digitar "hello" no chat gerava resposta
em inglês. Com o system prompt, a IA sempre responde em PT,
mantendo consistência com a UI.

---

## Anti-decisões: o que NÃO fazer e por quê

### ❌ Auto-instalar dependências

O `run.ps1` checa se o venv existe, mas **não** roda
`winget install Ollama.Ollama` automaticamente.

**Por que:** instalar software no PC do usuário sem
permissão explícita é a fronteira entre "ferramenta útil"
e "malware chato". O README instrui o passo a passo.

### ❌ Cloud APIs como fallback

Quando o Ollama não responde, **não** tentamos Claude/GPT
como fallback.

**Por que:** quebra a promessa de privacidade. O usuário
escolheu rodar local; a ferramenta respeita isso mesmo
quando está inconveniência.

### ❌ Streaming de tokens

A chamada `OllamaProvider.generate()` espera a resposta
inteira (sem `stream=True`).

**Por que:** a primeira versão com streaming complicou
bastante a UX (tokens aparecendo, scroll pulando, cache
mais difícil). Para a primeira release, resposta única
é mais simples e o cache funciona direto.

(Streaming está no roadmap — Change futuro.)

### ❌ Syntax highlight no editor

`QPlainTextEdit` sem highlight por enquanto.

**Por que:** as opções eram (a) `QScintilla` (binding
PyQt5/PySide6 meio abandonado, fork frágil) ou (b) Pygments
em `QSyntaxHighlighter` (funciona mas custa tempo de
desenvolvimento que pode ir pra features mais valiosas).

(No roadmap também.)

### ❌ GitFlow / release branches

Trunk-based. O `main` é sempre deployable.

**Por que:** projeto tem 1 dev. GitFlow é ceremony.

### ❌ Migration framework pro schema

Sem banco de dados. Configuração é `QSettings` com chaves
de string. Adicionar Alembic/SQLAlchemy pra gerenciar
schema de "uma chave de string" seria over-engineering.

---

## Resumo: tech radar

| Categoria   | Adotado                          | Rejeitado                          |
|-------------|----------------------------------|------------------------------------|
| GUI         | PySide6 6.8+                     | PyQt6, Electron, Tauri, Tkinter    |
| Ícones      | qtawesome + MDI (hífen)          | PNGs no repo, Iconify              |
| LLM         | Ollama + Qwen 2.5 Coder 3B       | OpenAI, Claude, Copilot, llama.cpp |
| HTTP        | requests 2.32                    | httpx, urllib3, aiohttp            |
| Markdown    | marked via CDN                   | mistune, markdown-it (local)       |
| Diagramas   | Mermaid.js via CDN               | PlantUML, Graphviz (server-side)   |
| Persistência| QSettings (registro/INI/plist)   | JSON, SQLite, TOML                 |
| Threading   | QRunnable + QThreadPool          | QThread, asyncio, threading        |
| Tipo        | typing.Protocol                  | abc.ABC, mixins                    |
| Teste       | pytest + requests-mock           | unittest, hypothesis              |
| GUI tests   | QT_QPA_PLATFORM=offscreen        | xvfb, Xvnc, Cypress               |
| Workflow    | SDD + trunk-based + conv. commits| GitFlow, GitHub Flow              |
| Versão      | Semver manual + git tags         | setuptools_scm, bump2version      |
| Idioma UI   | PT-BR (com SYSTEM_PROMPT)        | EN, i18n framework                |
| Idioma code | EN                              | PT-BR, mix                         |

---

## Referências

- [PySide6 docs](https://doc.qt.io/qtforpython-6/) — referência Qt
- [Qwen 2.5 Coder](https://ollama.com/library/qwen2.5-coder) — modelo
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md) — endpoint
- [Material Design Icons](https://materialdesignicons.com/) — coleção
- [qtawesome](https://github.com/spyder-ide/qtawesome) — binding
- [Trunk-based development](https://trunkbaseddevelopment.com/) — estratégia
- [Conventional Commits](https://www.conventionalcommits.org/) — formato

> Última atualização: Change 005 (interactive features) + hotfix
> 6-em-1 (PT-BR, cache, manual, contraste) — setembro 2026.
