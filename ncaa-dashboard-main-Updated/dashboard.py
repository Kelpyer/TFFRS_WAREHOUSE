import streamlit as st
from scraper import scrape_tfrrs_results, scrape_team_results
from data_cleaning import clean_tfrrs_data
from visualizations import plot_time_progression, plot_placement_distribution

st.set_page_config(page_title="NCAA Athlete Dashboard", page_icon="🏃", layout="wide")

st.title("NCAA Athlete Dashboard")

# ── Mode selector ────────────────────────────────────────────────────────────
mode = st.radio("Select mode:", ["Single Athlete", "Full Team"], horizontal=True)
st.divider()


# ── Shared cache + helpers ───────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_athlete_data(url):
    df_scraped = scrape_tfrrs_results(url, wait_time=15)
    return clean_tfrrs_data(df_scraped)


@st.cache_data(show_spinner=False)
def get_team_data(url):
    # progress_callback not used inside cache — handled outside
    df_scraped = scrape_team_results(url, wait_time_team=10, wait_time_athlete=15)
    return clean_tfrrs_data(df_scraped)


def show_results_ui(df_cleaned, csv_filename="results.csv"):
    """Shared UI block: preview table, CSV download, and graph buttons."""

    # ── Data preview ─────────────────────────────────────────────────────────
    st.subheader("Meet Results Preview")
    base_cols = ['Meet_Info', 'Event', 'Event_Type', 'Race_Date',
                 'Mark', 'Time_seconds', 'Mark_meters', 'Placement_Number', 'Round']
    # Include athlete name col if present (team mode)
    display_cols = ([c for c in ['Athlete_Name', 'Athlete_Year'] if c in df_cleaned.columns]
                    + base_cols)
    st.dataframe(df_cleaned[display_cols])

    # ── CSV download ─────────────────────────────────────────────────────────
    st.subheader("Download Results")
    csv = df_cleaned[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download as CSV",
        data=csv,
        file_name=csv_filename,
        mime="text/csv",
    )

    # ── Graphs ───────────────────────────────────────────────────────────────
    st.subheader("Graphs")

    # Optionally filter by athlete in team mode
    if "Athlete_Name" in df_cleaned.columns:
        athletes = ["All Athletes"] + sorted(df_cleaned["Athlete_Name"].unique().tolist())
        selected_athlete = st.selectbox("Filter graphs by athlete:", athletes)
        df_plot = (df_cleaned if selected_athlete == "All Athletes"
                   else df_cleaned[df_cleaned["Athlete_Name"] == selected_athlete])
    else:
        df_plot = df_cleaned

    unique_events = df_plot["Event"].unique().tolist()
    event_filter = st.selectbox("Select event:", unique_events)

    event_rows = df_plot[df_plot["Event"] == event_filter]
    selected_event_type = (event_rows["Event_Type"].iloc[0]
                           if len(event_rows) > 0 else "Track")

    graph_label = ("📈 Show Distance Progression Graph"
                   if selected_event_type == "Field"
                   else "📈 Show Time Progression Graph")

    if st.button(graph_label):
        fig = plot_time_progression(df_plot, event_filter)
        st.pyplot(fig)

    if st.button("📊 Show Placement Distribution Graph"):
        fig = plot_placement_distribution(df_plot)
        st.pyplot(fig)


# ── Single Athlete mode ──────────────────────────────────────────────────────
if mode == "Single Athlete":
    st.subheader("Enter Athlete TFRRS URL")
    st.caption("Example: https://www.tfrrs.org/athletes/8005941/Akron/Lane_Graham")
    url = st.text_input("Paste TFRRS Athlete Profile URL below:", key="athlete_url")

    if url:
        with st.spinner("Scraping athlete data..."):
            df_cleaned = get_athlete_data(url)
        show_results_ui(df_cleaned, csv_filename="athlete_results.csv")


# ── Full Team mode ───────────────────────────────────────────────────────────
else:
    st.subheader("Enter Team TFRRS URL")
    st.caption(
        "Example: https://www.tfrrs.org/teams/tf/OH_college_m_Akron.html\n\n"
        "**Tip:** Find your team URL by going to tfrrs.org → TEAMS, searching for "
        "your school, and copying the URL from the browser."
    )
    team_url = st.text_input("Paste TFRRS Team Page URL below:", key="team_url")

    st.info(
        "⏱️ Scraping a full roster takes a while — typically **1–3 minutes per athlete**. "
        "Results are cached so re-running is instant."
    )

    if team_url:
        # Show a live progress bar while scraping (only on first run; cached after)
        progress_bar = st.progress(0, text="Starting...")
        status_text = st.empty()

        def update_progress(current, total, name):
            pct = int((current / total) * 100) if total > 0 else 0
            progress_bar.progress(pct, text=f"Scraping athlete {current}/{total}: {name}")
            status_text.text(f"Last scraped: {name}")

        with st.spinner("Loading roster and scraping all athletes..."):
            # Can't pass callback into cached function directly, so call uncached
            # version on first load, then cache kicks in on re-runs.
            cache_key = team_url
            if cache_key not in st.session_state:
                df_raw = scrape_team_results(
                    team_url,
                    wait_time_team=10,
                    wait_time_athlete=15,
                    progress_callback=update_progress,
                )
                df_cleaned = clean_tfrrs_data(df_raw)
                st.session_state[cache_key] = df_cleaned
            else:
                df_cleaned = st.session_state[cache_key]

        progress_bar.empty()
        status_text.empty()

        athlete_count = (df_cleaned["Athlete_Name"].nunique()
                         if "Athlete_Name" in df_cleaned.columns else "?")
        st.success(f"✅ Scraped {len(df_cleaned)} results across {athlete_count} athletes.")

        show_results_ui(df_cleaned, csv_filename="team_results.csv")
