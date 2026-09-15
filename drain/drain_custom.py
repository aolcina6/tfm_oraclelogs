"""
drain_custom.py 

Implementación custom del algoritmo Drain (sin depender de la librería
drain3), usada por:
  - drain_unified.py (analyze_logs_by_origin, analyze_parsed_logs_with_drain)
  - drain/benchmarking/drain_benchmarking_unified.py. 

He, P., Zhu, J., Zheng, Z., & Lyu, M. R. (2017). Drain: An Online Log Parsing Approach with Fixed Depth Tree. 
IEEE International Conference on Web Services (ICWS).
"""
import os
import re
import sys
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.general_config import TIMESTAMP_PATTERNS
from parsing.log_parsing.multiline_utils import line_starts_new_event
from parsing.log_parsing.text_preprocessing import (
    ORCHESTRATION_LINE_RE,
    _condense_match,
    filter_ignored_lines,
    compile_ignore_patterns
)

PLACEHOLDER_REGEX_MAP = {
    '<TIMESTAMP>': r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}',
    '<NUM>': r'\d+',
    '<IP>': r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
    '<ALPHANUM>': r'[A-Za-z0-9_]+',
    '<UUID>': r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
    '<HEX>': r'0x[0-9a-fA-F]+',
    '<PATH>': r'/[\w/]+',
    '<PID>': r'\d+',
    '<SOAP_ENVELOPE>': r'(?:.|\n)*?',
    '<MIME_PART>': r'(?:.|\n)*?',
    '<BASE64_BLOB>': r'[A-Za-z0-9+/]{40,}={0,2}',
    '<JSON_BLOB>': r'\{(?:.|\n)*?\}',
    '<XML_BLOCK>': r'<[\w:-]+\b[^>]*>(?:.|\n)*?</[\w:-]+>',
    '<PEM_BLOCK>': r'-----BEGIN [A-Z ]+-----(?:.|\n)*?-----END [A-Z ]+-----',
    '<JWT>': r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
    '<STACKTRACE>': r'(?:.*\n?)+',
    '<LONG_LIST>': r'\((?:\s*\d+\s*,)+\s*\d+\s*\)',
    '<URL_WITH_QUERY>': r'https?://[^\s"\'<>]+\?[^\s"\'<>]+',
    '<*>': r'\S+',  # wildcard genérico de Drain (generalización por max_children/similitud)
}

class Node:
    """Nodo del árbol de prefijos utilizado por Drain."""

    def __init__(self, depth: int = 0, digit_or_token: Any = None):
        self.depth = depth
        self.digit_or_token = digit_or_token
        self.children = {}
        self.clusters = []


class LogCluster:
    """Representa un cluster de logs con una plantilla común."""

    def __init__(self, log_template_tokens: List[str], cluster_id: int):
        self.log_template_tokens = log_template_tokens
        self.log_id = cluster_id
        self.size = 0
        self.log_ids = []
        self.log_examples = []

    def add_log_id(self, log_id: int, log_message: str, original_message: str = None):
        self.log_ids.append(log_id)
        self.log_examples.append(original_message if original_message else log_message)
        self.size += 1

    def get_template(self) -> str:
        return ' '.join(self.log_template_tokens)


class Drain:
    """Implementación custom del algoritmo Drain (sin drain3)."""

    def __init__(self, depth: int = 4, st: float = 0.5, max_children: int = 100, max_clusters: int = 1024,
                 ignore_patterns: List[str] = None, timestamp_patterns: List[str] = None,
                 multiline: bool = True):
        """
        Args:
            depth (int): Profundidad del árbol de prefijos.
            st (float): Umbral de similitud para agrupar logs en un cluster.
            max_children (int): Máximo número de hijos por nodo del árbol.
            max_clusters (int): Máximo número de clusters permitidos.
            remove_timestamps (bool): Si True, elimina timestamps de los logs.
            remove_numbers (bool): Si True, normaliza números en los logs.
            ignore_patterns (List[str]): Lista de patrones regex para ignorar líneas.
            timestamp_patterns (List[str]): Lista de patrones regex para detectar timestamps.
            multiline (bool): Si True, agrupa líneas continuadas como un solo log.

        Returns:
            None
        """
        self.depth = depth
        self.st = st
        self.max_children = max_children
        self.max_clusters = max_clusters
        self.multiline = multiline

        self.root_node = Node()
        self.clusters = []
        self.cluster_counter = 0

        self.extra_delimiters = ['=', ':', ',', '(', ')', '[', ']', '{', '}', '<', '>']
        self._delimiter_table = str.maketrans({d: ' ' for d in self.extra_delimiters})

        self.timestamp_patterns = []
        if timestamp_patterns:
            for pattern in timestamp_patterns:
                try:
                    self.timestamp_patterns.append(re.compile(pattern))
                except Exception as e:
                    print(f"⚠️  Error compilando timestamp pattern '{pattern}': {e}")
        else:
            self.timestamp_patterns = [re.compile(p) for p in TIMESTAMP_PATTERNS]

        self.ignore_patterns = compile_ignore_patterns(ignore_patterns) if ignore_patterns else []

        self.number_patterns = [
            (re.compile(r'(?s)<[a-zA-Z0-9]+:Envelope\b.*?</[a-zA-Z0-9]+:Envelope>'), '<SOAP_ENVELOPE>'),
            (re.compile(r'(?s)------=_Part_\d+_\d+\.\d+.*?(?=------=_Part_|\Z)'), '<MIME_PART>'),
            (re.compile(r'\b[A-Za-z0-9+/]{40,}={0,2}\b'), '<BASE64_BLOB>'),
            (re.compile(r'(?s)\{[^{}]{0,20}"[a-zA-Z_][\w]*"\s*:.*?\}(?=\s|,|$)'), '<JSON_BLOB>'),
            (re.compile(r'(?s)<([a-zA-Z][\w:-]*)\b[^>]*>.*?</\1>'), '<XML_BLOCK>'),
            (re.compile(r'(?s)-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----'), '<PEM_BLOCK>'),
            (re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'), '<JWT>'),
            (re.compile(r'(?:^\s*at\s+[\w.$]+\([^)]*\)\s*\n?){2,}'), '<STACKTRACE>\n'),
            (re.compile(r'(?:^\s*File\s+"[^"]+",\s+line\s+\d+.*\n?){2,}'), '<STACKTRACE>\n'),
            (re.compile(r'\((?:\s*\d+\s*,){5,}\s*\d+\s*\)'), '<LONG_LIST>'),
            (re.compile(r'https?://[^\s"\'<>]+\?[^\s"\'<>]+'), '<URL_WITH_QUERY>'),
            (re.compile(r'\b[A-Za-z_][A-Za-z0-9_]*\d+[A-Za-z0-9_]*\b'), '<ALPHANUM>'),
            (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), '<IP>'),
            (re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'), '<UUID>'),
            (re.compile(r'\bTime:\s*\d{2}-[A-Z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2}\b'), 'Time: <TIMESTAMP>'),
            (re.compile(r'\b\d{2,}\b'), '<NUM>'),
            (re.compile(r'\b0x[0-9a-fA-F]+\b'), '<HEX>'),
            (re.compile(r'/[\w/]+/\d+'), '<PATH>'),
            (re.compile(r'\b\d+\.\b'), '<NUM>'),
            (re.compile(r'(/u01/[\w/]+_)\d+(\.trc)'), r'\1<PID>\2'),
        ]

        self.ignored_lines_count = 0
        self.ignored_lines_examples = []
        self.multiline_groups_count = 0
        self.continuation_lines_count = 0

    def _tree_search(self, tokens: List[str]) -> "Node":
        """
        Navega el árbol de prefijos siguiendo el algoritmo original de Drain:
        nivel 1 por longitud de secuencia, niveles siguientes por token
        literal (o comodín '<*>' si el token no tiene hijo propio), hasta
        alcanzar profundidad self.depth o quedarse sin tokens.

        Args:
            tokens (List[str]): Tokens del mensaje de log a buscar.

        Returns:
            Node: nodo hoja alcanzado (puede no existir aún, en cuyo caso
            devuelve None si no hay camino posible en el árbol actual).
        """
        seq_len = len(tokens)

        if seq_len not in self.root_node.children:
            return None

        node = self.root_node.children[seq_len]
        cur_depth = 1

        for token in tokens:
            # profundidad máxima alcanzada (dejamos margen para la raíz y el nivel de longitud)
            if cur_depth >= self.depth - 1 or cur_depth >= seq_len:
                break

            if token in node.children:
                node = node.children[token]
            elif '<*>' in node.children:
                node = node.children['<*>']
            else:
                return None

            cur_depth += 1

        return node

    def _add_cluster_to_tree(self, tokens: List[str], cluster: "LogCluster") -> None:
        """
        Inserta un nuevo cluster en el árbol de prefijos, creando los nodos
        intermedios necesarios (por longitud y por token), respetando
        self.max_children para decidir si un token se generaliza a '<*>'.

        Args:
            tokens (List[str]): Tokens de la plantilla inicial del cluster.
            cluster (LogCluster): Cluster a insertar en la hoja resultante.

        Returns:
            None
        """
        seq_len = len(tokens)

        if seq_len not in self.root_node.children:
            self.root_node.children[seq_len] = Node(depth=1, digit_or_token=seq_len)
        node = self.root_node.children[seq_len]

        cur_depth = 1
        for token in tokens:
            if cur_depth >= self.depth - 1 or cur_depth >= seq_len:
                break

            if token not in node.children:
                if not token[:1].isalnum() and token != '<*>':
                    # tokens muy "raros" (puntuación suelta) se generalizan directamente
                    key = '<*>'
                elif len(node.children) < self.max_children:
                    key = token
                elif '<*>' in node.children:
                    key = '<*>'
                else:
                    key = '<*>'
            else:
                key = token

            if key not in node.children:
                node.children[key] = Node(depth=cur_depth + 1, digit_or_token=key)

            node = node.children[key]
            cur_depth += 1

        node.clusters.append(cluster)

    def group_multiline_logs(self, lines: List[str]) -> List[str]:
        """
        Agrupa líneas continuadas en un solo log si self.multiline es True.
        Usa multiline_utils.line_starts_new_event para detectar el
        inicio de un nuevo evento.

        Args:
            lines (List[str]): Lista de líneas de log.
        
        Returns:
            List[str]: Lista de logs agrupados (cada log puede ser
            multilinea si se detectaron líneas continuadas).
        """
        grouped = []
        current_group = ""

        def _starts_new_event(line: str) -> bool:
            if not self.timestamp_patterns:
                return not (line and line[0] in (' ', '\t', '.', '|'))
            return line_starts_new_event(line, self.timestamp_patterns)

        for line in lines:
            if not _starts_new_event(line):
                if current_group:
                    current_group += '\n' + line
                    self.continuation_lines_count += 1
                else:
                    current_group = line
            else:
                if current_group:
                    grouped.append(current_group)
                    self.multiline_groups_count += 1
                current_group = line

        if current_group:
            grouped.append(current_group)
            self.multiline_groups_count += 1

        return grouped

    def parse(self, log_message: str, log_id: int = None) -> Dict[str, Any]:
        """
        Procesa un mensaje de log, lo agrupa en un cluster y devuelve información relevante.

        Args:
            log_message (str): Mensaje de log a procesar.
            log_id (int): ID del log (opcional).

        Returns:
            Dict[str, Any]: Diccionario con información del log procesado, incluyendo:
                - 'ignored': True si el log fue ignorado, False si fue procesado.
                - 'reason': Motivo por el cual fue ignorado (si aplica).
                - 'original_message': Mensaje original del log.
                - 'processed_message': Mensaje después de preprocesamiento.
                - 'tokens': Lista de tokens del mensaje procesado.
                - 'cluster_id': ID del cluster al que pertenece el log (si aplica).
                - 'template': Plantilla del cluster (si aplica).
                - 'log_id': ID del log.

        Note:
            El filtrado de ignore_patterns replica la lógica de
            parsing/log_parsing/text_preprocessing.py:
              1. Se condensa ORCHESTRATION TRACING antes de evaluar nada,
                 para evitar backtracking catastrófico de los regex de
                 ignore sobre JSON embebido gigante.
              2. Se filtra LÍNEA A LÍNEA (no se descarta el bloque
                 multilínea completo si solo una línea matchea un ignore
                 pattern).
        """
        if log_id is None:
            log_id = len(self.clusters)

        original_message = log_message

        if 'ORCHESTRATION TRACING:' in log_message:
            log_message = ORCHESTRATION_LINE_RE.sub(_condense_match, log_message)

        if self.ignore_patterns:
            filtered_message = filter_ignored_lines(log_message, self.ignore_patterns)

            if not filtered_message:
                self.ignored_lines_count += 1
                if len(self.ignored_lines_examples) < 10:
                    self.ignored_lines_examples.append(original_message[:100])
                return {'ignored': True, 'reason': 'matched_ignore_pattern'}

            log_message = filtered_message

        processed_message = log_message
        for pattern in self.timestamp_patterns:
            processed_message = pattern.sub('<TIMESTAMP>', processed_message)

        for compiled_pattern, replacement in self.number_patterns:
            processed_message = compiled_pattern.sub(replacement, processed_message)

        tokens = self._tokenize(processed_message)

        if not tokens:
            return {'ignored': True, 'reason': 'empty_after_tokenization'}

        cluster = self._search_and_add_to_cluster(tokens, log_id, original_message)

        return {
            'ignored': False,
            'original_message': original_message,
            'processed_message': processed_message,
            'tokens': tokens,
            'cluster_id': cluster.log_id,
            'template': cluster.get_template(),
            'log_id': log_id
        }

    def _tokenize(self, message: str) -> List[str]:
        """
        Tokeniza un mensaje de log reemplazando delimitadores adicionales por espacios
        y luego dividiendo por espacios.

        Args:
            message (str): Mensaje de log a tokenizar.

        Returns:
            List[str]: Lista de tokens.
        """
        return message.translate(self._delimiter_table).split()

    def _search_and_add_to_cluster(self, tokens: List[str], log_id: int, original_message: str) -> LogCluster:
        """
        Busca un cluster existente navegando el árbol de prefijos (búsqueda
        real de Drain: por longitud + tokens, con generalización a '<*>' al
        superar self.max_children). Si encuentra un cluster compatible en la
        hoja alcanzada, actualiza su plantilla y añade el log. Si no, crea
        un nuevo cluster y lo inserta en el árbol.

        Args:
            tokens (List[str]): Tokens del mensaje de log.
            log_id (int): ID del log.
            original_message (str): Mensaje original del log.

        Returns:
            LogCluster: Cluster al que pertenece el log.
        """
        leaf = self._tree_search(tokens)
        log_message_str = ' '.join(tokens)

        if leaf is not None:
            for cluster in leaf.clusters:
                if self._match_cluster(tokens, cluster):
                    self._update_template(tokens, cluster)
                    cluster.add_log_id(log_id, log_message_str, original_message)
                    return cluster

        new_cluster = LogCluster(list(tokens), len(self.clusters))
        new_cluster.add_log_id(log_id, log_message_str, original_message)
        self.clusters.append(new_cluster)
        self.cluster_counter += 1
        self._add_cluster_to_tree(tokens, new_cluster)

        return new_cluster

    def _match_cluster(self, tokens: List[str], cluster: LogCluster) -> bool:
        """
        Comprueba si los tokens del log coinciden con la plantilla del cluster
        (misma longitud + proporción de tokens iguales o ya comodín >= st).
        Solo se invoca sobre la lista corta de clusters de una hoja del
        árbol, no sobre todos los clusters descubiertos.

        Args:
            tokens (List[str]): Tokens del mensaje de log.
            cluster (LogCluster): Cluster a comparar.

        Returns:
            bool: True si coincide, False en caso contrario.
        """
        if len(tokens) != len(cluster.log_template_tokens):
            return False

        matches = sum(1 for t, ct in zip(tokens, cluster.log_template_tokens)
                      if t == ct or ct.startswith('<'))

        return matches / len(tokens) >= self.st

    def _update_template(self, tokens: List[str], cluster: LogCluster) -> None:
        """
        Actualiza la plantilla del cluster generalizando a '<*>' aquellos
        tokens que difieren entre el log actual y la plantilla existente.
        Parte intrínseca del algoritmo Drain: sin esto, las posiciones
        variables nunca se generalizarían tras el primer log del cluster.

        Args:
            tokens (List[str]): Tokens del log actual (misma longitud que
                la plantilla, ya garantizado por _match_cluster).
            cluster (LogCluster): Cluster cuya plantilla se actualiza.

        Returns:
            None
        """
        template = cluster.log_template_tokens
        for i, (t, ct) in enumerate(zip(tokens, template)):
            if ct.startswith('<'):
                continue
            if t != ct:
                template[i] = '<*>'

    def get_clusters_info(self) -> List[Dict[str, Any]]:
        """
        Devuelve información resumida de todos los clusters descubiertos.

        Returns:
            List[Dict[str, Any]]: Lista de diccionarios con información de cada cluster:
                - 'cluster_id': ID del cluster.
                - 'template': Plantilla del cluster.
                - 'size': Número de logs en el cluster.
                - 'log_ids': Lista de IDs de logs en el cluster (máx. 100).
                - 'examples': Lista de ejemplos de logs en el cluster (máx. 5).
        """
        clusters_sorted = sorted(self.clusters, key=lambda c: c.size, reverse=True)
        return [
            {
                'cluster_id': cluster.log_id,
                'template': cluster.get_template(),
                'size': cluster.size,
                'log_ids': cluster.log_ids[:100],
                'examples': cluster.log_examples[:5]
            }
            for cluster in clusters_sorted
        ]

    def generate_regex_patterns(self) -> List[Dict[str, Any]]:
        """
        Genera patrones regex a partir de los clusters descubiertos.

        Returns:
            List[Dict[str, Any]]: Lista de diccionarios con información de cada patrón:
                - 'template': Plantilla del cluster.
                - 'regex': Patrón regex generado a partir de la plantilla.
                - 'occurrences': Número de logs en el cluster.
                - 'cluster_id': ID del cluster.
                - 'examples': Lista de ejemplos de logs en el cluster (máx. 5).
        """
        patterns = []

        for cluster in sorted(self.clusters, key=lambda c: c.size, reverse=True):
            template = cluster.get_template()
            regex_parts = []

            for token in cluster.log_template_tokens:
                if token in PLACEHOLDER_REGEX_MAP:
                    regex_parts.append(PLACEHOLDER_REGEX_MAP[token])
                else:
                    regex_parts.append(re.escape(token))

            regex = r'\s+'.join(regex_parts)

            patterns.append({
                'template': template,
                'regex': regex,
                'occurrences': cluster.size,
                'cluster_id': cluster.log_id,
                'examples': cluster.log_examples[:5]
            })

        return patterns