import streamlit as st
import pandas as pd
import sys, os
import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from lib import database as db

st.set_page_config(page_title="História a Export", page_icon="📊", layout="wide")

if "username" not in st.session_state or not st.session_state.username:
    st.warning("Najprv sa prihlás na hlavnej stránke.")
    st.stop()

db.init_db()
user = db.get_user(st.session_state.user_id)

st.title("📊 História a Export")
st.caption("Prehľad tvojich tiketov a export do CSV pre ďalšiu analýzu (Excel, Google Sheets...).")

# ---------------- FILTER ----------------
filter_choice = st.radio(
    "Aké dáta chceš zobraziť?",
    ["📡 Syndikátne tikety (celý Feed)", "🔒 Iba moje súkromné tikety", "📋 Všetky moje tikety (súkromné aj zdieľané)"],
    horizontal=True,
)

if filter_choice == "📡 Syndikátne tikety (celý Feed)":
    tickets = db.get_feed_tickets()
elif filter_choice == "🔒 Iba moje súkromné tikety":
    tickets = db.get_private_tickets(user["id"])
else:
    tickets = db.get_my_tickets(user["id"])

if not tickets:
    st.info("Pre tento filter zatiaľ nie sú žiadne dáta.")
    st.stop()

df = pd.DataFrame([dict(t) for t in tickets])

# ---------------- PREHĽADNÉ STĹPCE ----------------
PREFERRED_ORDER = [
    "created_at", "match_date", "match_time", "sport", "liga", "timy",
    "soft_bookmaker", "typ_marketu", "tip", "status",
    "soft_kurz", "sharp_k", "sharp_l", "fair_kurz", "edge", "kelly_pct",
    "priebezna_hodnota_tiketu", "odporucany_vklad", "neposistena_cast",
    "proti_kurz", "proti_vklad", "pnl",
    "sharp_provider", "liquidity",
    "is_live", "mix_tiket", "pyramid_level", "shared", "ai_filled", "skore",
    "placed_at", "author" if "author" in df.columns else None,
]
ordered_cols = [c for c in PREFERRED_ORDER if c and c in df.columns]
remaining_cols = [c for c in df.columns if c not in ordered_cols]
display_df = df[ordered_cols + remaining_cols]

st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric("📋 Počet tiketov", len(display_df))
if "pnl" in display_df.columns:
    closed = display_df[display_df["status"].isin(["Vyhratý", "Prehratý"])]
    total_pnl = closed["pnl"].sum() if not closed.empty else 0.0
    c2.metric("📈 Celkové PnL", f"{total_pnl:+.2f} €")
if "edge" in display_df.columns:
    avg_edge = display_df["edge"].mean()
    c3.metric("⚡ Priemerný Edge", f"{avg_edge*100:.2f} %" if pd.notna(avg_edge) else "-")
if "status" in display_df.columns:
    open_count = len(display_df[display_df["status"] == "Otvorený"])
    c4.metric("🟢 Otvorené", open_count)

st.divider()
st.subheader("📋 Tabuľka dát")
st.dataframe(display_df, use_container_width=True, hide_index=True)

# ---------------- EXPORT DO CSV ----------------
st.divider()
st.subheader("⬇️ Export do CSV")

exp1, exp2 = st.columns(2)
separator_label = exp1.selectbox("Oddeľovač stĺpcov", ["Bodkočiarka ( ; )", "Čiarka ( , )"])
separator = ";" if "Bodkočiarka" in separator_label else ","
exp2.caption("Bodkočiarka je vhodnejšia pre slovenské/české nastavenie Excelu (desatinná čiarka), čiarka pre medzinárodné CSV nástroje.")

# UTF-8 s BOM (utf-8-sig), aby Excel automaticky správne rozpoznal diakritiku.
csv_bytes = display_df.to_csv(index=False, sep=separator).encode("utf-8-sig")

filter_slug = {
    "📡 Syndikátne tikety (celý Feed)": "feed",
    "🔒 Iba moje súkromné tikety": "sukromne",
    "📋 Všetky moje tikety (súkromné aj zdieľané)": "vsetky_moje",
}[filter_choice]
filename = f"synbet_export_{filter_slug}_{datetime.date.today().isoformat()}.csv"

st.download_button(
    "⬇️ Stiahnuť ako CSV",
    data=csv_bytes,
    file_name=filename,
    mime="text/csv",
    use_container_width=True,
)
