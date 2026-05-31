import asyncio
import edge_tts

# Mexican Spanish voices: es-MX-DaliaNeural (female), es-MX-JorgeNeural (male)
VOICE_ES = "es-MX-DaliaNeural"
VOICE_EN = "en-US-AriaNeural"


async def _speak(text: str, path: str, voice: str, rate: str = "+0%") -> None:
    await edge_tts.Communicate(text, voice, rate=rate).save(path)


def generate_speech(text: str, path: str, rate: str = "+0%",
                    lang: str = "es") -> None:
    voice = VOICE_ES if lang == "es" else VOICE_EN
    asyncio.run(_speak(text, path, voice, rate))
