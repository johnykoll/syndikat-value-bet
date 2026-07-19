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
  "match_time": str ('HH:MM' ak je viditeľný čas začiatku zápasu, inak ""),
  "opacny_kurz": float | None (kurz protistrany/opačného výsledku, ak je na
      screenshote viditeľný - typicky z arbitrážnych skenerov ako BetBurger),
  "typ_opacneho_kurzu": str - jedna z: "Žiadny", "Trhový pár (BetBurger)",
      "Sharp referencia protistrany" (podľa toho, čo AI z obrázka rozpozná),
  "sharp_provider": str (názov sharp protistrany/výmeny z BetBurgeru, napr.
      "Betdaq", "Pinnacle", inak ""),
  "liquidity": str (likvidita protistrany ako text presne tak, ako je na
      screenshote, napr. "150€", "1200€", inak "")
}
Ak sa parsovanie úplne nepodarí (žiadne pole sa nedalo obnoviť), vráti None a chybovú správu.
"""

import base64
import json
import re

PARSE_PROMPT = """Si expert na analýzu športových stávkových tiketov a arbitrážnych
skenerov (napr. BetBurger, OddsJam, RebelBetting) zo screenshotov.
Pozri sa na priložený obrázok a vráť VÝHRADNE jeden čistý JSON objekt (žiadny iný
text, žiadne markdown bločky) s týmito kľúčmi:

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
  "match_time": "čas začiatku zápasu vo formáte HH:MM (24-hodinový), ak je viditeľný, inak prázdny string",
  "opacny_kurz": 1.51,
  "typ_opacneho_kurzu": "Žiadny",
  "sharp_provider": "názov sharp protistrany/výmeny ak je viditeľný, napr. Betdaq, Pinnacle, inak prázdny string",
  "liquidity": "číslo likvidity presne tak, ako je napísané pod kurzom protistrany, napr. '$65.91' alebo '65.91', inak prázdny string"
}

DÔLEŽITÉ - arbitráž / surebet / BetBurger screenshoty:
Ak obrázok pochádza z arbitrážneho skenera (BetBurger a podobné) alebo inak jasne
zobrazuje DVOJICU kurzov na opačné výsledky rovnakého trhu (napr. Over/Under,
domáci/hosť, sharp vs soft strana):
  - Hlavný value tip (ten, ktorý má odporúčaný/zvýraznený vklad) zapíš klasicky
    do "soft_kurz" a jeho tip do "tip".
  - Kurz opačnej strany (napr. Under, keď náš tip je Over; alebo kurz hosťa,
    keď náš tip je na domáceho) zapíš do "opacny_kurz".
  - Ak je zrejmé, že ide o dvojicu z rôznych kníh/výmen tvoriacu arbitrážny pár
    (typický BetBurger layout s dvoma stĺpcami kurzov a dvoma kanceláriami),
    nastav "typ_opacneho_kurzu" na "Trhový pár (BetBurger)".
  - Ak je namiesto toho vidno len referenčný "sharp" kurz protistrany (nie
    priamy pár k nášmu tipu, skôr orientačná sharp kotva), nastav
    "typ_opacneho_kurzu" na "Sharp referencia protistrany".
  - Ak screenshot žiadny opačný/protistranový kurz vôbec neobsahuje, nechaj
    "opacny_kurz" na null a "typ_opacneho_kurzu" na "Žiadny".
  - Pri BetBurger layoute vytiahni "sharp_provider" ako názov burzy/knihy
    zobrazený pri kurze protistrany (napr. "Betdaq", "Pinnacle", "Betfair").
  - LIKVIDITA - typický BetBurger screenshot má DVA riadky nad sebou, jeden pre
    každú stranu stávky (napr. "Tipsport" hore, "Betdaq" dole). Každý riadok má
    v pravej časti tip (napr. "Team1 Win" / "Team2 Win") a vedľa neho kurz so
    šípkou (napr. "↑ 3.03" / "↑ 1.51"). LIKVIDITA sa nachádza IBA na riadku
    PROTISTRANY (sharp strana, riadok s "sharp_provider") - PRIAMO POD jej
    kurzom, v tom istom stĺpci, menším písmom, veľmi často so symbolom "$"
    (napr. "$65.91"). Riadok hlavného soft tipu túto druhú hodnotu pod kurzom
    typicky vôbec nemá. Príklad presného rozloženia:
        Tipsport   ...   Team1 Win   ↑ 3.03
        Betdaq     ...   Team2 Win   ↑ 1.51
                                      $65.91    <- toto je liquidity (patrí k riadku Betdaq/protistrany)
    Zapíš do "liquidity" presne to, čo je pod kurzom protistrany, vrátane
    symbolu meny, ak je prítomný (napr. "$65.91"). Niekedy môže byť likvidita
    aj bez symbolu meny (čisté číslo ako "65.91") - v oboch prípadoch ju zapíš
    presne tak, ako je napísaná. Iba ak pod kurzom protistrany naozaj žiadne
    takéto menšie číslo nevidíš, nechaj "liquidity" prázdne - nezamieňaj si ho
    so samotným kurzom a nevynechávaj ho len preto, že nemá symbol meny.

Dôležité pravidlá pre platný JSON:
- Ak sa v tíme, lige alebo tipe vyskytuje úvodzovka ('), escapuj ju alebo ju vynechaj.
- Nepoužívaj markdown bloky (```), žiadny text pred alebo za JSON objektom.
- Ak niektorú hodnotu nevieš určiť, daj prázdny string ("") alebo pre soft_kurz/opacny_kurz hodnotu null.
Vráť IBA JSON, nič iné.
"""

# Prázdna/predvyplnená schéma - použije sa ako základ pri čiastočnom aj úplnom
# zlyhaní parsovania, aby appka vždy dostala dict so všetkými očakávanými kľúčmi
# a nikdy nepadla na KeyError pri čítaní prefill.get(...) na strane formulára.
DEFAULT_SCHEMA = {
    "sport": "", "liga": "", "timy": "", "soft_bookmaker": "", "typ_marketu": "",
    "tip": "", "soft_kurz": None, "skore": "", "match_date": "", "match_time": "",
    "opacny_kurz": None, "typ_opacneho_kurzu": "Žiadny",
    "sharp_provider": "", "liquidity": "",
}

_STRING_FIELDS = ["sport", "liga", "timy", "soft_bookmaker", "typ_marketu", "tip",
                  "skore", "match_date", "match_time", "typ_opacneho_kurzu",
                  "sharp_provider", "liquidity"]

_NUMERIC_FIELDS = ["soft_kurz", "opacny_kurz"]

# Pole, ktoré sa pri vyhodnocovaní "je táto odpoveď úplne prázdna?" ignoruje -
# ide o klasifikačné pole s netriviálnym defaultom ("Žiadny"), nie o dátovú
# hodnotu z obrázka, takže samo o sebe by falošne vyzeralo ako "niečo sa našlo".
_EMPTINESS_IGNORED_FIELDS = {"typ_opacneho_kurzu"}


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*|\s*```$", "", text, flags=re.MULTILINE)
    return text.strip()


def _remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _normalize_smart_quotes(text: str) -> str:
    return (
        text.replace("\u201c", '"').replace("\u201d", '"')
        .replace("\u2018", "'").replace("\u2019", "'")
    )


def _regex_fallback_extract(raw_text: str) -> dict:
    """
    Posledná záchranná sieť: aj keby bol JSON štrukturálne nenávratne poškodený
    (napr. neescapovaná úvodzovka v hodnote), skús vytiahnuť polia po jednom
    priamo regexom. Vždy vráti kompletný dict so všetkými kľúčmi (chýbajúce
    polia zostanú na prázdnej/None defaultnej hodnote) - nikdy nevyhodí výnimku.
    """
    result = dict(DEFAULT_SCHEMA)
    for key in _STRING_FIELDS:
        m = re.search(rf'"{key}"\s*:\s*"(.*?)"\s*[,\}}\r\n]', raw_text, re.DOTALL)
        if m:
            result[key] = m.group(1).strip()
    for key in _NUMERIC_FIELDS:
        m = re.search(rf'"{key}"\s*:\s*([\d.]+)', raw_text)
        if m:
            try:
                result[key] = float(m.group(1))
            except ValueError:
                pass
    return result


def _extract_json(text: str) -> dict:
    """
    Extrémne robustné parsovanie JSON odpovede z AI modelu. NIKDY nevyhodí
    výnimku - vždy vráti dict (v najhoršom prípade DEFAULT_SCHEMA kópiu).

    Postupnosť pokusov, od najpresnejšieho po najzhovievavejší:
      1. Priamy json.loads() po odstránení markdown fence-ov (```json ... ```).
      2. Vystrihnutie len obsahu medzi prvou '{' a poslednou '}' (ak model pridal
         text pred/za JSON objektom).
      3. Bežné opravy: "smart quotes" -> rovné úvodzovky, odstránenie trailing čiarok.
      4. Regex extrakcia poľa po poli priamo zo surového textu - funguje aj keď
         je zvyšok JSONu nenávratne poškodený (napr. neescapovaná úvodzovka
         v jednom poli nezhodí parsovanie ostatných polí).
    """
    try:
        cleaned = _strip_markdown_fences(text)
    except Exception:
        cleaned = text

    # 1. Priamy pokus
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Vystrihni len { ... } blok, ak je obalený iným textom
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    candidate = match.group(0) if match else cleaned
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        pass

    # 3. Bežné opravy (smart quotes, trailing commas)
    try:
        repaired = _remove_trailing_commas(_normalize_smart_quotes(candidate))
        return json.loads(repaired)
    except (json.JSONDecodeError, TypeError):
        pass

    # 4. Regex fallback - vždy vráti použiteľný dict, nikdy nevyhodí výnimku
    return _regex_fallback_extract(text)


def _image_to_b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _is_effectively_empty(data: dict) -> bool:
    """
    True ak sa z odpovede nepodarilo vytiahnuť vôbec nič použiteľné.
    `typ_opacneho_kurzu` sa ignoruje - jeho default ("Žiadny") nie je prázdna
    hodnota v bežnom zmysle, takže by inak vždy pôsobil ako "niečo sa našlo".
    """
    if not data:
        return True
    return all(
        (data.get(k) in (None, "", 0))
        for k in DEFAULT_SCHEMA.keys()
        if k not in _EMPTINESS_IGNORED_FIELDS
    )


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
        data = _extract_json(content)
        if _is_effectively_empty(data):
            return None, (
                "OpenAI vrátila odpoveď, ale nepodarilo sa z nej obnoviť ani jedno pole "
                "(pravdepodobne nečitateľný alebo nepodporovaný screenshot). Skús iný obrázok "
                "alebo vyplň formulár ručne."
            )
        return data, None
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

    Model-fallback (skúšanie viacerých modelov) sa deje LEN pri chybe samotného
    API volania (404/403/network) - nie pri chybe parsovania JSONu. Parsovanie
    JSONu rieši samostatne extrémne odolná `_extract_json()`, ktorá nikdy nevyhodí
    výnimku, takže poškodená odpoveď z jedného modelu už nespôsobí zbytočné
    prepínanie na druhý model.

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

        models_to_try = ["gemini-2.5-flash", "gemini-3.5-flash"]
        last_error = None
        response = None

        # Fallback len na úrovni API volania (404/403/network), nie na parsovaní JSONu.
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[PARSE_PROMPT, image_part],
                    config=config,
                )
                last_error = None
                break
            except Exception as e:
                last_error = e
                response = None
                continue

        if response is None:
            return None, (
                f"Gemini API volanie zlyhalo na oboch skúšaných modeloch "
                f"({', '.join(models_to_try)}): {last_error}. "
                "Over API kľúč (má prístup k Gemini API?) a verziu balíčka google-genai."
            )

        data = _extract_json(response.text)
        if _is_effectively_empty(data):
            return None, (
                "Gemini vrátila odpoveď, ale nepodarilo sa z nej obnoviť ani jedno pole "
                "(poškodený/nečitateľný JSON alebo nepodporovaný screenshot). "
                "Skús to znova, prípadne vyplň formulár ručne."
            )
        return data, None
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
