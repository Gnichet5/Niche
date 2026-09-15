"""Aprovações por contexto: console e navegador usam o mesmo contrato."""
from contextvars import ContextVar

aprovador = ContextVar('aprovador', default=None)


def confirmar_acao(nome, argumentos):
    callback = aprovador.get()
    if callback is not None:
        return callback(nome, argumentos)
    print(f'\nJanus deseja executar {nome}: {argumentos}')
    return input('Permitir a execução? (S/N): ').strip().lower() == 's'
