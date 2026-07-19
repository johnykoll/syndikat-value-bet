import streamlit as st
import sys, os
import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from lib import database as db
from lib import formatting

st.set_page_config(page_title="Syndikátny Feed", page_icon="📡", layout="wide")

if "username" not in st.session_state or not st.session_state.username:
    st.warning("Najprv sa prihlás na hlavnej stránke.")
    st.stop()

db.init_db()
user = db.get_user(st.session_state.user_id)

EDGE_HIGH_THRESHOLD = 0.06
LIVE_STALE_MINUTES = 3


def _ticket_age_minutes(created_at: str):
    try:
        created_dt = datetime.datetime.fromisoformat(created_at)
        return (datetime.datetime.now() - created_dt).total_seconds() / 60
    except (ValueError, TypeError):
        return None


def render_feed_tab():
    st.caption("Live prehľad stávok, ktoré kamoši práve objavili.")

    # ---------------- AUTO-REFRESH ----------------
    ctrl1, ctrl2 = st.columns([2, 1])
    auto_refresh_on = ctrl1.toggle("🔄 Auto-refresh (každých 15 s)", value=False,
                                    help="Feed a komentáre sa budú automaticky obnovovať na pozadí.",
                                    key="feed_autorefresh_toggle")
    if ctrl2.button("🔄 Obnoviť teraz", key="feed_refresh_btn"):
        st.rerun()

    if auto_refresh_on:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=15_000, key="feed_autorefresh")
            st.caption("⏱️ Auto-refresh aktívny - stránka sa obnoví každých 15 sekúnd.")
        except ImportError:
            st.warning(
                "Auto-refresh vyžaduje balíček `streamlit-autorefresh`. "
                "Nainštaluj ho cez `pip install streamlit-autorefresh` a reštartuj appku. "
                "Dovtedy použi tlačidlo '🔄 Obnoviť teraz'."
            )

    tickets = db.get_feed_tickets()

    if not tickets:
        st.info("Feed je zatiaľ prázdny. Buď prvý, kto zdieľa value bet - choď na stránku **Nový Tiket**.")
        return

    for t in tickets:
        edge = t["edge"] or 0
        is_high_edge = edge >= EDGE_HIGH_THRESHOLD

        # ---- Starnutie LIVE tiketov (visual aging) ----
        elapsed_min = _ticket_age_minutes(t["created_at"])
        is_stale_live = bool(t["is_live"]) and elapsed_min is not None and elapsed_min > LIVE_STALE_MINUTES

        with st.container(border=True):
            if is_stale_live:
                st.markdown(
                    f"""<div style="background-color:#FFF3B0; border-left: 5px solid #D9822B;
                    padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                    ⚠️ <b>Pozor, tento LIVE tiket bol zdieľaný pred {int(elapsed_min)} minútami!</b>
                    Kurzy sa na zápase už pravdepodobne zmenili.
                    </div>""",
                    unsafe_allow_html=True,
                )
            elif t["is_live"]:
                st.caption(f"🔴 LIVE tiket · zdieľaný pred {int(elapsed_min)} min" if elapsed_min is not None else "🔴 LIVE tiket")

            top_c1, top_c2, top_c3 = st.columns([3, 2, 2])
            title = f"⚽ {t['timy']}" if t['timy'] else "⚽ Zápas"
            if is_high_edge:
                title = "🟢 " + title
            if is_stale_live:
                title = "🟡 " + title
            top_c1.markdown(f"### {title}")
            match_dt_str = formatting.format_match_dt(t["match_date"], t["match_time"])
            caption_line = f"{t['sport']} · {t['liga']} · autor: **{t['author']}**"
            if match_dt_str:
                caption_line += f" · 🕒 Zápas: {match_dt_str}"
            top_c1.caption(caption_line)

            top_c2.metric("Soft Kurz", f"{t['soft_kurz']:.2f}" if t["soft_kurz"] else "-")
            top_c3.metric("⚡ Edge", f"{edge*100:+.2f} %", delta_color="normal")

            c1, c2, c3, c4 = st.columns(4)
            c1.write(f"**Tip:** {t['tip'] or '-'}")
            c2.write(f"**Fair kurz:** {t['fair_kurz']:.3f}" if t["fair_kurz"] else "**Fair kurz:** -")
            c3.write(f"**Kelly:** {(t['kelly_pct'] or 0)*100:.2f} %")
            c4.write(f"**Odporúčaný vklad:** {t['odporucany_vklad']:.2f} €" if t["odporucany_vklad"] else "-")

            if t["sharp_provider"] or t["liquidity"]:
                sp_line = f"**Sharp protistrana:** {t['sharp_provider'] or '-'}"
                if t["liquidity"]:
                    sp_line += f" · **Likvidita:** {t['liquidity']}"
                st.caption(sp_line)

            if t["ai_filled"]:
                st.caption("🤖 Pôvodne auto-vyplnené z AI skenovania")

            # ---- Jedným klikom skopírovať (len pre ostatných, nie pre autora) ----
            if str(t["user_id"]) != str(user["id"]):
                copy_label = "⚠️ Skopírovať napriek starnutiu kurzu" if is_stale_live else "📋 Skopírovať do mojej kalkulačky"
                if st.button(copy_label, key=f"copy_{t['id']}"):
                    st.session_state.ai_prefill = {
                        "sport": t["sport"], "liga": t["liga"], "timy": t["timy"],
                        "soft_bookmaker": t["soft_bookmaker"], "typ_marketu": t["typ_marketu"],
                        "tip": t["tip"], "soft_kurz": t["soft_kurz"], "skore": t["skore"] or "",
                        "match_date": t["match_date"] or "", "match_time": t["match_time"] or "",
                        "sharp_provider": t["sharp_provider"] or "", "liquidity": t["liquidity"] or "",
                    }
                    st.success("Dáta skopírované! Choď na stránku 🆕 Nový Tiket - formulár bude predvyplnený.")

            # ---- Stiahnuť zo Syndikátu (len autor tiketu) ----
            if str(t["user_id"]) == str(user["id"]):
                if st.button("❌ Stiahnuť zo Syndikátu", key=f"unshare_{t['id']}"):
                    db.unshare_ticket(t["id"])
                    st.success("Tiket bol stiahnutý z Feedu a vrátený do tvojich súkromných tiketov.")
                    st.rerun()


            # ---- Emoji reakcie ----
            counts = db.get_reaction_counts(t["id"])
            rc1, rc2, rc3, rc4 = st.columns(4)
            if rc1.button(f"🔥 {counts.get('🔥', 0)}", key=f"fire_{t['id']}"):
                db.add_reaction(t["id"], user["id"], "🔥")
                st.rerun()
            if rc2.button(f"🔒 {counts.get('🔒', 0)}", key=f"lock_{t['id']}"):
                db.add_reaction(t["id"], user["id"], "🔒")
                st.rerun()
            if rc3.button(f"💰 {counts.get('💰', 0)}", key=f"money_{t['id']}"):
                db.add_reaction(t["id"], user["id"], "💰")
                st.rerun()

            # ---- Mikro-chat ----
            with st.expander(f"💬 Komentáre ({len(db.get_comments(t['id']))})"):
                for cm in db.get_comments(t["id"]):
                    st.markdown(f"**{cm['author']}** · _{cm['created_at']}_")
                    st.write(cm["message"])
                new_msg = st.text_input("Napíš správu (napr. 'Tipsport znižuje kurz, bleskovo podávajte!')",
                                         key=f"msg_input_{t['id']}")
                if st.button("Odoslať", key=f"send_{t['id']}") and new_msg.strip():
                    db.add_comment(t["id"], user["id"], new_msg.strip())
                    st.rerun()


def render_private_tab():
    st.caption("Tikety, ktoré si uložil len pre seba - nikto iný v Syndikáte ich nevidí.")

    if st.button("🔄 Obnoviť teraz", key="private_refresh_btn"):
        st.rerun()

    tickets = db.get_private_tickets(user["id"])

    if not tickets:
        st.info(
            "Zatiaľ nemáš žiadne súkromné tikety. Vytvor ich cez stránku **🆕 Nový Tiket** "
            "tlačidlom '💾 Uložiť tiket (len pre mňa)'."
        )
        return

    for t in tickets:
        edge = t["edge"] or 0
        elapsed_min = _ticket_age_minutes(t["created_at"])
        is_stale_live = bool(t["is_live"]) and elapsed_min is not None and elapsed_min > LIVE_STALE_MINUTES

        with st.container(border=True):
            if is_stale_live:
                st.markdown(
                    f"""<div style="background-color:#FFF3B0; border-left: 5px solid #D9822B;
                    padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                    ⚠️ <b>Tento LIVE tiket si uložil pred {int(elapsed_min)} minútami!</b>
                    Kurzy sa na zápase už pravdepodobne zmenili.
                    </div>""",
                    unsafe_allow_html=True,
                )

            top_c1, top_c2, top_c3 = st.columns([3, 2, 2])
            title = f"🔒 {t['timy']}" if t["timy"] else "🔒 Zápas"
            top_c1.markdown(f"### {title}")
            match_dt_str = formatting.format_match_dt(t["match_date"], t["match_time"])
            caption_line = f"{t['sport']} · {t['liga']}"
            if match_dt_str:
                caption_line += f" · 🕒 Zápas: {match_dt_str}"
            caption_line += f" · Status: **{t['status']}**"
            top_c1.caption(caption_line)

            top_c2.metric("Soft Kurz", f"{t['soft_kurz']:.2f}" if t["soft_kurz"] else "-")
            top_c3.metric("⚡ Edge", f"{edge*100:+.2f} %" if t["edge"] is not None else "-")

            c1, c2, c3, c4 = st.columns(4)
            c1.write(f"**Tip:** {t['tip'] or '-'}")
            c2.write(f"**Fair kurz:** {t['fair_kurz']:.3f}" if t["fair_kurz"] else "**Fair kurz:** -")
            c3.write(f"**Odporúčaný vklad:** {t['odporucany_vklad']:.2f} €" if t["odporucany_vklad"] else "-")
            c4.write(f"**PnL:** {t['pnl']:.2f} €" if t["pnl"] is not None else "**PnL:** -")

            if t["sharp_provider"] or t["liquidity"]:
                sp_line = f"**Sharp protistrana:** {t['sharp_provider'] or '-'}"
                if t["liquidity"]:
                    sp_line += f" · **Likvidita:** {t['liquidity']}"
                st.caption(sp_line)

            if t["ai_filled"]:
                st.caption("🤖 Pôvodne auto-vyplnené z AI skenovania")

            if st.button("🚀 Zdieľať teraz do Syndikátu", key=f"promote_{t['id']}"):
                db.share_ticket(t["id"])
                st.success("Tiket bol presunutý do Syndikátneho Feedu.")
                st.rerun()


st.title("📡 Syndikát")

tab_feed, tab_private = st.tabs(["📡 Syndikátny Feed", "🔒 Moje súkromné tikety"])

with tab_feed:
    render_feed_tab()

with tab_private:
    render_private_tab()
