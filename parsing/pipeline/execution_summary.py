"""
execution_summary.py

Construcción y persistencia del resumen histórico de ejecuciones
(_summary.json), con estadísticas de normalización, errores y contadores.
"""
from datetime import datetime


def build_execution_summary(
    execution_started_at,
    execution_mode,
    log_files,
    files_to_process,
    files_skipped,
    all_results,
    total_normalized,
    total_failed,
    total_no_timestamp,
):
    """
    Construye el dict de resumen de la ejecución actual.
    """
    execution_finished_at = datetime.now().isoformat(timespec='seconds')

    return {
        "timestamp": execution_started_at,
        "finished_at": execution_finished_at,
        "origin": execution_mode,
        "total_files": len(log_files),
        "files_to_process": len(files_to_process),
        "files_skipped": len(files_skipped),
        "processed_successfully": sum(1 for r in all_results.values() if "error" not in r),
        "errors": sum(1 for r in all_results.values() if "error" in r),
        "files_with_errors": [rel for rel, r in all_results.items() if "error" in r],
        "timestamp_normalization": {
            "total_normalized": total_normalized,
            "failed_to_normalize": total_failed,
            "no_timestamp": total_no_timestamp,
            "unified_format": "dd/mm/yy hh:mm:ss.ms"
        }
    }


def save_execution_summary(storage, output_folder, current_execution):
    """
    Añade current_execution al histórico y lo persiste en _summary.json.

    Returns:
        dict: el histórico completo de ejecuciones (execution_history).
    """
    summary_path = f"{output_folder}_summary.json"
    existing_summary = storage.read_json(summary_path) if storage.exists(summary_path) else {}
    execution_history = existing_summary.get("executions", [])
    execution_history.append(current_execution)

    summary = {
        "last_execution": current_execution,
        "total_executions": len(execution_history),
        "executions": execution_history
    }

    storage.write_json(summary_path, summary)
    return execution_history