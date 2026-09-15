LOG_TYPE = "jde"
MULTILINE = True
DRAIN_CONFIG = "baseline"
FILENAME_PATTERNS = [
    r'^jde_\d+',        # jde_20260805_1.log
    r'^.*enterprise.*', # COV_Enterprise_LOG.log
    r'^.*_jde_\d+', # ged_jde_74715
]
TIMESTAMP_PATTERNS = [
    r"(?P<day_name>\w{3})\s+(?P<month_name>\w{3})\s+(?P<day>\d{1,2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<microseconds>\d{6})"
]

PATTERNS = {
    "jde": (
        r'(?m)^(?P<pid>\d+)(?:/\d+)?[ \t]+'
        r'(?:[^\t\n]*)\t'                                             # bloque de rol opcional (WRK:..., SYS:..., o vacío), termina en TAB
        r'(?P<timestamp>\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\.\d{6})\t'
        r'(?P<component>\S+)\s*\n'
        r'(?P<message>(?:(?!^\d+(?:/\d+)?[ \t]+[^\t\n]*\t\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\.\d{6}).*\n?)*)'
    ),
}
EXTRACTORS = [
    # ===== ERRORES CRÍTICOS =====
    {
        "anchor": "ORA-",
        "extractor": "oracle_error_code",
        "regex": r"ORA-(?P<oracle_error_code>\d{5})",
        "priority": 1
    },
    {
        "anchor": "JDB",
        "extractor": "jde_error_code",
        "regex": r"(?P<jde_error_code>JDB\d{7})",
        "priority": 1
    },
]

IGNORE_PATTERNS = [
    r'^\s*$',
    r'^[=\*\-]{5,}\s*$',
    
    r'clean up',

    r'No email address found ',
    r'Print request failed',
    
    # Translation warnings
    r'Translation is null',
    r'RtfTemplate',

    r'This is Small Job kernel\s*',
    r'Attempting.*printer.*', 
    r'Enterprise.*One.*', 
    r'Active.*Kernel.*',
    r'.*registered.*entry.*', 
    r'KERNEL\s*RECYCLING', 
    r'Starting.*KERNEL.*', 
    r'INITIALIZING.*KERNEL.*', 
    r'ICU.*, '
    r'.*dispatchKernelQueueMsg.*'

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

    r"Initializing.*", 
    r"Terminating.*",

    r"(?:Getting)?.*(?:U|u)ser.*data.*", 

    r".*RUNBATCH.*", 

    r"Default\s*output.*", 
    
    r"Startup\s*for\s*User.*", 
    
    r".*XML\s*Session.*", 

    r".*Scheduler.*", # Scheduler is now started. // Attempting to auto-start the Scheduler., 

    r"Cleaning.*",

]