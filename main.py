"""Entrada do Janus. Sem argumentos: interface; --cli: console clássico."""
import argparse


def main():
    parser = argparse.ArgumentParser(description="Janus — assistente pessoal")
    parser.add_argument('--cli', action='store_true', help='Usar o console clássico')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if args.cli:
        from janus.runtime import main as console
        console()
    else:
        from janus.server import run
        run(args.port)


if __name__ == '__main__':
    main()
