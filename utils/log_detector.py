"""
log_detector.py

Módulo de detección de tipo de log basado en nombre de archivo y contenido.
"""
import re
import os

# Caché global de módulos de configuración cargados
_config_cache = {}

def detect_log_type(filename: str, storage=None, file_path=None):
    """
    Detecta el tipo de log basándose en:
    1. El nombre del archivo (usando FILENAME_PATTERNS de cada config)
    2. El contenido del archivo (analizando las primeras líneas)
    
    Args:
        filename: Nombre del archivo (ej: "jdedebug.log")
        storage: Backend de storage (opcional, para análisis de contenido)
        file_path: Ruta completa del archivo (opcional, para análisis de contenido)
    
    Returns:
        str: Tipo de log detectado ("jde", "listener", "alert", "general", etc.)
    """
    
    # ===== PASO 1: DETECCIÓN POR NOMBRE =====
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
    
    for config_file in os.listdir(config_dir):
        if not config_file.endswith("_config.py"):
            continue
        
        log_type = config_file.replace("_config.py", "")
        
        try:
            cfg_module = load_config_module(log_type)
            filename_patterns = getattr(cfg_module, 'FILENAME_PATTERNS', [])
            
            for pattern in filename_patterns:
                if re.search(pattern, filename, re.IGNORECASE):
                    print(f"  ✓ Tipo detectado por nombre: {log_type}")
                    return log_type
        
        except Exception as e:
            continue
    
    # ===== PASO 2: DETECCIÓN POR CONTENIDO =====
    if storage and file_path:
        print(f"  ⚠️  No se pudo detectar por nombre: {filename}")
        print(f"  🔍 Analizando contenido del archivo...")
        
        try:
            # ✅ CAMBIO: Usar read_all_bytes() y decodificar
            content_bytes = storage.read_all_bytes(file_path)
            
            # Leer solo los primeros 50KB para análisis (optimización)
            sample_bytes = content_bytes[:50000]
            sample_text = sample_bytes.decode('utf-8', errors='replace')
            
            # Buscar patrones característicos en el contenido
            for config_file in os.listdir(config_dir):
                if not config_file.endswith("_config.py"):
                    continue
                
                log_type = config_file.replace("_config.py", "")
                
                try:
                    cfg_module = load_config_module(log_type)
                    patterns = getattr(cfg_module, 'PATTERNS', {})
                    
                    # Probar los primeros 100 líneas con cada patrón
                    lines = sample_text.split('\n')[:100]
                    
                    for line in lines:
                        for pattern_name, pattern_regex in patterns.items():
                            if re.search(pattern_regex, line):
                                print(f"  ✓ Detectado por contenido: {log_type} (patrón: {pattern_name})")
                                return log_type
                
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"  ⚠️  Error detectando contenido de {file_path}: {e}")
    
    # ===== FALLBACK: TIPO DESCONOCIDO =====
    print(f"  ❌ No se pudo detectar el tipo de log para: {filename}")
    return "unknown"


def load_config_module(log_type: str):
    """
    Carga dinámicamente el módulo de configuración para un tipo de log.
    Usa caché para evitar reimportaciones.
    
    Args:
        log_type: Tipo de log ("jde", "listener", "alert", etc.)
    
    Returns:
        module: Módulo de configuración cargado
    """
    
    # ✅ Verificar caché
    if log_type in _config_cache:
        return _config_cache[log_type]
    
    try:
        # Cargar módulo dinámicamente
        module_name = f"config.{log_type}_config"
        cfg_module = __import__(module_name, fromlist=[''])
        
        # Guardar en caché
        _config_cache[log_type] = cfg_module
        
        return cfg_module
    
    except ModuleNotFoundError:
        print(f"  ⚠️  Config no encontrada: {log_type}_config.py")
        
        # Fallback a configuración general
        if log_type != "general":
            return load_config_module("general")
        
        return None
    
    except Exception as e:
        print(f"  ⚠️  Error cargando config {log_type}: {e}")
        
        # Fallback a configuración general
        if log_type != "general":
            return load_config_module("general")
        
        return None


def clear_config_cache():
    """
    Limpia la caché de módulos de configuración.
    Útil para forzar recarga en modo desarrollo.
    """
    global _config_cache
    _config_cache.clear()