# Change 005 — Interactive features (chat, editor, toolbar, polish)

> **Status:** Aguardando aprovação
> **Tipo:** Feature (5 sub-seções)
> **Risco:** Médio-Alto (write-to-disk no editor, multi-feature, QSS em vários pontos)
> **Pré-requisito externo:** Ollama rodando ✅

---

## 1. Contexto

O app está visual e funcionalmente completo (001–004), mas falta
**interatividade real**:
- Não dá pra conversar com a IA — só uma análise one-shot por clique
- O editor é read-only — usuário não consegue salvar mudanças
- Não há como criar pasta ou trocar a raiz do tree pela UI
- O tema light tem pastas quase invisíveis (QSS bug)
- Falta polish visual (padding)

O screenshot que motivou este change mostra exatamente esses gaps
no contexto do app em uso real (analisando `visão-geral.md`).

## 2. Mudança (5 sub-seções)

### 2.1. Chat com IA no painel direito

Adicionar caixa de texto + histórico de conversa ao `VisualizerPanel`:

- **`QTextEdit` no rodapé** do painel, multi-line, com botão "Send"
- Histórico de mensagens: lista de `(user_text, ai_response)` pairs
- Ao clicar num item do histórico, a resposta re-renderiza
- Contexto enviado pra IA: caminho do arquivo + conteúdo do arquivo (se carregado) + mensagem do user
- Resposta: markdown renderizado no topo (substitui o atual)
- `Enter` envia, `Shift+Enter` insere newline

### 2.2. Animação de loading

Substituir o placeholder estático "Analyzing..." por spinner animado:
- CSS `@keyframes` spin com 8 pontos (dot rotativo) em 1.2s loop
- Renderizado como SVG inline (zero dependência extra)
- Aparece no centro do visualizer enquanto worker está rodando
- Some quando `finished` ou `failed` é emitido

### 2.3. Editor editável (Save, Undo, AI-edit com autorização)

Transformar o `CodeEditorPanel` de read-only para editável com 3 features:

- **Save** (`Ctrl+S` ou botão): escreve o conteúdo de volta ao arquivo via
  `FileManager.write_file` (novo método)
- **Undo/Redo**: já vem grátis do `QPlainTextEdit` (built-in `Ctrl+Z` /
  `Ctrl+Y`), só precisa expor ação na toolbar
- **AI-edit com autorização**:
  - Botão "Edit with AI" no header do editor
  - Modal/dialog pede confirmação + campo opcional de instrução
  - Worker gera novo conteúdo do arquivo (pipeline `edit_file` novo na `AIEngine`)
  - Preview mostra diff ou novo conteúdo
  - "Apply" sobrescreve o arquivo (com `FileManager.write_file`)
  - "Cancel" descarta

  Se o usuário não autorizar, a IA faz só a análise atual (não mexe no arquivo).

### 2.4. Toolbar do FileExplorer

Adicionar toolbar horizontal no topo do `FileExplorerPanel` com 3 ações:

- **Select Folder** (`Ctrl+O`): abre `QFileDialog.getExistingDirectory`,
  troca a raiz do tree, persiste em `QSettings` (key=`root_dir`)
- **New Folder** (`Ctrl+Shift+N`): input inline (overlay) que aparece
  abaixo da toolbar, usuário digita o nome, Enter cria via
  `FileManager.create_folder` e fecha o input
- **Refresh** (`F5`): re-escaneia o `QFileSystemModel`

A raiz do tree passa a vir do QSettings (com fallback para `cwd`)
quando o painel é instanciado pelo `MainWindow`.

### 2.5. Polish QSS (theme light fix + padding)

- **Bug fix**: `QTreeView::branch` em `light.qss` está com cor muito clara
  (`#d0d0d0` sobre `#ffffff` = contraste 1.1:1). Mudar para `#a0a0a0` (3:1)
- **Padding**: `QTreeView`, `QPlainTextEdit`, `QWebEngineView` ganham
  `padding: 4px` interno (não confundir com margem externa) — 6 LOC no QSS

## 3. Fora de escopo

- Streaming de tokens do Ollama (não-streaming é suficiente)
- Syntax highlighting (próprio change)
- Múltiplas abas / split view
- File watcher (auto-reload)
- Drag-and-drop
- Busca dentro do arquivo (Ctrl+F)
- Atalhos de teclado completos (só os 3 acima)
- Conflitos em edição concorrente (não há concorrência)
- Undo/Redo visual (menu Edit com undo/redo) — vai entrar com QAction

## 4. Critérios de aceitação

- [ ] Painel direito tem input de chat no rodapé; Enter envia
- [ ] Histórico de conversas persiste na sessão (não entre execuções)
- [ ] Spinner animado aparece enquanto IA processa
- [ ] Editor é editável; `Ctrl+S` salva; arquivo no disco é atualizado
- [ ] Botão "Edit with AI" abre dialog de confirmação; IA reescreve o arquivo
  com base no conteúdo + instrução do user; preview antes de aplicar
- [ ] Toolbar do tree tem 3 botões: Select Folder, New Folder, Refresh
- [ ] Select Folder persiste em QSettings; raiz do tree muda
- [ ] New Folder tem input inline que aparece; Enter cria; Esc cancela
- [ ] Tema light: pastas do tree visíveis com contraste ≥ 3:1
- [ ] Padding interno nos 3 painéis
- [ ] `py -m pytest` verde (≥ 245 tests)
- [ ] Cobertura `app/ui/` ≥ 85% (mantida)
- [ ] Nenhuma regressão: smoke test do end-to-end (click → análise → save → re-load) funciona

## 5. Riscos

| Risco | Mitigação |
|---|---|
| Save sobrescreve o arquivo sem warning se disco cheio | `write_text` levanta OSError → caught → `show_error` no visualizer |
| AI-edit produz código inválido que quebra o syntax | Preview antes de aplicar; usuário pode cancelar; nunca silencioso |
| QSettings corrompido (root_dir inválido) | Try/except em `__init__`; fallback para `cwd` |
| Chat cresce sem limite, consome RAM | Cap em 50 mensagens por sessão (LRU); botão "Clear" |
| Spinner trava o event loop | Usa CSS animation (não bloqueia) |
| User recarrega enquanto worker roda | Worker cancelado via flag; UI mostra "cancelled" |
| `Ctrl+S` no QPlainTextEdit é nativo — pode conflitar com futura hotkey | Documentado; behavior nativo é OK |

## 6. Definition of Done

- [ ] 4 artefatos revisados
- [ ] Todos os blocos A–H do tasks.md marcados
- [ ] pytest verde
- [ ] Smoke test do save + AI-edit + chat + create folder manuais
- [ ] Commit + arquivado

## 7. Rollback

`git revert <commit>` desfaz tudo. Services e UI do 004 permanecem
funcionais; a janela volta a abrir com o comportamento read-only e
sem chat/toolbar.
