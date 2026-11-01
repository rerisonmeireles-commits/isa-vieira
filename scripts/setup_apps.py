#!/usr/bin/env python3
"""
setup_apps.py
Cria os 14 apps do projeto Django dentro de apps/ e corrige o AppConfig
(name = "apps.<app>") automaticamente.

Uso:
    python setup_apps.py            # cria apps que faltam + corrige apps.py
    python setup_apps.py --fix-only # só corrige o name nos apps existentes
    python setup_apps.py --force    # apaga e recria os apps existentes

Requisitos:
    - Rodar na raiz do projeto (onde está o manage.py)
    - manage.py configurado com AUTH_USER_MODEL = "accounts.Usuario"
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

APPS = [
    "accounts", "clinic", "registry", "professionals", "patients",
    "insurance", "scheduling", "attendance", "clinical", "exercise",
    "documents", "financial", "communication", "audit",
]

BASE_DIR = Path(__file__).resolve().parent
APPS_DIR = BASE_DIR / "apps"
MANAGE_PY = BASE_DIR / "manage.py"


def run_manage(*args):
    """Executa `python manage.py <args>` com o interpretador atual."""
    return subprocess.run(
        [sys.executable, str(MANAGE_PY), *args],
        cwd=BASE_DIR,
    )


def corrigir_apps_config(app):
    """Troca name = '<app>' por name = 'apps.<app>' no apps.py."""
    arquivo = APPS_DIR / app / "apps.py"
    if not arquivo.exists():
        return False
    conteudo = arquivo.read_text(encoding="utf-8")
    novo = re.sub(
        r"name\s*=\s*['\"]([^'\"]+)['\"]",
        f'name = "apps.{app}"',
        conteudo,
        count=1,
    )
    if novo != conteudo:
        arquivo.write_text(novo, encoding="utf-8")
        return True
    return False


def criar_app(app, force=False):
    """Cria um app (ou remove+recria se force) e corrige o apps.py."""
    destino = APPS_DIR / app

    # Só pula o app se o diretório existir E tiver conteúdo (app real).
    # Diretório vazio ou inexistente → cria e preenche via startapp.
    if destino.exists() and any(destino.iterdir()):
        if not force:
            return "existe"
        shutil.rmtree(destino)

    # ⚠️ A mudança-chave: o startapp NÃO cria o diretório de destino.
    # Precisamos criá-lo antes, senão o Django aborta com CommandError.
    destino.mkdir(parents=True, exist_ok=True)

    resultado = run_manage("startapp", app, f"apps/{app}")
    if resultado.returncode != 0:
        return "erro"

    return "criado"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix-only", action="store_true",
                        help="Apenas corrige o name nos apps já existentes.")
    parser.add_argument("--force", action="store_true",
                        help="Apaga e recria apps existentes (perde conteúdo).")
    args = parser.parse_args()

    if not MANAGE_PY.exists():
        sys.exit("ERRO: manage.py não encontrado. Execute o script na raiz do projeto.")

    APPS_DIR.mkdir(exist_ok=True)
    (APPS_DIR / "__init__.py").touch(exist_ok=True)

    criados = []
    existentes = []
    corrigidos = []

    for app in APPS:
        if args.fix_only:
            if corrigir_apps_config(app):
                corrigidos.append(app)
            continue

        status = criar_app(app, force=args.force)

        if status == "erro":
            print(f"  [ERRO] {app}: falha no startapp.")
            continue

        if status == "existe":
            existentes.append(app)
        else:
            criados.append(app)

        if corrigir_apps_config(app):
            corrigidos.append(app)

    print("\nResumo:")
    print(f"  Criados:      {', '.join(criados) or 'nenhum'}")
    print(f"  Já existiam:  {', '.join(existentes) or 'nenhum'}")
    print(f"  apps.py OK:   {', '.join(corrigidos) or 'nenhum'}")

    if not args.fix_only and existentes:
        print("\nDica: apps já existentes foram verificados. Se algum ainda apontar")
        print("      name = '<app>', rode: python setup_apps.py --fix-only")


if __name__ == "__main__":
    main()