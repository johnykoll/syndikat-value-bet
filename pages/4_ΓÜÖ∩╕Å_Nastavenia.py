import streamlit as st
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from lib import database as db

st.set_page_config(page_title="Nastavenia", page_icon="⚙️", layout="centered")

if "username" not in st.session_state or not st.session_state.username:
    st.warning("Najprv sa prihlás na hlavnej stránke.")
    st.stop()

db.init_db()
user = db.get_user(st.session_state.user_id)

st.title("⚙️ Nastavenia")
st.caption(f"Profil: **{user['username']}**")

with st.form("settings_form"):
    bankroll = st.number_input("💶 Aktuálny Bankroll (€)", min_value=0.0, value=float(user["bankroll"]), step=10.0)
    kelly_frakcia = st.select_slider("📐 Kelly Frakcia", options=[0.25, 0.5, 1.0],
                                      value=user["kelly_frakcia"] if user["kelly_frakcia"] in [0.25, 0.5, 1.0] else 0.25)
    max_bet_limit = st.slider("🚧 Max Bet Limit (% bankrollu)", min_value=0.5, max_value=25.0,
                               value=user["max_bet_limit"] * 100, step=0.5) / 100
    global_marza = st.slider("📊 Globálna marža sharp stávkovej kancelárie (%)", min_value=0.0, max_value=15.0,
                              value=user["global_marza"] * 100, step=0.1) / 100
    submitted = st.form_submit_button("💾 Uložiť nastavenia", type="primary")

if submitted:
    db.update_user_settings(user["id"], bankroll, kelly_frakcia, max_bet_limit, global_marza)
    st.success("Nastavenia uložené.")
    st.rerun()

st.divider()
st.subheader("🤖 AI Skenovanie - API kľúče")
st.caption(
    "API kľúče sa zadávajú priamo na stránke **Nový Tiket** pri skenovaní a ukladajú sa "
    "iba dočasne v rámci tvojej session (nikdy natrvalo do databázy). "
    "Potrebuješ vlastný kľúč od OpenAI (platform.openai.com) alebo Google AI Studio (Gemini)."
)

st.divider()
st.subheader("💸 Manuálna úprava bankrollu")
st.caption("Použi napr. po vklade/výbere v skutočnej stávkovej kancelárii.")
delta = st.number_input("Zmena bankrollu (+/- €)", value=0.0, step=10.0)
if st.button("Aplikovať zmenu"):
    db.adjust_user_bankroll(user["id"], delta)
    st.success(f"Bankroll upravený o {delta:+.2f} €.")
    st.rerun()
