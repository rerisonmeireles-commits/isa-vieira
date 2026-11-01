@echo off
cd /d C:\Projetos\isa_vieira\clinica_fisio
if not exist logs mkdir logs
.venv\Scripts\python.exe manage.py marcar_contas_atrasadas >> logs\marcar_contas_atrasadas.log 2>&1