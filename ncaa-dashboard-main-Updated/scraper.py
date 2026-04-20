import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def _make_driver():
    """Create a headless Chrome driver."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )


# ---------------------------------------------------------------------------
# Single athlete scraper (unchanged logic, extracted to its own function)
# ---------------------------------------------------------------------------
def scrape_tfrrs_results(url, wait_time=15):
    """
    Scrapes meet results from a single TFRRS athlete profile page.
    Returns a DataFrame with columns: Meet_Info, Event, Mark, Place
    """
    driver = _make_driver()
    try:
        driver.get(url)
        time.sleep(wait_time)

        tables = driver.find_elements(By.TAG_NAME, "table")
        data = []

        for table_index in range(4, len(tables)):
            table = tables[table_index]
            text = table.text.strip().split("\n")
            if len(text) >= 2:
                meet_info = text[0]
                for line in text[1:]:
                    parts = line.split()
                    if len(parts) >= 2:
                        event = parts[0]
                        mark = parts[1]
                        place = " ".join(parts[2:]) if len(parts) > 2 else ""
                        data.append([meet_info, event, mark, place])

        return pd.DataFrame(data, columns=["Meet_Info", "Event", "Mark", "Place"])
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# Team roster scraper
# ---------------------------------------------------------------------------
def scrape_team_roster(team_url, wait_time=10):
    """
    Scrapes the roster from a TFRRS team page.

    The team page URL format is:
        https://www.tfrrs.org/teams/tf/STATE_college_gender_SchoolName.html
    e.g.: https://www.tfrrs.org/teams/tf/OH_college_m_Akron.html

    Returns a list of dicts: [{'name': ..., 'year': ..., 'url': ...}, ...]
    """
    driver = _make_driver()
    try:
        driver.get(team_url)
        time.sleep(wait_time)

        roster = []

        # The ROSTER table comes after the TOP MARKS table on the page.
        # Each row has: [Athlete Name (link)] [Year]
        # Athlete links look like /athletes/ID/School/Name.html
        tables = driver.find_elements(By.TAG_NAME, "table")

        for table in tables:
            rows = table.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) == 2:
                    link_tag = cells[0].find_elements(By.TAG_NAME, "a")
                    if link_tag:
                        href = link_tag[0].get_attribute("href")
                        # Filter to athlete profile links only
                        if href and "/athletes/" in href:
                            name = link_tag[0].text.strip()
                            year = cells[1].text.strip()
                            # Normalize URL: strip trailing .html if present,
                            # TFRRS athlete pages work with or without it
                            athlete_url = href.rstrip("/")
                            if athlete_url.endswith(".html"):
                                athlete_url = athlete_url[:-5]
                            roster.append({
                                "name": name,
                                "year": year,
                                "url": athlete_url,
                            })

        return roster
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# Team-wide scraper: roster → each athlete → combined DataFrame
# ---------------------------------------------------------------------------
def scrape_team_results(team_url, wait_time_team=10, wait_time_athlete=15,
                        progress_callback=None):
    """
    Scrapes all athlete results for an entire team.

    Steps:
      1. Load the team page and extract every athlete URL from the ROSTER table.
      2. Visit each athlete's profile page and scrape their results.
      3. Combine everything into one DataFrame, adding athlete name + year columns.

    Args:
        team_url:           Full URL of the TFRRS team page.
        wait_time_team:     Seconds to wait for the team page to load.
        wait_time_athlete:  Seconds to wait per athlete page.
        progress_callback:  Optional callable(current, total, athlete_name)
                            for progress reporting (e.g. Streamlit progress bar).

    Returns:
        DataFrame with columns:
            Athlete_Name, Athlete_Year, Meet_Info, Event, Mark, Place
    """
    # Step 1: get roster
    roster = scrape_team_roster(team_url, wait_time=wait_time_team)
    if not roster:
        return pd.DataFrame(
            columns=["Athlete_Name", "Athlete_Year", "Meet_Info", "Event", "Mark", "Place"]
        )

    all_results = []
    total = len(roster)

    # Step 2: scrape each athlete
    for i, athlete in enumerate(roster):
        if progress_callback:
            progress_callback(i, total, athlete["name"])

        try:
            df_athlete = scrape_tfrrs_results(
                athlete["url"], wait_time=wait_time_athlete
            )
            if not df_athlete.empty:
                df_athlete.insert(0, "Athlete_Year", athlete["year"])
                df_athlete.insert(0, "Athlete_Name", athlete["name"])
                all_results.append(df_athlete)
        except Exception as e:
            print(f"[WARN] Failed to scrape {athlete['name']}: {e}")

        # Brief pause between athletes to be polite to the server
        time.sleep(1)

    if progress_callback:
        progress_callback(total, total, "Done")

    # Step 3: combine
    if all_results:
        return pd.concat(all_results, ignore_index=True)
    else:
        return pd.DataFrame(
            columns=["Athlete_Name", "Athlete_Year", "Meet_Info", "Event", "Mark", "Place"]
        )
