import os
import time
import math
import struct
import threading
import logging
import pygame
import pyaudio
import speech_recognition as sr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class GerenciadorAudio:
    """
    Gerenciador de áudio avançado para o assistente Janus.
    Implementa:
    1. Reprodução assíncrona com suporte a interrupção por voz em tempo real (Full-Duplex).
    2. Detecção de palavra de ativação (Wake Word 'Janus') contínua em segundo plano.
    """

    def __init__(self, whisper_model=None, threshold_interrupcao=1500, threshold_wake=1200):
        self.whisper_model = whisper_model
        self.threshold_interrupcao = threshold_interrupcao  # Nível de RMS para considerar fala durante reprodução
        self.threshold_wake = threshold_wake               # Nível de RMS para iniciar escuta da Wake Word
        
        self.reproduzindo = False
        self.interrompido = False
        self.ouvidor_wake_ativo = False
        self.gatilho_wake_disparado = False

        self._lock = threading.Lock()
        
        # Inicializa Pygame Mixer para áudio se não tiver sido inicializado
        if not pygame.mixer.get_init():
            pygame.mixer.init()

    def _calcular_rms(self, chunk):
        """Calcula o Root Mean Square (RMS) de um bloco de áudio PCM 16-bit para medir volume."""
        count = len(chunk) // 2
        if count == 0:
            return 0
        format_str = f"{count}h"
        try:
            shorts = struct.unpack(format_str, chunk)
            sum_squares = sum(s ** 2 for s in shorts)
            return math.sqrt(sum_squares / count)
        except Exception:
            return 0

    def tocar_audio_com_interrupcao(self, arquivo_mp3):
        """
        Toca um arquivo de áudio MP3 enquanto monitora o microfone via PyAudio.
        Se o usuário começar a falar acima do threshold de áudio, a reprodução é interrompida na hora.
        """
        if not os.path.exists(arquivo_mp3):
            logging.warning(f"Arquivo de áudio não encontrado: {arquivo_mp3}")
            return False

        self.reproduzindo = True
        self.interrompido = False

        try:
            pygame.mixer.music.load(arquivo_mp3)
            pygame.mixer.music.play()
        except Exception as e:
            logging.error(f"Erro ao iniciar reprodução no pygame: {e}")
            self.reproduzindo = False
            return False

        # Configuração da captura de microfone para monitorar interrupção
        p = pyaudio.PyAudio()
        stream = None
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024
            )
        except Exception as e:
            logging.warning(f"Não foi possível abrir stream para monitorar interrupção: {e}")

        frames_voz_consecutivos = 0
        FRAMES_PARA_INTERROMPER = 3  # ~200ms de voz contínua para evitar disparos falsos

        while pygame.mixer.music.get_busy() and self.reproduzindo:
            if stream:
                try:
                    data = stream.read(1024, exception_on_overflow=False)
                    rms = self._calcular_rms(data)
                    
                    if rms > self.threshold_interrupcao:
                        frames_voz_consecutivos += 1
                        if frames_voz_consecutivos >= FRAMES_PARA_INTERROMPER:
                            logging.info(f"🔊 Interrupção por voz detectada! (RMS={int(rms)}). Parando áudio...")
                            pygame.mixer.music.stop()
                            self.interrompido = True
                            self.reproduzindo = False
                            break
                    else:
                        frames_voz_consecutivos = max(0, frames_voz_consecutivos - 1)
                except Exception as e:
                    logging.debug(f"Erro na leitura da stream de áudio: {e}")

            time.sleep(0.02)

        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        p.terminate()

        pygame.mixer.music.unload()
        try:
            if os.path.exists(arquivo_mp3):
                os.remove(arquivo_mp3)
        except Exception as e:
            logging.warning(f"Erro ao remover arquivo temporário de áudio: {e}")

        self.reproduzindo = False
        return self.interrompido

    def iniciar_monitoramento_wake_word(self, callback_ativacao):
        """
        Inicia uma thread em background para escutar a palavra de ativação 'Janus'.
        Quando detectada, chama 'callback_ativacao()'.
        """
        self.ouvidor_wake_ativo = True
        t = threading.Thread(target=self._loop_wake_word, args=(callback_ativacao,), daemon=True)
        t.start()
        logging.info("👂 Módulo de detecção de Wake Word ('Janus') iniciado em segundo plano.")

    def parar_monitoramento_wake_word(self):
        self.ouvidor_wake_ativo = False

    def _loop_wake_word(self, callback_ativacao):
        recognizer = sr.Recognizer()
        
        while self.ouvidor_wake_ativo:
            if self.reproduzindo:
                time.sleep(0.5)
                continue

            try:
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.2)
                    recognizer.pause_threshold = 0.8
                    try:
                        # Escuta de curtíssima duração (timeout curto)
                        audio = recognizer.listen(source, timeout=2.0, phrase_time_limit=3.0)
                        
                        texto = None
                        if self.whisper_model:
                            nome_temp = "temp_wake.wav"
                            with open(nome_temp, "wb") as f:
                                f.write(audio.get_wav_data())
                            segments, _ = self.whisper_model.transcribe(nome_temp, beam_size=1, language="pt", vad_filter=True)
                            texto = "".join([s.text for s in segments]).strip().lower()
                            if os.path.exists(nome_temp):
                                os.remove(nome_temp)
                        else:
                            try:
                                texto = recognizer.recognize_google(audio, language="pt-BR").lower()
                            except Exception:
                                pass

                        if texto:
                            logging.debug(f"[WakeWord Monitor] Ouvido: {texto}")
                            palavras_gatilho = ["janus", "janos", "janu", "jarvis", "ei janus", "hey janus"]
                            if any(gatilho in texto for gatilho in palavras_gatilho):
                                logging.info(f"✨ Palavra de ativação detectada: '{texto}'")
                                callback_ativacao(texto)
                                time.sleep(1.0) # Evita re-disparos imediatos
                    except sr.WaitTimeoutError:
                        pass
                    except Exception as e:
                        logging.debug(f"Erro temporário na captura de Wake Word: {e}")
            except Exception as e:
                logging.error(f"Erro no loop de Wake Word: {e}")
                time.sleep(1.0)

if __name__ == "__main__":
    print("Módulo de teste do GerenciadorAudio...")
    gerenciador = GerenciadorAudio()
    print("Instanciado com sucesso!")
