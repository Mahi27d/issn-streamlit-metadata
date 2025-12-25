import streamlit as st
import pandas as pd
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
    "Upload **CSV / Excel / TXT** or manually enter ISSNs. "
    "Extract article metadata from Crossref for a selected date range."
)

# ---- Date range ----
col1, col2 = st.columns(2)
with col1:
    from_date = st.date_input("From publication date", value=date(2025, 1, 1))
with col2:
    to_date = st.date_input("To publication date", value=date(2025, 12, 31))

# ---- Manual ISSN input ----
st.subheader("Option 1: Enter ISSNs manually")
manual_issns = st.text_area(
    "Enter ISSNs (comma or new-line separated)",
    placeholder="1234-5678\n2345-6789"
)

# ---- File upload ----
st.subheader("Option 2: Upload ISSN file")
uploaded_file = st.file_uploader(
    "Supported files: CSV, Excel (.xlsx), TXT",
    type=["csv", "xlsx", "txt"]
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

def normalize_issns(issns):
    clean = []
    for i in issns:
        if i:
            clean.append(i.strip())
    return sorted(set(clean))  # remove duplicates

def extract_issns_from_file(file):
    issns = []
    file_name = file.name.lower()

    if file_name.endswith(".csv"):
        df = pd.read_csv(file)
        for col in df.columns:
            if "issn" in col.lower():
                issns.extend(df[col].astype(str).tolist())
                break

    elif file_name.endswith(".xlsx"):
        df = pd.read_excel(file)
        for col in df.columns:
            if "issn" in col.lower():
                issns.extend(df[col].astype(str).tolist())
                break

    elif file_name.endswith(".txt"):
        content = file.getvalue().decode("utf-8", errors="ignore")
        issns.extend(content.splitlines())

    return issns

# ================= MAIN =================
if run:

    # ---- Validation ----
    if from_date > to_date:
        st.error("From date must be earlier than To date.")
        st.stop()

    issns = []

    # ---- Manual ----
    if manual_issns.strip():
        issns.extend(manual_issns.replace(",", "\n").splitlines())

    # ---- File ----
    if uploaded_file:
        issns.extend(extract_issns_from_file(uploaded_file))

    issns = normalize_issns(issns)

    if not issns:
        st.error("No ISSNs found. Please enter ISSNs or upload a valid file.")
        st.stop()

    st.success(f"Total ISSNs to process: {len(issns)}")

    # ---- Output setup ----
    os.makedirs("output", exist_ok=True)

    progress = st.progress(0)
    total = len(issns)
    completed = 0

    file_part = 1
    rows_written = 0
    generated_files = []

    def open_new_file(part):
        filename = f"output/issn_articles_{from_date}_to_{to_date}_part{part}.csv"
        f = open(filename, "w", newline="", encoding="utf-8")
        writer = pd.DataFrame(columns=[
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
        ])
        return f, writer, filename

    current_file, buffer_df, current_path = open_new_file(file_part)
    generated_files.append(current_path)

    # ---- Processing ----
    for issn in issns:
        articles = fetch_articles(issn, from_date, to_date)

        for art in articles:
            buffer_df.loc[len(buffer_df)] = [
                issn,
                art.get("DOI"),
                art.get("title", [""])[0],
                art.get("volume"),
                art.get("issue"),
                art.get("page"),
                art.get("container-title", [""])[0],
                art.get("publisher"),
                str(from_date),
                str(to_date)
            ]

            rows_written += 1

            if rows_written >= MAX_ROWS_PER_FILE:
                buffer_df.to_csv(current_file, index=False)
                current_file.close()

                file_part += 1
                rows_written = 0
                current_file, buffer_df, current_path = open_new_file(file_part)
                generated_files.append(current_path)

        time.sleep(SLEEP)
        completed += 1
        progress.progress(min(completed / total, 1.0))

    buffer_df.to_csv(current_file, index=False)
    current_file.close()

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
