# ------------------------------------------------------------------------------------
# Enterprise Server / kernel de JDE EnterpriseOne 
# Pendiente clasificar logs HTML. 
# ------------------------------------------------------------------------------------
LOG_TYPE = "e1root"
MULTILINE = True
DRAIN_CONFIG = "baseline"
FILENAME_PATTERNS = [
    r'^e1root_.*',        # e1root_20260805_1.log
    r'^.*_html_log.*',        # COV_HTML_LOG.log
    r'^.*_e1root_.*',        # any_e1root_*.log
    r'^jderoot_\d+', # jderoot_20260805_1.log 
    r'^.*_jderoot_.*', # any_JDEROOT_*.log (ej: COV_JDEROOT_LOG.log)
]

TIMESTAMP_PATTERNS = [
    # "03 Aug 2026 10:16:39,059" (día mes año hora:minuto:segundo,milisegundos) - INGLÉS
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s+\d{2}:\d{2}:\d{2}[,.]\d{3}",

    # "27 jul 2026 07:28:13,046" (día mes año hora:minuto:segundo,milisegundos) - ESPAÑOL
    r"\d{1,2}\s+(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\s+\d{4}\s+\d{2}:\d{2}:\d{2}[,.]\d{3}",
]


PATTERNS = {
    # Formato: "07 Aug 2026 15:01:04,413 [MANDATORY] USER  - [JAS]             message"
    "e1root_with_user": r'(?P<timestamp>\d{2}\s+\w+\s+\d{4}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(?P<level>\w+)\s*\]\s+(?P<user>[A-Z0-9_-]+)\s+-\s+\[(?P<component>[^\]]+)\]\s*(?P<message>.*)',
    
    # Formato: "07 Aug 2026 15:01:04,413 [MANDATORY]  - [12345][JAS]             message"
    "e1root_with_pid": r'(?P<timestamp>\d{2}\s+\w+\s+\d{4}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(?P<level>\w+)\s*\]\s+-\s+\[(?P<process_id>\d+)\]\[(?P<component>[^\]]+)\]\s*(?P<message>.*)',
    
    # Formato: "07 Aug 2026 15:01:04,413 [MANDATORY]  - [JAS]             message"
    "e1root_simple": r'(?P<timestamp>\d{2}\s+\w+\s+\d{4}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(?P<level>\w+)\s*\]\s*-\s+\[(?P<component>[^\]]+)\]\s*(?P<message>.*)'
}

EXTRACTORS = [
    # {
    #     "anchor": "Process",
    #     "extractor": "process_id",
    #     "regex": r"\[(?P<process_id>\d+)\]"
    # },
    # {
    #     "anchor": "RUNTIME",
    #     "extractor": "runtime_component",
    #     "regex": r"\[(?P<component>RUNTIME|KERNEL|MANAGER|REPOSITORY|SECURITY|WORKFLOW|FORMS|REPORTS|BI|ORCHESTRATOR|INTEROP|BSFN|UBE)\]"
    # },
    # {
    #     "anchor": "thread",
    #     "extractor": "thread_action",
    #     "regex": r"(?P<action>starting|stoping|stopped)"
    # },
    # ===== USUARIOS =====
    {
        "anchor": "User",
        "extractor": "user",
        "regex": [
            r"user:+(?P<username>[A-Z0-9_-]+)"
        ]
    },
    {
        "anchor": "Service",
        "extractor": "service_name",
        "regex": [
            r"Service[:\s]+(?P<service_name>[\w.-]+)",
            r"Starting service\s+(?P<service_name>[\w.-]+)",
            r"Stopping service\s+(?P<service_name>[\w.-]+)"
        ]
    },
    # # ===== APLICACIONES JDE (UBE/BSFN) =====
    # {
    #     "anchor": "UBE",
    #     "extractor": "jde_application",
    #     "regex": [
    #         r"UBE[:\s]+(?P<jde_application>[RP]\d{6,8})",
    #         r"Application[:\s]+(?P<jde_application>[RP]\d{6,8})",
    #         r"\[(?P<jde_application>[RP]\d{6,8})\]"
    #     ]
    # },
    # {
    #     "anchor": "BSFN",
    #     "extractor": "business_function",
    #     "regex": [
    #         r"BSFN[:\s]+(?P<business_function>B\d{7})",
    #         r"Business Function[:\s]+(?P<business_function>B\d{7})"
    #     ]
    # },
     # ===== ERRORES =====
    {
        "anchor": "Error",
        "extractor": "error_code",
        "regex": [
            r"Error[:\s]+(?P<error_code>\d+)",
            r"ErrorCode[:\s]+(?P<error_code>\d+)",
            r"Error\s+Code[:\s]+(?P<error_code>\d+)"
        ]
    },
    {
        "anchor": "Exception",
        "extractor": "exception_type",
        "regex": [
            r"com\.(?!jdedwards\.database\.base\.JDBException\b)(?P<exception_type>[\w.]+Exception)",
            r"Exception Type[:\s]+(?P<exception_type>[\w.]+)"
        ]
    },
    {
        "anchor": "database.base.JDBException",
        "extractor": "db_exception_type",
        "regex": [
            r"\[(?P<exception_type>[A-Z0-9_]+)\]"
        ]
    },
    
    # ===== TABLAS JDE =====
    {
        "anchor": "F",
        "extractor": "jde_table",
        "regex": [
            r"Table[:\s]+(?P<jde_table>F\d{2,6}[\w]*)",
            r"FROM\s+(?P<jde_table>F\d{2,6}[\w]*)",
            r"INTO\s+(?P<jde_table>F\d{2,6}[\w]*)",
            r"\[(?P<jde_table>F\d{2,6}[\w]*)\]"
        ]
    },

    # ===== SQL Y QUERIES =====
    {
        "anchor": "SQL",
        "extractor": "sql_statement_type",
        "regex": r"(?P<sql_statement_type>SELECT|INSERT|UPDATE|DELETE|MERGE)\s+"
    },
]

IGNORE_PATTERNS = [
    # r'\s*',  # Líneas vacías
    r'[=\*\-]{5,}\s*',  # Separadores, 

    # Threads de cleanup y mantenimiento
    r'clean up thread',
    r'cleanup thread',
    r'thread pool.*cleanup',
    
    # Logging verboso de bajo valor
    r'RtfTemplate\.generateReport',
    r'Translation is null for',  
    r'getCachedObject.*cache hit',
    r'getCachedObject.*cache miss',
    
    # Operaciones repetitivas de bajo nivel
    r'^\[INFO\s*\].*-\s*\[RUNTIME\].*starting thread',  
    r'^\[INFO\s*\].*-\s*\[RUNTIME\].*stoping thread',   
    r'^\[INFO\s*\].*-\s*\[RUNTIME\].*stopped thread',
    
    # Debug traces innecesarios
    r'Entering method',
    r'Exiting method',
    r'Method entry:',
    r'Method exit:',
    
    # Status checks periódicos
    r'Health check.*OK',
    r'Heartbeat received',
    r'Keep-alive.*sent',

    # Session management verboso
    r'Session.*created\s*$',  # Solo si no tiene más info
    r'Session.*destroyed\s*$',
    
    # Cache operations de bajo valor
    r'Cache entry added',
    r'Cache entry removed',
    r'Cache entry expired',
    
    # Configuration dumps largos
    r'Configuration parameter:.*=',
    r'System property:.*=',

    r'Previous\s*serialized\s*objects', 
    r'(?:Discovered|Discovery)', 
    r'Manifest', 
    r'Package:', 
    r'Update\s*Pkg',
    r'.*package.*discovery.*', # This server is using Automatic Package discovery.

    r'.*serialized\s*object.*', # The serialized object database will be maintained by the system.

    r'.*EnterpriseOne.*'
]

LEVEL_MAPPING = {
    "SEVERE": "ERROR",
    "ERROR": "ERROR",
    "FATAL": "ERROR",
    "CRITICAL": "ERROR",

    "MANDATORY": "WARN",     # Suele usarse para avisos que siempre deben registrarse
    "WARNING": "WARN",
    "WARN": "WARN",

    "APP": "INFO",           # Mensajes de aplicación normales
    "INFO": "INFO",
    "NOTICE": "INFO",

    "DEBUG": "DEBUG",
    "TRACE": "DEBUG",
    "VERBOSE": "DEBUG",
}