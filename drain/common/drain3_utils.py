"""
drain3_utils.py 

Utils para Drain3 (enmascaramiento de logs, configuración de Drain3, etc.)
"""
from typing import List, Dict, Any
import base64 

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.masking import MaskingInstruction
from drain3.persistence_handler import PersistenceHandler

from config.general_config import TIMESTAMP_PATTERNS

# ============================================================
#    PERSISTENCIA 
# ============================================================
class StoragePersistence(PersistenceHandler):
    """
    Handler de persistencia de Drain3 que delega la lectura/escritura del
    estado (blob binario comprimido internamente por Drain3 con zlib) al
    storage backend del proyecto (local o S3).

    Args: 
        storage: Backend de almacenamiento (local o S3).
    
    Returns: 
        None
    """

    def __init__(self, storage, path: str):
        self.storage = storage
        self.path = path

    def load_state(self):
        """
        Carga el estado de Drain3 desde storage (JSON con base64). 
        
        Args:
            None

        Returns:
            bytes: Estado binario de Drain3, o None si no existe.
        """
        if not self.storage.exists(self.path):
            return None
        try:
            data = self.storage.read_json(self.path)
            encoded_state = data.get('state_b64')
            if not encoded_state:
                return None
            return base64.b64decode(encoded_state)
        except Exception as e:
            print(f"  ⚠️  Error cargando estado de Drain3: {e}")
            return None

    def save_state(self, state):
        """
        Guarda el estado de Drain3 en storage (JSON con base64).

        Args:
            state (bytes): Estado binario de Drain3 a guardar.
        
        Returns:
            None
        """
        try:
            encoded_state = base64.b64encode(state).decode('ascii')
            self.storage.write_json(self.path, {'state_b64': encoded_state})
        except Exception as e:
            print(f"  ⚠️  Error guardando estado de Drain3: {e}")

# ============================================================
# CONFIGS DE DRAIN3
# ============================================================
def build_masking_instructions(timestamp_patterns: List[str] = None,
                                include_timestamp: bool = True) -> List[MaskingInstruction]:
    """
    Máscaras COMUNES para Drain3, usadas tanto en logs crudos como en
    mensajes ya parseados. Unifica lo que antes eran dos listas
    divergentes (build_template_miner_config vs build_message_only_config)
    para que ambos paths enmascaren exactamente igual y la comparación
    raw vs parsed en el benchmark sea justa.

    El orden importa: las máscaras más específicas (SQL, códigos JDE,
    UUID, IP...) van ANTES que las genéricas (ALPHANUM, NUM), porque
    Drain3 aplica las instrucciones en orden y una máscara genérica
    aplicada primero puede "romper" el patrón que buscaría una máscara
    más específica después.

    Args:
        timestamp_patterns (List[str]): Patrones de timestamp del origen
            (o los globales de TIMESTAMP_PATTERNS si no se pasan). Solo
            se usan si include_timestamp=True.
        include_timestamp (bool): Si True, añade máscaras de timestamp
            (para logs crudos, que aún tienen timestamp en el texto).
            Si False, se omite (para mensajes ya parseados, donde el
            timestamp ya fue extraído a un campo aparte) — salvo el
            patrón "Time: DD-MON-YYYY HH:MM:SS" que aparece embebido
            dentro del propio mensaje en algunos logs JDE y se mantiene
            siempre.

    Returns:
        List[MaskingInstruction]: Lista de instrucciones de enmascaramiento.
    """
    instructions = []

    if include_timestamp:
        patterns_to_use = timestamp_patterns or TIMESTAMP_PATTERNS
        for pattern in patterns_to_use:
            try:
                instructions.append(MaskingInstruction(pattern, "TIMESTAMP"))
            except Exception as e:
                print(f"  ⚠️  Error compilando timestamp pattern '{pattern[:50]}...': {e}")


    instructions.extend([
        MaskingInstruction(r'(?<=ORCHESTRATION TRACING: )\[.*\]', "ORCH_JSON"),
        MaskingInstruction(
            r'(?s)\b(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|SELECT\s+DISTINCT)\b.*?(?=;|$)',
            "SQL_QUERY_UPPER"
        ),
        MaskingInstruction(
            r'(?s)\b(?:select|insert\s+into|update|delete\s+from|select\s+distinct)\b.*?(?=;|$)',
            "SQL_QUERY_LOWER"
        ),
        MaskingInstruction(
            r'(?s)\b(?:Select|Insert\s+into|Update|Delete\s+from|Select\s+distinct)\b.*?(?=;|$)',
            "SQL_QUERY_CAP"
        ),
        MaskingInstruction(r'\bLIB\d{7}\b', "LIBCODE"),
        MaskingInstruction(r'\b[A-Z]\d{6}\b', "JDECODE"),
        MaskingInstruction(r'\bContext ID:\s*[\d.:]+', "CONTEXT_ID"),
        MaskingInstruction(
            r"Time:\s*\d{2}-[A-Z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2}",
            "TIMESTAMP"
        ),
        MaskingInstruction(
            r'(?s)<[a-zA-Z0-9]+:Envelope\b.*?</[a-zA-Z0-9]+:Envelope>',
            "SOAP_ENVELOPE"
        ),
        MaskingInstruction(
            r'(?s)------=_Part_\d+_\d+\.\d+.*?(?=------=_Part_|\Z)',
            "MIME_PART"
        ),
        MaskingInstruction(r'\b[A-Za-z0-9+/]{40,}={0,2}\b', "BASE64_BLOB"),
        MaskingInstruction(
            r'(?s)\{[^{}]{0,20}"[a-zA-Z_][\w]*"\s*:.*?\}(?=\s|,|$)',
            "JSON_BLOB"
        ),
        MaskingInstruction(
            r'(?s)<([a-zA-Z][\w:-]*)\b[^>]*>.*?</\1>',
            "XML_BLOCK"
        ),
        MaskingInstruction(
            r'(?s)-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----',
            "PEM_BLOCK"
        ),
        MaskingInstruction(
            r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b',
            "JWT"
        ),
        MaskingInstruction(
            r'(?:^\s*at\s+[\w.$]+\([^)]*\)\s*\n?){2,}',
            "STACKTRACE"
        ),
        MaskingInstruction(
            r'(?:^\s*File\s+"[^"]+",\s+line\s+\d+.*\n?){2,}',
            "STACKTRACE"
        ),
        MaskingInstruction(r'\((?:\s*\d+\s*,){5,}\s*\d+\s*\)', "LONG_LIST"),
        MaskingInstruction(r'https?://[^\s"\'<>]+\?[^\s"\'<>]+', "URL_WITH_QUERY"),
    ])

    # --- Máscaras genéricas, comunes a ambos paths ---
    instructions.extend([
        MaskingInstruction(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b', "UUID"),
        MaskingInstruction(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', "IP"),
        MaskingInstruction(r'\b0x[0-9a-fA-F]+\b', "HEX"),
        MaskingInstruction(r'/[\w/.-]+/[\w/.-]+', "PATH"),
        MaskingInstruction(r'\b[A-Za-z_][A-Za-z0-9_]*\d+[A-Za-z0-9_]*\b', "ALPHANUM"),
        MaskingInstruction(r'\b\d{2,}\b', "NUM"),
    ])

    return instructions


def build_template_miner_config(timestamp_patterns: List[str], depth: int, st: float,
                                 max_children: int) -> TemplateMinerConfig:
    """
    Config de Drain3 para LOGS CRUDOS (incluye máscaras de timestamp).

    Args:
        timestamp_patterns (List[str]): Lista de patrones de timestamp a usar.
        depth (int): Profundidad del árbol de Drain3.
        st (float): Umbral de similitud para clustering.
        max_children (int): Máximo número de hijos por nodo.

    Returns:
        TemplateMinerConfig: Configuración de Drain3 lista para usar.
    """
    config = TemplateMinerConfig()
    config.drain_sim_th = st
    config.drain_depth = depth
    config.drain_max_children = max_children
    config.drain_max_clusters = 2048
    config.masking_instructions = build_masking_instructions(
        timestamp_patterns, include_timestamp=True
    )
    config.mask_prefix = "<"
    config.mask_suffix = ">"
    config.profiling_enabled = False
    return config



def build_message_only_config(depth: int, st: float, max_children: int) -> TemplateMinerConfig:
    """
    Config de Drain3 para MENSAJES YA PARSEADOS (sin timestamps/niveles,
    porque ya fueron extraídos por el parseo estructurado previo).

    Usa exactamente el mismo conjunto de máscaras de dominio y genéricas
    que build_template_miner_config (vía build_masking_instructions),
    salvo las máscaras de TIMESTAMP del origen (ya no aplican, el
    timestamp vive en un campo aparte tras el parseo). Mantiene
    extra_delimiters, decisión deliberada para separar mejor campos
    tipo 'clave=valor'/'clave:valor' en mensajes ya extraídos.

    Args:
        depth (int): Profundidad del árbol de Drain3.
        st (float): Umbral de similitud para clustering.
        max_children (int): Máximo número de hijos por nodo.

    Returns:
        TemplateMinerConfig: Configuración de Drain3 lista para usar.
    """
    config = TemplateMinerConfig()
    config.drain_sim_th = st
    config.drain_depth = depth
    config.drain_max_children = max_children
    config.drain_max_clusters = 2048
    config.extra_delimiters = [':', '|', '/', '=', ',', '[', ']', '(', ')']
    config.masking_instructions = build_masking_instructions(include_timestamp=False)
    config.mask_prefix = "<"
    config.mask_suffix = ">"
    config.profiling_enabled = False
    return config
