# carriers/dhl_client.py
import os, base64, json, requests
from datetime import datetime, timedelta
from urllib.parse import urlencode
from dotenv import load_dotenv

# Carga variables .env (busca en cwd)
load_dotenv(".env")

# --- Helpers de tiempo ---
def _iso_utc():
    # DHL acepta plannedShippingDateAndTime en ISO8601 (UTC)
    return (datetime.utcnow() + timedelta(minutes=2)).replace(microsecond=0).isoformat() + "Z"

def _today():
    return datetime.utcnow().date().isoformat()

# --- Config base / entorno ---
def _base_url():
    env = (os.getenv("DHL_ENV") or "sandbox").lower()
    # En sandbox/test el endpoint real suele ser el /express.api.../test
    if env in ("sandbox", "test"):
        return "https://express.api.dhl.com/mydhlapi/test"
    # Producción
    return "https://express.api.dhl.com/mydhlapi"

def _basic_headers():
    key = os.getenv("DHL_API_KEY")
    secret = os.getenv("DHL_API_SECRET")
    if not key or not secret:
        raise RuntimeError("Faltan DHL_API_KEY y/o DHL_API_SECRET en .env")

    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
    }

# ------------------- API: /rates -------------------
def cotizar_dhl(
    origen_cp: str,
    destino_cp: str,
    peso_kg: float,
    largo: float = 10.0,
    ancho: float = 10.0,
    alto: float = 10.0,
    origin_country: str = "MX",
    dest_country: str = "MX",
    origin_city: str | None = None,
    dest_city: str | None = None,
    is_customs_declarable: bool = False,
):
    if not origin_city or not dest_city:
        raise RuntimeError("DHL requiere originCityName y destinationCityName (ciudades).")

    base = _base_url()
    headers = _basic_headers()

    # --- Fechas candidatas: próximos 7 días, privilegiando días hábiles ---
    from datetime import date, timedelta
    hoy = date.today()
    candidates = []
    # primero agrega próximo lunes si hoy es sábado/domingo
    for i in range(0, 7):
        d = hoy + timedelta(days=i)
        candidates.append(d)

    def is_weekend(d: date):
        return d.weekday() >= 5  # 5=sábado, 6=domingo

    # reordena: días hábiles primero
    candidates.sort(key=lambda d: (is_weekend(d), d))

    account = os.getenv("DHL_ACCOUNT_NUMBER")
    if not account:
        raise RuntimeError("Falta DHL_ACCOUNT_NUMBER en .env")

    base_params = dict(
        accountNumber=account,
        originCountryCode=origin_country,
        originPostalCode=str(origen_cp),
        originCityName=origin_city,
        destinationCountryCode=dest_country,
        destinationPostalCode=str(destino_cp),
        destinationCityName=dest_city,
        unitOfMeasurement="metric",
        isCustomsDeclarable=str(is_customs_declarable).lower(),
        weight=float(peso_kg),
        length=float(largo),
        width=float(ancho),
        height=float(alto),
        strictValidation="false",
    )

    errors = []
    # --- Intentos GET por cada fecha candidata ---
    for d in candidates:
        # 1) plannedShippingDate solo
        params = {**base_params, "plannedShippingDate": d.isoformat()}
        url = f"{base}/rates?{urlencode(params)}"
        r = requests.get(url, headers=headers, timeout=45)
        if r.status_code == 200:
            return {"mode": "GET", "url": r.url, "params": params, "json": r.json()}

        errors.append(("GET", r.status_code, r.reason, url, r.text[:800]))

        # 2) plannedShippingDate + plannedShippingDateAndTime
        params2 = {**params, "plannedShippingDateAndTime": (datetime.utcnow().replace(microsecond=0).isoformat() + "Z")}
        url2 = f"{base}/rates?{urlencode(params2)}"
        r2 = requests.get(url2, headers=headers, timeout=45)
        if r2.status_code == 200:
            return {"mode": "GET", "url": r2.url, "params": params2, "json": r2.json()}

        errors.append(("GET", r2.status_code, r2.reason, url2, r2.text[:800]))

    # --- POST como plan C con la primera fecha hábil de candidates ---
    d0 = next((d for d in candidates if not is_weekend(d)), candidates[0])
    body = {
        "customerDetails": {
            "shipperDetails":   {"postalCode": str(origen_cp),  "countryCode": origin_country, "cityName": origin_city},
            "receiverDetails":  {"postalCode": str(destino_cp), "countryCode": dest_country,   "cityName": dest_city},
        },
        "accounts": [{"number": account, "typeCode": "shipper"}],
        "plannedShippingDateAndTime": (datetime.utcnow().replace(microsecond=0).isoformat() + "Z"),
        "unitOfMeasurement": "metric",
        "isCustomsDeclarable": bool(is_customs_declarable),
        "packages": [{"weight": float(peso_kg), "dimensions": {"length": float(largo), "width": float(ancho), "height": float(alto)}}],
        "requestAllValueAddedServices": True,
        # "productCode": "N",  # si tu tenant lo exige, prueba 'N' o 'G'
    }
    r3 = requests.post(f"{base}/rates", headers={**headers, "Content-Type": "application/json"}, json=body, timeout=60)
    if r3.status_code == 200:
        return {"mode": "POST", "url": f"{base}/rates", "body": body, "json": r3.json()}

    def short(txt): 
        return txt if len(txt) < 800 else txt[:800] + "...(+recortado)"
    raise RuntimeError(
        "All attempts failed for /rates (Basic Auth):\n\n" +
        "\n\n".join([f"{m} {code} {reason}\nURL={u}\nBODY={short(b)}" for (m,code,reason,u,b) in errors[:6]]) +
        (f"\n\nPOST {r3.status_code} {r3.reason}\nBODY={short(r3.text)}" if r3 is not None else "")
    )

# ------------------- Normalizador → ofertas internas -------------------
def normalizar_ofertas_dhl(resp_json: dict):
    """
    Convierte la respuesta de DHL en lista de ofertas estandarizadas:
    [{"carrier":"DHL","productCode":"G","productName":"ECONOMY SELECT DOMESTIC",
      "totalPrice":629.38,"currency":"MXN","eta":"2025-08-11","raw":{...}}, ...]
    """
    ofertas = []
    products = resp_json.get("products") or []
    for p in products:
        totals = p.get("totalPrice") or []
        total, currency = None, None
        # prioriza MXN
        for t in totals:
            if t.get("priceCurrency") == "MXN":
                total = t.get("price"); currency = "MXN"; break
        if total is None and totals:
            total = totals[0].get("price")
            currency = totals[0].get("priceCurrency")

        # ETA
        eta = None
        dc = p.get("deliveryCapabilities") or {}
        if dc.get("estimatedDeliveryDateAndTime"):
            eta = str(dc["estimatedDeliveryDateAndTime"]).split("T")[0]

        # Evita productos "cero" (operativos) si no traen monto
        if total is not None and float(total) > 0:
            ofertas.append({
                "carrier": "DHL",
                "productCode": p.get("productCode"),
                "productName": p.get("productName"),
                "totalPrice": float(total),
                "currency": currency or "MXN",
                "eta": eta,
                "raw": p,
            })

    ofertas.sort(key=lambda x: x["totalPrice"])
    return ofertas