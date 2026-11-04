# FILE: main.py
# Starts the WebSocket server and audio pipeline, then shuts both down cleanly.
import asyncio
import os
from pathlib import Path
from pipeline import AudioPipeline
from server.ws_server import WebSocketServer
from config import CLOUD_ENABLED, GROQ_API_KEY_1, GROQ_API_KEY_2, TTS_VOICE

async def run():
    print("Loading Jarvis backend...")
    # Initialize only from an explicitly configured shutdown password.
    try:
        from security.credentials import migrate_legacy_password
        migrate_legacy_password()
    except Exception as e:
        print(f"  ⚠️  Password migration skipped: {e}")
    server = WebSocketServer()
    await server.start()
    pipeline = AudioPipeline(server, asyncio.get_running_loop())
    server.on_message(pipeline.handle_message)
    print("  Loading LLM brain (Groq 5-Key Failover Pool)...")
    if not (GROQ_API_KEY_1 or GROQ_API_KEY_2):
        print("  ⚠️  No Groq API keys set - LLM will not work!")
    else:
        print("  ✓ Groq 5-Key Pool configured (Key 1: Router · Key 2: Coder · Keys 3, 4, 5: Dynamic Fallback)")
    print(f"  TTS voice: {TTS_VOICE}")

    pipeline.start()
    async def heartbeat():
        heartbeat_path = Path(__file__).resolve().parent / "data" / "heartbeat"
        heartbeat_path.parent.mkdir(exist_ok=True)
        while True:
            heartbeat_path.touch()
            await asyncio.sleep(5)
    asyncio.create_task(heartbeat())
    async def restart_watcher():
        sentinel = Path(__file__).resolve().parent / "data" / "restart_requested"
        while True:
            if sentinel.exists():
                # The supervisor consumes the sentinel and starts a clean process.
                os._exit(0)
            await asyncio.sleep(0.5)
    asyncio.create_task(restart_watcher())
    # Start Cloud Gateway Bridge (allows phone companion to talk to Jarvis.bat directly)
    cloud_bridge = None
    try:
        if CLOUD_ENABLED:
            from cloud.cloud_bridge import CloudBridge
            cloud_bridge = CloudBridge()
            asyncio.create_task(cloud_bridge.start())
            print("  ✓ Cloud Bridge started (Phone Companion connected directly to Jarvis.bat)")
    except Exception as e:
        print(f"  ⚠️  Cloud Bridge failed to start: {e}")

    print("Jarvis backend ready. Listening for wake word.")
    try:
        await asyncio.Future()
    finally:
        if cloud_bridge:
            cloud_bridge.stop()
        pipeline.stop()
        await server.stop()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Jarvis backend stopped")
