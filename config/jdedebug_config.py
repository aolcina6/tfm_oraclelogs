# ------------------------------------------------------------------------------------
# Logs de depuración de JD Edwards EnterpriseOne
# ------------------------------------------------------------------------------------
LOG_TYPE = "jdedebug"
MULTILINE = True
DRAIN_CONFIG = "baseline"
FILENAME_PATTERNS = [
    r'^jdedebug_\d+',        # jdedebug_20260805_1.log
    r'jdedebug[\._-]',       # jdedebug-server.log, jdedebug.log
    r'jdedebug\.log$',       # jdedebug.log
    r'.*_jdedebug_.*', # any_JDEDEBUG_*.log (ej: COV_JDEDEBUG_LOG.log)
]

TIMESTAMP_PATTERNS = [
    # "Jul 15 20:14:45.760727" (mes día hh:mm:ss.microsegundos)
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*\d{1,2}\s*\d{2}:\d{2}:\d{2}\.\d{6}\s*"
]

PATTERNS = {
    # Patrón 0: Solo timestamp (sin más componentes)
    "jdedebug_timestamp_only": r'^(?P<timestamp>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}\d{1,2}\s+\d{2}:\d{2}:\d{2}\.\d{6})$',
    
    # Patrón 1: TAB-separado CON TAB EXTRA
    "jdedebug_tab_separated_extra": r'^(?P<timestamp>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}\d{1,2}\s+\d{2}:\d{2}:\d{2}\.\d{6})\s*\t\s*(?P<component>\S+(?:\s+\S+)?)\s*\t\s*-\s*[\t\s]*(?P<message>.+)$',
    
    # Patrón 2: Con PID/TID
    "jdedebug_pid_tid": r'^(?P<timestamp>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}\d{1,2}\s+\d{2}:\d{2}:\d{2}\.\d{6})\s+-\s+(?P<pid>\d+)/(\d+)\s+(?P<component>\S+)\s+(?P<message>.+)$',
    
    # Patrón 3: TAB-separado SIN TAB EXTRA
    "jdedebug_tab_separated": r'^(?P<timestamp>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}\d{1,2}\s+\d{2}:\d{2}:\d{2}\.\d{6})\s*\t\s*(?P<component>\S+(?:\s+\S+)?)\s*\t\s*-\s+(?P<message>.+)$',
    
    # Patrón 4: FILE.LINE
    "jdedebug_file_line": r'^(?P<timestamp>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}\d{1,2}\s+\d{2}:\d{2}:\d{2}\.\d{6})\s*\t(?P<source_file>\S+)\s*\t\s*-\s+(?P<message>.+)$',
    
    # Patrón 5: Metadatos
    "jdedebug_metadata": r'^(?P<key>PID/PSThread_ID|System Thread ID|Thread Name|CALLSTACK):\s*(?P<value>.*)$',
    
    # Patrón 6: Header del callstack
    "jdedebug_callstack_header": r'^(?P<header>Level\s+Program\s+Library\s+Module\s+Statement\s+Procedure)$',
    
    # Patrón 7: Stack frame
    "jdedebug_stack_frame": r'^(?P<level>\d+)\s+(?P<program>\S+)\s+(?P<library>\S+)\s+(?P<module>\S+)\s+(?P<statement>\S+)(?:\s+(?P<procedure>.+))?$',
    
    # Patrón 8: Continuación multilínea
    "jdedebug_continuation": r'^(?P<message>.+)$',
}

EXTRACTORS = [
     # ===== ERRORES Y EXCEPCIONES =====
    {
        "anchor": "Error",
        "extractor": "error_code",
        "regex": r"Error\s+(?P<error_code>\d{4})",
        "priority": 1
    },
    {
        "anchor": ".c",
        "extractor": "error_source_file",
        "regex": r"(?P<error_source_file>[\w_]+\.c)\s+Line\s+(?P<error_line>\d+)",
        "priority": 1
    },
    {
        "anchor": "failed",
        "extractor": "operation_failed",
        "regex": r"(?P<operation_failed>[\w\s]+)\s+failed",
        "priority": 1
    },
    # ===== IDENTIFICADORES =====
    {
        "anchor": "WRK:",
        "extractor": "username",
        "regex": r"WRK:(?P<username>[A-Z][A-Z0-9]+)_",
        "priority": 2
    },
    # ===== APLICACIONES JDE =====
    {
        "anchor": "_",
        "extractor": "jde_application",
        "regex": [
            r"WRK:[A-Z0-9]+_[A-F0-9]+_(?P<jde_application>[PRP]\d{5,8})",
            r"Application\s+Name.*?\[(?P<jde_application>[PRP]\d{5,8})\]",
        ],
        "priority": 3
    },
        # ===== TABLAS JDE =====
    {
        "anchor": "FROM",
        "extractor": "jde_table",
        "regex": [
            r"FROM\s+[\w.]+\.(?P<jde_table>F\d{2,6}[\w]*)",
            r"Table[:\s]+(?P<jde_table>F\d{2,6}[\w]*)",
        ],
        "priority": 5
    },
    
    # ===== SQL OPERATIONS =====
    {
        "anchor": "SELECT",
        "extractor": "sql_statement_type",
        "regex": r"(?P<sql_statement_type>SELECT|INSERT|UPDATE|DELETE)\s+",
        "priority": 6
    },
]

IGNORE_PATTERNS = [
    r'^\s*$',
    r'^[=\*\-]{5,}\s*$',
    r'.*jdeDebugInit.*',
    r'.*DEBUG\s*INIT.*'
]