"""
Streamlit dashboard for the job market tracker.

Launch with:
    python run.py dashboard
  or directly:
    streamlit run dashboard/app.py
"""
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import func, select

# Ensure project root is on the path when running via `streamlit run`
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.db import SessionLocal, init_db
from storage.models import Job, JobSkill

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Job Market Tracker",
    page_icon="📊",
    layout="wide",
)

# ── Ensure DB exists ──────────────────────────────────────────────────────────
init_db()


# ── Helper: load data ────────────────────────────────────────────────────────
def load_jobs(sites: list[str], start: date, end: date) -> pd.DataFrame:
    session = SessionLocal()
    try:
        stmt = (
            select(Job.id, Job.site, Job.title, Job.company, Job.url, Job.scraped_at)
            .where(Job.site.in_(sites))
            .where(Job.scraped_at >= datetime.combine(start, datetime.min.time()))
            .where(Job.scraped_at <= datetime.combine(end, datetime.max.time()))
        )
        rows = session.execute(stmt).fetchall()
        return pd.DataFrame(rows, columns=["id", "site", "title", "company", "url", "scraped_at"])
    finally:
        session.close()


def load_skills(job_ids: list[int]) -> pd.DataFrame:
    if not job_ids:
        return pd.DataFrame(columns=["job_id", "skill_name", "category"])
    session = SessionLocal()
    try:
        stmt = select(JobSkill.job_id, JobSkill.skill_name, JobSkill.category).where(
            JobSkill.job_id.in_(job_ids)
        )
        rows = session.execute(stmt).fetchall()
        return pd.DataFrame(rows, columns=["job_id", "skill_name", "category"])
    finally:
        session.close()


def last_scraped_at() -> str:
    session = SessionLocal()
    try:
        result = session.execute(select(func.max(Job.scraped_at))).scalar()
        if result:
            return result.strftime("%Y-%m-%d %H:%M UTC")
        return "Never"
    finally:
        session.close()


def all_categories() -> list[str]:
    session = SessionLocal()
    try:
        rows = session.execute(select(JobSkill.category).distinct()).fetchall()
        return sorted(r[0] for r in rows)
    finally:
        session.close()


# ── Header ───────────────────────────────────────────────────────────────────
col_title, col_scrape = st.columns([4, 1])
with col_title:
    st.title("📊 Job Market Tracker")
    st.caption(f"Last scraped: {last_scraped_at()}")

with col_scrape:
    st.write("")
    if st.button("🔄 Scrape now", use_container_width=True):
        with st.spinner("Scraping... this may take a few minutes."):
            result = subprocess.run(
                [sys.executable, str(Path(__file__).parent.parent / "run.py"), "scrape"],
                capture_output=True,
                text=True,
            )
        if result.returncode == 0:
            st.success("Done!")
            st.text(result.stdout[-500:] if result.stdout else "")
        else:
            st.error("Scrape failed.")
            st.text(result.stderr[-1000:] if result.stderr else "")
        st.rerun()

st.divider()

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")

    selected_sites = st.multiselect(
        "Source",
        options=["jobteaser", "studerendeonline"],
        default=["jobteaser", "studerendeonline"],
    )

    today = date.today()
    date_range = st.date_input(
        "Date range",
        value=(today - timedelta(days=30), today),
        max_value=today,
    )
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = today - timedelta(days=30), today

    available_categories = all_categories()
    selected_categories = st.multiselect(
        "Skill category",
        options=available_categories,
        default=available_categories,
    )

# ── Load data ─────────────────────────────────────────────────────────────────
if not selected_sites:
    st.warning("Select at least one source in the sidebar.")
    st.stop()

jobs_df = load_jobs(selected_sites, start_date, end_date)
total_jobs = len(jobs_df)

if total_jobs == 0:
    st.info("No jobs found for the selected filters. Try scraping first or widening the date range.")
    st.stop()

skills_df = load_skills(jobs_df["id"].tolist())

# Apply category filter
if selected_categories:
    skills_df = skills_df[skills_df["category"].isin(selected_categories)]

# ── Metrics ───────────────────────────────────────────────────────────────────
m1, m2, m3 = st.columns(3)
m1.metric("Jobs in view", total_jobs)
m2.metric("Unique companies", jobs_df["company"].nunique())
m3.metric("Unique skills found", skills_df["skill_name"].nunique() if not skills_df.empty else 0)

st.divider()

# ── Skill frequency chart ─────────────────────────────────────────────────────
if skills_df.empty:
    st.info("No skills extracted yet. Run a scrape first.")
else:
    freq = (
        skills_df.groupby(["skill_name", "category"])["job_id"]
        .nunique()
        .reset_index()
        .rename(columns={"job_id": "job_count"})
    )
    freq["pct"] = (freq["job_count"] / total_jobs * 100).round(1)
    freq = freq.sort_values("job_count", ascending=False)

    top20 = freq.head(20).sort_values("job_count", ascending=True)  # ascending for horizontal bar

    fig = px.bar(
        top20,
        x="job_count",
        y="skill_name",
        color="category",
        orientation="h",
        labels={"job_count": "Number of listings", "skill_name": "Skill", "category": "Category"},
        title=f"Top {len(top20)} Skills (out of {total_jobs} listings)",
        hover_data={"pct": True},
    )
    fig.update_layout(
        height=520,
        yaxis_title=None,
        legend_title="Category",
        margin=dict(l=0, r=20, t=40, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Full data table ───────────────────────────────────────────────────────
    st.subheader("All skills")
    display_df = freq[["skill_name", "category", "job_count", "pct"]].copy()
    display_df.columns = ["Skill", "Category", "# Listings", "% of Listings"]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "% of Listings": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    csv = display_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Download as CSV", csv, "skills.csv", "text/csv")

    st.divider()

    # ── Skill drill-down ──────────────────────────────────────────────────────
    st.subheader("Drill-down: jobs mentioning a skill")
    skill_options = freq["skill_name"].tolist()
    selected_skill = st.selectbox("Select a skill", options=skill_options)

    if selected_skill:
        matching_job_ids = skills_df[skills_df["skill_name"] == selected_skill]["job_id"].tolist()
        matching_jobs = jobs_df[jobs_df["id"].isin(matching_job_ids)][
            ["title", "company", "site", "url", "scraped_at"]
        ].copy()
        matching_jobs["scraped_at"] = matching_jobs["scraped_at"].dt.strftime("%Y-%m-%d")
        matching_jobs.columns = ["Title", "Company", "Site", "URL", "Scraped"]

        st.caption(f"{len(matching_jobs)} listing(s) mention **{selected_skill}**")
        st.dataframe(
            matching_jobs,
            use_container_width=True,
            hide_index=True,
            column_config={
                "URL": st.column_config.LinkColumn("URL"),
            },
        )
