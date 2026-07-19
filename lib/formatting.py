"""
Malé zdieľané pomocné funkcie pre formátovanie dátumu/času zápasu.
Použité vo Feede aj v Pyramíde, aby formát bol všade rovnaký.
"""

import datetime


def format_match_dt(match_date: str, match_time: str) -> str:
    """
    Naformátuje uložený dátum (ISO 'YYYY-MM-DD') a čas (napr. '15:30') zápasu
    do čitateľného slovenského tvaru: '19. 7. 2026 o 15:30'.
    Ak dátum chýba alebo je nevalidný, vráti prázdny reťazec.
    """
    if not match_date:
        return ""
    try:
        d = datetime.date.fromisoformat(match_date)
    except (ValueError, TypeError):
        return ""
    date_part = f"{d.day}. {d.month}. {d.year}"
    if match_time:
        return f"{date_part} o {match_time}"
    return date_part
