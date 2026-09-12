# Catálogo Pessoal — Como Usar

> Disponível a partir do **Change 006**. Este é o "second brain" local
> da ArchExplorer AI: um banco SQLite (`catalogo.db`) onde você guarda
> soluções, padrões e trechos de código que quer consultar mais tarde.

---

## O que é o catálogo?

Diferente do **Projeto** (modo Explorer, à esquerda), que mostra o
diretório atual de trabalho, o **Catálogo** mostra uma base *pessoal*
de soluções: snippets, padrões, "receitas" que você acumulou ao longo
de anos. Ele vive no seu próprio `catalogo.db`, em
`~/Documents/ArchExplorer/`, e existe independentemente de qual pasta
você esteja explorando.

A ideia é simples: você está trabalhando num problema, abre o catálogo,
busca "LRU" e acha o snippet que escreveu em 2023. Clica em
**Inserir no editor** e ele aparece no arquivo atual.

## Como abrir

1. Menu `View > Painel esquerdo > Catálogo` ou `Ctrl+2`.
2. A coluna da esquerda vira a lista de entries; a coluna da direita
   mostra a preview da entry selecionada.
3. `Ctrl+1` volta para o Explorer.

O modo é persistido entre execuções (escrito em `QSettings`).

## Criar uma entry

1. Clique em **+Nova** (no topo da coluna do catálogo).
2. Preencha:
   - **Título** (obrigatório, até 200 caracteres).
   - **Linguagem** (combobox editável — escolha ou digite).
   - **Categoria** (opcional — `patterns`, `algorithms`, `utils`, etc.).
   - **Tags** (separadas por vírgula — viram lowercase e dedup automático).
   - **Descrição** (markdown livre — fica renderizada na preview).
   - **Código** (obrigatório — o snippet em si).
   - **Origem** (opcional — caminho:linha de onde veio).
   - **Pública** (checkbox — entra no export JSON).
3. **Salvar**. A entry aparece na lista e na preview à direita.

## Buscar

- Digite na caixa de busca — o filtro aplica com debounce de 200 ms.
- A busca usa **SQLite FTS5** com prefix-match (`term*`): digitar
  `cach` acha `cache`, `cached`, `caching`.
- Combos à direita da busca filtram por **categoria** e **linguagem**.
- Os filtros resetam para "Todas" ao reabrir o app.

## Editar e excluir

- Selecione uma entry na lista → **Editar** (ou clique no botão na preview).
- O mesmo formulário abre, preenchido. Mude o que quiser e salve.
- **Excluir** pede confirmação (Yes/No). É permanente — não há lixeira.

## Inserir no editor

1. Selecione uma entry.
2. Clique em **Inserir no editor**.
3. Se nenhum arquivo estiver aberto, o app mostra um aviso em vez de
   descartar a ação silenciosamente.
4. Com um arquivo aberto, o código é colado **na posição do cursor**
   (não substitui o conteúdo). O app volta automaticamente para o
   modo Explorer (`Ctrl+1`) para você ver o que foi inserido.
5. O arquivo vira `dirty` — `Ctrl+S` salva.

## Onde fica o banco?

```
%USERPROFILE%\Documents\ArchExplorer\catalogo.db
```

No Linux/macOS: `~/Documents/ArchExplorer/catalogo.db`.

### Trocar a localização

Precedência (maior para menor):

1. **CLI**: `python -m app.main --catalog-db C:/caminho/db.db`
2. **Env var**: `ARCHEXPLORER_CATALOG_DB=C:/caminho/db.db python -m app.main`
3. **QSettings**: chave `catalog/db_path` em
   `HKCU\Software\ArchExplorer\ArchExplorer AI\` (Windows) ou
   `~/.config/ArchExplorer/ArchExplorer AI.conf` (Linux).
4. **Default**: `~/Documents/ArchExplorer/catalogo.db`.

### Backup automático

Se o `catalogo.db` estiver corrompido na abertura, o serviço renomeia
o arquivo existente para `catalogo.db.bak` (preservando os dados para
recuperação manual) e cria um banco novo. A operação é silenciosa mas
lançada como `CatalogoError` com `backup=<caminho>`.

## Importar / Exportar

Hoje o `CatalogoService` tem `export_json()` e `import_json(payload)`.
A UI ainda não expõe botões para isso — o usuário acessa via
`python -c "from app.services import CatalogoService; print(CatalogoService().export_json())"`
ou via um script próprio. **Change 007** deve adicionar botões
`Exportar` / `Importar` na toolbar.

Formato JSON:

```json
{
  "version": 1,
  "exported_at": "2026-09-12T17:00:00+00:00",
  "entries": [
    {
      "id": 1,
      "title": "LRU cache",
      "code": "...",
      "language": "python",
      "description": "...",
      "category": "data-structures",
      "origin_path": "src/cache.py",
      "origin_line": 42,
      "is_public": false,
      "created_at": "2026-09-12T17:00:00+00:00",
      "updated_at": "2026-09-12T17:00:00+00:00",
      "tags": ["cache", "lru"]
    }
  ]
}
```

## Limites e validação

- **Título**: 1–200 caracteres.
- **Código**: 1–100.000 caracteres.
- **Descrição**: 0–10.000 caracteres.
- **Linguagem**: 1–30 caracteres.
- **Categoria**: 0–50 caracteres.
- **Tags**: até 20, lowercase, dedup, regex `^[a-z0-9_.-]{1,30}$`.
- **Origem linha**: ≥ 1.

Entries inválidas são rejeitadas com `CatalogoError("...",
length=..., max_length=...)`.

## Roadmap (changes futuras)

- **Change 007**: botões Exportar/Importar na toolbar; gist sync;
  drag-and-drop de arquivos para o catálogo.
- **Change 008**: syntax highlight no editor de código da preview;
  RAG sobre o catálogo para o chat do visualizador.
- **Change 009**: empacotamento `.exe` (PyInstaller + Inno Setup).
