"""
learning_queue.py

Gestión de la "cola de aprendizaje": líneas de log que no matchearon
ningún patrón (o ningún template) durante el parseo, guardadas para
revisión manual posterior.
"""
import os


def clear_learning_queue(storage, output_folder):
    """
    Limpia la carpeta de learning queue antes de procesar.
    Esto asegura que solo contenga líneas sin matchear de la ejecución actual.
    """
    learning_queue_folder = f"{output_folder}_learning_queue"

    try:
        if storage.exists(learning_queue_folder):
            files = storage.list_files(prefix=learning_queue_folder, extension=".json")

            if files:
                print(f"🗑️  Limpiando learning queue anterior...")
                for file_path, rel_path in files:
                    storage.delete_file(file_path)
                    print(f"  ✓ Eliminado: {rel_path}")
                print(f"✓ Learning queue limpiada ({len(files)} archivos eliminados)\n")
            else:
                print(f"✓ Learning queue vacía (nada que limpiar)\n")
        else:
            print(f"✓ Carpeta de learning queue creada (primera ejecución)\n")

    except Exception as e:
        print(f"⚠️  Error limpiando learning queue: {e}")
        print(f"Continuando de todas formas...\n")


def write_learning_queue(storage, output_folder, rel_path, unmatched):
    """
    Escribe las líneas sin matchear de un archivo a su fichero de
    learning queue correspondiente.

    Args:
        storage: Backend de storage.
        output_folder (str): Carpeta base de salida.
        rel_path (str): Ruta relativa del archivo fuente.
        unmatched (list): Líneas sin matchear.
    """
    base_name = os.path.splitext(os.path.basename(rel_path))[0]
    learning_path = f"{output_folder}_learning_queue/{base_name}_learning_queue.json"

    storage.write_json(learning_path, {
        "source_file": rel_path,
        "total_unmatched": len(unmatched),
        "description": "Líneas que no coincidieron con ningún patrón.",
        "lines": unmatched
    })
    print(f"  ⚠️  Cola de aprendizaje: {len(unmatched)} líneas → {learning_path}")
    print(f"  🔄 Archivo NO se marcará como procesado (tiene líneas sin matchear)")