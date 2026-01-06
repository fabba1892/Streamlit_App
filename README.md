---

# 📡 Ops Command Center: Telecom Intelligence Engine

A modular, scalable **Streamlit Architect** solution designed for Telecommunications Operators to triage network incidents, prioritize engineering resources, and visualize regional performance via Geospatial Intelligence.

## 🚀 Quick Start
1. **Clone the Repo:**
   ```bash
   git clone https://github.com/fabba1892/Streamlit_App.py
   cd your-folder
   ```
2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the App:**
   ```bash
   streamlit run main.py
   ```

---

## 🛠 Project Architecture

### 1. Data Engine (The "Smart" Kernel)
The app uses a **Vectorized String Normalization** engine to join Operational Incident data with Regional Metadata (Sonar). 
- **Fuzzy Logic:** Automatically strips prefixes (e.g., `KZN_`) and special characters to ensure high match rates between messy Excel sheets.
- **Dynamic Schema:** Adapts to column name shifts (e.g., looks for "Lat" or "Latitude" automatically).

### 2. The 3-Page Framework
*   **🚨 Incident Operations:** Real-time triage. Focused on SLA compliance, P4 criticals, and Root Cause Sunburst charts.
*   **🎯 Strategic Prioritization:** Uses a weighted **Risk Score Formula**: 
    $$\text{Risk Score} = \text{Frequency} \times \left( \frac{1}{\text{Site Rank}} \right) \times 100$$
    This identifies "Problem Children" (sites with high failure rates but high importance).
*   **🌍 Network Intelligence:** Geospatial heatmaps using `carto-darkmatter` for high-contrast visualization of site failures against technological layers (5G/LTE/Modernization).

### 3. UI/UX Design
- **Neon Dark Mode:** Custom CSS injection for a "Command Center" aesthetic.
- **Robust Fail-safes:** Skeleton UI renders even without data, providing a professional dashboard structure at all times.

---

## 📊 Data Requirements
To utilize the dashboard, upload an Excel file (`.xlsx`) containing:
1.  **Sheet: `AnalysisSheet`** 
    - Columns: `Site`, `Summary`, `MTTR (Hours)`, `Incident MSDP Priority`, `Year Week`.
2.  **Sheet: `Sonar_{Region}`** (e.g., `Sonar_KZN`)
    - Columns: `Latitude`, `Longitude`, `County`, `Site Rank`, `Technology`.

---

## 🏗 Modular Roadmap
- [ ] **Multi-Region Support:** Already architected to handle WES, CEN, EAS, and more.
- [ ] **Automated Hit-Lists:** One-click Excel exports for engineering teams.
- [ ] **Predictive Analytics:** Integrating failure trend forecasting.

---

### What you should add to your GitHub Repo for a complete professional look:

1.  **`requirements.txt`:** Create a file with these contents:
    ```text
    pandas
    streamlit
    plotly
    openpyxl
    ```
2.  **Screenshots Folder:** Create a `assets/` folder and add screenshots of your:
    *   Neon Dashboard Home.
    *   The Strategic Risk Matrix.
    *   The High-Contrast Heatmap.
3.  **Sample Data:** A folder named `data/` containing a *sanitized* (dummy) version of your Excel file so others can test the app immediately.
4.  **License:** A `LICENSE` file (usually MIT) to clarify how others can use your code.
5.  **`.gitignore`:** To prevent temporary python files or private data from being uploaded:
    ```text
    __pycache__/
    .streamlit/
    *.xlsx
    *.csv
    ```
