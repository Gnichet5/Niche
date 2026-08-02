import asyncio
import edge_tts
import os
import time
from audio_manager import GerenciadorAudio

async def gerar_audio_teste(texto, arquivo="teste_fala.mp3"):
    communicate = edge_tts.Communicate(texto, "pt-BR-AntonioNeural", rate="+10%")
    await communicate.save(arquivo)

def main():
    print("--- TESTE DE INTEGRAÇÃO DO GERENCIADOR DE ÁUDIO ---")
    
    texto = "Teste de fala rapida do sistema Janus."
    
    print("1. Gerando audio de teste com Edge TTS...")
    asyncio.run(gerar_audio_teste(texto, "teste_fala.mp3"))
    print("Audio gerado com sucesso!")

    gerenciador = GerenciadorAudio(threshold_interrupcao=99999) # Threshold alto para nao interromper no ambiente de teste
    
    print("2. Reproduzindo audio...")
    interrompido = gerenciador.tocar_audio_com_interrupcao("teste_fala.mp3")
    
    if interrompido:
        print("[SUCESSO] Reproducao interrompida.")
    else:
        print("[SUCESSO] Reproducao concluida com exito.")

if __name__ == "__main__":
    main()
