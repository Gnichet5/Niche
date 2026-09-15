import ast
from pathlib import Path
import tempfile
import unittest

from memory_config import resolver_caminho_memoria


class MemoriaTests(unittest.TestCase):
    def test_padrao_preserva_banco_e_ignora_drive_antigo(self):
        base = Path(__file__).resolve().parent
        self.assertEqual(
            resolver_caminho_memoria(base, {"JARVIS_DB_PATH": "G:/antigo"}),
            base / "memoria_jarvis_v2",
        )

    def test_caminho_relativo_rejeitado(self):
        with self.assertRaises(ValueError):
            resolver_caminho_memoria(environ={"JANUS_DB_PATH": "memoria"})

    def test_unidade_ausente_nao_cria_pasta(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "ausente"
            with self.assertRaises(FileNotFoundError):
                resolver_caminho_memoria(environ={"JANUS_DB_PATH": str(destino)})
            self.assertFalse(destino.exists())

    def test_exige_banco_migrado(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"JANUS_DB_PATH": tmp}
            with self.assertRaises(FileNotFoundError):
                resolver_caminho_memoria(environ=env)
            # Apenas valida caminho; não abre o Chroma nem o banco real.
            (Path(tmp) / "chroma.sqlite3").touch()
            self.assertEqual(resolver_caminho_memoria(environ=env), Path(tmp))

    def test_registro_expoe_apenas_ferramentas_publicas(self):
        source = Path(__file__).with_name("tools.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        publicas = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)
                    and not n.name.startswith("_")}
        registro = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "FERRAMENTAS_JANUS"
                                for t in n.targets))
        nomes = [n.id for n in registro.elts]
        self.assertEqual(set(nomes), publicas)
        self.assertEqual(len(nomes), len(set(nomes)))


if __name__ == "__main__":
    unittest.main()
