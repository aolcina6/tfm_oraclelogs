"""
regex_cache.py 

Módulo de caché global para regex compiladas.
Mejora el rendimiento evitando recompilar los mismos patrones.
"""

import re
from typing import Optional, Pattern, Union

# ===== CACHÉ GLOBAL DE REGEX COMPILADAS =====
_REGEX_CACHE: dict[str, Optional[Pattern]] = {}
_CACHE_ENABLED = True  # Flag para desactivar caché si causa problemas


def enable_cache(enabled: bool = True):
    """
    Activa o desactiva la caché de regex.
    Útil para debugging si la caché causa problemas.

    Args:
        enabled: True para activar, False para desactivar
    """
    global _CACHE_ENABLED
    _CACHE_ENABLED = enabled
    if not enabled:
        print("⚠️  Caché de regex DESACTIVADA")


def get_compiled_regex(pattern: str, flags: int = 0) -> Optional[Pattern]:
    """
    Obtiene una regex compilada desde caché o la compila y cachea.
    
    Args:
        pattern: Patrón regex como string
        flags: Flags de re.compile (re.IGNORECASE, etc.)
    
    Returns:
        Pattern compilado o None si hay error
    
    Ejemplo:
        >>> regex = get_compiled_regex(r'\d{4}-\d{2}-\d{2}')
        >>> if regex:
        >>>     match = regex.search("2024-01-15")
    """
    if not _CACHE_ENABLED:
        # Si la caché está desactivada, compilar directamente
        try:
            return re.compile(pattern, flags)
        except re.error:
            return None
    
    # Crear clave única que incluye flags
    cache_key = f"{pattern}|{flags}" if flags else pattern
    
    if cache_key not in _REGEX_CACHE:
        try:
            _REGEX_CACHE[cache_key] = re.compile(pattern, flags)
        except re.error as e:
            # Solo mostrar error la primera vez
            print(f"⚠️  Error compilando regex: {pattern[:80]}...")
            print(f"    Error: {e}")
            _REGEX_CACHE[cache_key] = None
            return None
    
    return _REGEX_CACHE[cache_key]


def compile_pattern(pattern: Union[str, Pattern], flags: int = 0) -> Optional[Pattern]:
    """
    Compila un patrón solo si es string.Si ya es un Pattern compilado, lo devuelve tal cual.
        
    Args:
        pattern: String o Pattern ya compilado
        flags: Flags de compilación (solo si pattern es string)
    
    Returns:
        Pattern compilado o None
    
    Ejemplo:
        >>> # Funciona con strings
        >>> regex = compile_pattern(r'\d+')
        >>> 
        >>> # También funciona con Pattern ya compilado (no hace nada)
        >>> existing = re.compile(r'\d+')
        >>> regex = compile_pattern(existing)  # Devuelve existing sin cambios
    """
    # Si ya es un Pattern compilado, devolverlo tal cual
    if isinstance(pattern, re.Pattern):
        return pattern
    
    # Si es string, compilar con caché
    if isinstance(pattern, str):
        return get_compiled_regex(pattern, flags)
    
    # Tipo no soportado
    return None


def clear_cache():
    """
    Limpia la caché de regex.
    Útil al final de cada ejecución o para testing.
    """
    global _REGEX_CACHE
    size = len(_REGEX_CACHE)
    _REGEX_CACHE.clear()
    if size > 0:
        print(f"🧹 Caché de regex limpiada ({size} patrones)")


def get_cache_stats() -> dict:
    """
    Retorna estadísticas de la caché.
    
    Returns:
        dict con:
        - total_patterns: Total de patrones en caché
        - valid: Patrones compilados exitosamente
        - invalid: Patrones que fallaron al compilar
        - cache_enabled: Si la caché está activa
    """
    if not _CACHE_ENABLED:
        return {
            'total_patterns': 0,
            'valid': 0,
            'invalid': 0,
            'cache_enabled': False
        }
    
    valid_patterns = sum(1 for v in _REGEX_CACHE.values() if v is not None)
    invalid_patterns = sum(1 for v in _REGEX_CACHE.values() if v is None)
    
    return {
        'total_patterns': len(_REGEX_CACHE),
        'valid': valid_patterns,
        'invalid': invalid_patterns,
        'cache_enabled': _CACHE_ENABLED
    }


def precompile_patterns(patterns: list[str]) -> dict[str, Optional[Pattern]]:
    """
    Pre-compila una lista de patrones y los guarda en caché.
    Útil para compilar todos los patrones al inicio del procesamiento.
    
    Args:
        patterns: Lista de strings con patrones regex
    
    Returns:
        dict: {pattern_string: compiled_pattern_or_None}
    
    Ejemplo:
        >>> patterns = [r'\d+', r'[A-Z]+', r'invalid(']
        >>> compiled = precompile_patterns(patterns)
        >>> print(f"Compilados: {sum(1 for p in compiled.values() if p)}")
    """
    compiled = {}
    for pattern in patterns:
        compiled[pattern] = get_compiled_regex(pattern)
    return compiled


# ===== FUNCIONES DE COMPATIBILIDAD RETROACTIVA =====

def search(pattern: str, text: str, flags: int = 0):
    """
    Wrapper de re.search() que usa caché.
    Compatible 100% con re.search().
    """
    compiled = get_compiled_regex(pattern, flags)
    if compiled:
        return compiled.search(text)
    return None


def match(pattern: str, text: str, flags: int = 0):
    """
    Wrapper de re.match() que usa caché.
    Compatible 100% con re.match().
    """
    compiled = get_compiled_regex(pattern, flags)
    if compiled:
        return compiled.match(text)
    return None


def findall(pattern: str, text: str, flags: int = 0):
    """
    Wrapper de re.findall() que usa caché.
    Compatible 100% con re.findall().
    """
    compiled = get_compiled_regex(pattern, flags)
    if compiled:
        return compiled.findall(text)
    return []


def finditer(pattern: str, text: str, flags: int = 0):
    """
    Wrapper de re.finditer() que usa caché.
    Compatible 100% con re.finditer().
    """
    compiled = get_compiled_regex(pattern, flags)
    if compiled:
        return compiled.finditer(text)
    return iter([])