"""Gradelift Upper Limb Mock Exam - timed quiz (Streamlit).

No login, unlimited retakes. Questions and settings are read from a Google
Sheet (through Streamlit Secrets), so answers never sit in the public repo.
"""
import os
import random
from datetime import datetime, timedelta, timezone

import streamlit as st

st.set_page_config(page_title="Gradelift Mock Exam", page_icon="🩺", layout="centered")

LETTERS = ["A", "B", "C", "D"]
PASS_MARK = 0.60  # tags below this are flagged for revision


def now():
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------- data
@st.cache_data(ttl=600)
def load_exam():
    """Returns (settings, questions). Cached for 10 minutes."""
    if os.environ.get("MOCK_LOCAL_XLSX"):  # local testing without Google
        import openpyxl

        wb = openpyxl.load_workbook(os.environ["MOCK_LOCAL_XLSX"], data_only=True)
        rows = list(wb["Questions"].iter_rows(values_only=True))
        recs = [dict(zip(rows[0], r)) for r in rows[1:]]
        ws = wb["Settings"]
        vals = [ws["B3"].value, ws["B4"].value, ws["B8"].value]
    elif "sheet_url" in st.secrets:  # simple mode: Sheet shared as "Anyone with the link can view"
        import re
        from urllib.parse import quote

        import pandas as pd

        sid = re.search(r"/d/([A-Za-z0-9_-]+)", st.secrets["sheet_url"]).group(1)

        def tab(name, headers):
            return pd.read_csv(
                f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tv?tqx=out:csv"
                f"&sheet={quote(name)}&headers={headers}",
                dtype=str,
                keep_default_na=False,
            )

        recs = tab("Questions", 1).to_dict("records")
        cells = [str(c).strip() for row in tab("Settings", 0).values.tolist() for c in row]
        find = lambda label: cells[cells.index(label) + 1]
        vals = [None, find("Time limit (minutes)"), find("Telegram CTA link")]
    else:
        import gspread

        gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
        sh = gc.open_by_key(st.secrets["sheet_id"])
        recs = sh.worksheet("Questions").get_all_records()
        v = sh.worksheet("Settings").get_all_values()
        vals = [v[2][1], v[3][1], v[7][1]]
    settings = {"minutes": int(float(vals[1])), "cta": str(vals[2]).strip()}
    qs = [
        {
            "no": int(float(r["Question No."])),
            "tag": r["Tag"],
            "q": r["Question"],
            "opts": [str(r[f"Option {l}"]) for l in LETTERS],
            "ans": str(r["Correct Answer"]).strip().upper(),
            "why": r.get("Explanation", "") or "",
        }
        for r in recs
        if r.get("Question")
    ]
    return settings, qs


# -------------------------------------------------------------------- logic
def collect(qs):
    return {q["no"]: st.session_state.get(f"ans_{q['no']}") for q in qs}


def submit(qs):
    st.session_state.answers = collect(qs)
    st.session_state.phase = "results"
    st.rerun()


def reset():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


# ----------------------------------------------------------------------- UI
def intro(settings, qs):
    st.title("🩺 Gradelift Upper Limb Mock Exam")
    st.markdown(
        f"""
- **{len(qs)} questions** covering the whole upper limb
- **{settings['minutes']} minutes.** The timer starts when you press Start and can't be paused
- You can retake it as many times as you like
- Don't refresh or close the page during the exam, or you'll lose your answers
"""
    )
    if st.button("Start exam", type="primary"):
        order = list(qs)
        random.shuffle(order)  # new order every attempt
        st.session_state.order = [q["no"] for q in order]
        st.session_state.deadline = now() + timedelta(minutes=settings["minutes"])
        st.session_state.phase = "exam"
        st.rerun()


def exam(settings, qs):
    by_no = {q["no"]: q for q in qs}
    deadline = st.session_state.deadline

    st.markdown(
        "<style>.st-key-timerbar{position:sticky;top:3rem;z-index:999;padding:.4rem .8rem;"
        "background:var(--secondary-background-color);border-radius:.5rem}</style>",
        unsafe_allow_html=True,
    )
    with st.container(key="timerbar"):

        @st.fragment(run_every=1)
        def timer():
            left = int((deadline - now()).total_seconds())
            if left <= 0:
                submit(qs)  # time's up: auto-submit
            done = sum(1 for q in qs if st.session_state.get(f"ans_{q['no']}"))
            m, s = divmod(left, 60)
            icon = "🔴" if left < 300 else "⏱️"
            st.markdown(f"**{icon} {m:02d}:{s:02d} left** &nbsp;|&nbsp; {done}/{len(qs)} answered")

        timer()

    for n, no in enumerate(st.session_state.order, start=1):
        q = by_no[no]
        st.markdown(f"**{n}. {q['q']}**")
        st.radio(
            "answer",
            LETTERS,
            index=None,
            key=f"ans_{no}",
            format_func=lambda l, q=q: f"{l}. {q['opts'][LETTERS.index(l)]}",
            label_visibility="collapsed",
        )
        st.divider()

    unanswered = sum(1 for q in qs if not st.session_state.get(f"ans_{q['no']}"))
    if st.button("Submit exam", type="primary"):
        st.session_state.confirm = True
    if st.session_state.get("confirm"):
        st.warning(f"Submit now? You have {unanswered} unanswered question(s).")
        c1, c2 = st.columns(2)
        if c1.button("Yes, submit"):
            submit(qs)
        if c2.button("Go back"):
            st.session_state.confirm = False
            st.rerun()


def results(settings, qs):
    answers = st.session_state.answers
    per_tag, score = {}, 0
    for q in qs:
        ok = answers.get(q["no"]) == q["ans"]
        score += ok
        t = per_tag.setdefault(q["tag"], [0, 0])
        t[0] += ok
        t[1] += 1
    st.title("Your result")
    st.metric("Score", f"{score} / {len(qs)}", f"{round(100 * score / len(qs))}%", delta_color="off")

    # Telegram CTA, directly above the feedback
    st.success("**Lower limb class is next!** Join our Telegram channel to follow the lower limb class.")
    st.link_button("Join the Telegram channel 👉", settings["cta"], type="primary")

    st.subheader("Feedback by topic")
    weak = []
    for tag, (c, t) in per_tag.items():
        st.write(f"**{tag}** — {c}/{t}")
        st.progress(c / t)
        if c / t < PASS_MARK:
            weak.append((tag, c, t))
    if weak:
        st.subheader("Revise these")
        for tag, c, t in weak:
            st.write(f"• You got {c} of {t} right in **{tag.split(': ', 1)[-1]}**. Go back and review it.")
    else:
        st.write("Strong across every topic. Well done!")

    missed = [q for q in qs if answers.get(q["no"]) != q["ans"]]
    if missed:
        with st.expander(f"Review the {len(missed)} question(s) you missed"):
            for q in missed:
                mine = answers.get(q["no"])
                st.markdown(f"**{q['q']}**")
                st.write(f"Your answer: {mine + '. ' + q['opts'][LETTERS.index(mine)] if mine else 'Not answered'}")
                st.write(f"Correct: {q['ans']}. {q['opts'][LETTERS.index(q['ans'])]}")
                if q["why"]:
                    st.caption(q["why"])
                st.divider()
    if st.button("🔁 Take it again"):
        reset()


def main():
    try:
        settings, qs = load_exam()
    except Exception:
        st.error("The exam isn't available right now. Please try again shortly.")
        st.stop()
    phase = st.session_state.get("phase", "intro")
    {"intro": intro, "exam": exam, "results": results}[phase](settings, qs)


main()
