"""Rutes per defecte del pipeline (derivades del fitxer de bloqueig)."""
from __future__ import annotations

from pathlib import Path

from . import sources as S
from .softcatala import DictToolsPaths

TOOL_DIR = S.TOOL_DIR
REPO_DIR = S.REPO_DIR
DATA_DIR = TOOL_DIR / 'data'
ASSETS_DIR = REPO_DIR / 'assets'
LEXICON_DIR = ASSETS_DIR / 'lexicon'


def default_dict_tools(cache: Path = S.DEFAULT_CACHE) -> DictToolsPaths:
    return DictToolsPaths(S.load_lock().softcatala_dir(cache))


def default_dump(cache: Path = S.DEFAULT_CACHE) -> Path:
    return S.load_lock().dump_path(cache)
