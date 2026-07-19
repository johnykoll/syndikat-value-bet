"""
AI Skenovanie screenshotov (OCR + parsing).

Podporuje dvoch providerov - používateľ si v Nastaveniach vyberie, ktorého chce
použiť, a zadá vlastný API kľúč (ukladá sa iba do st.session_state, nikdy do DB).

  - OpenAI gpt-4o-mini (vision)
  - Google Gemini 2.5 Flash (vision)

Obe funkcie vracajú rovnaký normalizovaný dict:
{
  "sport": str, "liga": str, "timy": str, "soft_bookmaker": str,
  "typ_marketu": str, "tip": str, "soft_kurz": float, "skore": str,
  "match_date": str (ISO 'YYYY-MM-DD' ak je viditeľný dátum zápasu, inak ""),
  "match_time": str ('HH:MM' ak je viditeľný čas začiatku zápasu, inak "")
}
Ak sa parsovanie nepodarí, vráti None a chybovú správu.
"""

import base64
import json
import re

PARSE_PROMPT = """Si expert na analýzu športových stávkových tiketov zo screenshotov.
Pozri sa na priložený obrázok stávkového tiketu / kurzovej ponuky a vráť VÝHRADNE
jeden čistý JSON objekt (žiadny iný text, žiadne markdown bločky) s týmito kľúčmi:

{
  "sport": "napr. Futbal, Tenis, Hokej",
  "liga": "názov súťaže/ligy ak je viditeľný",
  "timy": "Tím A - Tím B",
  "soft_bookmaker": "názov stávkovej kancelárie ak je viditeľný (napr. Tipsport, Fortuna, Niké)",
  "typ_marketu": "napr. 1X2, Hándicap, Total Over/Under",
  "tip": "konkrétny tip, napr. '1', 'Over 2.5'",
  "soft_kurz": 1.85,
  "skore": "aktuálne skóre ak je viditeľné, inak prázdny string",
  "match_date": "dátum začiatku zápasu vo formáte YYYY-MM-DD, ak je na obrázku viditeľný dátum (napr. '19.7.' alebo '19.7.2026'), inak prázdny string",
  "match_time": "čas začiatku zápasu vo formáte HH:MM (24-hodinový), ak je viditeľný, inak prázdny string"
}

Ak niektorú hodnotu nevieš určiť, daj prázdny string ("") alebo pre soft_kurz hodnotu null.
Vráť IBA JSON, nič iné.
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*|\s*```$", "", text, flags=re.MULTILINE)
    return json.loads(text)


def _image_to_b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def parse_with_openai(image_bytes: bytes, api_key: str) -> tuple:
    """Vráti (data_dict | None, error_message | None). Vyžaduje balíček `requests`."""
    import requests

    b64 = _image_to_b64(image_bytes)
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 500,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PARSE_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                        ],
                    }
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(content), None
    except Exception as e:
        return None, f"OpenAI parsing zlyhalo: {e}"


def parse_with_gemini(image_bytes: bytes, api_key: str) -> tuple:
    """
    Vráti (data_dict | None, error_message | None).

    Používa oficiálne Google Gen AI Python SDK (balíček `google-genai`, import
    `from google import genai`) namiesto ručného skladania REST URL cez `requests`.

    Model - DÔLEŽITÉ (stav overený k júlu 2026 priamo na oficiálnej Google
    deprecation stránke ai.google.dev/gemini-api/docs/deprecations):
      - "gemini-2.5-flash"  -> AKTÍVNY, oficiálny shutdown dátum až 16. 10. 2026. PRIMÁRNY.
      - "gemini-3.5-flash"  -> najnovší model (máj 2026), zatiaľ bez oznámeného shutdownu. FALLBACK.
      - "gemini-2.0-flash"  -> už VYPNUTÝ Googlom od 1. 6. 2026 - volania naň vracajú 404.
      - "gemini-1.5-flash"  -> vypnutý ešte skôr (celá 1.x generácia je mŕtva).
    Preto sa 2.0/1.5 NEPOUŽÍVAJÚ ako fallback - dali by presne tú istú 404 chybu.

    Ak aj "gemini-2.5-flash" hádže 404, najčastejšie príčiny bývajú mimo názvu modelu:
    API kľúč bez prístupu k modelu (napr. neaktivovaná Generative Language API pre projekt),
    alebo zastaraná verzia balíčka `google-genai` (over cez `pip show google-genai`,
    prípadne `pip install --upgrade google-genai`).

    Vyžaduje: pip install google-genai (pridané do requirements.txt).
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None, (
            "Chýba knižnica `google-genai`. Nainštaluj ju cez `pip install google-genai` "
            "a reštartuj appku."
        )

    try:
        client = genai.Client(api_key=api_key)
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        config = types.GenerateContentConfig(response_mime_type="application/json")

        # Primárny model + jeden odolný fallback na aktuálne podporovaný model
        # (obidva sú k júlu 2026 oficiálne živé - pozri poznámku vyššie).
        models_to_try = ["gemini-2.5-flash", "gemini-3.5-flash"]
        last_error = None

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[PARSE_PROMPT, image_part],
                    config=config,
                )
                return _extract_json(response.text), None
            except Exception as e:
                last_error = e
                continue

        return None, (
            f"Gemini parsing zlyhalo na oboch skúšaných modeloch ({', '.join(models_to_try)}): "
            f"{last_error}. Over API kľúč (má prístup k Gemini API?) a verziu balíčka google-genai."
        )
    except Exception as e:
        return None, f"Gemini parsing zlyhalo: {e}"


def parse_screenshot(image_bytes: bytes, provider: str, api_key: str) -> tuple:
    if not api_key:
        return None, "Chýba API kľúč. Zadaj ho v sekcii Nastavenia, aby fungovalo AI skenovanie."
    if provider == "OpenAI (gpt-4o-mini)":
        return parse_with_openai(image_bytes, api_key)
    elif provider == "Google Gemini Flash":
        return parse_with_gemini(image_bytes, api_key)
    return None, f"Neznámy provider: {provider}"
