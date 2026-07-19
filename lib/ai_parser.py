"""
AI Skenovanie screenshotov (OCR + parsing).

Podporuje dvoch providerov - používateľ si v Nastaveniach vyberie, ktorého chce
použiť, a zadá vlastný API kľúč (ukladá sa iba do st.session_state, nikdy do DB).

  - OpenAI gpt-4o-mini (vision)
  - Google Gemini 1.5/2.0 Flash (vision)

Obe funkcie vracajú rovnaký normalizovaný dict:
{
  "sport": str, "liga": str, "timy": str, "soft_bookmaker": str,
  "typ_marketu": str, "tip": str, "soft_kurz": float, "skore": str
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
  "skore": "aktuálne skóre ak je viditeľné, inak prázdny string"
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
    """Vráti (data_dict | None, error_message | None). Vyžaduje balíček `requests`."""
    import requests

    b64 = _image_to_b64(image_bytes)
    try:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={api_key}",
            json={
                "contents": [
                    {
                        "parts": [
                            {"text": PARSE_PROMPT},
                            {"inline_data": {"mime_type": "image/png", "data": b64}},
                        ]
                    }
                ]
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _extract_json(content), None
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
