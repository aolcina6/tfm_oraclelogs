#!/usr/bin/env python3
"""
benchmark_semantic_grouping.py

Compara distintas configuraciones de semantic_grouping.py (método de
embedding + distance_threshold), midiendo:
- Tiempo de generación de embeddings
- Tiempo de clustering
- Nº de grupos formados
- Silhouette score (calidad del clustering: cohesión intra-grupo vs
  separación inter-grupo; rango [-1, 1], más alto = mejor)
- Distribución de tamaños de grupo (para detectar over/under-clustering)

Uso:
    python drain/benchmark_semantic_grouping.py templates/alert_jde_template.json
    python drain/benchmark_semantic_grouping.py templates/alert_jde_template.json \
        --thresholds 0.1 0.15 0.2 0.25 0.3 --methods sentence_transformers tfidf
    python drain/benchmark_semantic_grouping.py templates/alert_jde_template.json --csv resultados.csv
"""
import json
import sys
import time
import argparse
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from sklearn.metrics import silhouette_score
import csv as csv_module
import os
import matplotlib
matplotlib.use("Agg")  # backend sin GUI, seguro en servidores/CI
import matplotlib.pyplot as plt
from semantic_grouping import normalize_template, cluster_embeddings


# ============================================================
# Embeddings instrumentados por método, para poder medir tiempos
# de forma aislada (a diferencia de get_embeddings() en
# semantic_grouping.py, que decide el método automáticamente con
# fallback y no permite forzar uno concreto).
# ============================================================
def get_embeddings_sentence_transformers(texts: list) -> np.ndarray:
    """
    Obtiene embeddings usando SentenceTransformers (all-MiniLM-L6-v2), 
    normalizados para distancia coseno.

    Args:
        texts (list): Lista de strings a convertir en embeddings.

    Returns:
        np.ndarray: Matriz de embeddings normalizados (shape: [n_texts, embedding_dim]).
    """
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return np.array(embeddings)


def get_embeddings_tfidf(texts: list) -> np.ndarray:
    """
    Obtiene embeddings usando TF-IDF + SVD, normalizados para distancia coseno.

    Args:
        texts (list): Lista de strings a convertir en embeddings.

    Returns:
        np.ndarray: Matriz de embeddings normalizados (shape: [n_texts, n_components]).
    """
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

    norms = np.linalg.norm(embeddings, axis=1)
    zero_mask = norms == 0
    if zero_mask.any():
        print(f"⚠️  {zero_mask.sum()} template(s) con embedding nulo tras SVD "
              f"(probablemente texto casi vacío tras normalizar) — "
              f"se les añade ruido mínimo para permitir distancia coseno.")
        rng = np.random.RandomState(42)
        embeddings[zero_mask] += rng.normal(scale=1e-6, size=(zero_mask.sum(), embeddings.shape[1]))

    return normalize(embeddings)


EMBEDDING_METHODS = {
    "sentence_transformers": get_embeddings_sentence_transformers,
    "tfidf": get_embeddings_tfidf,
}


def load_templates(input_path: str) -> tuple:
    """
    Carga templates y sizes desde x_template.json, igual que semantic_grouping.py.
    
    Args:
        input_path (str): Ruta al fichero x_template.json.
    
    Returns:
        tuple: (templates, sizes) donde:
    """
    with open(input_path, encoding='utf-8') as f:
        data = json.load(f)

    clusters_raw = data['clusters']
    if isinstance(clusters_raw, list):
        clusters = {str(c['cluster_id']): c for c in clusters_raw}
    else:
        clusters = clusters_raw

    cluster_ids = list(clusters.keys())
    templates = [clusters[cid]['template'] for cid in cluster_ids]
    sizes = [clusters[cid].get('size', 0) for cid in cluster_ids]
    return templates, sizes


def compute_silhouette(embeddings: np.ndarray, labels: np.ndarray) -> float:
    """
    Silhouette score sobre distancia coseno. Requiere al menos 2
    clusters distintos y menos clusters que muestras; si no se cumple,
    devuelve NaN (caso degenerado: todo en 1 solo grupo, o cada
    elemento en su propio grupo).

    Args:
        embeddings (np.ndarray): Matriz de embeddings (shape: [n_samples, n_features]).
        labels (np.ndarray): Etiquetas de cluster para cada muestra (shape: [n_samples]).

    Returns:
        float: Silhouette score (rango [-1, 1]) o NaN si no es computable.
    """
    n_labels = len(set(labels))
    if n_labels < 2 or n_labels >= len(labels):
        return float('nan')

    return silhouette_score(embeddings, labels, metric='cosine')


def group_size_stats(labels: np.ndarray) -> dict:
    """
    Estadísticas de distribución de tamaños de grupo.
    
    Args:
        labels (np.ndarray): Etiquetas de cluster para cada muestra (shape: [n_samples]).

    Returns:
        dict: Diccionario con estadísticas:
            - n_groups: número de grupos distintos
            - max_group_size: tamaño del grupo más grande
            - min_group_size: tamaño del grupo más pequeño
            - mean_group_size: tamaño medio de grupo (float, 2 decimales)
            - median_group_size: tamaño mediano de grupo (float)
            - singleton_groups: número de grupos con solo 1 elemento
    """
    _, counts = np.unique(labels, return_counts=True)
    return {
        "n_groups": len(counts),
        "max_group_size": int(counts.max()),
        "min_group_size": int(counts.min()),
        "mean_group_size": round(float(counts.mean()), 2),
        "median_group_size": float(np.median(counts)),
        "singleton_groups": int(np.sum(counts == 1)),  # grupos de 1 solo template = no agrupado
    }


def run_benchmark(input_path: str, thresholds: list, methods: list) -> list:
    """
    Ejecuta el benchmark de semantic_grouping.py para un origen concreto, probando
    todas las combinaciones de método de embedding y distance_threshold.

    Args:
        input_path (str): Ruta al fichero x_template.json.
        thresholds (list): Lista de distance_threshold a probar.
        methods (list): Lista de métodos de embedding a probar (keys de EMBEDDING_METHODS).

    Returns:
        list: Lista de diccionarios con resultados por combinación (método x threshold).
    """
    templates, sizes = load_templates(input_path)
    normalized = [normalize_template(t) for t in templates]

    print(f"📊 {len(templates)} templates cargados desde {input_path}\n")

    results = []

    for method_name in methods:
        if method_name not in EMBEDDING_METHODS:
            print(f"⚠️  Método desconocido '{method_name}', omitido "
                  f"(disponibles: {list(EMBEDDING_METHODS.keys())})")
            continue

        embed_fn = EMBEDDING_METHODS[method_name]

        # Generar embeddings UNA sola vez por método
        print(f"🔤 Generando embeddings con '{method_name}'...")
        try:
            t0 = time.perf_counter()
            embeddings = embed_fn(normalized)
            embedding_time = time.perf_counter() - t0
        except ImportError as e:
            print(f"  ⚠️  '{method_name}' no disponible ({e}), omitido\n")
            continue

        print(f"  ✓ Embeddings generados en {embedding_time:.3f}s "
              f"(shape={embeddings.shape})\n")

        for threshold in thresholds:
            t0 = time.perf_counter()
            labels = cluster_embeddings(embeddings, threshold)
            clustering_time = time.perf_counter() - t0

            silhouette = compute_silhouette(embeddings, labels)
            stats = group_size_stats(labels)

            row = {
                "method": method_name,
                "threshold": threshold,
                "n_templates": len(templates),
                "embedding_time_s": round(embedding_time, 3),
                "clustering_time_s": round(clustering_time, 3),
                "total_time_s": round(embedding_time + clustering_time, 3),
                "silhouette_score": round(silhouette, 4) if not np.isnan(silhouette) else None,
                **stats,
            }
            results.append(row)

            print(f"  [{method_name} | threshold={threshold}] "
                  f"grupos={stats['n_groups']:>4} | "
                  f"singletons={stats['singleton_groups']:>4} | "
                  f"silhouette={row['silhouette_score']} | "
                  f"clustering={clustering_time:.3f}s")

        print()

    return results


def print_summary_table(results: list) -> None:
    """
    Imprime una tabla resumen de los resultados del benchmark, ordenada por
    método y threshold, con columnas:   
        method, threshold, n_groups, singleton_groups, silhouette_score, total_time_s
    """
    if not results:
        print("⚠️  No hay resultados que mostrar")
        return

    print("\n" + "=" * 100)
    print("📋 RESUMEN COMPARATIVO")
    print("=" * 100)

    header = f"{'method':<22} {'thresh':>7} {'n_groups':>9} {'singl.':>7} {'silhouette':>11} {'total_s':>9}"
    print(header)
    print("-" * len(header))

    for row in sorted(results, key=lambda r: (r['method'], r['threshold'])):
        silh = f"{row['silhouette_score']:.4f}" if row['silhouette_score'] is not None else "N/A"
        print(f"{row['method']:<22} {row['threshold']:>7} {row['n_groups']:>9} "
              f"{row['singleton_groups']:>7} {silh:>11} {row['total_time_s']:>9}")

    valid_rows = [r for r in results if r['silhouette_score'] is not None]
    if valid_rows:
        best = max(valid_rows, key=lambda r: r['silhouette_score'])
        print("\n🏆 Mejor configuración por silhouette score:")
        print(f"   método={best['method']}, threshold={best['threshold']}, "
              f"silhouette={best['silhouette_score']}, grupos={best['n_groups']}, "
              f"singletons={best['singleton_groups']}, tiempo={best['total_time_s']}s")
        
    return best if valid_rows else None


def save_csv(results: list, csv_path: str) -> None:
    """
    Guarda los resultados detallados en un CSV, con una fila por combinación
    (método x threshold) y columnas:
        method, threshold, n_templates, embedding_time_s, clustering_time_s,
        total_time_s, silhouette_score, n_groups, singleton_groups,
        max_group_size, min_group_size, mean_group_size, median_group_size

    Args:
        results (list): Lista de diccionarios con resultados por combinación.
        csv_path (str): Ruta del fichero CSV a generar.

    Returns:
        None
    """

    if not results:
        return

    fieldnames = list(results[0].keys())
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv_module.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n💾 CSV guardado: {csv_path}")

def print_multi_origin_summary(origin_rows: list) -> None:
    """
    Imprime la tabla comparativa final entre orígenes, incluyendo la
    comparación explícita tfidf vs sentence_transformers (columna
    'Δsilh si tfidf' y '¿tfidf suficiente?').
    """
    if not origin_rows:
        print("⚠️  No hay orígenes que resumir")
        return

    print("\n" + "=" * 155)
    print("🗂️  RESUMEN COMPARATIVO ENTRE ORÍGENES")
    print("=" * 155)

    header = (f"{'Origen':<20} {'n_tpl':>6} {'Método ganador':<22} {'Thresh':>7} "
              f"{'Silh.máx':>9} {'n_grp':>6} {'%singl':>7} {'t_tfidf(s)':>11} {'t_st(s)':>9} "
              f"{'Δsilh_tfidf':>12} {'¿tfidf OK?':>11}")
    print(header)
    print("-" * len(header))

    for row in origin_rows:
        silh = f"{row['best_silhouette']:.4f}" if row['best_silhouette'] is not None else "N/A"
        thr = f"{row['best_threshold']}" if row['best_threshold'] is not None else "N/A"
        pct = f"{row['pct_singletons']}" if row['pct_singletons'] is not None else "N/A"
        t_tfidf = f"{row['tfidf_time_s']:.3f}" if row['tfidf_time_s'] is not None else "N/A"
        t_st = f"{row['st_time_s']:.3f}" if row['st_time_s'] is not None else "N/A"


    print("=" * 155)

def save_multi_origin_csv(origin_rows: list, csv_path: str) -> None:
    import csv as csv_module

    if not origin_rows:
        return

    fieldnames = list(origin_rows[0].keys())
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv_module.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(origin_rows)

    print(f"\n💾 CSV resumen entre orígenes guardado: {csv_path}")

def plot_threshold_evolution(results: list, origin: str, output_dir: str = ".") -> None:
    """
    Genera un PNG con 3 subplots por origen:
      1) n_groups vs threshold, una línea por método
      2) silhouette_score vs threshold, una línea por método
      3) singleton_groups (y % singletons) vs threshold, una línea por método

    Sirve para identificar visualmente el "codo" donde el nº de grupos
    se estabiliza, el silhouette alcanza su máximo, y a partir de qué
    threshold empieza a dispararse la sobre-fragmentación (singletons),
    para elegir el threshold óptimo por método.

    Args:
        results (list): filas devueltas por run_benchmark() (todas las
            combinaciones método x threshold de un mismo origen).
        origin (str): nombre del origen (para título y nombre de fichero).
        output_dir (str): carpeta donde guardar el PNG.
    """
    if not results:
        print(f"⚠️  No hay resultados para graficar en '{origin}'")
        return

    methods = sorted({r['method'] for r in results})

    fig, (ax_groups, ax_silh, ax_singl) = plt.subplots(1, 3, figsize=(20, 5))

    for method in methods:
        method_rows = sorted(
            (r for r in results if r['method'] == method),
            key=lambda r: r['threshold']
        )
        if not method_rows:
            continue

        thresholds = [r['threshold'] for r in method_rows]
        n_groups = [r['n_groups'] for r in method_rows]
        silhouettes = [r['silhouette_score'] for r in method_rows]  # puede tener None
        singletons = [r['singleton_groups'] for r in method_rows]
        pct_singletons = [
            round(100 * r['singleton_groups'] / r['n_groups'], 1) if r['n_groups'] else 0.0
            for r in method_rows
        ]

        ax_groups.plot(thresholds, n_groups, marker='o', label=method)

        # Filtrar puntos None (silhouette degenerado) para no romper la línea,
        # pero mantener el hueco visualmente (NaN en vez de saltarlos del todo)
        silh_plot = [s if s is not None else float('nan') for s in silhouettes]
        ax_silh.plot(thresholds, silh_plot, marker='o', label=method)

        ax_singl.plot(thresholds, singletons, marker='o', label=f"{method} (abs.)")
        ax_singl.plot(thresholds, pct_singletons, marker='x', linestyle='--',
                      label=f"{method} (%)", alpha=0.6)

    ax_groups.set_xlabel("distance_threshold")
    ax_groups.set_ylabel("n_groups")
    ax_groups.set_title(f"{origin}: nº de grupos vs threshold")
    ax_groups.legend()
    ax_groups.grid(True, alpha=0.3)

    ax_silh.set_xlabel("distance_threshold")
    ax_silh.set_ylabel("silhouette_score")
    ax_silh.set_title(f"{origin}: silhouette vs threshold")
    ax_silh.axhline(0, color='gray', linewidth=0.8, linestyle='--')
    ax_silh.legend()
    ax_silh.grid(True, alpha=0.3)

    ax_singl.set_xlabel("distance_threshold")
    ax_singl.set_ylabel("singletons (abs. / %)")
    ax_singl.set_title(f"{origin}: singletons vs threshold")
    ax_singl.legend()
    ax_singl.grid(True, alpha=0.3)

    fig.suptitle(f"Evolución por threshold — origen: {origin}")
    fig.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{origin}_threshold_evolution.png")
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

    print(f"📈 Gráfico guardado: {output_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark de configuraciones para semantic_grouping.py"
    )
    parser.add_argument('inputs', type=str, nargs='+',
                         help="Ruta(s) a x_template.json (uno o varios orígenes)")
    parser.add_argument('--thresholds', type=float, nargs='+',
                         default=[0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75],
                         help="Lista de distance_threshold a probar")
    parser.add_argument('--methods', type=str, nargs='+',
                         default=["sentence_transformers", "tfidf"],
                         help="Métodos de embedding a probar (sentence_transformers, tfidf)")
    parser.add_argument('--csv', type=str, default=None,
                         help="Ruta opcional para exportar resultados detallados a CSV "
                              "(por origen, si hay varios inputs, se sufija con el nombre del origen)")
    parser.add_argument('--summary-csv', type=str, default=None,
                         help="Ruta opcional para exportar la tabla resumen entre orígenes a CSV")
    parser.add_argument('--plot', action='store_true',
                         help="Generar gráficos PNG (n_groups y silhouette vs threshold, "
                              "una línea por método) por cada origen")
    parser.add_argument('--plot-dir', type=str, default="benchmark_plots",
                         help="Carpeta donde guardar los gráficos (default: benchmark_plots)")
    args = parser.parse_args()

    import os

    origin_rows = []

    for input_path in args.inputs:
        origin_name = os.path.splitext(os.path.basename(input_path))[0].replace("_template", "")

        print(f"\n{'#'*100}")
        print(f"# ORIGEN: {origin_name}  ({input_path})")
        print(f"{'#'*100}")

        results = run_benchmark(input_path, args.thresholds, args.methods)
        print_summary_table(results)

        if args.plot:
            plot_threshold_evolution(results, origin_name, output_dir=args.plot_dir)

        if args.csv:
            if len(args.inputs) > 1:
                base, ext = os.path.splitext(args.csv)
                csv_path = f"{base}_{origin_name}{ext}"
            else:
                csv_path = args.csv
            save_csv(results, csv_path)

    # Solo tiene sentido la tabla comparativa si hay más de un origen,
    # pero se imprime igualmente con 1 para tener un formato consistente.
    print_multi_origin_summary(origin_rows)

    if args.summary_csv:
        save_multi_origin_csv(origin_rows, args.summary_csv)


if __name__ == '__main__':
    main()