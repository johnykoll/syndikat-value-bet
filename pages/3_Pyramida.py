import streamlit as st
import pandas as pd
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from lib import database as db
from lib import pyramida

st.set_page_config(page_title="Pyramída", page_icon="🏆", layout="wide")

if "username" not in st.session_state or not st.session_state.username:
    st.warning("Najprv sa prihlás na hlavnej stránke.")
    st.stop()

db.init_db()
user = db.get_user(st.session_state.user_id)

st.title("🏆 Moja Pyramída")
st.caption("Pravidlá platné od 28. 4. 2026 - kurzová mapa a odmeny podľa oficiálneho znenia (Bod 2.1, 2.3, 2.5.1, 3.1.1).")

level = user["pyramid_level"]
st.subheader(f"Aktuálny level: {level} / 10")
st.progress(level / 10)
st.info(pyramida.get_level_message(level) if level > 0 else "Zatiaľ si nezačal pyramídu. Pošli tiket cez 🆕 Nový Tiket a zaškrtni 'Poslať do Pyramídy'.")

m1, m2, m3 = st.columns(3)
m1.metric("💶 Pyramída Profit (€)", f"{user['pyramid_profit']:.2f} €")
m2.metric("🎫 Nety (vernostné body)", f"{user['pyramid_body']}")
m3.metric("🏆 Hlavná cena", "Získaná! 🎉" if user["pyramid_hlavna_cena"] else "Zatiaľ nie")

with st.expander("📜 Kritické pravidlá (rýchly prehľad)"):
    st.markdown(f"""
- **Bod 2.1** - minimálny vklad do Pyramídy je **{pyramida.MIN_PYRAMID_STAKE_EUR:.2f} €**.
- **Bod 2.3** - LIVE tikety sú od **Levelu {pyramida.LIVE_BLOCKED_FROM_LEVEL}** vyššie úplne zakázané.
- **Bod 2.3** - Mix tikety od **Levelu {pyramida.MIX_WARNING_FROM_LEVEL}** vyššie sa neodporúčajú (varovanie).
- **Bod 3.1.1** - kurzová mapa je definitívna a lineárne stúpajúca (1.1 → 10.0).
- **Bod 2.5.1** - odmena za výhru sa pripisuje automaticky pri zaznačení tiketu ako "Vyhratý".
""")

st.divider()
st.subheader("📋 Rebrík levelov")
ladder_rows = []
my_tickets = {t["pyramid_level"]: t for t in db.get_pyramid_tickets(user["id"])}
for lvl in range(1, 11):
    lvl_status = "✅ Splnené" if lvl <= level else ("👉 Ďalší krok" if lvl == level + 1 else "🔒 Uzamknuté")
    ticket = my_tickets.get(lvl)
    live_warning = "🚫 LIVE zakázané" if lvl >= pyramida.LIVE_BLOCKED_FROM_LEVEL else (
        "⚠️ Mix neodporúčaný" if lvl >= pyramida.MIX_WARNING_FROM_LEVEL else "-"
    )
    ladder_rows.append({
        "Level": lvl,
        "Min. kurz": f"{pyramida.get_min_odds(lvl):.2f}",
        "Odmena": pyramida.format_reward(lvl),
        "Obmedzenia": live_warning,
        "Status": lvl_status,
        "Zápas": ticket["timy"] if ticket else "-",
    })
st.dataframe(pd.DataFrame(ladder_rows), use_container_width=True, hide_index=True)

st.divider()
st.subheader("👑 Syndikátny Leaderboard")
all_users = db.list_users()
lb = pd.DataFrame([dict(u) for u in all_users])[
    ["username", "pyramid_level", "pyramid_profit", "pyramid_body", "pyramid_hlavna_cena", "bankroll"]
]
lb["pyramid_hlavna_cena"] = lb["pyramid_hlavna_cena"].apply(lambda v: "🏆" if v else "")
lb.rename(columns={
    "username": "Hráč", "pyramid_level": "Level", "pyramid_profit": "Pyramída Profit €",
    "pyramid_body": "Nety", "pyramid_hlavna_cena": "Hlavná cena", "bankroll": "Bankroll €",
}, inplace=True)
lb = lb.sort_values(["Level", "Pyramída Profit €"], ascending=[False, False])
st.dataframe(lb, use_container_width=True, hide_index=True)

if not lb.empty:
    st.bar_chart(lb.set_index("Hráč")["Level"])
