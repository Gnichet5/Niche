import os
import time
import psutil
import subprocess
import logging

# Configuração do painel do Watchdog
logging.basicConfig(level=logging.INFO, format="%(asctime)s [WATCHDOG] %(message)s")

# Regras de Negócio do Auto-Healing
TIMEOUT_SEGUNDOS = 60  # Se o JARVIS ficar 1 minuto inteiro sem emitir pulso, ele mata
ARQUIVO_HEARTBEAT = "heartbeat.txt"
ARQUIVO_LOG_SISTEMA = "watchdog_historico.log"
NOME_SCRIPT_JARVIS = "main.py"

def buscar_pid_jarvis():
    """Vareja os processos do Windows atrás do Python rodando o main.py"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Verifica se é um processo python e se 'main.py' está nos argumentos
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                if proc.info['cmdline'] and any(NOME_SCRIPT_JARVIS in cmd for cmd in proc.info['cmdline']):
                    return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def registrar_incidente(motivo):
    """Deixa um bilhete para o JARVIS ler depois e saber que apagou"""
    with open(ARQUIVO_LOG_SISTEMA, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] INCIDENTE CRÍTICO: {motivo}\n")

def executar_auto_healing(pid_travado, motivo):
    """O executor: Mata sem dó e levanta limpo"""
    logging.warning(f"Iniciando protocolo de Auto-Healing. Motivo: {motivo}")
    registrar_incidente(motivo)

    if pid_travado:
        logging.info(f"Aniquilando processo travado (PID: {pid_travado})...")
        try:
            psutil.Process(pid_travado).kill()
            time.sleep(2)  # Dá um tempo pro Windows soltar os arquivos/drivers de áudio
        except Exception as e:
            logging.error(f"Erro ao tentar matar o processo: {e}")

    logging.info("Ressuscitando o JARVIS...")
    # Levanta uma nova janela independente com o script
    subprocess.Popen(f"start python {NOME_SCRIPT_JARVIS}", shell=True)
    
    # Reseta o pulso para não entrar em loop infinito de mortes
    with open(ARQUIVO_HEARTBEAT, "w") as f:
        f.write(str(time.time()))

def iniciar_monitoramento():
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 50)
    print(" WATCHDOG (MONITOR DE AUTO-HEALING) INICIADO ".center(50, "="))
    print("=" * 50)
    
    # Cria o arquivo de pulso se não existir para evitar falsos positivos no primeiro boot
    if not os.path.exists(ARQUIVO_HEARTBEAT):
        with open(ARQUIVO_HEARTBEAT, "w") as f:
            f.write(str(time.time()))

    while True:
        time.sleep(10)  # O Watchdog checa os sinais vitais a cada 10 segundos
        
        pid_jarvis = buscar_pid_jarvis()
        
        if not pid_jarvis:
            logging.error("O JARVIS não está rodando no momento.")
            executar_auto_healing(None, "Processo não encontrado (Crash Silencioso)")
            continue

        try:
            # Pega a última vez que o main.py bateu o ponto
            ultimo_pulso = os.path.getmtime(ARQUIVO_HEARTBEAT)
            tempo_agora = time.time()
            tempo_sem_resposta = tempo_agora - ultimo_pulso
            
            if tempo_sem_resposta > TIMEOUT_SEGUNDOS:
                logging.error(f"O JARVIS está catatônico! Sem sinais há {tempo_sem_resposta:.1f} segundos.")
                executar_auto_healing(pid_jarvis, f"Timeout de {TIMEOUT_SEGUNDOS}s estourado (Possível travamento de Driver/API)")
            else:
                logging.info(f"Status: SAUDÁVEL. (Último pulso há {tempo_sem_resposta:.1f}s)")
                
        except Exception as e:
            logging.error(f"Falha no monitoramento: {e}")

if __name__ == "__main__":
    iniciar_monitoramento()