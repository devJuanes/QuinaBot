"""
Servicio de broker IQ Option: login, mantiene sesion, obtiene saldo/cuenta/mercado.
Se ejecuta en proceso separado. Escribe broker_data.json para la API.
"""
import sys
import os
import json
import asyncio

os.chdir(os.path.dirname(os.path.abspath(__file__)))
# No usar WindowsSelectorEventLoopPolicy: no soporta subprocess (Playwright lo necesita)

DATA_FILE = os.path.join(os.path.dirname(__file__), "broker_data.json")
CMD_FILE = os.path.join(os.path.dirname(__file__), "broker_cmd.json")


def write_data(data: dict):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def read_cmd():
    try:
        if os.path.exists(CMD_FILE):
            with open(CMD_FILE, "r", encoding="utf-8") as f:
                cmd = json.load(f)
            os.remove(CMD_FILE)
            return cmd
    except Exception:
        pass
    return None


async def main():
    from automation import run_iq_login, get_broker

    write_data({"status": "pending", "balance": None, "account_type": None, "market": None})
    headless = os.getenv("BROKER_HEADLESS", "true").lower() in ("1", "true", "yes")
    broker = await run_iq_login(keep_open=True, headless=headless)
    if not broker:
        write_data({"status": "error", "error": "Login fallido"})
        return

    write_data({"status": "success", "balance": None, "account_type": None, "market": None})
    await asyncio.sleep(8)  # Esperar a que la pagina de trading cargue completamente
    while True:
        try:
            cmd = read_cmd()
            if cmd:
                if cmd.get("command") == "switch_account":
                    await broker.switch_account(to_demo=cmd.get("to_demo"))
                elif cmd.get("command") == "select_market":
                    await broker.select_market(cmd.get("market", ""))

            bal = await broker.get_balance_and_account()
            market = await broker.get_selected_market()
            write_data({
                "status": "success",
                "balance": bal.get("balance"),
                "account_type": bal.get("account_type"),
                "market": market,
            })
        except Exception as e:
            write_data({"status": "error", "error": str(e)})
        await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
