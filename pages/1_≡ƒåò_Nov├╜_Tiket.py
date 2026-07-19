import streamlit as st
import sys, os
import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from lib import database as db
from lib import calculations as calc
from lib import ai_parser
from lib import pyramida

st.set_page_config(page_title="Nový Tiket", page_icon="🆕", layout="wide")

if "username" not in st.session_state or not st.session_state.username:
    st.warning("Najprv sa prihlás na hlavnej stránke.")
    st.stop()

db.init_db()
user = db.get_user(st.session_state.user_id)

st.title("🆕 Nový Tiket")

# ---------------- AI SKENOVANIE SCREENSHOTU ----------------
with st.expander("🤖 AI Skenovanie screenshotu (voliteľné)", expanded=False):
    st.caption("Nahraj screenshot tiketu alebo kurzovej ponuky - AI sa pokúsi predvyplniť formulár nižšie.")
    c1, c2 = st.columns(2)
    provider = c1.selectbox("AI provider", ["OpenAI (gpt-4o-mini)", "Google Gemini Flash"])
    api_key = c2.text_input("API kľúč", type="password",
                             help="Kľúč sa ukladá iba počas tejto session, nikde sa neukladá natrvalo.")
    uploaded_img = st.file_uploader("Drag & drop obrázok (alebo vlož zo schránky)", type=["png", "jpg", "jpeg"])

    if uploaded_img is not None and st.button("🔍 Analyzovať screenshot"):
        with st.spinner("AI analyzuje screenshot..."):
            data, err = ai_parser.parse_screenshot(uploaded_img.getvalue(), provider, api_key)
        if err:
            st.error(err)
        else:
            st.session_state.ai_prefill = data
            st.success("🤖 Auto-vyplnené - skontroluj a uprav polia nižšie podľa potreby.")

prefill = st.session_state.get("ai_prefill", {}) or {}
if prefill:
    st.info("🤖 Formulár nižšie bol predvyplnený z AI skenovania.")

# ---------------- ZÁKLADNÉ INFO O ZÁPASE ----------------
st.subheader("1️⃣ Základné info o zápase")
c1, c2, c3 = st.columns(3)
sport = c1.text_input("Šport", value=prefill.get("sport", ""))
liga = c2.text_input("Liga / Súťaž", value=prefill.get("liga", ""))
timy = c3.text_input("Tímy (napr. Slovan - Trnava)", value=prefill.get("timy", ""))

c1, c2, c3 = st.columns(3)
soft_bookmaker = c1.text_input("Soft stávková kancelária", value=prefill.get("soft_bookmaker", ""))
typ_marketu = c2.text_input("Typ marketu", value=prefill.get("typ_marketu", ""))
tip = c3.text_input("Tip", value=prefill.get("tip", ""))

# ---- Dátum a čas zápasu (na kontrolu 42-dňovej lehoty Pyramídy a value bet analytiku) ----
prefill_date_val = None
if prefill.get("match_date"):
    try:
        prefill_date_val = datetime.date.fromisoformat(prefill["match_date"])
    except (ValueError, TypeError):
        prefill_date_val = None

prefill_time_val = None
if prefill.get("match_time"):
    try:
        prefill_time_val = datetime.datetime.strptime(prefill["match_time"], "%H:%M").time()
    except (ValueError, TypeError):
        prefill_time_val = None

dc1, dc2 = st.columns(2)
match_date = dc1.date_input("📅 Dátum zápasu", value=prefill_date_val or datetime.date.today(),
                             format="DD.MM.YYYY")
match_time = dc2.time_input("🕒 Čas zápasu", value=prefill_time_val or datetime.time(hour=15, minute=0))

if prefill and (prefill_date_val or prefill_time_val):
    st.caption("🤖 Dátum/čas zápasu auto-vyplnené z AI skenovania - skontroluj, či sedí so screenshotom.")

is_live = st.checkbox("🔴 LIVE stávka (zápas prebieha, kurzy sa menia každú minútu)",
                       help="Ak zaškrtneš, tiket vo Feede dostane po 3 minútach vizuálne upozornenie, "
                            "že kurzy sú pravdepodobne už neplatné.")
mix_tiket = st.checkbox("🎟️ Mix Tiket (kombinácia viacerých udalostí/zápasov)")

# ---------------- MATEMATICKÉ JADRO ----------------
st.subheader("2️⃣ Kurzy a Fair Kurz")
st.caption(
    "Zadaj buď priamy sharp kurz, alebo kurz protistrany (napr. z BetBurger arbitráže) - "
    "obe polia sú teraz voliteľné, appka si sama vyberie správny výpočtový scenár."
)

c1, c2, c3 = st.columns(3)
soft_kurz = c1.number_input("Soft Kurz (náš tip)", min_value=1.01,
                             value=float(prefill.get("soft_kurz") or 2.00), step=0.01, format="%.2f")
global_marza = c2.number_input("Globálna marža %", min_value=0.0, max_value=20.0,
                                value=user["global_marza"] * 100, step=0.1, format="%.1f") / 100
sharp_k_input = c3.number_input(
    "Sharp Kurz (priamy, nepovinné)", min_value=0.0, value=0.0, step=0.01, format="%.2f",
    help="Nechaj na 0, ak nemáš priamy sharp kurz referenčnej stávkovej kancelárie.",
)
sharp_k = sharp_k_input if sharp_k_input > 1.0 else None

st.markdown("**Opačný kurz protistrany** (napr. BetBurger arbitráž alebo sharp referencia opačnej strany)")
oc1, oc2 = st.columns(2)
OPPONENT_ROLE_OPTIONS = {
    "Žiadny (nemám)": "none",
    "Trhový pár - BetBurger/arbitráž (Scenár 2)": "market_pair",
    "Sharp referenčný kurz protistrany (Scenár 3)": "sharp_reference",
}
# Mapovanie kanonických hodnôt z AI (lib/ai_parser.py DEFAULT_SCHEMA["typ_opacneho_kurzu"])
# na interné role-kódy použité vyššie. AI vracia "Žiadny" / "Trhový pár (BetBurger)" /
# "Sharp referencia protistrany" - toto je zámerne iný (kratší) text než popisky v
# dropdowne, preto je tu explicitný prekladový slovník namiesto priameho porovnania reťazcov.
AI_ROLE_TO_INTERNAL = {
    "Žiadny": "none",
    "Trhový pár (BetBurger)": "market_pair",
    "Sharp referencia protistrany": "sharp_reference",
}
INTERNAL_TO_LABEL = {v: k for k, v in OPPONENT_ROLE_OPTIONS.items()}

ai_role_internal = AI_ROLE_TO_INTERNAL.get(prefill.get("typ_opacneho_kurzu"), "none")
default_label = INTERNAL_TO_LABEL.get(ai_role_internal, "Žiadny (nemám)")
default_role_index = list(OPPONENT_ROLE_OPTIONS.keys()).index(default_label)

opponent_role_label = oc1.selectbox(
    "Čo predstavuje opačný kurz?", list(OPPONENT_ROLE_OPTIONS.keys()), index=default_role_index,
)
opponent_role = OPPONENT_ROLE_OPTIONS[opponent_role_label]
opacny_kurz_input = oc2.number_input(
    "Opačný kurz protistrany", min_value=0.0,
    value=float(prefill.get("opacny_kurz") or 0.0), step=0.01, format="%.2f",
    disabled=(opponent_role == "none"),
    help="Napr. Betdaq/Betfair kurz z BetBurger screenshotu, alebo sharp kurz opačnej strany.",
)
opacny_kurz = opacny_kurz_input if (opacny_kurz_input > 1.0 and opponent_role != "none") else None

if prefill and prefill.get("opacny_kurz"):
    st.caption("🤖 Opačný kurz aj jeho typ boli auto-vyplnené z AI skenovania - skontroluj, či sedia so screenshotom.")

spc1, spc2 = st.columns(2)
sharp_provider = spc1.text_input(
    "Sharp protistrana (výmena/kancelária)", value=prefill.get("sharp_provider", ""),
    placeholder="napr. Betdaq, Pinnacle",
    help="Kto poskytol opačný/sharp kurz - dôležité pri BetBurger arbitráži.",
)
liquidity = spc2.text_input(
    "Likvidita protistrany", value=prefill.get("liquidity", ""),
    placeholder="napr. 150€",
    help="Dostupná likvidita na strane protistrany, presne tak ako na screenshote.",
)
if prefill and (prefill.get("sharp_provider") or prefill.get("liquidity")):
    st.caption("🤖 Sharp protistrana aj likvidita boli auto-vyplnené z AI skenovania.")

fair, scenario_used = calc.resolve_fair_kurz(soft_kurz, sharp_k, opacny_kurz, opponent_role, global_marza)
edge = calc.edge_pct(soft_kurz, fair) if fair else None

SCENARIO_LABELS = {
    1: "Scenár 1 - priamy sharp kurz",
    2: "Scenár 2 - trhový pár (BetBurger)",
    3: "Scenár 3 - sharp protistrana + marža",
}

r1, r2, r3 = st.columns(3)
r1.metric("🎯 Fair Kurz", f"{fair:.3f}" if fair else "-")
r2.metric("⚡ Edge", f"{edge*100:+.2f} %" if edge is not None else "-")
r3.metric("🧮 Použitý scenár", SCENARIO_LABELS.get(scenario_used, "-"))

if fair is None:
    st.info("Zadajte buď priamy sharp kurz, alebo kurz protistrany pre výpočet Kellyho vkladu.")
elif edge is not None:
    if edge >= 0.06:
        st.success(pyramida.get_edge_message(edge))
    elif edge < 0.02:
        st.warning(pyramida.get_edge_message(edge))

# ---------------- KELLY & RISK PANEL ----------------
st.subheader("3️⃣ Kellyho kalkulačka a Risk Panel")
c1, c2, c3, c4 = st.columns(4)
bankroll = c1.number_input("Aktuálny Bankroll (€)", min_value=0.0, value=float(user["bankroll"]), step=10.0)
kelly_frakcia = c2.selectbox("Kelly Frakcia", [1.0, 0.5, 0.25],
                              index=[1.0, 0.5, 0.25].index(user["kelly_frakcia"]) if user["kelly_frakcia"] in [1.0, 0.5, 0.25] else 2)
max_bet_limit = c3.number_input("Max Bet Limit (% bankrollu)", min_value=0.1, max_value=100.0,
                                 value=user["max_bet_limit"] * 100, step=0.5) / 100
priebezna_hodnota_tiketu = c4.number_input("Priebežná hodnota tiketu (€)", min_value=0.0, value=50.0, step=5.0)

kelly_pct = calc.kelly_percent(edge, soft_kurz, kelly_frakcia, max_bet_limit, bankroll) if edge is not None else 0.0
vklad = calc.odporucany_vklad(bankroll, kelly_pct)

if bankroll <= 0:
    st.error("⚠️ Bankroll je 0 € alebo záporný. Kelly kalkulačka aj Under-hedging sú bezpečne vynulované - "
              "najprv si uprav bankroll v sekcii Nastavenia.")

r1, r2 = st.columns(2)
r1.metric("📐 Kelly %", f"{kelly_pct*100:.2f} %")
r2.metric("💶 Odporúčaný Vklad", f"{vklad:.2f} €")

# ---------------- UNDER-HEDGING ----------------
st.subheader("4️⃣ Stratégia Under-Hedgingu")
neposistena = calc.neposistena_cast(priebezna_hodnota_tiketu, vklad)
hedge_zaklad = calc.suma_na_poistenie(priebezna_hodnota_tiketu, neposistena)

c1, c2 = st.columns(2)
c1.metric("🟢 Nepoistená časť (Value Bet)", f"{neposistena:.2f} €")
c2.metric("🛡️ Suma na poistenie (Hedge základ)", f"{hedge_zaklad:.2f} €")

proti_kurz = st.number_input("Proti-Kurz (na hedge stávku)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
proti_vklad = calc.hedge_stavka(hedge_zaklad, soft_kurz, proti_kurz if proti_kurz > 0 else None)
st.metric("🔗 Prepojený Proti-Vklad (Hedge stávka)", f"{proti_vklad:.2f} €" if proti_vklad is not None else "-")

# ---------------- PYRAMÍDA ----------------
st.subheader("5️⃣ Tipsport Pyramída (voliteľné)")
st.caption("Validácia podľa oficiálnych pravidiel súťaže Pyramída, platných od 28. 4. 2026.")
send_to_pyramid = st.checkbox("📌 Poslať do Pyramídy")
pyramid_level = None
pyramid_blocked = False

if send_to_pyramid:
    next_level = min(user["pyramid_level"] + 1, 10)
    pyramid_level = st.selectbox("Level", list(range(1, 11)), index=next_level - 1)
    min_odds = pyramida.get_min_odds(pyramid_level)

    if soft_kurz < min_odds:
        st.error(f"⚠️ Level {pyramid_level} vyžaduje minimálny kurz {min_odds:.2f}. Tvoj soft kurz je {soft_kurz:.2f}.")
        pyramid_blocked = True
    else:
        st.success(f"✅ Kurz spĺňa minimum pre level {pyramid_level} ({min_odds:.2f}).")

    st.caption(f"🎁 Odmena za výhru na tomto leveli: **{pyramida.format_reward(pyramid_level)}**")

    # Bod 2.3 - LIVE tikety sú od 8. kola vyššie úplne zakázané (KRITICKÉ, hard block).
    if is_live and pyramid_level >= pyramida.LIVE_BLOCKED_FROM_LEVEL:
        st.error("❌ Pravidlá Pyramídy zakazujú podávať LIVE tikety od 8. kola vyššie! Tiket nie je možné zaradiť.")
        pyramid_blocked = True

    # Bod 2.3 - Mix tikety od 7. kola vyššie sú len varovanie, nie hard block.
    if mix_tiket and pyramid_level >= pyramida.MIX_WARNING_FROM_LEVEL:
        st.warning(
            f"⚠️ Level {pyramid_level} a Mix Tiket súčasne - pravidlá Pyramídy od 7. kola vyššie "
            "Mix tikety neodporúčajú. Over si podmienky súťaže pred podaním."
        )

    # Bod 2.1 - minimálny vklad 2 € pre akýkoľvek tiket poslaný do Pyramídy.
    stake_for_pyramid = st.number_input(
        "Skutočný vklad do Pyramídy (€)", min_value=0.0,
        value=float(vklad) if vklad else 0.0, step=0.5,
        help="Ak sa líši od odporúčaného Kelly vkladu, uprav na skutočnú sumu, ktorú do Pyramídy podávaš.",
    )
    if stake_for_pyramid < pyramida.MIN_PYRAMID_STAKE_EUR:
        st.error("⚠️ Minimálny vklad pre Pyramídu je 2 EUR!")
        pyramid_blocked = True

# ---------------- ULOŽIŤ / ZDIEĽAŤ ----------------
st.divider()
skore = st.text_input("Skóre (voliteľné)", value=prefill.get("skore", ""))
status = st.selectbox("Status tiketu", ["Otvorený", "Vyhratý", "Prehratý"])

pnl = None
if status != "Otvorený":
    pnl = calc.ciastkovy_pnl(status, priebezna_hodnota_tiketu, soft_kurz, proti_vklad, proti_kurz)

colA, colB = st.columns(2)

def _build_ticket_data(shared_flag: int):
    return {
        "sport": sport, "liga": liga, "timy": timy, "soft_bookmaker": soft_bookmaker,
        "typ_marketu": typ_marketu, "tip": tip,
        "sharp_k": sharp_k, "sharp_l": opacny_kurz, "soft_kurz": soft_kurz,
        "fair_kurz": fair, "edge": edge, "kelly_pct": kelly_pct,
        "priebezna_hodnota_tiketu": priebezna_hodnota_tiketu,
        "odporucany_vklad": vklad, "neposistena_cast": neposistena,
        "proti_kurz": proti_kurz if proti_kurz > 0 else None, "proti_vklad": proti_vklad,
        "skore": skore, "status": status, "pnl": pnl,
        "pyramid_level": pyramid_level, "shared": shared_flag,
        "ai_filled": 1 if prefill else 0, "is_live": 1 if is_live else 0,
        "mix_tiket": 1 if mix_tiket else 0,
        "match_date": match_date.isoformat(), "match_time": match_time.strftime("%H:%M"),
        "sharp_provider": sharp_provider, "liquidity": liquidity,
    }


def _credit_pyramid(user_id: int, level: int, pnl_value):
    """Bod 2.5.1 - odmena sa pripisuje len pri úspešnej výhre daného kola."""
    reward = pyramida.get_level_reward(level) if status == "Vyhratý" else None
    db.update_pyramid_progress(user_id, level, pnl_value or 0, reward)
    if reward:
        st.toast(f"🎁 Pripísaná odmena za Level {level}: {pyramida.format_reward(level)}", icon="🎉")


submit_disabled = bool(send_to_pyramid and pyramid_blocked)
if submit_disabled:
    st.error("🚫 Tiket nie je možné odoslať do Pyramídy, kým sú vyššie zobrazené kritické chyby aktívne. "
              "Oprav ich, alebo odznač '📌 Poslať do Pyramídy'.")

if colA.button("💾 Uložiť tiket (len pre mňa)", use_container_width=True, disabled=submit_disabled):
    tid = db.create_ticket(user["id"], _build_ticket_data(shared_flag=0))
    if send_to_pyramid and pyramid_level:
        _credit_pyramid(user["id"], pyramid_level, pnl)
    st.session_state.pop("ai_prefill", None)
    st.success(f"Tiket #{tid} uložený.")

if colB.button("🚀 Zdieľať do Syndikátu", type="primary", use_container_width=True, disabled=submit_disabled):
    tid = db.create_ticket(user["id"], _build_ticket_data(shared_flag=1))
    if send_to_pyramid and pyramid_level:
        _credit_pyramid(user["id"], pyramid_level, pnl)
    st.session_state.pop("ai_prefill", None)
    st.success(f"Tiket #{tid} zdieľaný do Syndikátneho Feedu! 🚀 Choď na stránku Syndikátny Feed.")
