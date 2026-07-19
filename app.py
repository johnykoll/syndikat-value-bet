import streamlit as st
import pandas as pd
import sys, os

sys.path.append(os.path.dirname(__file__))
from lib import database as db

st.set_page_config(page_title="Syndikát MVP", page_icon="💰", layout="wide")
db.init_db()

# ---------------- LOGIN / USER SWITCHER ----------------
if "username" not in st.session_state:
    st.session_state.username = None

st.sidebar.title("💰 Syndikát MVP")

if not st.session_state.username:
    st.title("👋 Vitaj v Syndikáte")
    st.caption("Zadaj svoju prezývku - ak si tu prvý krát, automaticky sa ti vytvorí profil s defaultným bankrollom.")
    existing = [u["username"] for u in db.list_users()]
    if existing:
        st.write("Existujúci členovia:", ", ".join(existing))
    name = st.text_input("Tvoja prezývka")
    if st.button("Vstúpiť do Syndikátu", type="primary") and name.strip():
        st.session_state.username = name.strip()
        st.rerun()
    st.stop()

user = db.get_or_create_user(st.session_state.username)
st.session_state.user_id = user["id"]

st.sidebar.success(f"Prihlásený ako **{user['username']}**")
if st.sidebar.button("Odhlásiť sa"):
    st.session_state.username = None
    st.rerun()

st.sidebar.divider()
st.sidebar.metric("💶 Bankroll", f"{user['bankroll']:.2f} €")
st.sidebar.metric("🏆 Pyramída level", f"{user['pyramid_level']} / 10")
st.sidebar.caption("Choď na **Nový Tiket** pre pridanie stávky, alebo na **Syndikátny Feed** pre live prehľad kamošov.")

# ---------------- DASHBOARD ----------------
st.title("📊 Dashboard")

my_tickets = db.get_my_tickets(user["id"])
df = pd.DataFrame([dict(t) for t in my_tickets])

col1, col2, col3, col4 = st.columns(4)
col1.metric("💶 Aktuálny Bankroll", f"{user['bankroll']:.2f} €")

if not df.empty:
    closed = df[df["status"].isin(["Vyhratý", "Prehratý"])]
    total_pnl = closed["pnl"].sum() if not closed.empty else 0.0
    open_count = len(df[df["status"] == "Otvorený"])
    avg_edge = df["edge"].mean() if "edge" in df else 0.0
    col2.metric("📈 Celkové PnL", f"{total_pnl:+.2f} €")
    col3.metric("🟢 Otvorené tikety", open_count)
    col4.metric("⚡ Priemerný Edge", f"{avg_edge*100:.1f} %" if pd.notna(avg_edge) else "-")
else:
    col2.metric("📈 Celkové PnL", "0.00 €")
    col3.metric("🟢 Otvorené tikety", 0)
    col4.metric("⚡ Priemerný Edge", "-")

st.divider()
st.subheader("🕓 Moje posledné tikety")

if df.empty:
    st.info("Zatiaľ nemáš žiadne tikety. Vytvor prvý cez stránku **Nový Tiket** v ľavom menu.")
else:
    show_cols = ["created_at", "sport", "timy", "tip", "soft_kurz", "fair_kurz",
                 "edge", "kelly_pct", "odporucany_vklad", "status", "pnl", "shared"]
    show_cols = [c for c in show_cols if c in df.columns]
    display_df = df[show_cols].copy()
    if "edge" in display_df:
        display_df["edge"] = (display_df["edge"] * 100).round(2).astype(str) + " %"
    if "kelly_pct" in display_df:
        display_df["kelly_pct"] = (display_df["kelly_pct"] * 100).round(2).astype(str) + " %"
    display_df.rename(columns={
        "created_at": "Vytvorené", "sport": "Šport", "timy": "Zápas", "tip": "Tip",
        "soft_kurz": "Soft kurz", "fair_kurz": "Fair kurz", "edge": "Edge",
        "kelly_pct": "Kelly %", "odporucany_vklad": "Vklad €", "status": "Status",
        "pnl": "PnL €", "shared": "Zdieľané",
    }, inplace=True)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

st.divider()
st.subheader("🏆 Syndikátny rebríček (Top bankroll)")
all_users = db.list_users()
lb_df = pd.DataFrame([dict(u) for u in all_users])[["username", "bankroll", "pyramid_level", "pyramid_profit"]]
lb_df.rename(columns={"username": "Hráč", "bankroll": "Bankroll €",
                       "pyramid_level": "Pyramída Level", "pyramid_profit": "Pyramída Profit €"}, inplace=True)
lb_df = lb_df.sort_values("Bankroll €", ascending=False)
st.dataframe(lb_df, use_container_width=True, hide_index=True)
