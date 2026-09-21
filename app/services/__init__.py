"""Services layer — file management, AI engine, diagram generation, LPS.

The services layer is the application's business logic. It is isolated
from the UI (see ``app/ui/``) and the engine layer (concrete HTTP clients,
filesystem operations, etc.) by Python typing (``Protocol``s) and by
dependency injection at the ``MainWindow`` boundary.
"""

from app.services.ai_engine import (
    ANALYZE_ARCHITECTURE_PROMPT,
    EDIT_FILE_PROMPT,
    EXTRACT_UML_STRUCTURE_PROMPT,
    GENERATE_COMPONENT_PROMPT,
    SYSTEM_PROMPT,
    AIEngine,
    IAIProvider,
    MockAIProvider,
    OllamaProvider,
)
from app.services.catalog_service import CatalogoService, default_catalog_path, normalize_tags
from app.services.diagram_generator import (
    BaseDiagramRenderer,
    MermaidRenderer,
)
from app.services.exceptions import (
    AIServiceUnavailableError,
    ArchExplorerError,
    CatalogoError,
    DiagramParsingError,
    FileOperationError,
    LlmToolError,
    LpsSpecError,
    LpsValidationError,
)
from app.services.file_manager import (
    ClipboardMode,
    ClipboardState,
    FileItem,
    FileManager,
)
from app.services.filesystem_agent import FileSystemAgent
from app.services.llm_adapter import (
    FILE_TOOLS,
    LlmAdapter,
    LlmResponse,
    LiteLlmAdapter,
    ToolCall,
    run_agent_loop,
)
from app.services.lps_models import (
    FeatureEdge,
    FeatureGroup,
    FeatureModel,
    FeatureNode,
    LpsComponent,
    ProductRun,
)
from app.services.lps_service import LpsService
from app.services.lps_components_seed import (
    list_starter_uuids,
    seed_default_components,
)
from app.services.models import Entry, Tag
from app.services.template_engine import TemplateEngine
from app.services.variability_solver import (
    EncodedModel,
    ValidationResult,
    VariabilitySolver,
)

__all__ = [
    "AIEngine",
    "AIServiceUnavailableError",
    "ANALYZE_ARCHITECTURE_PROMPT",
    "ArchExplorerError",
    "BaseDiagramRenderer",
    "CatalogoError",
    "CatalogoService",
    "ClipboardMode",
    "ClipboardState",
    "DiagramParsingError",
    "EDIT_FILE_PROMPT",
    "EncodedModel",
    "Entry",
    "EXTRACT_UML_STRUCTURE_PROMPT",
    "FILE_TOOLS",
    "FeatureEdge",
    "FeatureGroup",
    "FeatureModel",
    "FeatureNode",
    "FileItem",
    "FileManager",
    "FileOperationError",
    "FileSystemAgent",
    "GENERATE_COMPONENT_PROMPT",
    "IAIProvider",
    "LlmAdapter",
    "LlmResponse",
    "LlmToolError",
    "LiteLlmAdapter",
    "LpsComponent",
    "LpsService",
    "LpsSpecError",
    "LpsValidationError",
    "MermaidRenderer",
    "MockAIProvider",
    "OllamaProvider",
    "ProductRun",
    "SYSTEM_PROMPT",
    "Tag",
    "TemplateEngine",
    "ToolCall",
    "ValidationResult",
    "VariabilitySolver",
    "default_catalog_path",
    "list_starter_uuids",
    "normalize_tags",
    "run_agent_loop",
    "seed_default_components",
]
