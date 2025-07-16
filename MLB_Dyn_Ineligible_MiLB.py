import streamlit as st
import requests
import pandas as pd
from typing import Dict, List
import math
import time
from datetime import datetime
import os
from io import StringIO

# Page configuration
st.set_page_config(
    page_title="MLB Dynasty Minors Eligibility Checker",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_fangraphs_stats():
    """Fetch all career stats from FanGraphs APIs with caching"""
    batting_stats = {}
    pitching_stats = {}
    page_size = 200
    
    # Common URL parameters
    base_params = {
        'age': '',
        'pos': 'all',
        'lg': 'all',
        'qual': '0',
        'season': '2025',
        'season1': '2010',
        'startdate': '',
        'enddate': '',
        'month': '0',
        'hand': '',
        'team': '0',
        'pageitems': str(page_size),
        'ind': '0',
        'rost': '0',
        'players': '',
        'type': '8',
        'postseason': '',
        'sortdir': 'default',
        'sortstat': 'WAR'
    }
    
    # Progress bar for batting stats
    with st.spinner("Fetching batting statistics..."):
        progress_bar = st.progress(0)
        page = 1
        total_pages = 0
        
        # First, count total pages
        try:
            url = "https://www.fangraphs.com/api/leaders/major-league/data"
            params = {**base_params, 'stats': 'bat', 'pagenum': '1'}
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get('data'):
                total_pages = math.ceil(len(data['data']) / page_size) + 5  # Estimate
        except Exception as e:
            st.error(f"Error estimating pages: {str(e)}")
            total_pages = 10
        
        # Fetch batting stats
        page = 1
        while True:
            try:
                url = "https://www.fangraphs.com/api/leaders/major-league/data"
                params = {**base_params, 'stats': 'bat', 'pagenum': str(page)}
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if not data.get('data'):
                    break
                
                # Add to dictionary for quick lookups
                for player in data['data']:
                    batting_stats[player['playerid']] = {
                        'name': player['Name'],
                        'career_AB': player['AB']
                    }
                
                page += 1
                progress_bar.progress(min(page / total_pages, 1.0))
                time.sleep(0.5)  # Reduced delay for better UX
                
            except Exception as e:
                st.error(f"Error fetching batting stats page {page}: {str(e)}")
                break
        
        progress_bar.empty()
    
    # Progress bar for pitching stats
    with st.spinner("Fetching pitching statistics..."):
        progress_bar = st.progress(0)
        page = 1
        
        while True:
            try:
                url = "https://www.fangraphs.com/api/leaders/major-league/data"
                params = {**base_params, 'stats': 'pit', 'pagenum': str(page)}
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if not data.get('data'):
                    break
                
                # Add to dictionary for quick lookups
                for player in data['data']:
                    pitching_stats[player['playerid']] = {
                        'name': player['Name'],
                        'career_IP': player.get('IP', 0)
                    }
                
                page += 1
                progress_bar.progress(min(page / total_pages, 1.0))
                time.sleep(0.5)
                
            except Exception as e:
                st.error(f"Error fetching pitching stats page {page}: {str(e)}")
                break
        
        progress_bar.empty()
    
    return batting_stats, pitching_stats

@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_fantrax_rosters(league_id: str) -> Dict:
    """Fetch rosters from Fantrax API with caching"""
    try:
        url = f"https://www.fantrax.com/fxea/general/getTeamRosters?leagueId={league_id}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching Fantrax rosters: {str(e)}")
        return None

def load_player_id_mapping(file_path=None) -> pd.DataFrame:
    """Load the Player ID mapping file from path"""
    try:
        if file_path and os.path.exists(file_path):
            # Read from file path
            df = pd.read_csv(file_path, na_values=['', 'nan', 'NaN', 'NULL', 'null'])
        else:
            st.error("No valid Player ID mapping file provided")
            return pd.DataFrame()
        
        # Rename Fantrax ID column if needed
        if 'FANTRAXID' in df.columns:
            df = df.rename(columns={'FANTRAXID': 'Fantrax_ID'})
        
        # Clean up the IDFANGRAPHS column - preserve non-integer values as they indicate no MLB experience
        if 'IDFANGRAPHS' in df.columns:
            # Count truly missing values (NaN, empty, None) before any conversion
            original_nan_count = df['IDFANGRAPHS'].isna().sum()
            
            # Also count empty strings
            empty_string_count = (df['IDFANGRAPHS'] == '').sum()
            
            # Total truly missing values
            truly_missing = original_nan_count + empty_string_count
        
        return df
    except Exception as e:
        st.error(f"Error loading Player ID mapping file: {str(e)}")
        return pd.DataFrame()

def check_minors_eligibility(stats: Dict, is_pitcher: bool) -> tuple[bool, float]:
    """
    Check if a player is minors eligible based on career AB/IP thresholds
    Returns: (is_eligible, current_total)
    """
    if is_pitcher:
        current_ip = stats.get('career_IP', 0)
        return current_ip <= 50, current_ip
    else:
        current_ab = stats.get('career_AB', 0)
        return current_ab <= 130, current_ab

def find_ineligible_minors(rosters: Dict, id_mapping: pd.DataFrame, batting_stats: Dict, pitching_stats: Dict) -> List[Dict]:
    """Find players incorrectly placed in minors slots"""
    ineligible_players = []
    missing_players = set()
    
    if rosters is None or 'rosters' not in rosters:
        st.error("Invalid roster data received")
        return ineligible_players
    
    for team_id, team_data in rosters['rosters'].items():
        team_name = team_data['teamName']
        
        for player in team_data['rosterItems']:
            if player['status'] == 'MINORS':
                fantrax_id = player['id']
                
                # Look up player info in mapping file
                player_row = id_mapping[id_mapping['Fantrax_ID'] == fantrax_id]
                if player_row.empty:
                    missing_players.add(f"Missing FanGraphs ID mapping for Fantrax ID: {fantrax_id}")
                    continue
                    
                try:
                    # Handle NaN values in IDFANGRAPHS column
                    fangraphs_id_raw = player_row['IDFANGRAPHS'].iloc[0]
                    player_name = player_row['FANTRAXNAME'].iloc[0]
                    
                    # Check if the value is NaN or completely missing
                    if pd.isna(fangraphs_id_raw) or fangraphs_id_raw == '' or fangraphs_id_raw is None:
                        missing_players.add(f"No FanGraphs ID for Fantrax ID: {fantrax_id}")
                        continue
                    
                    # Try to convert to integer - if it fails, player has no MLB experience (minors eligible)
                    try:
                        fangraphs_id = int(fangraphs_id_raw)
                        
                        is_pitcher = player['position'] in ['SP', 'RP', 'P']
                        
                        # Get career stats based on player type
                        if is_pitcher:
                            stats = pitching_stats.get(fangraphs_id, {})
                        else:
                            stats = batting_stats.get(fangraphs_id, {})
                        
                        if not stats:
                            missing_players.add(f"No stats for {player_name} (FG ID: {fangraphs_id})")
                            continue
                        
                        is_eligible, current_total = check_minors_eligibility(stats, is_pitcher)
                        if not is_eligible:
                            ineligible_players.append({
                                'Player': player_name,
                                'Position': player['position'],
                                'Team': team_name,
                                'Current_Total': round(current_total, 1),
                                'Threshold': '50 IP' if is_pitcher else '130 AB'
                            })
                    
                    except (ValueError, TypeError):
                        # Player has non-integer FanGraphs ID - means no MLB experience, so minors eligible
                        # Don't add to missing_players, just continue (player is eligible by default)
                        continue
                        
                except Exception as e:
                    st.error(f"Error processing player {fantrax_id}: {str(e)}")
                    continue
    
    # Display missing player information
    if missing_players:
        with st.expander("⚠️ Missing Player Data", expanded=False):
            st.warning("Some players could not be processed due to missing FanGraphs IDs:")
            for msg in sorted(missing_players):
                st.text(msg)
    
    return ineligible_players

def main():
    # Header
    st.markdown('<h1 class="main-header">⚾ MLB Dynasty Minors Eligibility Checker</h1>', unsafe_allow_html=True)
    
    # Default configuration
    league_id = "xe7mir7dm4hja3dz"
    
    # Try to find the Player ID Key file in common locations
    possible_paths = [
        "Player ID Key.csv",
        "Apps/Fantrax_Leagues_Dashboard/Fantrax_Leagues_Dashboard/Player ID Key.csv",
        "../Player ID Key.csv"
    ]
    
    file_path = None
    for path in possible_paths:
        if os.path.exists(path):
            file_path = path
            break
    
    if not file_path:
        st.error("❌ Player ID Key CSV not found. Please ensure 'Player ID Key.csv' is in the app directory.")
        st.stop()
    
    # Show configuration status
    st.info(f"**League ID:** {league_id}")
    
    # Main content
    if st.button("🔍 Analyze Minors Eligibility", type="primary"):
        
        with st.spinner("Loading data and analyzing rosters..."):
            # Fetch stats
            batting_stats, pitching_stats = fetch_fangraphs_stats()
            
            # Fetch rosters
            rosters = fetch_fantrax_rosters(league_id)
            if not rosters:
                st.error("Failed to fetch rosters")
                return
            
            # Load player mapping
            id_mapping = load_player_id_mapping(file_path=file_path)
            if id_mapping.empty:
                st.error("Failed to load player mapping")
                return
            
            # Find ineligible players
            ineligible = find_ineligible_minors(rosters, id_mapping, batting_stats, pitching_stats)
            
            # Display results
            st.subheader("📊 Analysis Results")
            
            if ineligible:
                # Create DataFrame
                df = pd.DataFrame(ineligible)
                df = df[['Player', 'Position', 'Team', 'Current_Total', 'Threshold']]
                
                # Display metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Ineligible Players", len(ineligible))
                with col2:
                    pitchers = len(df[df['Position'].isin(['SP', 'RP', 'P'])])
                    st.metric("Pitchers", pitchers)
                with col3:
                    batters = len(df[~df['Position'].isin(['SP', 'RP', 'P'])])
                    st.metric("Batters", batters)
                
                # Display table
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Download button
                csv = df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Results as CSV",
                    data=csv,
                    file_name=f"ineligible_minors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
                
                # Summary by team
                st.subheader("📈 Summary by Team")
                team_summary = df.groupby('Team').size().sort_values(ascending=False)
                st.bar_chart(team_summary)
                
            else:
                st.success("🎉 No ineligible players found in minors slots!")
                
                # Display empty state metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Ineligible Players", 0)
                with col2:
                    st.metric("Pitchers", 0)
                with col3:
                    st.metric("Batters", 0)
    
    # Information section
    with st.expander("ℹ️ About This Tool", expanded=False):
        st.markdown("""
        **MLB Dynasty Minors Eligibility Checker**
        
        This tool analyzes your MLB League on Fantrax to identify players who are incorrectly placed in minors slots.
        
        **Eligibility Rules:**
        - **Pitchers**: Must have ≤ 50 career IP to be minors eligible
        - **Batters**: Must have ≤ 130 career AB to be minors eligible
        
        **How to use:**
        1. Click "Analyze Minors Eligibility" to run the analysis
        2. Review results and download the CSV if needed
        
        **Configuration:**
        - **League ID**: xe7mir7dm4hja3dz (MLB League)
        
        **Data Sources:**
        - Player statistics: FanGraphs API
        - Roster data: Fantrax API
        - Player mapping: self-managed Player ID Key
        """)
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666;'>"
        "Built with Streamlit • Data from FanGraphs & Fantrax"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
