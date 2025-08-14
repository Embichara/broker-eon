# carriers/dhl_client.py
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(".env")

def _get_env(name, default=None):
    v = os.getenv(name, default)
    if isinstance(v, str):
        v = v.strip()
    return v

DHL_API_KEY     = _get_env("DHL_API_KEY")
DHL_API_SECRET  = _get_env("DHL_API_SECRET")  # opcional (fallback Basic)
DHL_ACCOUNT     = _get_env("DHL_ACCOUNT_NUMBER")
ENV             = (_get_env("DHL_ENV", "sandbox") or "sandbox").lower()

# Si tu tenant te dio usuario/contraseña explícitos para Basic:
BASIC_USER = _get_env("DHL_BASIC_USER")
BASIC_PASS = _get_env("DHL_BASIC_PASS")

BASE = (
    "https://express.api.dhl.com/mydhlapi"
    if ENV in ("prod", "production", "live")
    else "https://express.api.dhl.com/mydhlapi/test"
)

def _today_iso_date():
    return datetime.utcnow().date().isoformat()

def _iso_in(hours: int = 2):
    return (datetime.utcnow() + timedelta(hours=hours)).replace(microsecond=0).isoformat() + "Z"

def _headers():
    if not DHL_API_KEY:
        raise RuntimeError("Falta DHL_API_KEY en .env")
    return {
        "Accept": "application/json",
        "DHL-API-Key": DHL_API_KEY,
    }

def _auth_primary():
    # Si hay credenciales explícitas de Basic en .env
    if BASIC_USER and BASIC_PASS:
        return (BASIC_USER, BASIC_PASS)
    # Si no, intenta con API_KEY/API_SECRET (algunos tenants lo usan como Basic)
    if DHL_API_KEY and DHL_API_SECRET:
        return (DHL_API_KEY, DHL_API_SECRET)
    return None

def _mk_params(origen_cp, destino_cp, peso_kg, largo, ancho, alto,
               origin_city, dest_city, origin_country, dest_country,
               is_customs_declarable):
    # Envío doméstico: no declarable. Internacional: respeta flag (default True).
    customs = False
    if origin_country.upper() != dest_country.upper():
        customs = bool(is_customs_declarable) if is_customs_declarable is not None else True

    params = {
        "originCountryCode": origin_country.upper(),
        "originPostalCode": str(origen_cp).strip(),
        "destinationCountryCode": dest_country.upper(),
        "destinationPostalCode": str(destino_cp).strip(),
        "plannedShippingDate": _today_iso_date(),
        "unitOfMeasurement": "metric",
        "strictValidation": "false",
        "isCustomsDeclarable": "true" if customs else "false",
        "weight": float(peso_kg),
        "length": float(largo),
        "width": float(ancho),
        "height": float(alto),
    }
    if origin_city:
        params["originCityName"] = origin_city
    if dest_city:
        params["destinationCityName"] = dest_city
    return params

def cotizar_dhl(
    origen_cp: str,
    destino_cp: str,
    peso_kg: float,
    *,
    largo: float = 10.0,
    ancho: float = 10.0,
    alto: float = 10.0,
    origin_city: str | None = None,
    dest_city: str | None = None,
    origin_country: str = "MX",
    dest_country: str = "MX",
    is_customs_declarable: bool | None = None,  # aceptado por compatibilidad con tu UI
) -> dict:
    """
    Intenta /rates con varias estrategias para evitar 401:
      1) Header DHL-API-Key + accountNumber
      2) (si 401) Header + Basic Auth
      3) (si 401 y sandbox) Header (+Basic si disponible) sin accountNumber
    Devuelve: {"mode": "GET", "attempt": <int>, "url": <url>, "json": <dict>}
    """
    headers = _headers()
    url = f"{BASE}/rates"

    # Params base
    params = _mk_params(
        origen_cp, destino_cp, peso_kg, largo, ancho, alto,
        origin_city, dest_city, origin_country, dest_country,
        is_customs_declarable,
    )

    attempts = []

    # ---- Attempt 1: API-Key + accountNumber (si hay cuenta)
    auth = None
    if DHL_ACCOUNT:
        params_1 = dict(params)
        params_1["accountNumber"] = DHL_ACCOUNT
        r1 = requests.get(url, headers=headers, params=params_1, auth=auth, timeout=45)
        attempts.append(("APIKEY+ACC", r1.status_code, r1.url, r1.text))
        if r1.status_code < 400:
            return {"mode": "GET", "attempt": 1, "url": r1.url, "json": r1.json()}
        if r1.status_code != 401:
            # error diferente a 401: propagar
            raise requests.HTTPError(f"{r1.status_code} {r1.reason}\nURL={r1.url}\nBODY={r1.text}", response=r1)

    # ---- Attempt 2: API-Key + Basic Auth + accountNumber
    auth = _auth_primary()
    if auth and DHL_ACCOUNT:
        params_2 = dict(params)
        params_2["accountNumber"] = DHL_ACCOUNT
        r2 = requests.get(url, headers=headers, params=params_2, auth=auth, timeout=45)
        attempts.append(("APIKEY+BASIC+ACC", r2.status_code, r2.url, r2.text))
        if r2.status_code < 400:
            return {"mode": "GET", "attempt": 2, "url": r2.url, "json": r2.json()}
        if r2.status_code != 401:
            raise requests.HTTPError(f"{r2.status_code} {r2.reason}\nURL={r2.url}\nBODY={r2.text}", response=r2)

    # ---- Attempt 3 (solo sandbox): sin accountNumber
    if ENV != "prod":
        params_3 = dict(params)
        # sin accountNumber
        r3 = requests.get(url, headers=headers, params=params_3, auth=auth, timeout=45)
        attempts.append(("SANDBOX_NO_ACC" + ("+BASIC" if auth else ""), r3.status_code, r3.url, r3.text))
        if r3.status_code < 400:
            return {"mode": "GET", "attempt": 3, "url": r3.url, "json": r3.json()}
        # si aquí no es 401, propaga
        if r3.status_code != 401:
            raise requests.HTTPError(f"{r3.status_code} {r3.reason}\nURL={r3.url}\nBODY={r3.text}", response=r3)

    # Si todos fallan con 401
    # Construimos un mensaje claro con los intentos realizados (sin exponer el API Key)
    lines = ["All attempts failed for /rates (401 Unauthorized). Tried:"]
    for label, code, tried_url, body in attempts:
        lines.append(f"- {label}: {code}\n  URL={tried_url}\n  BODY={body}")
    raise requests.HTTPError("\n".join(lines))

def normalizar_ofertas_dhl(data_json: dict) -> list[dict]:
    ofertas = []
    products = data_json.get("products") or []
    for p in products:
        code = p.get("productCode")
        name = p.get("productName") or code or "N/D"
        total_prices = p.get("totalPrice") or []
        price_mxn = next((x for x in total_prices if (x or {}).get("priceCurrency") == "MXN"), None)
        price_any = price_mxn or (total_prices[0] if total_prices else None)
        price = (price_any or {}).get("price")
        curr = (price_any or {}).get("priceCurrency") or "MXN"

        deliv = p.get("deliveryCapabilities") or {}
        eta = deliv.get("estimatedDeliveryDateAndTime")
        etd_days = deliv.get("totalTransitDays")
        etd = None
        if isinstance(etd_days, (int, float)) or (isinstance(etd_days, str) and etd_days.isdigit()):
            etd = int(etd_days)

        if code is not None and price is not None:
            ofertas.append({
                "productCode": code,
                "productName": name,
                "totalPrice": float(price),
                "currency": curr,
                "eta": eta,
                "etd_days": etd,
                "raw": p,
            })
    ofertas.sort(key=lambda x: x["totalPrice"])
    return ofertas