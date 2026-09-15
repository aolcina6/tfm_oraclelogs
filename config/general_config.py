# Expresiones regulares para detectar formatos de timestamp con named groups
TIMESTAMP_PATTERNS = [
    # Formato: 2023-10-11 12:34:56
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})",

    # Formato: 11/10/2023 12:34:56
    r"^(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})",

    # Formato: 2023/10/11 12:34:56
    r"^(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})",

    # Formato: 29 Jun 2026 02:04:07,195 (Weblogic)
    r"^(?P<day>\d{2})\s+(?P<month_name>\w{3})\s+(?P<year>\d{4})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}),(?P<milliseconds>\d{3})",

    # Formato: 217668	Thu Jun 25 18:00:02.591327 (JDE con PID y día de la semana)
    r"^(?P<pid>\d{6})\t(?P<day_name>\w{3})\s+(?P<month_name>\w{3})\s+(?P<day>\d{1,2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<microseconds>\d{6})",

    # Formato: Thu Jun 25 18:00:02.591327 (JDE sin PID)
    r"^(?P<day_name>\w{3})\s+(?P<month_name>\w{3})\s+(?P<day>\d{1,2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<microseconds>\d{6})",

    # Formato: Wed Jun 24 16:26:13 CEST 2026 (con timezone)
    r"^(?P<day_name>\w{3})\s+(?P<month_name>\w{3})\s+(?P<day>\d{1,2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\s+(?P<timezone>\w{3,4})\s+(?P<year>\d{4})",

    # Formato: 06-JUL-2026 21:12:31 (Oracle alert log, sin milisegundos)
    r"^(?P<day>\d{2})-(?P<month_name>\w{3})-(?P<year>\d{4})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})",

    # Formato: Time 06-JUL-2026 21 12 31 (Oracle TNS listener/alert, con espacios en vez de ':')
    r"^Time\s+(?P<day>\d{2})-(?P<month_name>\w{3})-(?P<year>\d{4})\s+(?P<hour>\d{2})\s+(?P<minute>\d{2})\s+(?P<second>\d{2})",

    # Formato: 11 ene 2026 02:04:07,195 (día + mes literal español + año)
    r"^(?P<day>\d{1,2})\s+(?P<month_name>ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"
    r"\s+(?P<year>\d{4})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})[,.](?P<milliseconds>\d{3})",

    # Formato: 11 Jan 2026 02:04:07,195 (día + mes literal inglés + año)
    r"^(?P<day>\d{1,2})\s+(?P<month_name>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+(?P<year>\d{4})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})[,.](?P<milliseconds>\d{3})",

    # Formato: Mon DD HH:MM:SS (syslog clásico, sin año ni timezone)
    r"^(?P<month_name>\w{3})\s+(?P<day>\d{1,2})\s+"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})",
]

# Delimitadores comunes en los logs
DELIMITERS = [" ", ",", "|", "\t"]

# Mapeo de nombres de meses a números
MONTH_MAP = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
}

MONTH_NAME_TO_NUM = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
}

MONTH_MAP_LOWERCASE = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
}

MONTH_MAP_UPPERCASE = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
}

MONTH_MAP_CAPITALIZED = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}

MONTH_MAP_SPANISH = {
    'ene': '01', 'feb': '02', 'mar': '03', 'abr': '04',
    'may': '05', 'jun': '06', 'jul': '07', 'ago': '08',
    'sep': '09', 'oct': '10', 'nov': '11', 'dic': '12',
}

IMPLICIT_LEVEL_PATTERNS = {
    "ERROR": [
        r"\berror\b",
        r"\bexception\b",
        r"\bfailed\b",
        r"\bfailure\b",
        r"\bfatal\b",
        r"\bunable to\b",
        r"\bcannot\b",
        r"\bcan't\b",
        r"\bnot able to\b",
        r"\bdenied\b",
        r"\binvalid\b",
        r"\btimeout\b",
        r"\btimed out\b",
        r"\bconnection refused\b",
        r"\bstatus code\s*=\s*5\d{2}\b",
    ],
    "WARN": [
        r"\bwarning\b",
        r"\bwarn\b",
        r"\bdeprecated\b",
        r"\bretry(?:ing)?\b",
        r"\bretried\b",
        r"\breconnecting\b",
        r"\bskipping\b",
        r"\bnot found\b",
        r"\bmissing\b",
    ],
}