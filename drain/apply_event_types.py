#!/usr/bin/env python3
"""
apply_event_types.py

Aplica un mapeo manual de {group_id: (event_type, severity)} sobre
e1root_template_regex.json, actualizando SOLO esos dos campos y
dejando todo lo demás (pattern, member_cluster_ids, representative_*)
completamente intacto.

Uso:
    python drain/apply_event_types.py templates/e1root_template_regex.json
"""
import json
import sys

# ============================================================
# Mapeo group_id -> (event_type, severity)
# Basado en análisis semántico del representative_template de cada
# grupo. Los grupos que YA tenían event_type/severity asignado
# manualmente NO están en este dict y por tanto no se tocan.
# ============================================================
EVENT_TYPE_MAP = {
    21:  ("GLS_NO_LINES_TO_PROCESS", "WARN"),
    43:  ("OAUTH_JWT_LOGIN_FAILURE", "ERROR"),
    27:  ("BSFN_THREAD_POOL_CONFIG", "INFO"),
    73:  ("UDO_SECURITY_TIMEOUT", "WARN"),
    69:  ("UI_INVALID_OBJECT", "WARN"),
    68:  ("UI_INVALID_OBJECT", "WARN"),
    132: ("HTML_CLIENT_BUSY", "WARN"),
    81:  ("PACKAGE_NOT_FOUND", "WARN"),
    105: ("PRODUCT_CODE_LOAD_FAILURE", "WARN"),
    129: ("AIS_VALIDATE_FAILURE", "ERROR"),
    106: ("PO_DATA_FETCH_ERROR", "WARN"),
    67:  ("GRID_ROW_INSERT_WARNING", "WARN"),
    76:  ("BAD_PARAMETER", "WARN"),
    131: ("BUFFER_LENGTH_MISMATCH", "WARN"),
    33:  ("ENCRYPTION_DECODE_ERROR", "ERROR"),
    98:  ("ORCHESTRATION_VALUE_NOT_FOUND", "WARN"),
    96:  ("COLUMN_TITLE_MISSING", "INFO"),
    75:  ("DATASOURCE_OVERRIDE_ERROR", "ERROR"),
    117: ("NULL_POINTER_EXCEPTION", "ERROR"),
    124: ("SQL_QUERY_TIMEOUT", "WARN"),
    92:  ("AIS_VALIDATE_FAILURE", "ERROR"),
    87:  ("DATASOURCE_NOT_FOUND", "ERROR"),
    80:  ("LOGIN_FAILURE", "ERROR"),
    133: ("SOCKET_FAILURE", "ERROR"),
    74:  ("SOCKET_FAILURE", "ERROR"),
    86:  ("CONNECTION_FAILURE", "ERROR"),
    121: ("BSFN_FAILURE", "ERROR"),
    97:  ("RUNTIME_RELINFO_EXCEPTION", "ERROR"),
    127: ("INFINITE_LOOP_DETECTED", "ERROR"),
    130: ("AIS_DATA_ACCESS_ERROR", "ERROR"),
    93:  ("LOGIN_FAILURE", "ERROR"),
    103: ("AUTHENTICATION_FAILURE", "ERROR"),
    108: ("NULL_POINTER_EXCEPTION", "ERROR"),
    85:  ("INVOCATION_TARGET_EXCEPTION", "ERROR"),
    71:  ("NULL_POINTER_EXCEPTION", "ERROR"),
    107: ("SECURITY_LIST_EXCEPTION", "ERROR"),
    100: ("OBJECT_MANAGER_ERROR", "ERROR"),
    128: ("LOGIN_FAILURE", "ERROR"),
    113: ("BUSINESS_VIEW_WARNING", "WARN"),
    47:  ("LOGIN_FAILURE", "ERROR"),
    82:  ("JDBC_DRIVER_NOT_FOUND", "WARN"),
    48:  ("THREAD_INFO", "INFO"),
    70:  ("DATA_DICTIONARY_MISSING", "WARN"),
    36:  ("NULL_POINTER_EXCEPTION", "ERROR"),
    78:  ("ORCHESTRATION_PARSE_ERROR", "ERROR"),
    126: ("MESSAGE_SEND_FAILURE", "ERROR"),
    66:  ("MESSAGE_SEND_FAILURE", "ERROR"),
    23:  ("FASTPATH_USER_ERROR", "WARN"),
    125: ("AIS_DATA_ACCESS_ERROR", "ERROR"),
    118: ("DATABASE_FAILURE", "ERROR"),
    119: ("NUMBER_FORMAT_EXCEPTION", "ERROR"),
    79:  ("KERNEL_RECYCLING_IGNORED", "INFO"),
    63:  ("SOCKET_FAILURE", "ERROR"),
    34:  ("CONFIG_INFO", "INFO"),
    123: ("CONFIG_INFO", "INFO"),
    83:  ("CONFIG_INFO", "INFO"),
    58:  ("LAUNCHUBE_FAILURE", "ERROR"),
    72:  ("LAUNCHUBE_FAILURE", "ERROR"),
    101: ("TRANSACTION_ROLLBACK_WARNING", "WARN"),
    37:  ("REQUEST_TIMEOUT", "ERROR"),
    88:  ("ORCHESTRATION_UPLOAD_FAILURE", "ERROR"),
    77:  ("LOGIN_FAILURE", "WARN"),
    57:  ("CONFIG_WARNING", "WARN"),
    111: ("CONFIG_INFO", "INFO"),
    28:  ("MAF_COMPONENT_ERROR", "WARN"),
    16:  ("LOGIN_FAILURE", "ERROR"),
    102: ("CONFIG_WARNING", "WARN"),
    122: ("BSFN_FAILURE", "ERROR"),
    65:  ("BSSV_CONNECTION_RUNTIME_FAILURE", "ERROR"),
    52:  ("KERNEL_NOT_FOUND", "ERROR"),
    35:  ("JAS_FAILURE", "ERROR"),
    40:  ("BSFN_FAILURE", "ERROR"),
    32:  ("NULL_POINTER_EXCEPTION", "ERROR"),
    94:  ("PROCESS_EVENT_EXCEPTION", "ERROR"),
    112: ("LOGIN_FAILURE", "ERROR"),
    60:  ("CLIENT_EXCEPTION", "ERROR"),
    55:  ("HTML_CLIENT_WARNING", "WARN"),
    120: ("DATABASE_FAILURE", "ERROR"),
    91:  ("JAS_SHUTDOWN", "INFO"),
    99:  ("LOGIN_FAILURE", "WARN"),
    109: ("SERVER_PROBLEM", "ERROR"),
    38:  ("TRANSACTION_ROLLBACK_WARNING", "WARN"),
    61:  ("ACCESS_DENIED", "ERROR"),
    104: ("AUTHORIZATION_FAILURE", "ERROR"),
    17:  ("KERNEL_NOT_FOUND", "ERROR"),
    49:  ("ORCHESTRATION_PARSE_ERROR", "ERROR"),
    84:  ("DATABASE_FAILURE", "ERROR"),
    59:  ("NULL_POINTER_EXCEPTION", "ERROR"),
    64:  ("DATABASE_FAILURE", "ERROR"),
    110: ("LOGIN_FAILURE", "ERROR"),
    89:  ("MEDIA_OBJECT_NOT_FOUND", "WARN"),
    51:  ("FILE_ACCESS_DENIED", "ERROR"),
    53:  ("GRID_EXCEPTION", "ERROR"),
    50:  ("GRID_EXCEPTION", "ERROR"),
    90:  ("SYSTEM_LIFECYCLE", "INFO"),
    54:  ("SYSTEM_LIFECYCLE", "INFO"),
    46:  ("LOGIN_FAILURE", "ERROR"),
    29:  ("FILE_NOT_FOUND", "ERROR"),
    45:  ("JAS_MAFLET_INFO", "INFO"),
    25:  ("GRID_EXCEPTION", "WARN"),
    22:  ("CLASS_CAST_EXCEPTION", "ERROR"),
    41:  ("NULL_POINTER_EXCEPTION", "ERROR"),
}


def apply_event_types(input_path: str) -> None:
    """
    Aplica el mapeo EVENT_TYPE_MAP sobre el archivo JSON de grupos.
    
    Args:
        input_path (str): Ruta al archivo JSON de grupos (e1root_template_regex.json).
    
    Returns:
        None
    """
    with open(input_path, encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    already_set = 0
    not_in_map = 0

    for group in data['groups']:
        gid = group['group_id']

        if group.get('event_type') is not None or group.get('severity') is not None:
            already_set += 1
            continue

        if gid in EVENT_TYPE_MAP:
            event_type, severity = EVENT_TYPE_MAP[gid]
            group['event_type'] = event_type
            group['severity'] = severity
            updated += 1
        else:
            not_in_map += 1

    with open(input_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ {updated} grupo(s) actualizados")
    print(f"⏭️  {already_set} grupo(s) ya tenían event_type/severity (no tocados)")
    if not_in_map > 0:
        print(f"⚠️  {not_in_map} grupo(s) sin entrada en EVENT_TYPE_MAP (quedan como null)")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Uso: python apply_event_types.py <ruta_al_regex.json>")
        sys.exit(1)

    apply_event_types(sys.argv[1])