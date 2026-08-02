import os
import time
import queue
import numpy as np
import pyaudio
import torch
from faster_whisper import WhisperModel

def int2float(sound):
    abs_max = np.abs(sound).max()
    sound = sound.astype('float32')
    if abs_max > 0:
        sound *= 1/32768
    sound = sound.squeeze()
    return sound

def main():
    print("Carregando Silero VAD...")
    # Carrega Silero VAD
    model_vad, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                      model='silero_vad',
                                      force_reload=False,
                                      trust_repo=True)
    (get_speech_timestamps, _, read_audio, VADIterator, collect_chunks) = utils
    
    print("Carregando Whisper Model (tiny para teste rápido)...")
    # Para teste rápido, usamos o modelo tiny ou base.
    whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    CHUNK = 512 # Pedaço de áudio pequeno para VAD

    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

    print("Escutando... Fale algo!")
    
    frames = []
    is_speaking = False
    silence_counter = 0
    SILENCE_THRESHOLD = int(RATE / CHUNK * 0.7) # 0.7 segundos de silêncio para cortar

    try:
        # Loop reduzido apenas para validar a funcionalidade (150 iterações aprox ~5 seg)
        for _ in range(300):
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_np = np.frombuffer(data, dtype=np.int16)
            audio_float = int2float(audio_np)
            tensor_audio = torch.from_numpy(audio_float)
            
            # Checa probabilidade de voz no chunk atual
            speech_prob = model_vad(tensor_audio, RATE).item()
            
            if speech_prob > 0.5:
                if not is_speaking:
                    print("Voz detectada! Gravando...")
                    is_speaking = True
                silence_counter = 0
                frames.append(data)
            else:
                if is_speaking:
                    frames.append(data)
                    silence_counter += 1
                    if silence_counter > SILENCE_THRESHOLD:
                        print("Fim de fala. Processando áudio no Whisper...")
                        break
    except KeyboardInterrupt:
        pass
    
    stream.stop_stream()
    stream.close()
    audio.terminate()
    
    if len(frames) > 0:
        import wave
        wf = wave.open("temp_test.wav", 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        print("Transcrevendo...")
        segments, info = whisper_model.transcribe("temp_test.wav", beam_size=1, language="pt")
        text = "".join([segment.text for segment in segments])
        print(f"Transcrição: {text}")
        
        if os.path.exists("temp_test.wav"):
            os.remove("temp_test.wav")
    else:
        print("Nenhuma voz foi gravada no tempo de teste.")
        
    print("Teste finalizado com sucesso.")

if __name__ == "__main__":
    main()
