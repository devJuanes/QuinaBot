"""
Login IQ Option en proceso separado (evita NotImplementedError con uvicorn en Windows).
Escribe resultado en broker_status.json.
"""
import sys
import os
import json
import asyncio

os.chdir(os.path.dirname(os.path.abspath(__file__)))
# Proceso separado: usa event loop por defecto (ProactorEventLoop en Windows soporta subprocess)

STATUS_FILE = os.path.join(os.path.dirname(__file__), "broker_status.json")


def write_status(status: str, error: str = None):
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump({"status": status, "error": error, "logged_in": status == "success"}, f)
    except Exception:
        pass


async def main():
    write_status("pending")
    try:
        from automation import run_iq_login
        result = await run_iq_login(keep_open=False, headless=True)
        write_status("success" if result else "error", None if result else "Login fallido")
    except Exception as e:
        write_status("error", str(e))


if __name__ == "__main__":
    asyncio.run(main())
