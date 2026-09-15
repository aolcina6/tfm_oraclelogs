LOG_TYPE = "bssv"
MULTILINE = True
DRAIN_CONFIG = "strict_deep"
FILENAME_PATTERNS = [
    r'^bssv_\d+',       # bssv_20260726_11.log
    r'bssv[\._-]',      # bssv-server.log
    r'bssv\.log$',      # bssv.log
    r'.*_bssv_.*',  # any_BSSV_*.log (ej: COV_BSSV_LOG.log)
]

TIMESTAMP_PATTERNS = [
    # Formato: "07 ago 2026 01:51:46,148" (día mes_literal año hh:mm:ss,ms) - ESPAÑOL
    r"^\d{2}\s+(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\s+\d{4}\s+\d{2}:\d{2}:\d{2},\d{3}\s*",
    
    # Formato: "07 Aug 2026 01:51:46,148" (día mes_literal año hh:mm:ss,ms) - INGLÉS
    r"^\d{2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s+\d{2}:\d{2}:\d{2},\d{3}\s*",
]

PATTERNS = {
    "bssv": r'(?P<timestamp>\d{2}\s+\w+\s+\d{4}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(?P<level>\w+)\s*\]\s+-\s+\[(?P<component>BSSVFRAMEWORK)\]\s+\[Context ID:\s+(?P<context_id>[^\]]+)\]\s+\[(?P<client>[A-Za-z0-9_]+)\]\[(?P<pid>[A-Za-z0-9_]+)\]\s+(?P<message>.*)'
}

IGNORE_PATTERNS = [
    # r'\s*$',
    r'={5,}\s*$',
    r'-{5,}\s*$',
    r'Content-',
    r'<(?:/?soap:|/?env:|/?S:)',
    r'------=_Part_',
    r'Recuperamos\s*credenciales',
    
    # PDF embebido
    r'^endobj\s*$',
    r'^stream\s*$',
    r'^endstream\s*$',
    r'^\d+\s+\d+\s+f\s*$',
    r'^xref\s*$',
    r'^trailer\s*$',
    r'^startxref\s*$',
    r'^%%EOF\s*$',
    r'^\d+\s+0\s+obj\s*$',
    r'^/Type\s+/Font',
    r'^/Type\s+/Page',
    r'^/Type\s+/Catalog',
    r'^/Type\s+/Filespec',
    r'^/Length\s+\d+',
    r'^/Filter\s+/',
    r'^/ProcSet\s+',
    r'^/BaseFont\s+/',
    r'^/Subtype\s+/Image',
    r'^/Width\s+\d+',
    r'^/Height\s+\d+',
    r'^/ColorSpace\s+/',
    r'^/BitsPerComponent\s+\d+',
    r'^\d+\s+\d+\s+R\s*$',
    r'^%PDF-',
    r'^%����',
    
    # Caracteres binarios/corruptos
    r'![$]7MX',
    r'![.%]gX',
    r'!fAD!!fAD',
    r'!!2\s*\?!!2',
    r'!;[*]Y\s+!;[*]Y',
    r"!'N%[+]!'N%",
    r'!-ig!!-ig',
    r'!\\.&\s+S!\\.&\s+S',
    r'^[!@#$%^&*]{10,}',
    r'^[A-Za-z0-9+/]{100,}$',
    r'^[0-9a-fA-F\s]{100,}$',
    r'rrr[A-Z][a-z]{3,}',
    r'ValueObject.*NULL.*NULL.*NULL',
    r'Update\s+Pkg.*Built.*Deployed.*Detected',
]
