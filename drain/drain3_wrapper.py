"""
drain3_wrapper.py 

Envoltorio sobre drain3.TemplateMiner que aplica exactamente la misma
lógica de preprocesado/filtrado de ignore_patterns que usa Drain custom
(drain_custom.Drain).

https://github.com/logpai/Drain3
"""
import re
from typing import List

from drain3 import TemplateMiner

from drain.common.cluster_metrics import (
    extract_clusters_info,
)
from parsing.log_parsing.text_preprocessing import (
    filter_ignored_lines,
    strip_leading_separator_lines,
    compile_ignore_patterns,
)

class Drain3Wrapper:
    """
    Envoltorio sobre drain3.TemplateMiner que aplica exactamente la misma
    lógica de preprocesado/filtrado de ignore_patterns que usa Drain
    custom (drain_custom.Drain), para que ambos engines compartan una
    única fuente de verdad y dejen de reimplementar el filtrado por
    separado en cada script de benchmarking.

    TemplateMiner no soporta ignore_patterns de forma nativa; este
    wrapper resuelve esa carencia reutilizando:
      - strip_leading_separator_lines: limpieza de separadores iniciales.
      - filter_ignored_lines: filtrado línea a línea contra ignore_patterns
        (incluye ya el tratamiento de 'ORCHESTRATION TRACING:').
    """

    def __init__(self, config, ignore_patterns: List[str] = None):
        """
        Args:
            config: TemplateMinerConfig ya construido (ver
                build_template_miner_config / build_message_only_config).
            ignore_patterns (List[str]): patrones regex en crudo a
                ignorar (se compilan aquí, igual que en Drain custom).
        """
        self._template_miner = TemplateMiner(persistence_handler=None, config=config)
        self._compiled_ignore = compile_ignore_patterns(ignore_patterns or [])
        self.ignored_lines_count = 0

    def parse(self, text: str, log_id: int = None):
        """
        Interfaz equivalente a Drain.parse(): aplica strip_leading_separator_lines
        + filter_ignored_lines (misma lógica que Drain custom) y, si el
        texto resultante no queda vacío, lo pasa a TemplateMiner.add_log_message().

        Args:
            text (str): línea o mensaje (puede ser multilínea) a procesar.
            log_id: no usado por TemplateMiner, se mantiene por simetría
                de firma con Drain.parse().

        Returns:
            dict con 'ignored' (bool) y, si no se ignoró, el resultado
            nativo de TemplateMiner (cluster_id, template_mined, change_type).
        """
        if not text or not text.strip():
            return {'ignored': True}

        text = strip_leading_separator_lines(text.strip())

        if self._compiled_ignore:
            text = filter_ignored_lines(text, self._compiled_ignore)
            if not text:
                self.ignored_lines_count += 1
                return {'ignored': True}

        result = self._template_miner.add_log_message(text)
        result['ignored'] = False
        return result

    def get_clusters_info(self):
        """Interfaz equivalente a Drain.get_clusters_info()."""
        return extract_clusters_info(self._template_miner)