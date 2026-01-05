import pandas as pd
import streamlit as st
import plotly.express as px
import os
import re
from io import BytesIO

# --- 1. CONFIGURATION & SETUP ---
st.set_page_config(
    page_title="KZN Ops Command Center",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CUSTOM CSS (The "Neon/Dark" Dashboard Look) ---
def inject_custom_css():
    st.markdown("""
        <style>
        /* Main Background */
        .stApp {
            background-color: #0e1117;
        }
        
        /* Container/Div Styling with Neon Glow */
        div[data-testid="stMetric"], div[data-testid="stDataFrame"], .stPlotlyChart {
            background-color: #1a1c24;
            border: 1px solid #30333d;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 0 5px rgba(0, 200, 255, 0.1); /* Subtle Blue Neon Glow */
            transition: box-shadow 0.3s ease-in-out;
        }
        
        div[data-testid="stMetric"]:hover, .stPlotlyChart:hover {
            border: 1px solid #00c8ff;
            box_shadow: 0 0 15px rgba(0, 200, 255, 0.3);
        }

        /* Titles */
        h1, h2, h3 {
            color: #ffffff !important;
            font-family: 'Segoe UI', sans-serif;
        }
        
        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background-color: #11141d;
            border-right: 1px solid #30333d;
        }
        </style>
        """, unsafe_allow_html=True)

inject_custom_css()

# --- 3. INTELLIGENT DATA ENGINE ---
@st.cache_data(ttl=600)
def load_and_process_data(file_input, region_code="KZN"):
    """
    Accepts either a File Path (string) or an UploadedFile object (BytesIO).
    Returns (DataFrame, ErrorMessage).
    """
    if file_input is None:
        return None, "No file loaded."

    try:
        # A. LOAD SHEETS
        # check if it's a file path (string) or uploaded object
        # pandas read_excel handles both smoothly
        df_ops = pd.read_excel(file_input, sheet_name="AnalysisSheet", engine="openpyxl", dtype={'Year Week': str})
        
        # Dynamic Sheet Loading
        sonar_sheet = f"Sonar_{region_code}"
        try:
            df_sonar = pd.read_excel(file_input, sheet_name=sonar_sheet, engine="openpyxl")
        except:
            # Smart Fallback: Try to find ANY sheet with 'Sonar' in the name
            xl = pd.ExcelFile(file_input, engine='openpyxl')
            sonar_sheets = [s for s in xl.sheet_names if "Sonar" in s]
            if sonar_sheets:
                df_sonar = pd.read_excel(file_input, sheet_name=sonar_sheets[0], engine="openpyxl")
            else:
                # If absolute failure, create a dummy dataframe so the app doesn't crash
                df_sonar = pd.DataFrame(columns=['Site', 'Latitude', 'Longitude', 'County'])

        # B. NORMALIZE & JOIN KEYS (Fuzzy Logic)
        def normalize_key(s):
            if pd.isna(s): return ""
            s = str(s).lower()
            s = re.sub(r'kzn_\d+', '', s) 
            s = re.sub(r'[^a-z0-9]', '', s)
            return s.strip()

        df_ops['join_key'] = df_ops['Site'].apply(normalize_key)
        
        # Find the join key in Sonar (could be SiteName or Site)
        if 'SiteName' in df_sonar.columns:
            df_sonar['join_key'] = df_sonar['SiteName'].apply(normalize_key)
        elif 'Site' in df_sonar.columns:
            df_sonar['join_key'] = df_sonar['Site'].apply(normalize_key)
        else:
            df_sonar['join_key'] = "" # Fail safe

        df_sonar_clean = df_sonar.drop_duplicates(subset=['join_key'])

        # C. MERGE
        useful_sonar_cols = [
            'join_key', 'Latitude', 'Longitude', 'DISTRICT_COUNCIL', 
            'MUNICIPAL_DISTRICT', 'County', 'Technology', 'SiteOwner', 
            'GreenZone', 'Modernisation (1800/21)'
        ]
        existing_cols = [c for c in useful_sonar_cols if c in df_sonar_clean.columns]
        
        df_master = pd.merge(df_ops, df_sonar_clean[existing_cols], on='join_key', how='left')

        # D. CALCULATE STRATEGY METRICS
        for col in ['MTTR (Hours)', 'MTTR Target', 'Site Rank']:
            if col in df_master.columns:
                df_master[col] = pd.to_numeric(
                    df_master[col].astype(str).str.replace(',', '.'), 
                    errors='coerce'
                ).fillna(0)

        df_master['Variance'] = df_master['MTTR (Hours)'] - df_master['MTTR Target']
        freq_map = df_master['join_key'].value_counts()
        df_master['Frequency'] = df_master['join_key'].map(freq_map)
        
        safe_rank = df_master['Site Rank'].replace(0, 10000)
        df_master['Risk_Score'] = (df_master['Frequency'] * (1 / safe_rank)) * 100

        if "IN or OUT SLA" in df_master.columns:
            df_master["IN or OUT SLA"] = df_master["IN or OUT SLA"].astype(str).str.strip().str.upper()

        return df_master, None

    except Exception as e:
        return None, str(e)

# --- 4. HELPER FUNCTIONS ---
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Ops_Report')
    return output.getvalue()

def is_critical_incident(summary):
    if pd.isna(summary): return False
    tokens = {"out_of_service", "link_failure", "site_oos", "sites_down", "faulty", "down"}
    s = str(summary).lower()
    return any(t in s for t in tokens)

def render_empty_state(message="Awaiting Data Load..."):
    """Standardized empty state message"""
    st.info(f"📋 {message}")

# --- 5. PAGE RENDERERS (STRUCTURE FIRST, DATA SECOND) ---

def render_operations_page(df):
    """PAGE 1: Operations"""
    st.subheader("🚨 Incident Operations")
    
    # 1. KPI SECTION (Always render columns)
    k1, k2, k3, k4 = st.columns(4)
    
    if df is not None and not df.empty:
        # Populate Data
        p4_count = len(df[df['Incident MSDP Priority'] == 'P4']) if 'Incident MSDP Priority' in df.columns else 0
        sla_fail = (df['IN or OUT SLA'] == 'OUT').mean() if 'IN or OUT SLA' in df.columns else 0
        
        k1.metric("Total Incidents", len(df))
        k2.metric("P4 Critical", p4_count)
        k3.metric("SLA Failure Rate", f"{sla_fail:.1%}", delta_color="inverse")
        k4.metric("Avg MTTR", f"{df['MTTR (Hours)'].mean():.2f}h")
    else:
        # Skeleton State
        k1.metric("Total Incidents", "-", "No Data")
        k2.metric("P4 Critical", "-", "No Data")
        k3.metric("SLA Failure Rate", "-", "No Data")
        k4.metric("Avg MTTR", "-", "No Data")

    st.divider()

    # 2. ANALYSIS SECTION (Always render columns)
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("#### 📉 Top Repeat Offenders")
        if df is not None and not df.empty:
            crit_df = df[df['Summary'].apply(is_critical_incident)]
            if not crit_df.empty:
                top_sites = crit_df['Site'].value_counts().head(15).reset_index()
                top_sites.columns = ['Site', 'Count']
                fig = px.bar(top_sites, x='Count', y='Site', orientation='h', 
                             color='Count', color_continuous_scale='Reds', template="plotly_dark")
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                render_empty_state("No Critical Incidents found in Summary text.")
        else:
            render_empty_state("Waiting for Data Upload to show Top Sites...")

    with c2:
        st.markdown("#### 🕸️ Root Cause Hierarchy")
        if df is not None and not df.empty and {'Cause', 'Cause Tier 2'}.issubset(df.columns):
            sun_df = df.dropna(subset=['Cause', 'Cause Tier 2'])
            fig = px.sunburst(sun_df, path=['Cause', 'Cause Tier 2'], values='MTTR (Hours)', 
                              color='IN or OUT SLA', color_discrete_map={'IN':'#00CC96', 'OUT':'#EF553B'})
            fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_empty_state("Waiting for Data Upload to show Root Cause...")


def render_strategy_page(df):
    """PAGE 2: Strategy"""
    st.subheader("🎯 Strategic Prioritization")
    
    k1, k2, k3 = st.columns(3)
    
    if df is not None and not df.empty:
        prob_children = df[df['Variance'] > 0]
        k1.metric("Problem Children", len(prob_children), "Over Target")
        k2.metric("Avg Variance", f"{df['Variance'].mean():.2f}h")
        k3.metric("Max Risk Score", f"{df['Risk_Score'].max():.2f}")
    else:
        k1.metric("Problem Children", "-", "No Data")
        k2.metric("Avg Variance", "-", "No Data")
        k3.metric("Max Risk Score", "-", "No Data")

    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### ⚠️ Risk Matrix (Rank vs Frequency)")
        if df is not None and not df.empty:
            fig = px.scatter(
                df, x="Site Rank", y="Frequency", color="Risk_Score", 
                size="MTTR (Hours)", hover_name="Site",
                color_continuous_scale="Turbo", size_max=20, template="plotly_dark"
            )
            fig.update_xaxes(autorange="reversed")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_empty_state("Chart awaiting data...")

    with c2:
        st.markdown("#### 📊 Variance Distribution")
        if df is not None and not df.empty:
            fig = px.histogram(df, x="Variance", color="IN or OUT SLA", nbins=30, template="plotly_dark")
            fig.add_vline(x=0, line_dash="dash", line_color="white")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_empty_state("Chart awaiting data...")

    st.divider()
    st.subheader("📋 Engineering Hit List")
    if df is not None and not df.empty:
        report_cols = ['Site', 'Site Rank', 'Frequency', 'MTTR (Hours)', 'Variance', 'Risk_Score', 'County']
        final_cols = [c for c in report_cols if c in df.columns]
        hit_list = df[final_cols].sort_values('Risk_Score', ascending=False).drop_duplicates()
        
        st.dataframe(hit_list.head(50), use_container_width=True)
        
        st.download_button(
            label="📥 Download Priority Report",
            data=convert_df_to_excel(hit_list),
            file_name="KZN_Priority_Report.xlsx"
        )
    else:
        render_empty_state("Data table will appear here.")


def render_intelligence_page(df):
    """PAGE 3: Intelligence"""
    st.subheader("🌍 Network Intelligence (Sonar)")

    if df is not None and not df.empty:
        map_df = df.dropna(subset=['Latitude', 'Longitude'])
        if not map_df.empty:
            st.markdown("#### 📍 Regional Heatmap")
            
            # --- HIGH CONTRAST MAP LOGIC ---
            # Using carto-darkmatter makes the background black, 
            # so we need bright colors for the dots (Turbo or Plasma)
            
            fig = px.scatter_mapbox(
                map_df, lat="Latitude", lon="Longitude", 
                color="Risk_Score", size="Frequency",
                hover_name="Site", 
                color_continuous_scale="Portland", # Bright colors (Red/Yellow/Blue)
                size_max=15, zoom=6,
                mapbox_style="carto-darkmatter", # Dark background for contrast
                height=600
            )
            fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Data loaded, but no Latitude/Longitude found. Check Sonar Sheet.")
    else:
        # Show empty map container
        st.markdown("#### 📍 Regional Heatmap")
        st.info("Map disabled: No data loaded.")

# --- 6. MAIN CONTROLLER ---

def main():
    # A. SIDEBAR HEADER
    st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/c2/Vodacom_Logo.svg/1200px-Vodacom_Logo.svg.png", width=150)
    st.sidebar.title("Ops Command")
    
    # B. FILE UPLOAD & CONFIG
    st.sidebar.subheader("📂 Data Source")
    
    # Region Selection (Needed for Sonar sheet logic)
    region = st.sidebar.selectbox("Region", ["KZN", "WES", "CEN", "EAS", "LIM", "MPU"], index=0)
    
    # 1. Dynamic File Uploader
    uploaded_file = st.sidebar.file_uploader("Upload Report (.xlsx)", type=['xlsx'])
    
    # 2. Fallback to Local File if no upload
    default_path = "data/KZN Repeat Outage 2.xlsx"
    
    # Determine which source to use
    if uploaded_file is not None:
        data_source = uploaded_file
        source_type = "Upload"
    elif os.path.exists(default_path):
        data_source = default_path
        source_type = "Local"
    else:
        data_source = None
        source_type = "None"

    # C. LOAD DATA (If source exists)
    df_master = None
    if data_source:
        with st.spinner(f"Processing {source_type} Data..."):
            df_master, error = load_and_process_data(data_source, region)
            if error:
                st.sidebar.error(f"Error: {error}")

    # D. DYNAMIC SIDEBAR FILTERS (Only if data loaded)
    if df_master is not None and not df_master.empty:
        st.sidebar.divider()
        st.sidebar.subheader("🔍 Filters")
        
        # 1. COUNTY FILTER (Requested)
        if 'County' in df_master.columns:
            # Handle NaN values safely
            counties = sorted(df_master['County'].dropna().astype(str).unique())
            sel_county = st.sidebar.multiselect("County", counties)
            if sel_county:
                df_master = df_master[df_master['County'].isin(sel_county)]

        # 2. WEEK FILTER
        if 'Year Week' in df_master.columns:
            weeks = sorted(df_master['Year Week'].dropna().unique())
            # Default to all, or last 4 weeks? Let's leave empty implies all
            sel_weeks = st.sidebar.multiselect("Year Week", weeks)
            if sel_weeks:
                df_master = df_master[df_master['Year Week'].isin(sel_weeks)]

        st.sidebar.success(f"Active Records: {len(df_master)}")
    else:
        st.sidebar.warning("No Data Active")

    # E. NAVIGATION & ROUTING
    st.sidebar.divider()
    page = st.sidebar.radio("Navigation", ["Operations", "Strategy", "Intelligence"])

    if page == "Operations":
        render_operations_page(df_master)
    elif page == "Strategy":
        render_strategy_page(df_master)
    elif page == "Intelligence":
        render_intelligence_page(df_master)

if __name__ == "__main__":
    main()