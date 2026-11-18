"""Registro del gasto de DataForSEO por proyecto (control de gastos de Convertix).

DataForSEO no tiene subcuentas y su panel no agrega el coste por `tag`
(https://dataforseo.com/help-center/how-to-track-api-usage-with-tag). Por eso cada llamada:
  1. lleva el proyecto en el `tag` de cada tarea (`etiquetar`), que DFS devuelve en `data.tag`;
  2. apunta su coste real, tarea a tarea, en un JSONL (`registrar`) que lee el recolector
     `dataforseo_registro` del panel de gastos.

Solo librería estándar, para que valga en skills, scripts sueltos y servidores.
Copia canónica: ~/Documents/Claude Code/_ControlGastos/registro_dfs/registro_dfs.py.
Si cambias esta, cambia las copias y sube VERSION.
"""
from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
RUTA_POR_DEFECTO = Path.home() / ".local" / "share" / "registro-dfs" / "llamadas.jsonl"
LARGO_MAXIMO_TAG = 255


CARPETA_PROYECTOS = Path.home() / "Documents" / "Claude Code"


def proyecto_de_carpeta(ruta: Path) -> str:
    """La carpeta de proyecto bajo ~/Documents/Claude Code (el mismo criterio que el recolector del histórico)."""
    try:
        return Path(ruta).resolve().relative_to(CARPETA_PROYECTOS).parts[0]
    except (ValueError, IndexError):
        return f"carpeta {Path(ruta).resolve().name}"


def proyecto_actual(por_defecto: str | None = None) -> str:
    """El proyecto de la llamada: `DFS_PROYECTO`, el que pase el script o, si no, la carpeta de trabajo."""
    return os.environ.get("DFS_PROYECTO") or por_defecto or proyecto_de_carpeta(Path.cwd())


def etiquetar(payload: list[dict], proyecto: str) -> list[dict]:
    """Pone `tag` = proyecto en cada tarea que no traiga uno propio."""
    return [{**tarea, "tag": tarea.get("tag") or proyecto[:LARGO_MAXIMO_TAG]} for tarea in payload]


def registrar(respuesta: dict | None, proyecto: str, persona: str | None = None) -> None:
    """Apunta una línea por tarea con su coste real. Nunca lanza: el registro no puede romper la llamada."""
    try:
        ruta = Path(os.environ.get("REGISTRO_DFS") or RUTA_POR_DEFECTO)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        momento = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lineas = [json.dumps({
            "momento_utc": momento, "proyecto": proyecto, "persona": persona or os.environ.get("DFS_PERSONA"),
            "maquina": socket.gethostname(), "task_id": tarea.get("id"),
            "endpoint": "/".join(tarea.get("path") or []), "tag": (tarea.get("data") or {}).get("tag"),
            "coste_usd": tarea.get("cost"), "status_code": tarea.get("status_code"), "version": VERSION,
        }, ensure_ascii=False) for tarea in (respuesta or {}).get("tasks") or [] if isinstance(tarea, dict)]
        if lineas:
            with ruta.open("a") as fichero:
                fichero.write("\n".join(lineas) + "\n")
    except Exception:  # noqa: BLE001 — el registro es telemetría
        pass
