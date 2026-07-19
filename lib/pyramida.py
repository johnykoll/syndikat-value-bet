"""
Pyramída Tracker - konfigurácia levelov a vtipné/motivačné hlášky AI asistenta.
Minimálne kurzy na level sú orientačné defaulty, dajú sa upraviť v Nastaveniach.
"""

DEFAULT_MIN_ODDS = {
    1: 1.20, 2: 1.25, 3: 1.30, 4: 1.35, 5: 1.40,
    6: 1.50, 7: 1.60, 8: 1.75, 9: 1.90, 10: 2.10,
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
