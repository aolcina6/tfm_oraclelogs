# ------------------------------------------------------------------------------------
# JD Edwards EnterpriseOne Listener
# ------------------------------------------------------------------------------------
LOG_TYPE = "listener"
MULTILINE = True
DRAIN_CONFIG = "deep"
INCREMENTAL = True

FILENAME_PATTERNS = [
    r'^listener_\d+',       # listener_20260805_1.log
    r'^listener.*',         # listener.log
    r'^.*_listener_.*',     # any_LISTENER_*.log (ej: COV_LISTENER_LOG.log)
]

TIMESTAMP_PATTERNS = [
    r"(?P<day>\d{2})-(?P<month_name>\w{3})-(?P<year>\d{4})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
]

PATTERNS = {
    "db_listener_connection": (
        r'^(?P<timestamp>\d{2}-\w{3}-\d{4}\s+\d{2}:\d{2}:\d{2})'
        r'\s*(?P<message>.+)$'
    )
}

EXTRACTORS = [
    {
        "anchor": "SERVICE_NAME", 
        "extractor": "service_name", 
        "regex": r"SERVICE_NAME=(?P<service_name>[^\)]+)"
    },
    {
        "anchor": "PROGRAM", 
        "extractor": "program", 
        "regex": r"PROGRAM=(?P<program>[^\)]+)"
    },
    {
        "anchor": "CID", 
        "extractor": "host_name", 
        "regex": r"CID=\([^)]*HOST=(?P<host_name>[^\)]+)"
    },
    {
        "anchor": "PROTOCOL=tcp", 
        "extractor": "host_ip", 
        "regex": r"PROTOCOL=tcp\)\(HOST=(?P<host_ip>[^\)]+)"
    },
    {
        "anchor": "PROTOCOL=tcp", 
        "extractor": "port", 
        "regex": r"PROTOCOL=tcp\)\(HOST=[^\)]+\)\(PORT=(?P<port>\d+)"
    },
    # ===== ERRORES TNS =====
    {
        "anchor": "TNS-",
        "extractor": "tns_error_code",
        "regex": r"TNS-(?P<tns_error_code>\d{5})",
        "priority": 1
    },
    {
        "anchor": "Linux Error:",
        "extractor": "linux_error_code",
        "regex": r"Linux Error:\s+(?P<linux_error_code>\d+):\s+(?P<linux_error_message>[^\n]+)",
        "priority": 1
    },
]

IGNORE_PATTERNS = [
    r'^\s*$',

    r'.*\* establish \* jde \* 0$',
    
    # Handoffs HTTP exitosos 
    r'.*\* handoff \* http \* 0$',
    
    # Service updates periódicos 
    r'.*\* service_update \* jde \* 0$',
    
    # Service registration
    r'.*\* service_register \* jde \* 0$',
    
    # Status checks 
    r'.*\* status \* 0$',
    
    # Ping checks
    r'.*\* ping \* 0$',
    
    # Version checks 
    r'.*\* version \* 1189$',
    
    # STARTUP MESSAGES
    r'LISTENER for Linux: Version',
    r'Version \d+\.\d+\.\d+\.\d+',
    r'System parameter file is',
    r'Log messages written to',
    r'Trace information written to',
    r'Trace level is currently',
    r'Started with pid=',
    r'Listening on:',
    r'Listener completed notification to CRS',
    r'TIMESTAMP \* CONNECT DATA',
    r'WARNING: Subscription for node down event',
    r'Dynamic address is already listened on',
    r'Creating new log segment:',
    
    # Ignorar timestamps ISO aislados (líneas incompletas/headers)
    # r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2}$',

]