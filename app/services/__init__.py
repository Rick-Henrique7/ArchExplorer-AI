"""Services layer — file management, AI engine, diagram generation.

The services layer is the application's business logic. It is isolated
from the UI (see ``app/ui/``) and the engine layer (concrete HTTP clients,
filesystem operations, etc.) by Python typing (``Protocol``s) and by
dependency injection at the ``MainWindow`` boundary.
"""

from app.services.ai_engine import (
    AIEngine,
    IAIProvider,
    MockAIProvider,
    OllamaProvider,
)
from app.services.diagram_generator import (
    BaseDiagramRenderer,
    MermaidRenderer,
)
from app.services.exceptions import (
    AIServiceUnavailableError,
    ArchExplorerError,
    DiagramParsingError,
    FileOperationError,
)
from app.services.file_manager import (
    ClipboardMode,
    ClipboardState,
    FileItem,
    FileManager,
)

__all__ = [
    "AIEngine",
    "AIServiceUnavailableError",
    "ArchExplorerError",
    "BaseDiagramRenderer",
    "ClipboardMode",
    "ClipboardState",
    "DiagramParsingError",
    "FileItem",
    "FileManager",
    "FileOperationError",
    "IAIProvider",
    "MermaidRenderer",
    "MockAIProvider",
    "OllamaProvider",
]
