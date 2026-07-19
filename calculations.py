"""
Matematické jadro aplikácie.
Všetky vzorce presne podľa zadania (Value Betting, Kelly, Under-hedging, PnL).
"""

from typing import Optional


def fair_kurz(sharp_k: float, sharp_l: Optional[float], global_marza: float) -> Optional[float]:
    """
    Inteligentný Fair Kurz.

    - Ak je zadaný iba sharp_k (opačný tip L je prázdny):
        Fair = K * (1 + globálna_marža)
    - Ak sú zadané OBA sharp kurzy (K aj L):
        Fair = 1 / ( (1/K) / ( (1/K) + (1/L) ) )
        (marža sa vtedy odvodí priamo z reálneho trhu, globálna marža sa ignoruje)
    """
    if sharp_k is None or sharp_k <= 0:
        return None

    if sharp_l is None or sharp_l <= 0:
        return sharp_k * (1 + global_marza)

    inv_k = 1 / sharp_k
    inv_l = 1 / sharp_l
    return 1 / (inv_k / (inv_k + inv_l))


def edge_pct(soft_kurz: float, fair_kurz_val: float) -> Optional[float]:
    """Edge (výhoda) v percentách vyjadrená ako desatinné číslo, napr. 0.05 = 5%."""
    if not soft_kurz or not fair_kurz_val:
        return None
    return (soft_kurz / fair_kurz_val) - 1


def kelly_percent(edge: float, soft_kurz: float, kelly_frakcia: float, max_bet_limit: float,
                   bankroll: Optional[float] = None) -> float:
    """
    Kelly %:
    = MAX(0, MIN(Max_Bet_Limit, (Edge / (Soft_Kurz - 1)) * Kelly_Frakcia))

    FAIL-SAFE: ak je bankroll nulový alebo záporný (napr. účet vyčistený a
    nastavenia neaktualizované), niet čo stávkovať - vráti sa bezpečná 0,
    žiadna ďalšia funkcia v reťazci (odporúčaný vklad, hedge) sa už nespustí
    s nezmyselným/záporným základom.
    """
    if bankroll is not None and bankroll <= 0:
        return 0.0
    if edge is None or soft_kurz is None or soft_kurz <= 1:
        return 0.0
    raw = (edge / (soft_kurz - 1)) * kelly_frakcia
    return max(0.0, min(max_bet_limit, raw))


def odporucany_vklad(bankroll: float, kelly_pct: float) -> float:
    """
    Odporúčaný Vklad € = Bankroll * Kelly_%.

    FAIL-SAFE: nulový/záporný bankroll okamžite vráti 0 € namiesto toho, aby sa
    záporná/nulová hodnota potiahla ďalej do Under-hedgingu (Nepoistená časť,
    Hedge základ, Proti-Vklad), kde by mohla spôsobiť pád stránky.
    """
    if bankroll is None or bankroll <= 0:
        return 0.0
    if kelly_pct is None or kelly_pct <= 0:
        return 0.0
    return bankroll * kelly_pct


def neposistena_cast(priebezna_hodnota_tiketu: float, odporucany_vklad_eur: float) -> float:
    """Nepoistená časť (Value Bet) € = MIN(Priebežná_hodnota_tiketu, Odporúčaný_Vklad_€)."""
    if priebezna_hodnota_tiketu is None:
        return 0.0
    return min(priebezna_hodnota_tiketu, odporucany_vklad_eur or 0.0)


def suma_na_poistenie(priebezna_hodnota_tiketu: float, neposistena_cast_eur: float) -> float:
    """Suma na poistenie (Hedge základ) € = Priebežná_hodnota_tiketu - Nepoistená_časť_€."""
    if priebezna_hodnota_tiketu is None:
        return 0.0
    return priebezna_hodnota_tiketu - (neposistena_cast_eur or 0.0)


def hedge_stavka(suma_na_poistenie_eur: Optional[float], soft_kurz: Optional[float],
                  proti_kurz: Optional[float]) -> Optional[float]:
    """
    Prepojený Proti-Vklad (Hedge stávka) = (Suma_na_poistenie * Soft_Kurz) / Proti_Kurz.
    Ak sú vstupy prázdne, hodnota zostáva prázdna (None).
    """
    if not suma_na_poistenie_eur or not soft_kurz or not proti_kurz:
        return None
    return (suma_na_poistenie_eur * soft_kurz) / proti_kurz


def ciastkovy_pnl(status: str, priebezna_hodnota_tiketu: float, soft_kurz: float,
                   proti_vklad: Optional[float], proti_kurz: Optional[float]) -> Optional[float]:
    """
    Zisk/Strata po kole - čistý, čiastkový výsledok (nie kumulatívny).

    - Status "Vyhratý" (Soft vyhráva, hedge prehráva):
        PnL = Priebežná_hodnota_tiketu * (Soft_Kurz - 1) - Proti_Vklad
    - Status "Prehratý" (Soft prehráva, hedge vyhráva):
        PnL = -Priebežná_hodnota_tiketu + (Proti_Vklad * (Proti_Kurz - 1))
    - Inak (napr. "Otvorený"): None
    """
    proti_vklad = proti_vklad or 0.0
    proti_kurz = proti_kurz or 0.0

    if status == "Vyhratý":
        return priebezna_hodnota_tiketu * (soft_kurz - 1) - proti_vklad
    elif status == "Prehratý":
        return -priebezna_hodnota_tiketu + (proti_vklad * (proti_kurz - 1))
    return None


def full_ticket_calculation(sharp_k: float, sharp_l: Optional[float], soft_kurz: float,
                             global_marza: float, bankroll: float, kelly_frakcia: float,
                             max_bet_limit: float, priebezna_hodnota_tiketu: float,
                             proti_kurz: Optional[float] = None) -> dict:
    """Skratka - spustí celý reťazec výpočtov naraz a vráti dict so všetkými hodnotami."""
    fair = fair_kurz(sharp_k, sharp_l, global_marza)
    edge = edge_pct(soft_kurz, fair) if fair else None
    kpct = kelly_percent(edge, soft_kurz, kelly_frakcia, max_bet_limit, bankroll) if edge is not None else 0.0
    vklad = odporucany_vklad(bankroll, kpct)
    neposistena = neposistena_cast(priebezna_hodnota_tiketu, vklad)
    hedge_zaklad = suma_na_poistenie(priebezna_hodnota_tiketu, neposistena)
    proti_vklad = hedge_stavka(hedge_zaklad, soft_kurz, proti_kurz)

    return {
        "fair_kurz": fair,
        "edge": edge,
        "kelly_pct": kpct,
        "odporucany_vklad": vklad,
        "neposistena_cast": neposistena,
        "hedge_zaklad": hedge_zaklad,
        "proti_vklad": proti_vklad,
    }
