@echo off
TITLE S.O.H.-X — Control Center
COLOR 0B
CLS

echo ###############################################################################
echo #                                                                             #
echo #                   CNGSM — S.O.H.-X CONTROL CENTER                           #
echo #                   Protocol: Omega-9 (Antigravity)                           #
echo #                                                                             #
echo ###############################################################################
echo.

:: 1. Iniciar Backend (API Starlette)
echo [1/3] Iniciando Kernel API (Porta 8000)...
start "SOH-X KERNEL" cmd /k "python backend\main.py"
timeout /t 2 >nul

:: 2. Iniciar Daemon do Hormuz
echo [2/3] Garantindo que o Daemon Hormuz esteja ativo...
schtasks /Run /TN "HormuzAgent" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Aviso: Nao foi possivel iniciar a tarefa agendada HormuzAgent.
) else (
    echo [OK] Daemon solicitado.
)

:: 3. Seleção de Modo Operacional
echo [3/3] Selecione o Modo Operacional:
echo.
echo [1] Dashboard Hormuz (Monitoramento e Tarefas)
echo [2] COWORKER Modo (Assistente de Programacao IA)
echo [3] MODO CONTEMPLATING (Pesquisa Profunda Multi-Agente)
echo [4] Sair
echo.

set /p choice="Escolha uma opcao [1-4]: "

if "%choice%"=="1" (
    cls
    python backend\hormuz\ui\cli.py "D:\Strait of Hormuz"
)
if "%choice%"=="2" (
    cls
    python backend\hormuz\ui\coworker_cli.py
)
if "%choice%"=="3" (
    cls
    python backend\contemplating_orchestrator.py
)
if "%choice%"=="4" (
    echo Encerrando sistema.
    exit
)

pause

