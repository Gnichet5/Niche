"""Resolve a memória persistente sem sincronização ou acesso à rede."""
import os
from pathlib import Path


def resolver_pasta_dados(base_dir=None, environ=None):
    """Exige o destino já preparado; nunca cria uma alternativa local."""
    env = os.environ if environ is None else environ
    base = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    configurado = env.get("JANUS_DATA_DIR", "").strip()
    if not configurado:
        return base
    destino = Path(configurado).expanduser()
    if not destino.is_absolute():
        raise ValueError("JANUS_DATA_DIR deve ser um caminho absoluto.")
    if not destino.is_dir():
        raise FileNotFoundError(f"Dados indisponíveis: {destino}. Conecte o USB e confira JANUS_DATA_DIR.")
    return destino


def resolver_caminho_memoria(base_dir=None, environ=None):
    env = os.environ if environ is None else environ
    base = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    configurado = env.get("JANUS_DB_PATH", "").strip()
    if not configurado:
        # Preserva o banco existente, inclusive ao iniciar de outra pasta.
        destino = resolver_pasta_dados(base, env) / "memoria_jarvis_v2"
        if not env.get("JANUS_DATA_DIR", "").strip():
            return destino
        configurado = str(destino)
    destino = Path(configurado).expanduser()
    if not destino.is_absolute():
        raise ValueError("JANUS_DB_PATH deve ser um caminho absoluto.")
    if not destino.is_dir():
        raise FileNotFoundError(
            f"Memória indisponível: {destino}. Conecte o pen drive e confira JANUS_DB_PATH."
        )
    if not (destino / "chroma.sqlite3").is_file():
        raise FileNotFoundError(
            f"Banco não encontrado em {destino}. Copie a pasta completa de memória "
            "com o Janus fechado antes de configurar JANUS_DB_PATH."
        )
    return destino
