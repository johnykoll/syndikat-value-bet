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

level = user["pyramid_level"]
st.subheader(f"Aktuálny level: {level} / 10")
st.progress(level / 10)
st.info(pyramida.get_level_message(level) if level > 0 else "Zatiaľ si nezačal pyramídu. Pošli tiket cez 🆕 Nový Tiket a zaškrtni 'Poslať do Pyramídy'.")

st.divider()
st.subheader("📋 Rebrík levelov")
ladder_rows = []
my_tickets = {t["pyramid_level"]: t for t in db.get_pyramid_tickets(user["id"])}
for lvl in range(1, 11):
    status = "✅ Splnené" if lvl <= level else ("👉 Ďalší krok" if lvl == level + 1 else "🔒 Uzamknuté")
    ticket = my_tickets.get(lvl)
    ladder_rows.append({
        "Level": lvl,
        "Min. kurz": f"{pyramida.get_min_odds(lvl):.2f}",
        "Status": status,
        "Zápas": ticket["timy"] if ticket else "-",
    })
st.dataframe(pd.DataFrame(ladder_rows), use_container_width=True, hide_index=True)

st.divider()
st.subheader("👑 Syndikátny Leaderboard")
all_users = db.list_users()
lb = pd.DataFrame([dict(u) for u in all_users])[["username", "pyramid_level", "pyramid_profit", "bankroll"]]
lb.rename(columns={"username": "Hráč", "pyramid_level": "Level",
                    "pyramid_profit": "Pyramída Profit €", "bankroll": "Bankroll €"}, inplace=True)
lb = lb.sort_values(["Level", "Pyramída Profit €"], ascending=[False, False])
st.dataframe(lb, use_container_width=True, hide_index=True)

if not lb.empty:
    st.bar_chart(lb.set_index("Hráč")["Level"])
