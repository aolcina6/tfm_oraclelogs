# ------------------------------------------------------------------------------------
# AIS (Application Interface Services) 
# Servidor que proporciona servicios REST y APIs para interactuar con EnterpriseOne.
# ------------------------------------------------------------------------------------
LOG_TYPE = "ais"
MULTILINE = True 
DRAIN_CONFIG = "baseline"
FILENAME_PATTERNS = [
    r'^ais_\d+',           # ais_20260805_1.log
    r'^ais[\._-]',         # ais-server.log, ais.log
    r'^ais',               # ais.log (exacto)
    r'.*[_-]ais[_-].*',    # Cualquier archivo con _ais_ o -ais- en el nombre
]

TIMESTAMP_PATTERNS = [
    # Formato: "07 ago 2026 01:51:46,148" (día mes_literal año hh:mm:ss,ms) - ESPAÑOL
    r"\d{1,2}\s+(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\s+\d{4}\s+\d{2}:\d{2}:\d{2}[,.]\d{3}",

    # Formato: "07 Aug 2026 01:51:46,148" o "07 Aug 2026 01:51:46.148" - INGLÉS
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s+\d{2}:\d{2}:\d{2}[,.]\d{3}",
]

TIMESTAMP_RE = r"\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2}:\d{2}[,.]\d{3}"

PATTERNS = {
    "ais_event": (
        r'(?P<timestamp>' + TIMESTAMP_RE + r')\s+'
        r'\[(?P<level>\w+)\s*\]\s+'
        r'(?:(?P<user>[^\s\-\[]+)\s+)?'
        r'-\s+\[(?P<component>CUSTOM|AIS)\]\s+'
        r'(?:' + TIMESTAMP_RE + r'\s+\[\w+\s*\]\s+\w+\s+-\s+\[\w+\]\s+)?'
    ),
}

EXTRACTORS = [
    {
        "anchor": "Job",
        "extractor": "job_number",
        "regex": [
            r"['\"]?jobNumber['\"]?\s*[:=]\s*['\"]?(?P<job_num>\d+)",
            r'(?:Job:\s*"|longEndPoint\s+)(?P<job_num>ORCH_[A-Za-z0-9_-]+)'
        ]
    }, 
    {
        "anchor": "AIS", 
        "extractor": "ais_parameter",
        "regex": r"AIS\s*Parameter\s*Not\s*Found\s*(\w*)$"
    }, 
        {
        "anchor": "[",
        "extractor": "business_module",
        "regex": [
            r"\[(?P<business_module>GLS|JDE|ERP|CUSTOM|BSSV)\]",
            r"Module:\s*(?P<business_module>GLS|JDE|ERP|CUSTOM)"
        ]
    },
    # ===== ERRORES Y ESTADOS =====
    {
        "anchor": "errorMessage",
        "extractor": "error_message",
        "regex": [
            r"<errorMessage>(?P<error_message>[^<]+)</errorMessage>",
            r"Error:\s*(?P<error_message>[^\n]+)",
            r"ERROR\s*[-:]\s*(?P<error_message>[^\n]+)"
        ]
    },
    {
        "anchor": "warningMessage",
        "extractor": "warning_message",
        "regex": [
            r"<warningMessage>(?P<warning_message>[^<]+)</warningMessage>",
            r"WARN:\s*(?P<warning_message>[^\n]+)"
        ]
    },
    {
        "anchor": "Step",
        "extractor": "orch_step_type",
        "regex": [
            r"Orchestration Step:\s*(?P<orch_step_type>[^:]+):",
        ]   
    }, 
        {
        "anchor": "Step",
        "extractor": "orch_step_name",
        "regex": [
            r"Orchestration Step:\s*[^:]+:\s*(?P<orchestration_name>.+)",
        ]   
    }, 
]

IGNORE_PATTERNS = [
    r'Entrada:.*', # Entrada: 2026-05-15
    r'fechaFormateada.*',  # fechaFormateada: 2026-05-15
    r'AIS Version:.*',  # AIS Version: 1.0.0
    r'OrchScriptEngineManager',  #OrchScriptEngineManager: ScriptEnginePoolSize (groovy and jython): 10
    r'Session Manager Instance',  # Session Manager Instance: 1
    r'RequestMonitorManager',  # RequestMonitorManager: RequestMonitorPoolSize: 10
    r'Session.*START.*',  
    r'.*AIS Server Startup.*',
    r'SYNC SERVER.*',
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