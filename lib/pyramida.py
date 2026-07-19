"""
Pyramída Tracker - konfigurácia levelov a vtipné/motivačné hlášky AI asistenta.

Kurzová mapa a odmeny sú prevzaté z oficiálnych pravidiel súťaže Pyramída,
platných od 28. 4. 2026 (Bod 3.1.1 a Bod 2.5.1) - toto je DEFINITÍVNA mapa,
nemá sa svojvoľne meniť v UI.
"""

# Bod 3.1.1 - minimálny kurz na level (definitívne, lineárne stúpajúce)
DEFAULT_MIN_ODDS = {
    1: 1.1, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0,
    6: 6.0, 7: 7.0, 8: 8.0, 9: 9.0, 10: 10.0,
}

# Bod 2.1 - minimálny vklad pre akýkoľvek tiket poslaný do Pyramídy
MIN_PYRAMID_STAKE_EUR = 2.00

# Bod 2.3 - od tohto levelu (vrátane) je LIVE tiket úplne zakázaný
LIVE_BLOCKED_FROM_LEVEL = 8

# Bod 2.3 - od tohto levelu (vrátane) treba varovať pred Mix tiketmi
MIX_WARNING_FROM_LEVEL = 7

# Bod 2.5.1 - odmena pripísaná pri výhre daného levelu.
# type: "body" = Nety (vernostné body, nie €), "eur" = reálne €, "hlavna_cena" = špeciálna cena bez číselnej hodnoty.
LEVEL_REWARDS = {
    4: {"type": "body", "amount": 200},
    5: {"type": "body", "amount": 400},
    6: {"type": "body", "amount": 800},
    7: {"type": "eur", "amount": 600},
    8: {"type": "eur", "amount": 8000},
    9: {"type": "eur", "amount": 80000},
    10: {"type": "hlavna_cena", "amount": None},
}

LEVEL_HLASKY = {
    1: "Level 1. Detský bazén. Ešte len rozcvička, kamoš. 🐣",
    2: "Level 2 splnený. Pomaly sa to rozbieha, netlač na pílu.",
    3: "Level 3! Už to začína vyzerať ako plán, nie ako náhoda.",
    4: "Level 4 - polovica druhej päťky. Bankroll drží, disciplína drží.",
    5: "Level 5! Presne v strede pyramídy. Odtiaľto to už bolí, ak to prešustríš.",
    6: "Level 6 - zóna, kde sa väčšina kamošov začne triasť. Ty nie. Dýchaj.",
    7: "Level 7! Kurzy stúpajú, nervy tiež. Kelly ťa drží pri zemi, nech to tak zostane.",
    8: "Level 8 - už cítiš vrchol pyramídy? Ešte 2 kroky, žiadne hrdinstvá.",
    9: "LEVEL 9! Jeden krok od vrcholu. Toto je presne ten moment, kedy si ľudia zvyknú zvýšia vklad. Nerob to.",
    10: "🏆 LEVEL 10 - VRCHOL PYRAMÍDY! Legenda syndikátu. Teraz si to poriadne vychutnaj a nezačínaj hneď odznova s dvojnásobným vkladom.",
}

EDGE_HLASKY_LOW = [
    "Edge pod 2%? To je skôr šum ako value. Radšej počkaj na lepší kurz.",
    "Tenký edge. Sharp knihy sa nemýlia často - over si čísla ešte raz.",
]

EDGE_HLASKY_HIGH = [
    "🔥 Edge nad 6%! Toto vyzerá ako skutočný value bet, skontroluj limity a poď na to.",
    "Pekný edge. Presne pre toto celý model existuje.",
]


def get_min_odds(level: int) -> float:
    return DEFAULT_MIN_ODDS.get(level, 1.0)


def get_level_message(level: int) -> str:
    return LEVEL_HLASKY.get(level, "Level splnený!")


def get_edge_message(edge: float) -> str:
    if edge is None:
        return ""
    if edge >= 0.06:
        return EDGE_HLASKY_HIGH[0]
    if edge < 0.02:
        return EDGE_HLASKY_LOW[0]
    return "Solídny edge, v rozumnom pásme pre Kelly stávkovanie."


def get_level_reward(level: int):
    """Vráti dict {type, amount} pre danú úroveň, alebo None ak level nemá odmenu (1-3)."""
    return LEVEL_REWARDS.get(level)


def format_reward(level: int) -> str:
    """Čitateľný popis odmeny pre level, na použitie v UI (ladder, potvrdenia)."""
    reward = get_level_reward(level)
    if not reward:
        return "-"
    if reward["type"] == "body":
        return f"{reward['amount']} Netov"
    if reward["type"] == "eur":
        return f"{reward['amount']:,} €".replace(",", " ")
    if reward["type"] == "hlavna_cena":
        return "🏆 Hlavná cena"
    return "-"
