import streamlit as st
import csv
import requests
import time
import os
from datetime import date

# ================= CONFIG =================
ROWS_PER_ISSN = 50               # Safe for Streamlit Cloud
MAX_ROWS_PER_FILE = 200_000      # Power BI friendly
SLEEP = 1
HEADERS = {"User-Agent": "ISSN-DateRange-Extractor/1.0"}

# ================= UI =================
st.set_page_config(page_title="ISSN Metadata Extractor", layout="wide")

st.title("ISSN Article Metadata Extractor (Crossref)")
st.write(
    "Use this app to **test with manual ISSNs** or **run using CSV upload**. "
    "You can also use **both together**."
)

# ---- Date range ----
col1, col2 = st.columns(2)
with col1:
    from_date = st.date_input("From publication date", value=date(2025, 1, 1))
with col2:
    to_date = st.date_input("To publication date", value=date(2025, 12, 31))

# ---- Manual ISSN input ----
st.subheader("Option 1: Enter ISSNs manually (for testing)")
manual_issns = st.text_area(
    "Enter ISSNs (comma or new-line separated)",
    placeholder="1234-5678\n2345-6789"
)

# ---- CSV upload ----
st.subheader("Option 2: Upload ISSN CSV")
uploaded_file = st.file_uploader(
    "Upload CSV (column name can be ISSN / issn / Issn)",
    type=["csv"]
)

run = st.button("Run Extraction")

# ================= FUNCTIONS =================
def fetch_articles(issn, from_date, to_date):
    url = "https://api.crossref.org/works"
    params = {
        "filter": (
            f"issn:{issn},"
            f"from-pub-date:{from_date},"
            f"until-pub-date:{to_date}"
        ),
        "rows": ROWS_PER_ISSN
    }
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()["message"]["items"]
    except:
        pass
    return []

def normalize_issn_list(raw_list):
    clean = []
    for i in raw_list:
        if i:
            clean.append(i.strip())
    return list(set(clean))  # remove duplicates

# ================= MAIN =================
if run:

    if from_date > to_date:
        st.error("From date must be earlier than To date.")
        st.stop()

    issns = []

    # ---- Manual ISSNs ----
    if manual_issns.strip():
        manual_list = manual_issns.replace(",", "\n").splitlines()
        issns.extend(manual_list)

    # ---- CSV ISSNs ----
    if uploaded_file:
        reader = csv.DictReader(
            uploaded_file.getvalue().decode("utf-8", errors="ignore").splitlines()
        )

        if not reader.fieldnames:
            st.error("Uploaded CSV has no header row.")
            st.stop()

        headers = [h.strip().lower() for h in reader.fieldnames]

        if "issn" not in headers:
            st.error("CSV must contain a column named 'issn'.")
            st.stop()

        issn_index = headers.index("issn")

        for row in reader:
            value = list(row.values())[issn_index]
            if value:
                issns.append(value)

    # ---- Final validation ----
    issns = normalize_issn_list(issns)

    if not issns:
        st.error("Please enter ISSNs manually or upload a CSV.")
        st.stop()

    st.success(f"Total ISSNs to process: {len(issns)}")

    # ---- Output setup ----
    os.makedirs("output", exist_ok=True)

    progress = st.progress(0)
    total = len(issns)
    done = 0

    file_part = 1
    rows_written = 0
    generated_files = []

    def open_new_file(part):
        filename = f"output/issn_articles_{from_date}_to_{to_date}_part{part}.csv"
        f = open(filename, "w", newline="", encoding="utf-8")
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ISSN",
                "DOI",
                "Article Title",
                "Volume",
                "Issue",
                "Page",
                "Journal Title",
                "Publisher",
                "From Date",
                "To Date"
            ]
        )
        writer.writeheader()
        return f, writer, filename

    file, writer, current_file = open_new_file(file_part)
    generated_files.append(current_file)

    # ---- Processing ----
    for issn in issns:
        articles = fetch_articles(issn, from_date, to_date)

        for art in articles:
            if rows_written >= MAX_ROWS_PER_FILE:
                file.close()
                file_part += 1
                rows_written = 0
                file, writer, current_file = open_new_file(file_part)
                generated_files.append(current_file)

            writer.writerow({
                "ISSN": issn,
                "DOI": art.get("DOI"),
                "Article Title": art.get("title", [""])[0],
                "Volume": art.get("volume"),
                "Issue": art.get("issue"),
                "Page": art.get("page"),
                "Journal Title": art.get("container-title", [""])[0],
                "Publisher": art.get("publisher"),
                "From Date": str(from_date),
                "To Date": str(to_date)
            })

            rows_written += 1

        time.sleep(SLEEP)
        done += 1
        progress.progress(min(done / total, 1.0))

    file.close()

    # ---- Download ----
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
