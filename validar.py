#!/usr/bin/env python3
"""Validador de formato de la Práctica 2. Uso: python validar.py RUTA_DEL_REPOSITORIO"""
import csv
import json
import os
import re
import subprocess
import sys

MAX_BYTES = 20 * 1024 * 1024
NULOS = {"None", "nan", "NaN", "NA", "<NA>", "null"}
EXT_PROHIBIDAS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif", ".webp", ".svg",
                  ".zip", ".tar", ".gz", ".7z")
CARPETAS_PROHIBIDAS = ("cache", "downloads", ".venv", "__pycache__")
EXT_PROHIBIDAS = EXT_PROHIBIDAS + (".sqlite",)  # caché de requests-cache
# Ficheros de ejemplo de la plantilla: no forman parte de la entrega, se conserven o no
PLANTILLA = ("memoria.pdf", "memoria.ca.pdf")

POBLACION = ["title", "timestamp", "size", "mime", "width", "height", "sha1", "user", "url"]
METADATOS = ["title", "date", "latitude", "longitude", "altitude", "author", "credit", "license",
             "license_url", "usage_terms", "attribution_required", "copyrighted", "make", "model",
             "software", "orientation", "width", "height", "size", "sha1"]

# fichero: (cabecera, columnas enteras, columnas que no pueden ir vacías)
CSV = {
    "dataset/requests.csv": (["timestamp", "section", "method", "url", "http_status", "bytes", "retry", "duration_ms"],
                             ["section", "http_status", "bytes", "retry", "duration_ms"],
                             ["timestamp", "section", "method", "url", "http_status", "bytes", "retry", "duration_ms"]),
    "dataset/population.csv": (POBLACION, ["size", "width", "height"], ["title", "timestamp", "size", "mime"]),
    "dataset/sample.csv": (POBLACION, ["size", "width", "height"], ["title", "timestamp", "size", "mime"]),
    "dataset/metadata_description.csv": (METADATOS, ["width", "height", "size"], ["title"]),
    "dataset/metadata_exif_api.csv": (METADATOS, ["width", "height", "size"], ["title"]),
    "dataset/metadata_file.csv": (METADATOS, ["width", "height", "size"], ["title"]),
}
OBLIGATORIOS = ["README.md", "requirements.txt", "results.json"] + list(CSV)

CATEGORIAS = ["all_present_agree", "all_present_disagree", "two_present_agree",
              "two_present_disagree", "only_one", "none"]
COMPARACIONES = ["date", "latitude", "longitude", "altitude", "author", "make", "model", "software",
                 "orientation"]
# Estructura de results.json: "int", "str", "texto", "int_o_str" (semilla), "conteos" o un diccionario
RESULTADOS = {
    "api": {"requests": "int", "key": "texto", "user_agent": "str"},
    "window": {"seed": "int_o_str", "day": "str", "shift": "int", "start": "str", "end": "str"},
    "population": {"requests": "int", "n": "int", "first_upload": "str", "last_upload": "str",
                   "mime_types": "conteos"},
    "sample": {"requests": "int", "titles_per_request": "int", "window_cost": "int", "sample_cost": "int",
               "n": "int"},
    "files": {"requests": "int", "n": "int", "bytes_downloaded": "int"},
    "analysis": {"comparisons": {k: {c: "int" for c in CATEGORIAS} for k in COMPARACIONES}},
}

FECHA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)")
ENTERO = re.compile(r"-?\d+")


def ficheros_entregados(raiz):
    """Ficheros que entrarían en la entrega (respeta .gitignore si es un repositorio git)."""
    if os.path.isdir(os.path.join(raiz, ".git")):
        try:
            # -z: sin -z git entrecomilla y escapa las rutas con caracteres no ASCII
            # (p. ej. «fotografía.jpg») y quedarían fuera del control.
            r = subprocess.run(["git", "-C", raiz, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            if r.returncode == 0:
                # El índice puede listar ficheros borrados del disco y aún no confirmados.
                return [f for f in r.stdout.split("\0")
                        if f and f not in PLANTILLA and os.path.exists(os.path.join(raiz, f))]
        except (OSError, subprocess.SubprocessError):
            pass
    # Sin repositorio git no se puede aplicar .gitignore: se recorre el disco saltando lo que la
    # plantilla ya excluye (cache/, downloads/, imágenes y comprimidos), que no entraría en la entrega.
    print("AVISO: %s no es un repositorio git; se omiten cache/, downloads/, .venv/ e imágenes como haría .gitignore." % raiz)
    lista = []
    for carpeta, subcarpetas, nombres in os.walk(raiz):
        subcarpetas[:] = [d for d in subcarpetas if d != ".git" and d.lower() not in CARPETAS_PROHIBIDAS]
        for n in nombres:
            ruta = os.path.join(carpeta, n)
            rel = os.path.relpath(ruta, raiz).replace(os.sep, "/")
            if n.lower().endswith(EXT_PROHIBIDAS) or rel in PLANTILLA or not os.path.isfile(ruta):
                continue  # también salta enlaces simbólicos rotos
            lista.append(rel)
    return lista


def comprobar_estructura(raiz, errores):
    for f in OBLIGATORIOS:
        if not os.path.isfile(os.path.join(raiz, f)):
            errores.append("Falta el fichero obligatorio %s." % f)
    entregados = ficheros_entregados(raiz)
    for f in entregados:
        partes = f.split("/")
        carpetas = [p.lower() for p in partes[:-1]]
        if any(p in CARPETAS_PROHIBIDAS for p in carpetas) or carpetas[:2] == ["data", "raw"]:
            errores.append("%s está dentro de una carpeta que no se debe subir (%s)." % (f, ", ".join(c + "/" for c in CARPETAS_PROHIBIDAS + ("data/raw",))))
        elif f.lower().endswith(EXT_PROHIBIDAS):
            errores.append("%s es una imagen, un fichero comprimido o una caché (.sqlite), que no se debe subir." % f)
        elif os.path.getsize(os.path.join(raiz, f)) > MAX_BYTES:
            errores.append("%s ocupa más de 20 MB." % f)
    if not any(f.startswith("source/") and f.lower().endswith(".py") for f in entregados):
        errores.append("La carpeta source/ no contiene ningún fichero .py.")


def comprobar_csv(raiz, nombre, cabecera, enteros, obligatorias, errores):
    ruta = os.path.join(raiz, nombre)
    if not os.path.isfile(ruta):
        return
    try:
        with open(ruta, encoding="utf-8", newline="") as fh:
            filas = list(csv.reader(fh))
    except UnicodeDecodeError:
        errores.append("%s no está en UTF-8." % nombre)
        return
    except csv.Error as e:
        errores.append("%s no se puede leer como CSV: %s." % (nombre, e))
        return
    if not filas:
        errores.append("%s está vacío: debe tener al menos la cabecera." % nombre)
        return
    leida = [c.lstrip("﻿") for c in filas[0]]
    if leida != cabecera:
        pista = ""
        if leida and leida[0] in ("", "Unnamed: 0") and leida[1:] == cabecera:
            pista = " (la primera columna parece el índice de pandas: use to_csv(..., index=False))"
        elif len(leida) == 1 and ";" in leida[0]:
            pista = " (el separador debe ser la coma, no el punto y coma)"
        errores.append("La cabecera de %s debe ser exactamente: %s%s" % (nombre, ",".join(cabecera), pista))
        return
    if len(filas) < 2 or not any(filas[1:]):
        errores.append("%s solo tiene la cabecera: faltan los datos." % nombre)
        return
    for i, fila in enumerate(filas[1:], start=2):
        if not fila:
            continue
        if len(fila) != len(cabecera):
            errores.append("%s, línea %d: tiene %d valores y la cabecera %d." % (nombre, i, len(fila), len(cabecera)))
            continue
        valores = dict(zip(cabecera, fila))
        for c, v in valores.items():
            if "\x00" in v:
                errores.append("%s, línea %d, columna %s: contiene el carácter nulo \\x00 (típico del EXIF); elimínelo, p. ej. con .rstrip('\\x00 ')." % (nombre, i, c))
            if v in NULOS:
                errores.append("%s, línea %d, columna %s: «%s»; un valor ausente es una celda vacía." % (nombre, i, c, v))
        for c in enteros:
            if valores[c] not in ("",) + tuple(NULOS) and not ENTERO.fullmatch(valores[c]):
                errores.append("%s, línea %d, columna %s: «%s» debe ser un entero sin decimales." % (nombre, i, c, valores[c]))
        for c in obligatorias:
            if valores[c] == "":
                errores.append("%s, línea %d: la columna %s no puede ir vacía." % (nombre, i, c))
        for c in ("timestamp",):
            if c in valores and valores[c] and not FECHA.fullmatch(valores[c]):
                errores.append("%s, línea %d, columna %s: «%s» no tiene el formato AAAA-MM-DDTHH:MM:SSZ." % (nombre, i, c, valores[c]))
        if nombre == "dataset/requests.csv":
            if valores["section"] not in ("1", "2", "3", "4"):
                errores.append("%s, línea %d: section debe ser 1, 2, 3 o 4." % (nombre, i))
            if valores["method"] not in ("GET", "POST"):
                errores.append("%s, línea %d: method debe ser GET o POST." % (nombre, i))
            if valores["retry"] not in ("0", "1"):
                errores.append("%s, línea %d: retry debe ser 0 o 1." % (nombre, i))


def tipo_ok(valor, tipo):
    es_int = isinstance(valor, int) and not isinstance(valor, bool)
    if tipo == "int":
        return es_int
    if tipo == "str":
        return isinstance(valor, str)
    if tipo == "texto":
        return valor is None or isinstance(valor, str)
    if tipo == "int_o_str":
        return es_int or (isinstance(valor, str) and valor.isdigit())
    if tipo == "conteos":
        return isinstance(valor, dict) and all(isinstance(v, int) and not isinstance(v, bool) for v in valor.values())
    return False


def comprobar_estructura_json(obj, esquema, ruta, errores):
    for clave, tipo in esquema.items():
        nombre = ruta + clave
        if not isinstance(obj, dict) or clave not in obj:
            errores.append("results.json: falta la clave «%s»." % nombre)
            continue
        valor = obj[clave]
        if isinstance(tipo, dict):
            if not isinstance(valor, dict):
                errores.append("results.json: «%s» debe ser un objeto {...}." % nombre)
            else:
                comprobar_estructura_json(valor, tipo, nombre + ".", errores)
        elif not tipo_ok(valor, tipo):
            esperado = {"int": "un entero (sin comillas ni decimales)", "str": "una cadena de texto",
                        "texto": "una cadena de texto", "int_o_str": "un entero o una cadena de dígitos",
                        "conteos": "un objeto con enteros"}[tipo]
            errores.append("results.json: «%s» debe ser %s." % (nombre, esperado))


def comprobar_resultados(raiz, errores):
    ruta = os.path.join(raiz, "results.json")
    if not os.path.isfile(ruta):
        return
    try:
        with open(ruta, encoding="utf-8-sig") as fh:  # admite BOM (Bloc de notas de Windows)
            obj = json.load(fh)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        errores.append("results.json no es JSON válido: %s." % e)
        return
    comprobar_estructura_json(obj, RESULTADOS, "", errores)
    if isinstance(obj, dict):
        api, ventana = obj.get("api"), obj.get("window")
        if isinstance(api, dict) and isinstance(api.get("user_agent"), str) and not api["user_agent"].strip():
            errores.append("results.json: «api.user_agent» está vacío.")
        if isinstance(ventana, dict) and ventana.get("seed") in (0, "0", ""):
            errores.append("results.json: «window.seed» sigue con el valor de la plantilla (0).")


def main():
    try:  # consolas de Windows (cp1252) con rutas no representables: no romper al imprimir
        sys.stdout.reconfigure(errors="backslashreplace")
    except Exception:
        pass
    if len(sys.argv) != 2:
        print("Uso: python validar.py RUTA_DEL_REPOSITORIO")
        return 2
    raiz = sys.argv[1]
    if not os.path.isdir(raiz):
        print("La ruta %s no existe o no es una carpeta." % raiz)
        return 2
    errores = []
    comprobar_estructura(raiz, errores)
    for nombre, (cabecera, enteros, obligatorias) in CSV.items():
        comprobar_csv(raiz, nombre, cabecera, enteros, obligatorias, errores)
    comprobar_resultados(raiz, errores)
    for e in errores[:200]:
        print("ERROR: " + e)
    if len(errores) > 200:
        print("... y %d errores más." % (len(errores) - 200))
    print("RESULTADO: OK" if not errores else "RESULTADO: NO-OK (%d errores)" % len(errores))
    return 0 if not errores else 1


if __name__ == "__main__":
    sys.exit(main())
