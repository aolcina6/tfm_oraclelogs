#!/usr/bin/env python3
"""
semantic_grouping.py

Agrupa los templates minados por Drain3 (ej: ais_template.json,
jde_template.json) en función de su similitud SEMÁNTICA, usando
embeddings + similitud coseno + clustering jerárquico aglomerativo.

Útil cuando Drain3 genera cientos de templates casi-duplicados
(pequeñas variaciones de orden/repetición en logs multilínea, como los
"Fatal NI connect error..." de alert_jde) que en realidad representan
el MISMO tipo de evento semántico.

Uso:
    python drain/semantic_grouping.py templates/alert_jde_template.json
    python drain/semantic_grouping.py templates/alert_jde_template.json --threshold 0.15
"""
import json
import sys
import argparse
import re
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from sklearn.cluster import AgglomerativeClustering

# ============================================================
# Normalización de texto: colapsar placeholders repetidos para
# que la métrica semántica no se vea dominada por cuántas veces
# se repite "Fatal NI connect error <NUM>." en el mensaje.
# ============================================================
_PLACEHOLDER_RE = re.compile(r'<[A-Z_*]+>')


def normalize_template(template: str) -> str:
    """
    Colapsa placeholders consecutivos repetidos y espacios múltiples,
    para que la comparación semántica se centre en la ESTRUCTURA del
    mensaje (qué tipo de evento es) y no en cuántas veces se repite.
    """
    text = _PLACEHOLDER_RE.sub('X', template)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============================================================
# Embeddings: sentence-transformers si está disponible, si no,
# fallback a TF-IDF + SVD (no requiere descargar modelos ni GPU).
# ============================================================
def get_embeddings(texts: list) -> np.ndarray:
    """
    Genera embeddings vectoriales para una lista de textos, usando TF-IDF + SVD.

    Args:
        texts (list): Lista de strings a vectorizar.

    Returns:
        np.ndarray: Matriz de embeddings normalizados (shape: [n_texts, n_components]).
    """
    print("🔤 Usando TF-IDF + SVD...")
    vectorizer = TfidfVectorizer(
        analyzer='word',
        token_pattern=r'[A-Za-z_]+|\d+|[^\sA-Za-z0-9]',
        ngram_range=(1, 2),
        max_features=5000,
    )
    tfidf = vectorizer.fit_transform(texts)

    n_components = min(100, tfidf.shape[0] - 1, tfidf.shape[1] - 1)
    n_components = max(n_components, 2)
    svd = TruncatedSVD(n_components=n_components, random_state=42)
    embeddings = svd.fit_transform(tfidf)

    # Para evitar vectores nulos (muy cortos o casi vacíos), se les añade un ruido mínimo 
    # para que tengan norma > 0 sin distorsionar demasiado la distancia coseno
    norms = np.linalg.norm(embeddings, axis=1)
    zero_mask = norms == 0
    if zero_mask.any():
        print(f"⚠️  {zero_mask.sum()} template(s) con embedding nulo tras SVD "
              f"(probablemente texto casi vacío tras normalizar) — "
              f"se les añade ruido mínimo para permitir distancia coseno.")
        rng = np.random.RandomState(42)
        embeddings[zero_mask] += rng.normal(scale=1e-6, size=(zero_mask.sum(), embeddings.shape[1]))

    return normalize(embeddings)


# ============================================================
# Clustering jerárquico con distancia coseno
# ============================================================
def cluster_embeddings(embeddings: np.ndarray, distance_threshold: float):
    """
    Agrupa los embeddings usando AgglomerativeClustering con distancia coseno.

    Args:
        embeddings (np.ndarray): Matriz de embeddings normalizados.
        distance_threshold (float): Umbral de distancia coseno para formar grupos.

    Returns:
        np.ndarray: Array de etiquetas de grupo para cada embedding.
    """
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric='cosine',
        linkage='average',
    )
    labels = clustering.fit_predict(embeddings)
    return labels


def find_representative(embeddings: np.ndarray, indices: list) -> int:
    """
    Dentro de un grupo, devuelve el índice (dentro de 'indices') del
    elemento más cercano al centroide del grupo — usado como template
    "representativo" para mostrar en el resumen.

    Args:
        embeddings (np.ndarray): Matriz de embeddings normalizados.
        indices (list): Lista de índices de los elementos del grupo.

    Returns:
        int: Índice del elemento más representativo dentro de 'indices'.
    """
    if len(indices) == 1:
        return indices[0]

    group_embeddings = embeddings[indices]
    centroid = group_embeddings.mean(axis=0)
    distances = np.linalg.norm(group_embeddings - centroid, axis=1)
    best_local_idx = np.argmin(distances)
    return indices[best_local_idx]


def semantic_group_templates(input_path: str, distance_threshold: float = 0.7) -> dict:
    """
    Agrupa semánticamente los templates de Drain3 en un JSON con la estructura:
    {
        "groups": [
            {
                "group_id": 0,
                "representative_cluster_id": "123",
                "representative_template": "...",
                "event_type": null,
                "severity": null,
                "member_cluster_ids": [
                    {"cluster_id": "123", "template": "...", "size": 10},
                    {"cluster_id": "124", "template": "...", "size": 5},
                    ...
                ],
                "num_members": 5,
                "total_size": 100
            },
            ...
        ]
    }

    Args:
        input_path (str): Ruta al fichero 'x_template.json' o 'x_template_regex.json'.
        distance_threshold (float): Umbral de distancia coseno para formar grupos.

    Returns:
        dict: Diccionario con la estructura de grupos semánticos.
    """
    with open(input_path, encoding='utf-8') as f:
        data = json.load(f)

    clusters_raw = data['clusters']

    # Soporta ambos formatos:
    # - x_template.json: 'clusters' es una LISTA de dicts, cada uno con
    #   su propia clave 'cluster_id' (ej. {"cluster_id": 4, "template": ...}).
    # - x_template_regex.json: 'clusters' es un DICT {cluster_id_str: {...}}.
    if isinstance(clusters_raw, list):
        clusters = {str(c['cluster_id']): c for c in clusters_raw}
    else:
        clusters = clusters_raw

    cluster_ids = list(clusters.keys())
    templates = [clusters[cid]['template'] for cid in cluster_ids]
    normalized = [normalize_template(t) for t in templates]

    print(f"📊 {len(templates)} templates a agrupar semánticamente...")

    embeddings = get_embeddings(normalized)
    labels = cluster_embeddings(embeddings, distance_threshold)

    n_groups = len(set(labels))
    print(f"✓ {n_groups} grupo(s) semántico(s) formados (de {len(templates)} templates originales)")

    # Organizar resultados por grupo
    groups_by_label = {}
    for idx, label in enumerate(labels):
        groups_by_label.setdefault(int(label), []).append(idx)

    result = {"groups": []}
    for label, indices in sorted(groups_by_label.items(), key=lambda x: -len(x[1])):
        representative_idx = find_representative(embeddings, indices)
        representative_cid = cluster_ids[representative_idx]

        member_cluster_ids = [cluster_ids[i] for i in indices]
        total_size = sum(clusters[cid].get('size', 0) for cid in member_cluster_ids)

        member_templates = [
            {
                "cluster_id": cid,
                "template": clusters[cid]['template'],
                "size": clusters[cid].get('size', 0),
            }
            for cid in member_cluster_ids
        ]

        result["groups"].append({
            "group_id": label,
            "representative_cluster_id": representative_cid,
            "representative_template": clusters[representative_cid]['template'],
            # Campos editables manualmente tras revisar el grupo. Se
            # inicializan a None; el usuario los rellena en el propio
            # JSON antes de ejecutar generate_regex_from_groups.py.
            "event_type": None,
            "severity": None,
            "member_cluster_ids": member_templates,
            "num_members": len(member_cluster_ids),
            "total_size": total_size,
        })

    return result


def main():
    parser = argparse.ArgumentParser(description="Agrupa templates de Drain3 por similitud semántica")
    parser.add_argument('input', type=str, help="Ruta a x_template.json")
    parser.add_argument('--threshold', type=float, default=0.6,
                         help="Distancia coseno máxima dentro de un grupo (default 0.6, más bajo = grupos más estrictos)")
    parser.add_argument('--output', type=str, default=None,
                         help="Ruta de salida (default: <input>_semantic_groups.json)")
    args = parser.parse_args()

    output_path = args.output or args.input.replace('.json', '_semantic_groups.json')

    result = semantic_group_templates(args.input, args.threshold)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"💾 Guardado: {output_path}")

    # Resumen en consola: los 10 grupos más grandes
    print("\n📋 Top 10 grupos más grandes:")
    for group in result["groups"][:10]:
        print(f"  Grupo {group['group_id']} ({group['num_members']} templates, "
              f"total_size={group['total_size']}):")
        print(f"    → {group['representative_template'][:100]}")


if __name__ == '__main__':
    main()