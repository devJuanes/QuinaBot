"""
Script de depuracion: ejecuta login y muestra que detecta el scraper.
Ejecutar: python debug_broker_scrape.py
El navegador se abre visible (headless=False) para que puedas ver la pagina.
"""
import asyncio
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))


async def main():
    from automation import run_iq_login

    print("Iniciando login (navegador visible)...")
    broker = await run_iq_login(keep_open=True, headless=False)
    if not broker:
        print("Login fallido.")
        return

    print("Login OK. Esperando 10 segundos para que cargue la pagina...")
    await asyncio.sleep(10)

    # Guardar TODO el texto de la pagina para depuracion
    try:
        full_text = await broker.page.evaluate("""() => {
            function getFullText(root) {
                let t = '';
                const walk = (node) => {
                    if (!node) return;
                    if (node.nodeType === 3) t += node.textContent || '';
                    if (node.shadowRoot) walk(node.shadowRoot);
                    for (const c of node.childNodes || []) walk(c);
                };
                walk(root);
                return t;
            }
            return getFullText(document.body);
        }""")
        dump_path = os.path.join(os.path.dirname(__file__), "debug_page_text.txt")
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(full_text or "(vacio)")
        print(f"\nTexto completo de la pagina guardado en: {dump_path}")
        print(f"  (primeros 500 chars): {repr((full_text or '')[:500])}")
    except Exception as e:
        print(f"Error al extraer texto: {e}")

    print("\n--- Intentando obtener saldo y cuenta ---")
    bal = await broker.get_balance_and_account()
    print(f"  balance: {bal.get('balance')!r}")
    print(f"  account_type: {bal.get('account_type')!r}")

    print("\n--- Intentando obtener mercado ---")
    market = await broker.get_selected_market()
    print(f"  market: {market!r}")

    try:
        path = os.path.join(os.path.dirname(__file__), "debug_screenshot.png")
        await broker.page.screenshot(path=path)
        print(f"\nScreenshot guardado en: {path}")
    except Exception as e:
        print(f"No se pudo guardar screenshot: {e}")

    print("\nManteniendo navegador abierto 45 segundos para inspeccionar...")
    await asyncio.sleep(45)
    await broker.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
