"""Entrada do Janus. Sem argumentos: interface; --cli: console clássico."""
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from memory_config import resolver_pasta_dados, resolver_caminho_memoria


def main():
    parser = argparse.ArgumentParser(description="Janus — assistente pessoal")
    parser.add_argument('--cli', action='store_true', help='Usar o console clássico')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent / '.env')
    try:
        pasta = resolver_pasta_dados()
        resolver_caminho_memoria()
        os.chdir(pasta)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Armazenamento indisponível: {exc}\n')
    if args.cli:
        from janus.runtime import main as console
        console()
    else:
        from janus.server import run
        run(args.port)


if __name__ == '__main__':
    main()
