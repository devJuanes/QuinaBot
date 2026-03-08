"""
QuinaBot — Automatización de broker (IQ Option).
Login con comportamiento humano (delays, typing) para evitar detección.
Credenciales: variables de entorno (.env). NUNCA hardcodear.
"""
import re
import sys
import asyncio
import random
import os
from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv

load_dotenv()

IQ_LOGIN_URL = os.getenv("IQ_OPTION_LOGIN_URL", "https://login.iqoption.com/es/login?redirect_url=traderoom%2F")


def _human_delay(min_ms: int = 300, max_ms: int = 700):
    """Delay aleatorio para simular comportamiento humano."""
    return asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def _human_type(page: Page, locator, text: str):
    """Escribir carácter por carácter con delay aleatorio."""
    await locator.click()
    await _human_delay(200, 400)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(80, 180))
    await _human_delay(150, 350)


class BrokerAutomation:
    def __init__(self, headless: bool = True):
        self.browser = None
        self.context = None
        self.page = None
        self.is_logged_in = False
        self.playwright = None
        self.headless = headless

    async def start(self):
        """Inicia el navegador (headless = sin ventana visible)."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-ES",
            timezone_id="Europe/Madrid",
        )
        self.page = await self.context.new_page()
        await self.page.goto(IQ_LOGIN_URL, wait_until="domcontentloaded")
        await _human_delay(1500, 2500)

    async def _accept_cookies(self):
        """Cierra el banner de cookies si aparece."""
        try:
            btn = self.page.get_by_role("button", name="Entendido")
            if await btn.is_visible():
                await _human_delay(400, 800)
                await btn.click()
                await _human_delay(500, 1000)
                return True
        except Exception:
            pass
        return False

    async def login(self, email: str, password: str) -> bool:
        """
        Inicia sesión en IQ Option.
        Retorna True si el login fue exitoso.
        """
        if not self.page:
            await self.start()

        try:
            await self._accept_cookies()

            # Email
            email_field = self.page.get_by_placeholder("Número de teléfono o correo electrónico")
            await email_field.wait_for(state="visible", timeout=8000)
            await _human_delay(300, 600)
            await _human_type(self.page, email_field, email)

            await _human_delay(400, 800)

            # Contraseña
            password_field = self.page.get_by_placeholder("Contraseña")
            await _human_type(self.page, password_field, password)

            await _human_delay(600, 1200)

            # Botón Entrar (submit del formulario, no Facebook/Google)
            await self.page.locator('[data-test-id="login-submit-button"]').click()

            # Esperar redirección al traderoom
            try:
                await self.page.wait_for_url(
                    lambda u: "traderoom" in u,
                    timeout=15000,
                )
            except Exception:
                pass

            await _human_delay(2000, 3500)

            url = self.page.url
            if "traderoom" in url or "login" not in url:
                self.is_logged_in = True
                self._log_success(email, url)
                return True

            self._log_failure("No se detectó redirección al traderoom")
            return False

        except Exception as e:
            self._log_failure(str(e))
            return False

    def _log_success(self, email: str, url: str):
        print("\n" + "=" * 50)
        print("[OK] LOGIN EXITOSO - IQ Option")
        print("=" * 50)
        print(f"   Email: {email[:3]}***{email[email.find('@'):]}")
        print(f"   URL actual: {url[:60]}...")
        print("=" * 50 + "\n")

    def _log_failure(self, reason: str):
        print("\n" + "=" * 50)
        print("[ERROR] LOGIN FALLIDO - IQ Option")
        print("=" * 50)
        print(f"   Motivo: {reason}")
        print("=" * 50 + "\n")

    async def _click_balance_dropdown(self) -> bool:
        """Abre el dropdown de saldo/cuenta haciendo click en el area del header. Dinamico."""
        try:
            # Estrategia 1: Click en elemento que contiene saldo ($ 108,920 o COL$ 1,340)
            for pattern in [re.compile(r"\$\s*[\d,.]+"), re.compile(r"COL\$\s*[\d,.]+")]:
                try:
                    loc = self.page.get_by_text(pattern).first
                    if await loc.count() > 0:
                        box = await loc.bounding_box()
                        if box and box["x"] > 400:  # Derecha de pantalla (header)
                            await loc.click()
                            await _human_delay(400, 700)
                            return True
                except Exception:
                    pass
            # Estrategia 2: Usar evaluate para encontrar y clickear el elemento del saldo
            clicked = await self.page.evaluate("""() => {
                const re = /(\\$|COL\\$)\\s*[\\d,.]+/;
                const els = Array.from(document.querySelectorAll('button, a, [role="button"], [class*="balance"], [class*="Balance"], [class*="dropdown"], [class*="Dropdown"]'));
                for (const el of els) {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (re.test(t)) {
                        const rect = el.getBoundingClientRect();
                        if (rect.right > 400 && rect.width > 30) {
                            el.click();
                            return true;
                        }
                    }
                }
                const all = Array.from(document.querySelectorAll('*'));
                for (const el of all) {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (re.test(t) && t.length < 25) {
                        const rect = el.getBoundingClientRect();
                        if (rect.right > window.innerWidth * 0.6 && rect.top < 150) {
                            el.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if clicked:
                await _human_delay(400, 700)
                return True
            return False
        except Exception:
            return False

    def _extract_from_text(self, text: str) -> tuple:
        """Extrae saldo y tipo de cuenta de texto plano. Fallback robusto."""
        balance = None
        account_type = None
        if not text:
            return balance, account_type
        m = re.search(r"(\$|COL\$)\s*[\d,.]+", text)
        if m:
            balance = m.group(0).strip()
        if "CUENTA DE PRÁCTICA" in text or "CUENTA DE PRACTICA" in text:
            if "CUENTA REAL" in text:
                account_type = "real" if "COL" in (balance or "") else "demo"
            else:
                account_type = "demo"
        elif "CUENTA REAL" in text:
            account_type = "real"
        if not account_type and balance:
            account_type = "real" if "COL" in balance else "demo"
        return balance, account_type

    async def get_balance_and_account(self):
        """Obtiene saldo y tipo de cuenta desde IQ Option. Incluye shadow DOM e iframes."""
        if not self.page or not self.is_logged_in:
            return {"balance": None, "account_type": None}
        balance = None
        account_type = None
        try:
            # 0) Esperar a que aparezca contenido de saldo (SPA carga async)
            try:
                await self.page.wait_for_function(
                    "() => /(\\$|COL\\$)\\s*[\\d,.]+/.test(document.body.innerText || '')",
                    timeout=12000,
                )
            except Exception:
                pass

            # 1) Extraer de body (incluyendo shadow DOM)
            result = await self.page.evaluate("""() => {
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
            if result:
                balance, account_type = self._extract_from_text(result)

            # 2) Si no hay nada, intentar iframes
            if not balance:
                frames = self.page.frames
                for frame in frames:
                    if frame == self.page.main_frame:
                        continue
                    try:
                        text = await frame.evaluate("""() => document.body ? (document.body.innerText || document.body.textContent || '') : ''""")
                        if text and ("$" in text or "COL" in text):
                            b, a = self._extract_from_text(text)
                            if b:
                                balance, account_type = b, a
                                break
                    except Exception:
                        pass

            # 3) Fallback: innerText directo del body
            if not balance:
                text = await self.page.evaluate("() => document.body.innerText || document.body.textContent || ''")
                balance, account_type = self._extract_from_text(text)

            # 4) Abrir dropdown para forzar render y obtener datos
            if not balance or not account_type:
                await self._click_balance_dropdown()
                await _human_delay(500, 800)
                text = await self.page.evaluate("() => document.body.innerText || ''")
                b, a = self._extract_from_text(text)
                if b:
                    balance = b
                if a:
                    account_type = a
                await self.page.keyboard.press("Escape")
        except Exception:
            pass
        return {"balance": balance, "account_type": account_type}

    async def get_selected_market(self):
        """Obtiene el mercado seleccionado (ej. BTC/USD (OTC) Blitz). Dinamico."""
        if not self.page or not self.is_logged_in:
            return None
        try:
            return await self.page.evaluate("""() => {
                const re = /[A-Z]{2,5}\\/[A-Z]{2,5}(\\s*\\(?OTC\\)?)?(\\s*Blitz)?/i;
                const matches = [];
                document.querySelectorAll('*').forEach(el => {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (re.test(t) && t.length < 50 && t.length > 5) {
                        const m = t.match(re);
                        if (m && !matches.includes(m[0])) matches.push(m[0].trim());
                    }
                });
                return matches[0] || null;
            }""")
        except Exception:
            pass
        return None

    async def switch_account(self, to_demo: bool = None):
        """Cambia entre cuenta Real y Demo. Dinamico: abre dropdown y hace click en la opcion."""
        if not self.page or not self.is_logged_in:
            return False
        try:
            if not await self._click_balance_dropdown():
                return False
            await _human_delay(500, 900)
            if to_demo is True:
                btn = self.page.get_by_text("CUENTA DE PRÁCTICA", exact=False).or_(
                    self.page.get_by_text("CUENTA DE PRACTICA", exact=False)
                ).first
            elif to_demo is False:
                btn = self.page.get_by_text("CUENTA REAL", exact=False).first
            else:
                # Alternar: ir a demo por defecto si no se especifica
                btn = self.page.get_by_text("CUENTA DE PRÁCTICA", exact=False).or_(
                    self.page.get_by_text("CUENTA DE PRACTICA", exact=False)
                ).first
            await btn.click()
            await _human_delay(1200, 2200)
            return True
        except Exception:
            return False

    async def select_market(self, market_name: str):
        """Selecciona un mercado (ej. BTC/USD OTC)."""
        if not self.page or not self.is_logged_in:
            return False
        try:
            market_btn = self.page.locator("[data-test-id='asset-selector'], [class*='asset-selector']").first
            await market_btn.click()
            await _human_delay(500, 1000)
            await self.page.get_by_text(market_name, exact=False).first.click()
            await _human_delay(1000, 2000)
            return True
        except Exception:
            return False

    async def execute_trade(self, signal_type: str, symbol: str, amount: float):
        """Placeholder para ejecutar operaciones (próxima fase)."""
        if not self.is_logged_in:
            print("[!] No hay sesion activa. Abortando.")
            return False
        print(f"[>>] Executing {signal_type} for {symbol} | Amount: {amount}")
        return True

    async def cleanup(self):
        """Cierra el navegador."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("[*] Sesion cerrada.")


# Instancia global y estado del login (para API/UI)
_broker_instance = None
_broker_login_status = {"status": "idle", "error": None}  # idle | pending | success | error


def get_broker():
    """Devuelve la instancia del broker si existe."""
    global _broker_instance
    return _broker_instance


def get_broker_status():
    """Estado del login: status, error, logged_in."""
    global _broker_instance, _broker_login_status
    logged = _broker_instance.is_logged_in if _broker_instance else False
    return {**_broker_login_status, "logged_in": logged}


async def run_iq_login(keep_open: bool = True, headless: bool = True):
    """
    Ejecuta el login con credenciales de .env.
    headless=True: sin ventana visible.
    keep_open=True: mantiene sesion para operar.
    """
    global _broker_instance, _broker_login_status
    _broker_login_status = {"status": "pending", "error": None}

    email = os.getenv("IQ_OPTION_EMAIL")
    password = os.getenv("IQ_OPTION_PASSWORD")

    if not email or not password:
        _broker_login_status = {"status": "error", "error": "Faltan credenciales en .env"}
        return None

    broker = BrokerAutomation(headless=headless)
    _broker_instance = broker
    try:
        success = await broker.login(email, password)
        if success:
            _broker_login_status = {"status": "success", "error": None}
            if not keep_open:
                await broker.cleanup()
                _broker_instance = None
            return broker
        _broker_login_status = {"status": "error", "error": "Login fallido"}
        await broker.cleanup()
        _broker_instance = None
        return None
    except Exception as e:
        _broker_login_status = {"status": "error", "error": str(e)}
        try:
            await broker.cleanup()
        except Exception:
            pass
        _broker_instance = None
        return None


async def _keep_alive():
    """Mantiene el proceso vivo para que el navegador no se cierre (solo CLI)."""
    global _broker_instance
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        b = get_broker()
        if b:
            await b.cleanup()
        _broker_instance = None


if __name__ == "__main__":
    import sys
    keep = "--keep-open" in sys.argv or "-k" in sys.argv
    async def main():
        result = await run_iq_login(keep_open=keep)
        if result and keep:
            print("[*] Presiona Ctrl+C para cerrar.")
            await _keep_alive()
    asyncio.run(main())
