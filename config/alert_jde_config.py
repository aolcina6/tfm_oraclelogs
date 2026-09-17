# ------------------------------------------------------------------------------------
# Mecanismo de alertas del Enterprise Server / JDE
# ------------------------------------------------------------------------------------

LOG_TYPE = "alert_jde"
MULTILINE = True
DRAIN_CONFIG = "baseline"
INCREMENTAL = True 

FILENAME_PATTERNS = [
    r'alert_jde'
]

TIMESTAMP_FLAT = (
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2}"
)

TIMESTAMP_PATTERNS = [
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})T"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"\.(?P<microseconds>\d+)(?P<tz>[+-]\d{2}:\d{2})"
]

PATTERNS = {
    "alert_jde_event": (
        r"(?m)^(?P<timestamp>" + TIMESTAMP_FLAT + r")\s*\n"
        r"(?P<message>(?:(?!^" + TIMESTAMP_FLAT + r").*\n?)*)"
    )
}

# ✅ Extractores para los patrones más relevantes del contenido
EXTRACTORS = [
    {
        "anchor": "ORA-", 
        "extractor": "ora_error_code", 
        "regex": r"(?P<ora_error_code>ORA-\d+)"
    },
    {
        "anchor": "TNS-", 
        "extractor": "tns_error_code", 
        "regex": r"(?P<tns_error_code>TNS-\d+)"
    },
    {
        "anchor": "Errors in file", 
        "extractor": "trace_file", 
        "regex": r"Errors in file (?P<trace_file>[^\s:]+)"
    },
    {
        "anchor": "Current username=", 
        "extractor": "db_username", 
        "regex": r"Current username=(?P<db_username>\S+)"
    }, 
    # # ===== TABLESPACES =====
    # {
    #     "anchor": "tablespace",
    #     "extractor": "tablespace_name",
    #     "regex": [
    #         r"tablespace\s+(?P<tablespace_name>\w+)",
    #         r"in tablespace\s+(?P<tablespace_name>\w+)",
    #     ]
    # },
    
    # # ===== TABLAS ORACLE =====
    # {
    #     "anchor": "SYS.",
    #     "extractor": "oracle_table",
    #     "regex": [
    #         r"(?P<oracle_table>SYS\.\w+)",
    #         r"(?P<oracle_table>AUDSYS\.\w+)",
    #     ]
    # },
    # # ===== JOBS Y PROCESOS =====
    # {
    #     "anchor": "job",
    #     "extractor": "oracle_job_name",
    #     "regex": r'job\s+"(?P<oracle_job_name>[^"]+)"'
    # },
    # {
    #     "anchor": "Process",
    #     "extractor": "background_process",
    #     "regex": [
    #         r"Process\s+(?P<background_process>[A-Z]{3,5}\d*)\s+",
    #         r"Starting background process\s+(?P<background_process>\w+)",
    #     ]
    # },
]

IGNORE_PATTERNS = [
    r'.*Dumping current patch information.*',
    
    # Bloque Shared IO Pool (desde "Shared IO Pool" hasta "===")
    r'Shared IO Pool defaulting.*',
    
    # Bloque SGA (desde **** hasta ****)
    r'\s*\*{4,}.*?Dump of system resources.*?(?=^\s*\*{4,})',

    # Líneas individuales del dump de patches
    r'Patch Id:\s*\d+\s*$',
    r'Patch Description:.*$',
    r'Patch Apply Time:.*$',
    r'Bugs Fixed:.*$',
    
    # Líneas de solo números (continuación de "Bugs Fixed")
    r'^[\d,\s]+$',
    
    # Líneas vacías
    # r'\s*$',
    
    # Líneas de puro separadores
    r'^[=\*\-]+$',

    # Cabecera de información de versión
    r"VERSION INFORMATION",

    # Versiones de Oracle / TNS
    r"TNS for Linux:",
    r"Oracle Bequeath NT Protocol Adapter for Linux:",
    r"TCP/IP NT Protocol Adapter for Linux:",
    r"Version \d+\.\d+\.\d+\.\d+\.\d+.*$",

    # Información de tracing
    r"Tracing not turned on",

    # Información adicional interna de Oracle
    r"Additional information:", 

    r"(?:XDB initialized\.)", 

    r"Thread.*log\s*sequence\s*", 
    r"Thread.*allocate.*log", 
    r".*crash.*thread.*", # Beginning crash recovery of 1 threads

    r"Resize operation completed",

    r"Per\s*process.*", # Per process system memlock (soft) limit = 128G
    
    r".*pagesize.*", # pagesize = 8192 // Available system pagesizes: // Supported system pagesize(s):
    r".*PAGESIZE.*", 

    r"4K.*", # 4K Configured <NUM> <NUM> NONE
    r".*Dynamic\s*allocate.*", # 2048K - Dynamic allocate and free memory regions

    r".*pga_aggregate_limit.*", # pga_aggregate_limit = 0

    r"QPI.*", # QPI: opatch file present, opatch QPI: qopiprep.bat file present, 

    r"VKTM.*ms", # VKTM running at (1)millisec precision with DBRM quantum (100)ms, 

    r"Started\s*redo.*", 

    r'.*background process.*',

    r'An\s*internal\s*routine.*', 

    r'Current\s*log.*', 

    r'Starting.*instance.*', 

    r'(?:Started|Completed)\s*redo\s*(?:scan|application)',

    r'.*Checkpoint\s*not\s*complete.*',

    r'.*XDB\s*installed.*', 

    r'.*GAP.*starting', 

    r'Starting\s*up.*', 
    
    r'Starting\s*background.*'
]