# ------------------------------------------------------------------------------------
# WebLogic
# servidor de aplicaciones Java sobre el que puede ejecutarse JAS
# ------------------------------------------------------------------------------------
LOG_TYPE = "weblogic"
MULTILINE = True
DRAIN_CONFIG = "deep"
FILENAME_PATTERNS = [
    r'^weblogic_\d+',        # weblogic_20260805_1.log
    r'weblogic\.log$',       # weblogic.log
    r'^.*_weblogic_.*', # any_WEBLOGIC_*.log (ej: COV_WEBLOGIC_LOG.log)
]

TIMESTAMP_PATTERNS = [
    r"(?P<day>\d{2})\s+(?P<month_name>\w{3})\s+(?P<year>\d{4})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}),(?P<milliseconds>\d{3})"
]

PATTERNS = {
    "weblogic": r'(?m)(?P<timestamp>\d{1,2}\s+\w{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(?P<level>[A-Z]+)\]\s*(?:(?P<user>[A-Za-z0-9_\-]+)\s+-\s+|\s*-\s+)\[(?P<app>[^\]]+)\]\[(?P<component>[^\]]+)\]\s*(?P<message>(?:[^\n\r]+(?:\n(?!\d{1,2}\s+\w{3}\s+\d{4}).*)*)*)'
}

EXTRACTORS = [
    # ===== ERRORES CRÍTICOS =====
    {
        "anchor": "ORA-",
        "extractor": "oracle_error_code",
        "regex": r"ORA-(?P<oracle_error_code>\d{5})"
    },
    {
        "anchor": "JDB",
        "extractor": "jde_error_code",
        "regex": r"(?P<jde_error_code>JDB\w+)"
    },
    # ===== USUARIOS =====
    {
        "anchor": "UserName",
        "extractor": "username",
        "regex": [
            r"UserName[:\s]+(?P<username>[A-Z0-9_-]+)",
            r"\[WARN\s*\]\s+(?P<username>[A-Z]+)\s+-\s+",
            r"\[SEVERE\]\s+(?P<username>[A-Z]+)\s+-\s+",
            r"user[:\s]+(?P<username>[A-Z][A-Z0-9]+)",
        ]
    },
    # ===== APLICACIONES JDE =====
    {
        "anchor": "App Name",
        "extractor": "jde_application",
        "regex": [
            r"App Name[:\s]+(?P<jde_application>P\d{5,8}_W\d{5,8}[A-Z]?_[A-Z0-9]+)",
            r"Form Name[:\s]+(?P<jde_application>P\d{5,8}_W\d{5,8}[A-Z]?)",
        ]
    },
    {
        "anchor": "Report Name",
        "extractor": "report_name",
        "regex": r"Report Name[:\s]+(?P<report_name>R\d{5,8}_?)"
    },
    
    # ===== TABLAS JDE =====
    {
        "anchor": "Table",
        "extractor": "jde_table",
        "regex": [
            r"Table[:\s]+(?P<jde_table>F\d{2,6}[\w]*)",
            r"Table or View Name[:\s]+(?P<jde_table>F\d{2,6}[\w]*)",
            r"for table\s+(?P<jde_table>F\d{2,6}[\w]*)",
        ]
    },
    # ===== EXCEPCIONES JAVA =====
    {
        "anchor": "Exception",
        "extractor": "exception_type",
        "regex": [
            r"(?P<exception_type>com\.jdedwards\.[\w.]+Exception)",
            r"(?P<exception_type>java\.[\w.]+Exception)",
            r"(?P<exception_type>oracle\.[\w.]+Exception)",
        ]
    },
    
    # ERROR MESSAGES
    {
        "anchor": "failed",
        "extractor": "operation_failed",
        "regex": [
            r"(?P<operation_failed>[\w\s]+)\s+failed",
            r"Failed to\s+(?P<operation_failed>[\w\s]+)",
            r"Unable to\s+(?P<operation_failed>[\w\s]+)",
        ]
    },
]

IGNORE_PATTERNS = [
    r'^\s*$',
    
    # PACKAGE UPDATE LOGS
    r'.*Update:\s+Update\s+Pkg\s+=.*Built\s+=.*Deployed\s+=.*Detected\s+=',
    
    # STARTUP/SHUTDOWN MESSAGES
    r'.*Initiating EnterpriseOne startup',
    r'.*Successfully initialized the EnterpriseOne web engine',
    r'.*Centralized Configuration is disabled',
    r'.*This server is using Automatic Package discovery',
    r'.*serialized object database will be maintained',
    r'.*Serialized objects have been found up to date',
    r'.*Discovery.*system is now in sync with the deployed package',
    r'.*Discovered enterprise server on host',
    r'.*Discovered package.*in Central Objects',
]