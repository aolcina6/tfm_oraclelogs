"""
init.py 

Módulo principal de ejecución del pipeline de parsing de logs. Detecta el tipo de log,
carga la configuración correspondiente, procesa los archivos y genera resultados en Parquet o JSON.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json
from collections import defaultdict
from datetime import datetime
from utils.utils import group_records_by_day
from storage.factory import get_storage_backend
from storage.decompress import extract_archives
from utils.log_detector import detect_log_type, load_config_module
from parsing.regex_cache import clear_cache
from parsing.registry import load_processed_files_registry, save_processed_files_registry
from parsing.template_classifier import clear_templates_cache
from parsing.log_parsing import autodiscover_config

from parsing.pipeline import (
    should_process_file,
    process_incremental_file,
    enrich_records,
    write_grouped_records,
    write_grouped_records_json,
    clear_learning_queue,
    write_learning_queue,
    build_execution_summary,
    save_execution_summary,
)

# Permite forzar/desactivar la ingesta a OpenSearch
ENV_INGEST_FLAG = "PARSING_NO_OPENSEARCH"


class PerformanceTracker:
    """
    Recoge tiempos de ejecución por fichero, fase y origen para poder
    generar un desglose de rendimiento del pipeline de parsing.

    Fases medidas por fichero:
        - parse: autodiscover_config() / process_incremental_file()
        - enrich: enrich_records()
        - group: group_records_by_day()
        - write: write_grouped_records() (+ write_learning_queue si aplica)
        - total: suma de las anteriores + overhead misceláneo del bucle

    Al finalizar, permite construir un resumen agregado por origen
    (log_type) con medias, mínimos, máximos y totales por fase.
    """

    def __init__(self):
        self._per_file = []  # lista de dicts: {rel_path, log_type, phases:{...}, total}

    def record_file(self, rel_path: str, log_type: str, phases: dict, total: float,
                     records_count: int = 0):
        self._per_file.append({
            'rel_path': rel_path,
            'log_type': log_type,
            'phases': phases,
            'total_seconds': total,
            'records_count': records_count,
        })

    def build_summary(self) -> dict:
        """
        Devuelve un dict con:
          - 'by_origin': {log_type: {phase: {sum, avg, min, max, count}, ...,
                                       total: {...}, files_count, records_count,
                                       avg_seconds_per_record}}
          - 'global': mismas métricas agregadas sobre todos los orígenes
          - 'per_file': detalle fichero a fichero (para depuración fina)
        """
        by_origin = defaultdict(lambda: defaultdict(list))
        origin_records = defaultdict(int)
        origin_files = defaultdict(int)

        global_phases = defaultdict(list)
        global_records = 0
        global_files = 0

        for entry in self._per_file:
            log_type = entry['log_type'] or "unknown"
            origin_files[log_type] += 1
            origin_records[log_type] += entry['records_count']
            global_files += 1
            global_records += entry['records_count']

            for phase, seconds in entry['phases'].items():
                by_origin[log_type][phase].append(seconds)
                global_phases[phase].append(seconds)

            by_origin[log_type]['total'].append(entry['total_seconds'])
            global_phases['total'].append(entry['total_seconds'])

        def _stats(values: list) -> dict:
            if not values:
                return {'sum': 0.0, 'avg': 0.0, 'min': 0.0, 'max': 0.0, 'count': 0}
            return {
                'sum': round(sum(values), 4),
                'avg': round(sum(values) / len(values), 4),
                'min': round(min(values), 4),
                'max': round(max(values), 4),
                'count': len(values),
            }

        by_origin_summary = {}
        for log_type, phases_dict in by_origin.items():
            phase_stats = {phase: _stats(values) for phase, values in phases_dict.items()}
            total_seconds = phase_stats.get('total', {}).get('sum', 0.0)
            records = origin_records[log_type]
            by_origin_summary[log_type] = {
                'files_count': origin_files[log_type],
                'records_count': records,
                'phases': phase_stats,
                'avg_seconds_per_file': round(total_seconds / origin_files[log_type], 4) if origin_files[log_type] else 0.0,
                'avg_seconds_per_record': round(total_seconds / records, 6) if records else 0.0,
            }

        global_stats = {phase: _stats(values) for phase, values in global_phases.items()}
        global_total = global_stats.get('total', {}).get('sum', 0.0)

        return {
            'by_origin': by_origin_summary,
            'global': {
                'files_count': global_files,
                'records_count': global_records,
                'phases': global_stats,
                'avg_seconds_per_file': round(global_total / global_files, 4) if global_files else 0.0,
                'avg_seconds_per_record': round(global_total / global_records, 6) if global_records else 0.0,
            },
            'per_file': self._per_file,
        }

    def format_summary(self, summary: dict = None) -> str:
        """
        Genera el mismo desglose que 'print_summary' pero como texto,
        para poder guardarlo en fichero además de imprimirlo por consola.
        """
        summary = summary if summary is not None else self.build_summary()
        lines = []

        lines.append(f"{'='*70}")
        lines.append(f"⏱️  MÉTRICAS DE RENDIMIENTO POR ORIGEN")
        lines.append(f"{'='*70}")

        for log_type, data in sorted(summary['by_origin'].items(),
                                      key=lambda kv: kv[1]['phases'].get('total', {}).get('sum', 0),
                                      reverse=True):
            total_stats = data['phases'].get('total', {})
            lines.append(f"\n📁 Origen: {log_type}")
            lines.append(f"   Ficheros procesados: {data['files_count']} | Registros: {data['records_count']}")
            lines.append(f"   Tiempo total: {total_stats.get('sum', 0):.3f}s | "
                          f"Media/fichero: {data['avg_seconds_per_file']:.3f}s | "
                          f"Media/registro: {data['avg_seconds_per_record']*1000:.3f}ms")
            lines.append(f"   Desglose por fase:")
            for phase in ('parse', 'enrich', 'group', 'write'):
                stats = data['phases'].get(phase)
                if stats:
                    lines.append(f"     - {phase:8s}: total={stats['sum']:8.3f}s  "
                                  f"media={stats['avg']:7.4f}s  "
                                  f"min={stats['min']:7.4f}s  max={stats['max']:7.4f}s")

        g = summary['global']
        lines.append(f"\n{'='*70}")
        lines.append(f"🌍 GLOBAL (todos los orígenes)")
        lines.append(f"{'='*70}")
        lines.append(f"   Ficheros: {g['files_count']} | Registros: {g['records_count']}")
        lines.append(f"   Tiempo total: {g['phases'].get('total', {}).get('sum', 0):.3f}s | "
                      f"Media/fichero: {g['avg_seconds_per_file']:.3f}s | "
                      f"Media/registro: {g['avg_seconds_per_record']*1000:.3f}ms")
        for phase in ('parse', 'enrich', 'group', 'write'):
            stats = g['phases'].get(phase)
            if stats:
                lines.append(f"     - {phase:8s}: total={stats['sum']:8.3f}s  "
                              f"media={stats['avg']:7.4f}s  "
                              f"min={stats['min']:7.4f}s  max={stats['max']:7.4f}s")
        lines.append(f"{'='*70}\n")

        return "\n".join(lines)

    def print_summary(self):
        summary = self.build_summary()
        print("\n" + self.format_summary(summary))
        return summary

    def save_summary_to_file(self, storage, output_folder: str, summary: dict = None,
                              execution_started_at: str = None) -> str:
        """
        Guarda el desglose de rendimiento (texto legible) en
        '<output_folder>/performance_metrics.txt', usando el backend de
        storage (LOCAL o S3), en modo append para conservar histórico.
        """
        summary = summary if summary is not None else self.build_summary()
        header = f"\n{'#'*70}\n# Ejecución: {execution_started_at or datetime.now().isoformat(timespec='seconds')}\n{'#'*70}\n"
        text = header + self.format_summary(summary)

        text_path = os.path.join(output_folder, "performance_metrics.txt")

        existing_text = ""
        try:
            if storage.exists(text_path):
                existing_bytes = storage.read_bytes(text_path)
                existing_text = existing_bytes.decode("utf-8")
        except Exception:
            existing_text = ""

        storage.write_bytes(text_path, (existing_text + text).encode("utf-8"))
        return text_path


def parsing_execution(log_folder: str = "logs/", ingest_to_opensearch: bool = False,
                       output_folder: str = "parsed_logs",
                       enable_performance_tracking: bool = False,
                       results_output_format: str = "parquet"):
    """
    Ejecuta el pipeline de parsing.

    Args:
        log_folder (str): Carpeta local donde están los logs a procesar.
                           Solo se usa si execution_mode == "LOCAL"; en S3
                           siempre se parte de la raíz del bucket.
        output_folder (str): Carpeta donde se guardan los resultados
                              parseados (default: "parsed_logs").
        enable_performance_tracking (bool): Si True, mide tiempos por fase/
                              origen y genera 'performance_metrics.*' al
                              finalizar. Desactivado por defecto para no
                              añadir overhead en ejecuciones normales.
        results_output_format (str): Formato de los ficheros de resultados
                              parseados: 'parquet' (default, eficiente para
                              producción) o 'json' (más legible, útil para
                              debugging).
    """
    if results_output_format not in ("parquet", "json"):
        raise ValueError(
            f"results_output_format debe ser 'parquet' o 'json', "
            f"recibido: '{results_output_format}'"
        )

    env_value = os.environ.get(ENV_INGEST_FLAG)
    if env_value is not None:
        ingest_to_opensearch = env_value.strip().lower() in ("1", "true", "yes")

    storage, execution_mode = get_storage_backend()

    print(f"\n{'='*60}")
    print(f"🌐 INFORMACIÓN DE EJECUCIÓN")
    print(f"{'='*60}")
    print(f"Execution Mode: {execution_mode}")
    print(f"Storage Class: {storage.__class__.__name__}")
    print(f"Storage Bucket (si S3): {getattr(storage, 'bucket', 'N/A')}")
    print(f"Formato resultados: {results_output_format}")
    print(f"Performance tracking: {'ON' if enable_performance_tracking else 'OFF'}")
    print(f"{'='*60}\n")

    if execution_mode == "S3":
        log_folder = ""
    elif not log_folder:
        raise ValueError(
            "En modo LOCAL, 'log_folder' es obligatorio: indica la ruta "
            "donde están los archivos .log a procesar (ej: 'logs/')."
        )
    elif not log_folder.endswith("/"):
        log_folder += "/"

    if not output_folder.endswith("/"):
        output_folder += "/"

    print(f"📂 Log folder: {log_folder or '(raíz)'}")
    print(f"📂 Output folder: {output_folder}")

    print(f"\n{'='*60}")
    print(f"🧹 LIMPIEZA INICIAL")
    print(f"{'='*60}")
    clear_learning_queue(storage, output_folder)

    print(f"🧹 Limpiando caché de regex...")
    clear_cache()
    clear_templates_cache()

    processed_registry = load_processed_files_registry(storage, output_folder)
    print(f"📋 Archivos previamente procesados: {len(processed_registry)}")

    print(f"\n📦 Buscando archivos comprimidos en: {log_folder or '(raíz del bucket)'}")
    extract_archives(storage, log_folder, delete_after_extract=False, exclude_prefix=output_folder)

    print(f"\nBuscando logs en: {log_folder or '(raíz del bucket)'}")

    log_files = storage.list_files(log_folder, ".log", exclude_prefix=output_folder)
    if not log_files:
        print("No se encontraron archivos de log.")
        return

    print(f"✓ Archivos de log encontrados: {len(log_files)}")

    # Filtrar archivos que ya fueron procesados
    files_to_process = []
    files_skipped = []

    for file_path, rel_path in log_files:
        # Detectar tipo de log y cargar módulo de configuración
        file_name = os.path.basename(rel_path)
        log_type = detect_log_type(file_name, storage=storage, file_path=file_path)
        cfg_module = load_config_module(log_type)
        is_incremental = getattr(cfg_module, 'INCREMENTAL', False)

        # Si el archivo es incremental, lo procesamos siempre (no se registra en processed_registry)
        if is_incremental:
            files_to_process.append((file_path, rel_path, log_type, cfg_module))
            continue

        # Si no es incremental, verificamos si ya fue procesado previamente
        should_proc, reason = should_process_file(storage, file_path, rel_path, processed_registry)

        if should_proc:
            files_to_process.append((file_path, rel_path, log_type, cfg_module))
        else:
            files_skipped.append(rel_path)

    print(f"\n📊 Resumen de filtrado:")
    print(f"  Total encontrados: {len(log_files)}")
    print(f"  A procesar: {len(files_to_process)}")
    print(f"  Omitidos (ya procesados): {len(files_skipped)}")

    if not files_to_process:
        print("\nNo hay archivos nuevos o modificados para procesar.")
        return

    # Cargar offsets_state para archivos incrementales
    offsets_path = os.path.join(output_folder, "offsets_state.json")
    offsets_state = storage.read_json(offsets_path) if storage.exists(offsets_path) else {}

    all_results = {}
    total_normalized = 0
    total_failed = 0
    total_no_timestamp = 0

    # Tracker de métricas de rendimiento (solo si está habilitado)
    perf_tracker = PerformanceTracker() if enable_performance_tracking else None

    execution_started_at = datetime.now().isoformat(timespec='seconds')

    # Recorremos los archivos a procesar, parseando, enriqueciendo y escribiendo resultados
    for file_path, rel_path, log_type, cfg_module in files_to_process:
        print(f"\n{'='*60}")
        print(f"Analizando archivo: {rel_path}")
        print(f"{'='*60}")

        file_start = time.perf_counter() if enable_performance_tracking else None
        phase_times = {}

        try:
            print(f"  ✓ Tipo detectado: {log_type}")
            is_incremental = getattr(cfg_module, 'INCREMENTAL', False)

            # --- FASE: parse ---
            t0 = time.perf_counter() if enable_performance_tracking else None
            if is_incremental:
                result = process_incremental_file(storage, file_path, rel_path, offsets_state, log_type, cfg_module)
                if result is None:
                    print(f"  ⚠️  No se pudo procesar {rel_path}")
                    if enable_performance_tracking:
                        phase_times['parse'] = time.perf_counter() - t0
                        perf_tracker.record_file(rel_path, log_type, phase_times, time.perf_counter() - file_start)
                    continue
            else:
                result = autodiscover_config(file_path, storage=storage, log_type=log_type, cfg_module=cfg_module)
                if result is None:
                    print(f"  ⚠️  No se pudo procesar {rel_path}")
                    if enable_performance_tracking:
                        phase_times['parse'] = time.perf_counter() - t0
                        perf_tracker.record_file(rel_path, log_type, phase_times, time.perf_counter() - file_start)
                    continue

            if enable_performance_tracking:
                phase_times['parse'] = time.perf_counter() - t0

            # --- FASE: enrich ---
            t0 = time.perf_counter() if enable_performance_tracking else None
            result = enrich_records(result, log_type)
            if enable_performance_tracking:
                phase_times['enrich'] = time.perf_counter() - t0

            total_normalized += result['normalization_stats']['normalized']
            total_failed += result['normalization_stats']['failed']
            total_no_timestamp += result['normalization_stats']['no_timestamp']

            all_results[rel_path] = result

            log_type = result.get('log_type') or result.get('config', {}).get('log_type')

            # --- FASE: group ---
            t0 = time.perf_counter() if enable_performance_tracking else None
            grouped = group_records_by_day(result['records'], rel_path)
            if enable_performance_tracking:
                phase_times['group'] = time.perf_counter() - t0

            unmatched = result.pop('unmatched', [])

            no_timestamp_records = result.pop('no_timestamp_records', [])
            for entry in no_timestamp_records:
                if isinstance(entry, dict) and 'reason' not in entry:
                    entry['reason'] = 'NO_TIMESTAMP'
            unmatched = unmatched + no_timestamp_records

            result.pop('_internal_config', None)
            result.pop('config', None)
            result.pop('normalization_stats', None)

            print(f"\n📦 Distribuyendo {len(result['records'])} registros en {len(grouped)} archivo(s) parquet...")

            # --- FASE: write ---
            t0 = time.perf_counter() if enable_performance_tracking else None
            if results_output_format == "json":
                write_grouped_records_json(storage, output_folder, grouped, log_type, rel_path)
            else:
                write_grouped_records(storage, output_folder, grouped, log_type, rel_path)

            has_unmatched = len(unmatched) > 0

            if unmatched:
                write_learning_queue(storage, output_folder, rel_path, unmatched)
            if enable_performance_tracking:
                phase_times['write'] = time.perf_counter() - t0

            if not is_incremental and not has_unmatched:
                try:
                    file_size = storage.get_file_size(file_path)
                except Exception:
                    file_size = 0

                processed_registry[rel_path] = {
                    'last_processed': datetime.now().isoformat(),
                    'size_bytes': file_size,
                    'records_count': len(result['records']),
                    'log_type': log_type,
                    'unmatched_lines': 0
                }
                print(f"  ✅ Archivo registrado como procesado completamente")

            elif not is_incremental and has_unmatched:
                try:
                    file_size = storage.get_file_size(file_path)
                except Exception:
                    file_size = 0

                processed_registry[rel_path] = {
                    'last_processed': datetime.now().isoformat(),
                    'size_bytes': file_size,
                    'records_count': len(result['records']),
                    'log_type': log_type,
                    'unmatched_lines': len(unmatched),
                    'needs_reprocessing': True
                }
                print(f"  ⚠️  Archivo marcado para reprocesamiento futuro ({len(unmatched)} líneas pendientes)")

            # Registro de métricas del fichero (caso exitoso)
            if enable_performance_tracking:
                file_total_time = time.perf_counter() - file_start
                perf_tracker.record_file(
                    rel_path, log_type, phase_times, file_total_time,
                    records_count=len(result['records'])
                )



        except Exception as e:
            print(f"✗ Error procesando {rel_path}: {e}")
            import traceback
            traceback.print_exc()
            all_results[rel_path] = {"error": str(e)}
            # ⏱️ Registramos igualmente el tiempo consumido hasta el fallo
            if enable_performance_tracking:
                perf_tracker.record_file(rel_path, log_type, phase_times, time.perf_counter() - file_start)

    storage.write_json(offsets_path, offsets_state)
    # Guardamos el registro de archivos procesados al final de la ejecución
    save_processed_files_registry(storage, output_folder, processed_registry)

    current_execution = build_execution_summary(
        execution_started_at, execution_mode, log_files, files_to_process,
        files_skipped, all_results, total_normalized, total_failed, total_no_timestamp,
    )
    execution_history = save_execution_summary(storage, output_folder, current_execution)

    # Solo si el tracking de performance está habilitado
    if enable_performance_tracking:
        performance_summary = perf_tracker.print_summary()

        performance_text_path = perf_tracker.save_summary_to_file(
            storage, output_folder, performance_summary, execution_started_at
        )
        print(f"💾 Métricas de rendimiento (texto) guardadas en: {performance_text_path}")

    print(f"\n{'='*60}")
    print(f"RESUMEN FINAL — Modo: {execution_mode}")
    print(f"{'='*60}")
    print(f"Ejecución #{len(execution_history)}")
    print(f"Archivos totales: {len(log_files)}")
    print(f"Procesados: {len(files_to_process)}")
    print(f"Omitidos: {len(files_skipped)}")
    print(f"Exitosos: {current_execution['processed_successfully']}")
    print(f"Errores: {current_execution['errors']}")
    print(f"Guardados en: {output_folder}")
    print(f"{'='*60}\n")

    if ingest_to_opensearch:
        print(f"\n{'='*60}")
        print(f"📤 INGESTA A OPENSEARCH")
        print(f"{'='*60}")
        try:
            from opensearch.ingest import ingest_execution_to_opensearch

            successfully_processed_rel_paths = [
                rel_path for rel_path, result in all_results.items()
                if isinstance(result, dict) and "error" not in result
            ]

            ingest_stats = ingest_execution_to_opensearch(
                storage=storage,
                output_folder=output_folder,
                rel_paths=successfully_processed_rel_paths,
            )
            print(f"✅ Ingesta completada: {ingest_stats}")
        except Exception as e:
            print(f"❌ Error durante la ingesta a OpenSearch: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ejecuta el pipeline de parsing de logs (Parquet/JSON, local o S3)."
    )
    parser.add_argument(
        "--log-folder", type=str, default="logs/",
        help="Carpeta local donde están los logs a procesar (solo aplica en modo LOCAL). Default: logs/",
    )
    parser.add_argument(
        "--output-folder", type=str, default="parsed_logs",
        help="Carpeta donde se guardan los resultados parseados. Default: parsed_logs",
    )
    parser.add_argument(
        "--ingest-to-opensearch", action="store_true",
        help="Si se indica, ingesta los resultados parseados a OpenSearch al finalizar.",
    )
    parser.add_argument(
        "--enable-performance-tracking", action="store_true",
        help="Si se indica, mide tiempos por fase/origen y genera 'performance_metrics.*'.",
    )
    parser.add_argument(
        "--results-output-format", type=str, default="parquet",
        choices=["parquet", "json"],
        help="Formato de los ficheros de resultados parseados. Default: parquet",
    )

    args = parser.parse_args()

    parsing_execution(
        log_folder=args.log_folder,
        ingest_to_opensearch=args.ingest_to_opensearch,
        output_folder=args.output_folder,
        enable_performance_tracking=args.enable_performance_tracking,
        results_output_format=args.results_output_format,
    )