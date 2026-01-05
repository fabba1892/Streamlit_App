Master code script below to use and base the ap off
🔽

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

# --- 2. CENTRALIZED DATA LOADING ENGINE ---
@st.cache_data(ttl=600)  # Auto-refresh every 10 minutes
def load_and_process_data(file_path, region_code="KZN"):
    """
    Loads Analysis and Sonar sheets, cleans strings, performs a vectorized join,
    and pre-calculates all strategic metrics (Variance, Risk Score).
    """
    if not os.path.exists(file_path):
        return None, f"File not found: {file_path}"

    try:
        # A. LOAD SHEETS
        # ---------------------------------------------------------
        df_ops = pd.read_excel(file_path, sheet_name="AnalysisSheet", engine="openpyxl", dtype={'Year Week': str})
        
        # Dynamic Sheet Loading based on Region (Future-Proofing)
        # For now, we default to 'Sonar_KZN', but logic allows 'Sonar_WES', etc.
        sonar_sheet = f"Sonar_{region_code}"
        try:
            df_sonar = pd.read_excel(file_path, sheet_name=sonar_sheet, engine="openpyxl")
        except:
            # Fallback if specific sheet name doesn't exist
            df_sonar = pd.read_excel(file_path, sheet_name="Sonar_KZN", engine="openpyxl")

        # B. NORMALIZE & JOIN KEYS (The "Fuzzy" Logic)
        # ---------------------------------------------------------
        def normalize_key(s):
            if pd.isna(s): return ""
            # Remove KZN_ prefix, special chars, whitespace, lower case
            s = str(s).lower()
            s = re.sub(r'kzn_\d+', '', s) 
            s = re.sub(r'[^a-z0-9]', '', s)
            return s.strip()

        df_ops['join_key'] = df_ops['Site'].apply(normalize_key)
        
        # Sonar usually has "KZN_1234 - SiteName", we clean that too
        if 'SiteName' in df_sonar.columns:
            df_sonar['join_key'] = df_sonar['SiteName'].apply(normalize_key)
        elif 'Site' in df_sonar.columns:
            df_sonar['join_key'] = df_sonar['Site'].apply(normalize_key)
        
        # Drop duplicates in Sonar to prevent row explosion
        df_sonar_clean = df_sonar.drop_duplicates(subset=['join_key'])

        # C. MERGE DATASETS
        # ---------------------------------------------------------
        # Select only useful columns from Sonar to keep memory usage low
        useful_sonar_cols = [
            'join_key', 'Latitude', 'Longitude', 'DISTRICT_COUNCIL', 
            'MUNICIPAL_DISTRICT', 'County', 'Technology', 'SiteOwner', 
            'GreenZone', 'Modernisation (1800/21)'
        ]
        # Only keep columns that actually exist in the file
        existing_cols = [c for c in useful_sonar_cols if c in df_sonar_clean.columns]
        
        df_master = pd.merge(df_ops, df_sonar_clean[existing_cols], on='join_key', how='left')

        # D. CALCULATE METRICS (Strategy Phase)
        # ---------------------------------------------------------
        # 1. MTTR Cleaning
        for col in ['MTTR (Hours)', 'MTTR Target', 'Site Rank']:
            if col in df_master.columns:
                df_master[col] = pd.to_numeric(
                    df_master[col].astype(str).str.replace(',', '.'), 
                    errors='coerce'
                ).fillna(0)

        # 2. Variance (Delta)
        df_master['Variance'] = df_master['MTTR (Hours)'] - df_master['MTTR Target']

        # 3. Frequency & Risk Score
        # Frequency = How many times this site appears in the filtered data
        freq_map = df_master['join_key'].value_counts()
        df_master['Frequency'] = df_master['join_key'].map(freq_map)

        # Risk Score = Freq * (1 / Rank). 
        # Handle Rank 0 or NaN to avoid division by zero errors.
        safe_rank = df_master['Site Rank'].replace(0, 10000)
        df_master['Risk_Score'] = (df_master['Frequency'] * (1 / safe_rank)) * 100

        # 4. Text Analysis Helper
        # Normalize 'IN or OUT SLA'
        if "IN or OUT SLA" in df_master.columns:
            df_master["IN or OUT SLA"] = df_master["IN or OUT SLA"].astype(str).str.strip().str.upper()

        return df_master, None

    except Exception as e:
        return None, str(e)

# --- 3. HELPER FUNCTIONS ---
def convert_df_to_excel(df):
    """Helper for the Download Button using BytesIO"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Ops_Report')
    return output.getvalue()

def is_critical_incident(summary):
    """Filter logic from Phase 1"""
    if pd.isna(summary): return False
    tokens = {"out_of_service", "link_failure", "site_oos", "sites_down", "faulty", "down"}
    s = str(summary).lower()
    return any(t in s for t in tokens)


# --- 4. PAGE RENDERERS ---

def render_operations_page(df):
    """PAGE 1: The 'What Happened' View (Original Pandas Logic)"""
    st.subheader("🚨 Incident Operations")
    
    # KPIS
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Incidents", len(df))
    
    p4_count = len(df[df['Incident MSDP Priority'] == 'P4']) if 'Incident MSDP Priority' in df.columns else 0
    k2.metric("P4 Critical Incidents", p4_count)
    
    sla_fail = (df['IN or OUT SLA'] == 'OUT').mean()
    k3.metric("SLA Failure Rate", f"{sla_fail:.1%}", delta_color="inverse")
    
    avg_mttr = df['MTTR (Hours)'].mean()
    k4.metric("Avg MTTR", f"{avg_mttr:.2f}h")

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 📉 Top 15 Repeat Offenders (Critical Summaries)")
        # Apply the summary text filter
        crit_df = df[df['Summary'].apply(is_critical_incident)]
        if not crit_df.empty:
            top_sites = crit_df['Site'].value_counts().head(15).reset_index()
            top_sites.columns = ['Site', 'Count']
            fig = px.bar(top_sites, x='Count', y='Site', orientation='h', color='Count', color_continuous_scale='Reds')
            fig.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No incidents matched the 'Critical Summary' keywords.")

    with c2:
        st.markdown("#### 🕸️ Root Cause Hierarchy")
        if {'Cause', 'Cause Tier 2'}.issubset(df.columns):
            # Drop empties for cleaner chart
            sun_df = df.dropna(subset=['Cause', 'Cause Tier 2'])
            fig = px.sunburst(sun_df, path=['Cause', 'Cause Tier 2'], values='MTTR (Hours)', color='IN or OUT SLA',
                              color_discrete_map={'IN':'#00CC96', 'OUT':'#EF553B'})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Cause columns missing.")


def render_strategy_page(df):
    """PAGE 2: The 'Why & Priority' View (Calculations)"""
    st.subheader("🎯 Strategic Prioritization")
    
    # Calculate "Problem Children" (Positive Variance)
    prob_children = df[df['Variance'] > 0]
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Problem Children (Over Target)", len(prob_children), delta="Sites failing targets", delta_color="inverse")
    k2.metric("Avg MTTR Variance", f"{df['Variance'].mean():.2f}h")
    k3.metric("Max Risk Score", f"{df['Risk_Score'].max():.2f}")

    st.divider()
    
    # Visuals
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### ⚠️ Risk Matrix (Rank vs Frequency)")
        st.caption("High Priority: Upper Left (High Freq, Low Rank Number)")
        fig = px.scatter(
            df, x="Site Rank", y="Frequency", color="Risk_Score", 
            size="MTTR (Hours)", hover_name="Site",
            color_continuous_scale="Turbo", size_max=20
        )
        # Reverse X axis because Rank 1 is better than Rank 9000
        fig.update_xaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)
        
    with c2:
        st.markdown("#### 📊 Variance Distribution")
        fig = px.histogram(df, x="Variance", color="IN or OUT SLA", nbins=30, 
                           title="Distribution of Time Over/Under Target")
        fig.add_vline(x=0, line_dash="dash", line_color="black", annotation_text="Target")
        st.plotly_chart(fig, use_container_width=True)

    # EXPORT SECTION
    st.divider()
    st.subheader("📋 Engineering Hit List")
    
    # Filter columns for the report
    report_cols = ['Site', 'Site Rank', 'Frequency', 'MTTR (Hours)', 'Variance', 'Risk_Score', 'County']
    # Only keep cols that exist
    final_cols = [c for c in report_cols if c in df.columns]
    
    hit_list = df[final_cols].sort_values('Risk_Score', ascending=False).drop_duplicates()
    
    # Download Button
    excel_data = convert_df_to_excel(hit_list)
    st.download_button(
        label="📥 Download Priority Report (Excel)",
        data=excel_data,
        file_name="KZN_Priority_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    # Show styled dataframe
    st.dataframe(
        hit_list.head(50).style.background_gradient(subset=['Risk_Score'], cmap='Reds'),
        use_container_width=True
    )


def render_intelligence_page(df):
    """PAGE 3: The 'Where' View (Sonar Integration)"""
    st.subheader("🌍 Network Intelligence (Sonar)")

    # Diagnostic
    matched = df['Latitude'].notna().sum()
    match_rate = matched / len(df) if len(df) > 0 else 0
    if match_rate < 0.1:
        st.error(f"⚠️ Low Geo-Match Rate: {match_rate:.1%}. Check Sonar Sheet names.")

    # MAP
    map_df = df.dropna(subset=['Latitude', 'Longitude'])
    if not map_df.empty:
        st.markdown("#### 📍 Regional Heatmap")
        
        # Determine safest column for hover
        district_col = 'DISTRICT_COUNCIL' if 'DISTRICT_COUNCIL' in df.columns else 'County'
        
        fig = px.scatter_mapbox(
            map_df, lat="Latitude", lon="Longitude", 
            color="Risk_Score", size="Frequency",
            hover_name="Site", 
            hover_data=["Variance", district_col, "Technology"],
            color_continuous_scale="Reds", size_max=15, zoom=7,
            mapbox_style="carto-positron", height=600
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No Lat/Long data available for map.")

    st.divider()
    
    # Admin & Tech Analysis
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("#### 🏛️ Performance by District")
        d_col = 'DISTRICT_COUNCIL' if 'DISTRICT_COUNCIL' in df.columns else 'MUNICIPAL_DISTR'
        if d_col in df.columns:
            # Group by district
            dist_perf = df.groupby(d_col)[['MTTR (Hours)', 'Risk_Score']].mean().sort_values('MTTR (Hours)').reset_index()
            fig = px.bar(dist_perf, x='MTTR (Hours)', y=d_col, orientation='h', color='Risk_Score')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("District columns not found in Sonar data.")

    with c2:
        st.markdown("#### 📡 Modernisation Impact")
        if 'Modernisation (1800/21)' in df.columns:
            mod_perf = df.groupby('Modernisation (1800/21)')['MTTR (Hours)'].mean().reset_index()
            fig = px.bar(mod_perf, x='Modernisation (1800/21)', y='MTTR (Hours)', 
                         color='MTTR (Hours)', title="Avg MTTR: Legacy vs Modern")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Modernisation column not found.")


# --- 5. MAIN APP CONTROLLER ---

def main():
    # A. SIDEBAR SETUP
    st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/c2/Vodacom_Logo.svg/1200px-Vodacom_Logo.svg.png", width=150)
    st.sidebar.title("Ops Command")
    
    # Region Selection (Scalability Feature)
    region = st.sidebar.selectbox("Select Region", ["KZN", "WES", "CEN", "EAS", "LIM", "MPU"], index=0)
    
    # Page Navigation
    page = st.sidebar.radio("Navigation", ["Operations (Incidents)", "Strategy (Priorities)", "Intelligence (Geo/Tech)"])
    
    st.sidebar.divider()

    # B. LOAD DATA
    file_path = "data/KZN Repeat Outage 2.xlsx" # Ensure this path is correct
    df_master, error = load_and_process_data(file_path, region)

    if error:
        st.error(f"Data Load Error: {error}")
        return

    # C. GLOBAL SIDEBAR FILTERS (Apply to all pages)
    st.sidebar.subheader("Global Filters")
    
    # Week Filter
    if 'Year Week' in df_master.columns:
        weeks = sorted(df_master['Year Week'].dropna().unique())
        sel_weeks = st.sidebar.multiselect("Year Week", weeks, default=weeks)
        if sel_weeks:
            df_master = df_master[df_master['Year Week'].isin(sel_weeks)]
            
    # Tech Filter (if available from Sonar)
    if 'Technology' in df_master.columns:
        techs = sorted(df_master['Technology'].dropna().unique())
        sel_tech = st.sidebar.multiselect("Technology", techs)
        if sel_tech:
            df_master = df_master[df_master['Technology'].isin(sel_tech)]

    # D. ROUTING
    if page == "Operations (Incidents)":
        render_operations_page(df_master)
    elif page == "Strategy (Priorities)":
        render_strategy_page(df_master)
    elif page == "Intelligence (Geo/Tech)":
        render_intelligence_page(df_master)

if __name__ == "__main__":
    main()


i need a file upload as well on the side bar for the data be able to be able to load the data not just running with the file already statically loaded
i must be able to load them dynamic as well via the file uploader 
also i need the counties as filters on the side bar 
 i need to make the map colours more distinct as the base colour for the map and the dots on the map is a little to close to one another so some i cannot see the dots clearly
