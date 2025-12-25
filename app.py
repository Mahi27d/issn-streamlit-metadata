import streamlit as st
import csv
import requests
import time
import os

# ================= CONFIG =================
ROWS_PER_ISSN = 50               # safe for Streamlit Cloud
MAX_ROWS_PER_FILE = 200_000      # browser + Power BI friendly
SLEEP = 1
HEADERS = {"User-Agent": "ISSN-Streamlit-GitHub/1.0"}

# ================= UI =================
st.set_page_config(page_title="ISSN Metadata Extractor", layout="wide")

st.title("ISSN Article Metadata Extractor")
st.write("Upload ISSN list and extract **year-wise, month-wise article metadata** (Crossref).")

year = st.number_input(
    "Select Publication Year",
    min_value=1900,
    max_value=2100,
    value=2025
)

uploaded_file = st.file_uploader(
    "Upload ISSN CSV file (must contain an ISSN column)",
    type=["csv"]
)

run = st.button("Run Extraction")

# ================= FUNCTIONS =================
def fetch_articles(issn, year, month):
    url = "https://api.crossref.org/works"
    params = {
        "filter": f"issn:{issn},from-pub-date:{year}-{month:02d}-01,until-pub-date:{year}-{month:02d}-31",
        "rows": ROWS_PER_ISSN
    }
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()["message"]["items"]
    except:
        pass
    return []

# ================= MAIN =================
if run:

    # ---------- VALIDATE FILE ----------
    if not uploaded_file:
        st.error("Please upload a CSV file.")
        st.stop()

    reader = csv.DictReader(
        uploaded_file.getvalue().decode("utf-8", errors="ignore").splitlines()
    )

    # Normalize column names
    if not reader.fieldnames:
        st.error("CSV file has no header row.")
        st.stop()

    normalized_headers = [h.strip().lower() for h in reader.fieldnames]

    if "issn" not in normalized_headers:
        st.error("CSV must contain a column named 'issn' (any case allowed).")
        st.stop()

    issn_index = normalized_headers.index("issn")

    # ---------- LOAD ISSNS ----------
    issns = []
    for row in reader:
        value = list(row.values())[issn_index]
        if value:
            issns.append(value.strip())

    if not issns:
        st.error("No ISSNs found in the uploaded file.")
        st.stop()

    st.success(f"Loaded {len(issns)} ISSNs")

    # ---------- OUTPUT SETUP ----------
    os.makedirs("output", exist_ok=True)

    progress = st.progress(0)
    total_steps = len(issns) * 12
    completed = 0

    generated_files = []

    # ---------- PROCESS MONTHS ----------
    for month in range(1, 13):
        month_str = f"{year}-{month:02d}"
        st.write(f"Processing {month_str}")

        part = 1
        rows_written = 0

        def open_new_file(part):
            filename = f"output/issn_articles_{month_str}_part{part}.csv"
            f = open(filename, "w", newline="", encoding="utf-8")
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Year",
                    "Month",
                    "ISSN",
                    "DOI",
                    "Article Title",
                    "Volume",
                    "Issue",
                    "Page",
                    "Journal Title",
                    "Publisher"
                ]
            )
            writer.writeheader()
            return f, writer, filename

        file, writer, current_file = open_new_file(part)
        generated_files.append(current_file)

        for issn in issns:
            articles = fetch_articles(issn, year, month)

            for art in articles:
                if rows_written >= MAX_ROWS_PER_FILE:
                    file.close()
                    part += 1
                    rows_written = 0
                    file, writer, current_file = open_new_file(part)
                    generated_files.append(current_file)

                writer.writerow({
                    "Year": year,
                    "Month": month_str,
                    "ISSN": issn,
                    "DOI": art.get("DOI"),
                    "Article Title": art.get("title", [""])[0],
                    "Volume": art.get("volume"),
                    "Issue": art.get("issue"),
                    "Page": art.get("page"),
                    "Journal Title": art.get("container-title", [""])[0],
                    "Publisher": art.get("publisher")
                })

                rows_written += 1

            time.sleep(SLEEP)
            completed += 1
            progress.progress(min(completed / total_steps, 1.0))

        file.close()

    # ---------- DOWNLOAD ----------
    st.success("Extraction completed successfully!")

    st.subheader("Download CSV files (Power BI ready)")
    for path in generated_files:
        with open(path, "rb") as f:
            st.download_button(
                label=f"Download {os.path.basename(path)}",
                data=f,
                file_name=os.path.basename(path),
                mime="text/csv"
            )
