# ------------------------------------------------------------------------------------
# JAS / Java Application Server
# ------------------------------------------------------------------------------------
LOG_TYPE = "jas"
MULTILINE = False
DRAIN_CONFIG = "very_strict"
FILENAME_PATTERNS = [
    r'^jas_\d+',        # jas_20260805_1.log
    r'.*_jas_.*',       # any_JAS_*.log (ej: COV_JAS_LOG.log)
]

TIMESTAMP_PATTERNS = [
    r"(?P<day>\d{2})\s+(?P<month_name>\w{3})\s+(?P<year>\d{4})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}),(?P<milliseconds>\d{3})"
]

PATTERNS = {
    "jas": r'^(?P<timestamp>\d{1,2}\s+\w{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(?P<level>\w+)\s*\]\s*-\s*\[(?P<pid>\d+)\]\[(?P<component>\w+)\]\s*(?P<message>[^\n\r]+)'
}

EXTRACTORS = [
    # # ===== IDENTIFICADORES DE PROCESO =====
    # {
    #     "anchor": "[",
    #     "extractor": "process_id",
    #     "regex": r"\[(?P<process_id>\d+)\]\[RUNTIME\]"
    # },
    
    # # ===== COMPONENTE (siempre es RUNTIME en JAS) =====
    # {
    #     "anchor": "RUNTIME",
    #     "extractor": "component",
    #     "regex": r"\[(?P<component>RUNTIME|XMLP|RTF|REPORTS)\]"
    # },
    # ===== ERRORES Y EXCEPCIONES =====
    {
        "anchor": "Exception",
        "extractor": "exception_type",
        "regex": [
            r"(?P<exception_type>com\.jdedwards\.xmlp\.exceptions\.[\w]+Exception)",
            r"(?P<exception_type>oracle\.xdo\.[\w.]+Exception)",
            r"(?P<exception_type>java\.[\w.]+Exception)"
        ]
    },
    {
        "anchor": "failed",
        "extractor": "error_message",
        "regex": [
            r"(?P<error_message>Excel Processor failed)",
            r"(?P<error_message>PDF Processor failed)",
            r"(?P<error_message>Report generation failed)",
            r"(?P<error_message>Email delivery failed)",
            r"(?P<error_message>Fax delivery failed)"
        ]
    },
     # ===== USUARIOS =====
    {
        "anchor": "User",
        "extractor": "username",
        "regex": [
            r"User[:\s]+(?P<username>[A-Z0-9_-]+)",
            r"UserID[:\s]+(?P<username>[A-Z0-9_-]+)",
            r"Submitted by[:\s]+(?P<username>[A-Z0-9_-]+)"
        ]
    },
    
    # ===== JOB QUEUE =====
    {
        "anchor": "Job",
        "extractor": "job_number",
        "regex": [
            r"Job[:\s]+(?P<job_number>\d+)",
            r"JobID[:\s]+(?P<job_number>\d+)"
        ]
    },
    # {
    #     "anchor": "Queue",
    #     "extractor": "queue_name",
    #     "regex": r"Queue[:\s]+(?P<queue_name>[\w_-]+)"
    # },
    # # ===== ENTORNO =====
    # {
    #     "anchor": "Environment",
    #     "extractor": "environment",
    #     "regex": [
    #         r"Environment[:\s]+(?P<environment>[A-Z\d]+)",
    #         r"Env[:\s]+(?P<environment>[A-Z\d]+)"
    #     ]
    # },
    # ===== DATA SOURCE =====
    {
        "anchor": "Data Source",
        "extractor": "data_source",
        "regex": r"Data Source[:\s]+(?P<data_source>[\w_-]+)"
    },
    {
        "anchor": "Connection",
        "extractor": "connection_string",
        "regex": r"Connection[:\s]+(?P<connection_string>jdbc:[\w:/.-]+)"
    },
]

IGNORE_PATTERNS = [
    r'^\s*$',
    r'[=\*\-]{5,}\s*',

    r'.*Translation is null\.\s+Continuing',
    
    # Thread management
    r'.*Thread pool.*cleanup',
    r'.*clean up thread', 
    
    # Report generation lifecycle
    r'.*begin report generation',
    r'.*report generation completed',
    
    # Logging verboso
    r'.*RtfTemplate\.generateReport\(\)',
    
    # Cache operations
    r'.*Cache.*hit\s*$',
    r'.*Cache.*miss\s*$',
    
    # Health checks
    r'.*Heartbeat.*OK',
    r'.*Keep-alive sent',
]