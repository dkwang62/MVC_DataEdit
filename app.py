import streamlit as st
import json
import copy
import re
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple, Set
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from functools import lru_cache

# ----------------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------------
DEFAULT_YEARS = ["2025", "2026"]
BASE_YEAR_FOR_POINTS = "2025"

# ----------------------------------------------------------------------
# WIDGET KEY HELPER (RESORT-SCOPED)
# ----------------------------------------------------------------------
@lru_cache(maxsize=1024)
def rk(resort_id: str, *parts: str) -> str:
    """Build a unique Streamlit widget key scoped to a resort."""
    safe_resort = resort_id or "resort"
    return "__".join([safe_resort] + [str(p) for p in parts])


# ----------------------------------------------------------------------
# PAGE CONFIG & ENHANCED STYLES (MODIFIED FOR COOL GRAY/INDIGO THEME)
# ----------------------------------------------------------------------
def setup_page():
    st.set_page_config(
        page_title="MVC Resort Editor V2",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'About': "MVC Resort Editor V2 - Professional Resort Management System"
        }
    )
    st.markdown("""
    <style>
        /* New Color Palette (Cool Gray/Indigo) */
        :root {
            --primary-color: #42A5F5; /* Bright Blue for actions/focus */
            --secondary-color: #66BB6A; /* Green for success */
            --danger-color: #EF5350; /* Red for warnings/delete */
            --dark-bg: #263238; /* Dark Slate Gray/Deep Indigo for Sidebar */
            --light-bg: #FAFAFA; /* Main Background */
            --card-bg: #FFFFFF; /* Content Card Background */
            --border-color: #CFD8DC; /* Light border */
            --text-color-dark: #37474F; /* Dark text */
            --header-accent: #7986CB; /* Indigo Accent */
        }
        
        /* Global Styles */
        .main {
            background-color: var(--light-bg);
            color: var(--text-color-dark);
        }
        
        /* Header Styling (Less aggressive) */
        .big-font {
            font-size: 38px !important;
            font-weight: 700;
            color: var(--text-color-dark);
            text-align: left;
            padding: 10px 0;
            margin-bottom: 10px;
            border-bottom: 2px solid var(--header-accent);
        }
        
        /* Card Styles */
        .card {
            background: var(--card-bg);
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            margin-bottom: 15px;
            border: 1px solid var(--border-color);
            transition: all 0.2s ease;
        }
        
        .card:hover {
            box-shadow: 0 4px 8px rgba(0,0,0,0.10);
            transform: translateY(-1px);
        }
        
        /* Section Headers */
        .section-header {
            font-size: 20px;
            font-weight: 700;
            color: var(--text-color-dark);
            padding: 12px 0;
            border-bottom: 2px solid var(--header-accent);
            margin-bottom: 16px;
            margin-top: 24px;
        }
        
        /* Sidebar Enhancements - Key change to dark-bg */
        section[data-testid="stSidebar"] {
            background-color: var(--dark-bg);
            color: var(--light-bg);
        }
        
        section[data-testid="stSidebar"] .stMarkdown {
            color: var(--light-bg);
        }
        
        /* Metric Card - Updated for better contrast */
        .metric-card {
            background: var(--card-bg);
            border-radius: 8px;
            padding: 15px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            margin: 8px 0;
            border-left: 4px solid var(--header-accent);
        }
        
        .metric-value {
            font-size: 28px;
            font-weight: 700;
            color: var(--primary-color);
        }
        
        .metric-label {
            color: var(--text-color-dark);
            font-weight: 500;
        }
        
        /* Tab Styling: More distinct selected tab */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
        }
        
        .stTabs [data-baseweb="tab"] {
            border-radius: 4px 4px 0 0;
            padding: 8px 16px;
            font-weight: 600;
            background-color: var(--border-color); /* Light gray for unselected */
            color: var(--text-color-dark);
        }
        
        .stTabs [aria-selected="true"] {
             background-color: var(--card-bg);
             border-top: 2px solid var(--primary-color) !important;
             color: var(--primary-color) !important;
        }
        
        /* Streamlit components text color */
        h1, h2, h3, h4, h5, h6, p, label, .stMarkdown, .stText, .stAlert {
            color: var(--text-color-dark);
        }

        /* Overriding text color for specific components in dark sidebar */
        section[data-testid="stSidebar"] .stMarkdown h3,
        section[data-testid="stSidebar"] .stMarkdown h4,
        section[data-testid="stSidebar"] .stMarkdown label {
            color: var(--light-bg) !important;
        }
        
        /* Info/Warning Boxes */
        .info-box {
            background: #E3F2FD; 
            border-left: 4px solid #42A5F5;
            color: var(--text-color-dark);
            padding: 16px;
            border-radius: 4px;
            margin: 12px 0;
        }
        
        .warning-box {
            background: #FFFDE7; 
            border-left: 4px solid #FFCA28;
            color: var(--text-color-dark);
            padding: 16px;
            border-radius: 4px;
            margin: 12px 0;
        }
        
        .error-box {
            background: #FFEBEE;
            border-left: 4px solid var(--danger-color);
            color: var(--text-color-dark);
            padding: 16px;
            border-radius: 4px;
            margin: 12px 0;
        }
        
        .success-box {
            background: #E8F5E9;
            border-left: 4px solid var(--secondary-color);
            color: var(--text-color-dark);
            padding: 16px;
            border-radius: 4px;
            margin: 12px 0;
            font-weight: 500;
        }

    </style>
    """, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# SESSION STATE MANAGEMENT
# ----------------------------------------------------------------------
def initialize_session_state():
    defaults = {
        'refresh_trigger': False,
        'last_upload_sig': None,
        'data': None,
        'current_resort_id': None,
        'previous_resort_id': None,
        'working_resorts': {},
        'last_save_time': None,
        'delete_confirm': False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def save_data():
    st.session_state.last_save_time = datetime.now()


def show_save_indicator():
    if st.session_state.last_save_time:
        elapsed = (datetime.now() - st.session_state.last_save_time).total_seconds()
        if elapsed < 3:
            st.sidebar.markdown("""
                <div style='background: #66BB6A; color: white; padding: 12px; border-radius: 8px; text-align: center; font-weight: 600;'>
                    ✓ Changes Saved
                </div>
            """, unsafe_allow_html=True)


def reset_state_for_new_file():
    for k in ["data", "current_resort_id", "previous_resort_id",
              "working_resorts", "delete_confirm", "last_save_time"]:
        st.session_state[k] = {} if k == "working_resorts" else None


# ----------------------------------------------------------------------
# OPTIMIZED HELPER FUNCTIONS
# ----------------------------------------------------------------------
@lru_cache(maxsize=128)
def get_years_from_data_cached(data_hash: int) -> Tuple[str, ...]:
    """Cached version of get_years_from_data"""
    return tuple(sorted(get_years_from_data(st.session_state.data)))


def get_years_from_data(data: Dict[str, Any]) -> List[str]:
    """Derive list of years from global_holidays or resort years."""
    years: Set[str] = set()
    gh = data.get("global_holidays", {})
    years.update(gh.keys())
    for r in data.get("resorts", []):
        years.update(str(y) for y in r.get("years", {}).keys())
    return sorted(years) if years else DEFAULT_YEARS


def safe_date(d: Optional[str], default: str = "2025-01-01") -> date:
    if not d or not isinstance(d, str):
        return datetime.strptime(default, "%Y-%m-%d").date()
    try:
        return datetime.strptime(d.strip(), "%Y-%m-%d").date()
    except ValueError:
        return datetime.strptime(default, "%Y-%m-%d").date()


def get_resort_list(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return data.get("resorts", [])


def find_resort_by_id(data: Dict[str, Any], rid: str) -> Optional[Dict[str, Any]]:
    return next((r for r in data.get("resorts", []) if r.get("id") == rid), None)


def find_resort_index(data: Dict[str, Any], rid: str) -> Optional[int]:
    return next((i for i, r in enumerate(data.get("resorts", [])) if r.get("id") == rid), None)


def generate_resort_id(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', name.strip().lower())
    return re.sub(r'-+', '-', slug).strip('-') or "resort"


def generate_resort_code(name: str) -> str:
    parts = [p for p in name.replace("'", "'").split() if p]
    return "".join(p[0].upper() for p in parts[:3]) or "RST"


def make_unique_resort_id(base_id: str, resorts: List[Dict[str, Any]]) -> str:
    existing = {r.get("id") for r in resorts}
    if base_id not in existing:
        return base_id
    i = 2
    while f"{base_id}-{i}" in existing:
        i += 1
    return f"{base_id}-{i}"


# ----------------------------------------------------------------------
# FILE OPERATIONS WITH ENHANCED UI
# ----------------------------------------------------------------------
def handle_file_upload():
    st.sidebar.markdown("### 📤 Upload Data")
    uploaded = st.sidebar.file_uploader(
        "Choose V2 JSON file",
        type="json",
        key="file_uploader",
        help="Upload your MVC V2 data file"
    )
    if uploaded:
        size = getattr(uploaded, "size", 0)
        current_sig = f"{uploaded.name}:{size}"
        if current_sig != st.session_state.last_upload_sig:
            try:
                raw_data = json.load(uploaded)
                if "schema_version" not in raw_data or not raw_data.get("resorts"):
                    st.sidebar.error("❌ Invalid V2 file format")
                    return
                reset_state_for_new_file()
                st.session_state.data = raw_data
                st.session_state.last_upload_sig = current_sig
                resorts_list = get_resort_list(raw_data)
                st.sidebar.success(f"✅ Loaded {len(resorts_list)} resorts")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"❌ Error: {str(e)}")


def create_download_button_v2(data: Dict[str, Any]):
    if data:
        st.sidebar.markdown("### 📥 Download Data")
        json_data = json.dumps(data, indent=2, ensure_ascii=False)
        st.sidebar.download_button(
            label="💾 Download V2 JSON",
            data=json_data,
            file_name="data_v2.json",
            mime="application/json",
            key="download_v2_btn",
            type="primary",
            use_container_width=True
        )


def handle_file_verification():
    with st.sidebar.expander("🔍 Verify File", expanded=False):
        verify_upload = st.file_uploader(
            "Upload to verify",
            type="json",
            key="verify_uploader"
        )
        if verify_upload:
            try:
                uploaded_data = json.load(verify_upload)
                current_json = json.dumps(st.session_state.data, sort_keys=True)
                uploaded_json = json.dumps(uploaded_data, sort_keys=True)
                if current_json == uploaded_json:
                    st.success("✅ Files match")
                else:
                    st.error("❌ Files differ")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")


def handle_merge_from_another_file_v2(data: Dict[str, Any]):
    with st.sidebar.expander("🔀 Merge Resorts", expanded=False):
        merge_upload = st.file_uploader(
            "Upload V2 file to merge",
            type="json",
            key="merge_uploader_v2"
        )
        if merge_upload:
            try:
                merge_data = json.load(merge_upload)
                if "resorts" not in merge_data:
                    st.error("❌ Invalid V2 schema")
                    return

                target_resorts = data.setdefault("resorts", [])
                existing_ids = {r.get("id") for r in target_resorts}
                merge_resorts = merge_data.get("resorts", [])

                if not merge_resorts:
                    st.warning("No resorts found")
                    return

                display_map = {
                    f"{r.get('display_name', r.get('id'))} ({r.get('id')})": r
                    for r in merge_resorts
                }

                selected_labels = st.multiselect(
                    "Select resorts",
                    list(display_map.keys()),
                    key="selected_merge_resorts_v2"
                )

                if selected_labels and st.button("🔀 Merge", key="merge_btn_v2", use_container_width=True, type="primary"):
                    merged_count = 0
                    skipped = []
                    for label in selected_labels:
                        resort_obj = display_map[label]
                        rid = resort_obj.get("id")
                        if rid in existing_ids:
                            skipped.append(resort_obj.get("display_name", rid))
                            continue
                        target_resorts.append(copy.deepcopy(resort_obj))
                        existing_ids.add(rid)
                        merged_count += 1

                    save_data()
                    if merged_count:
                        st.success(f"✅ Merged {merged_count} resort(s)")
                    if skipped:
                        st.warning(f"Skipped: {', '.join(skipped)}")
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")


# ----------------------------------------------------------------------
# RESORT MANAGEMENT WITH ENHANCED UI
# ----------------------------------------------------------------------
def render_resort_grid(resorts: List[Dict[str, Any]], current_resort_id: Optional[str]):
    st.markdown("### 🏨 Resort Selection")
    
    if not resorts:
        st.info("No resorts available. Create one below!")
        return
    
    # Use a selectable dropdown for many resorts instead of a horizontal grid
    resort_options = sorted([r.get("display_name", r.get("id")) for r in resorts])
    current_name = next((r.get("display_name", r.get("id")) for r in resorts if r.get("id") == current_resort_id), None)
    
    selected_name = st.selectbox(
        "Select an MVC Resort to Edit",
        options=resort_options,
        index=resort_options.index(current_name) if current_name in resort_options else 0,
        key="resort_selectbox"
    )

    # Convert selected name back to ID
    if selected_name and current_name != selected_name:
        selected_resort = next((r for r in resorts if r.get("display_name", r.get("id")) == selected_name), None)
        if selected_resort and selected_resort.get("id") != current_resort_id:
            st.session_state.current_resort_id = selected_resort.get("id")
            st.session_state.delete_confirm = False
            st.rerun()


def is_duplicate_resort_name(name: str, resorts: List[Dict[str, Any]]) -> bool:
    target = name.strip().lower()
    return any(r.get("display_name", "").strip().lower() == target for r in resorts)


def handle_resort_creation_v2(data: Dict[str, Any], current_resort_id: Optional[str]):
    resorts = data.setdefault("resorts", [])

    with st.expander("➕ Create or Clone Resort", expanded=False):
        new_name = st.text_input(
            "New Resort Name",
            placeholder="e.g., Pulse San Francisco",
            key="new_resort_name"
        )
        
        col1, col2 = st.columns(2)

        with col1:
            if st.button("✨ Create Blank", key="create_blank_btn", use_container_width=True, type="secondary") and new_name:
                name = new_name.strip()
                if not name:
                    st.error("❌ Name cannot be empty")
                elif is_duplicate_resort_name(name, resorts):
                    st.error("❌ Name already exists")
                else:
                    base_id = generate_resort_id(name)
                    rid = make_unique_resort_id(base_id, resorts)
                    code = generate_resort_code(name)
                    new_resort = {
                        "id": rid,
                        "display_name": name,
                        "code": code,
                        "region": "Unknown",
                        "timezone": "UTC",
                        "years": {}
                    }
                    resorts.append(new_resort)
                    st.session_state.current_resort_id = rid
                    save_data()
                    st.success(f"✅ Created {name}")
                    st.rerun()

        with col2:
            if st.button("📋 Clone Current", key="clone_current_resort_action", use_container_width=True, type="secondary") and new_name:
                name = new_name.strip()
                if not name:
                    st.error("❌ Name cannot be empty")
                elif is_duplicate_resort_name(name, resorts):
                    st.error("❌ Name already exists")
                elif not current_resort_id:
                    st.error("❌ Select a resort first")
                else:
                    src = find_resort_by_id(data, current_resort_id)
                    if src is None:
                        st.error("❌ Source not found")
                    else:
                        base_id = generate_resort_id(name)
                        rid = make_unique_resort_id(base_id, resorts)
                        code = generate_resort_code(name)
                        cloned = copy.deepcopy(src)
                        cloned["id"] = rid
                        cloned["display_name"] = name
                        cloned["code"] = code
                        resorts.append(cloned)
                        st.session_state.current_resort_id = rid
                        save_data()
                        st.success(f"✅ Cloned to {name}")
                        st.rerun()


def handle_resort_deletion_v2(data: Dict[str, Any], current_resort_id: Optional[str]):
    if not current_resort_id:
        return
    
    current_resort = find_resort_by_id(data, current_resort_id)
    if not current_resort:
        return

    if not st.session_state.delete_confirm:
        # Initial delete button
        if st.button("🗑️ Delete Resort", key="delete_resort_init", type="secondary", use_container_width=True):
            st.session_state.delete_confirm = True
            st.rerun()
    else:
        name = current_resort.get("display_name", current_resort_id)
        st.markdown(f"""
            <div class='error-box'>
                <h4>⚠️ Confirm Deletion</h4>
                <p>Are you sure you want to permanently delete <strong>{name}</strong>?</p>
                <p>This action cannot be undone.</p>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔥 DELETE FOREVER", key=f"delete_resort_final_{current_resort_id}", type="primary", use_container_width=True):
                idx = find_resort_index(data, current_resort_id)
                if idx is not None:
                    data.get("resorts", []).pop(idx)
                st.session_state.current_resort_id = None
                st.session_state.delete_confirm = False
                st.session_state.working_resorts.pop(current_resort_id, None)
                save_data()
                st.success("✅ Resort deleted")
                st.rerun()
        with col2:
            if st.button("❌ Cancel", key=f"delete_cancel_{current_resort_id}", use_container_width=True):
                st.session_state.delete_confirm = False
                st.rerun()
        st.stop()


# ----------------------------------------------------------------------
# WORKING RESORT MANAGEMENT
# ----------------------------------------------------------------------
def handle_resort_switch_v2(data: Dict[str, Any], current_resort_id: Optional[str], previous_resort_id: Optional[str]):
    if previous_resort_id and previous_resort_id != current_resort_id:
        working_resorts = st.session_state.working_resorts
        if previous_resort_id in working_resorts:
            working = working_resorts[previous_resort_id]
            committed = find_resort_by_id(data, previous_resort_id)
            if committed is None:
                working_resorts.pop(previous_resort_id, None)
            elif working != committed:
                st.warning(f"⚠️ Unsaved changes in {committed.get('display_name', previous_resort_id)}")
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("💾 Save", key="switch_save_prev", use_container_width=True, type="primary"):
                        commit_working_to_data_v2(data, working, previous_resort_id)
                        del working_resorts[previous_resort_id]
                        st.session_state.previous_resort_id = current_resort_id
                        st.rerun()
                with col2:
                    if st.button("🚫 Discard", key="switch_discard_prev", use_container_width=True, type="secondary"):
                        del working_resorts[previous_resort_id]
                        st.session_state.previous_resort_id = current_resort_id
                        st.rerun()
                with col3:
                    if st.button("↩️ Stay", key="switch_cancel_prev", use_container_width=True, type="secondary"):
                        st.session_state.current_resort_id = previous_resort_id
                        st.rerun()
                st.stop()
    st.session_state.previous_resort_id = current_resort_id


def commit_working_to_data_v2(data: Dict[str, Any], working: Dict[str, Any], resort_id: str):
    idx = find_resort_index(data, resort_id)
    if idx is not None:
        data["resorts"][idx] = copy.deepcopy(working)
        save_data()


def render_save_button_v2(data: Dict[str, Any], working: Dict[str, Any], resort_id: str):
    committed = find_resort_by_id(data, resort_id)
    if committed is not None and committed != working:
        if st.button("💾 Save All Changes", type="primary", key=f"save_resort_{resort_id}", use_container_width=True):
            commit_working_to_data_v2(data, working, resort_id)
            st.session_state.working_resorts.pop(resort_id, None)
            st.success("✅ Changes saved successfully! Reloading...")
            st.rerun()
    elif committed is not None and committed == working:
        st.button("✅ No Changes to Save", disabled=True, key=f"save_resort_unchanged_{resort_id}", use_container_width=True)


# ----------------------------------------------------------------------
# SEASON MANAGEMENT
# ----------------------------------------------------------------------
def ensure_year_structure(resort: Dict[str, Any], year: str):
    years = resort.setdefault("years", {})
    year_obj = years.setdefault(year, {})
    year_obj.setdefault("seasons", [])
    year_obj.setdefault("holidays", [])
    return year_obj


def get_all_season_names_for_resort(working: Dict[str, Any]) -> Set[str]:
    names: Set[str] = set()
    for year_obj in working.get("years", {}).values():
        names.update(s.get("name") for s in year_obj.get("seasons", []) if s.get("name"))
    return names


def delete_season_across_years(working: Dict[str, Any], season_name: str):
    years = working.get("years", {})
    for year_obj in years.values():
        year_obj["seasons"] = [s for s in year_obj.get("seasons", []) if s.get("name") != season_name]


def render_season_dates_editor_v2(working: Dict[str, Any], years: List[str], resort_id: str):
    st.markdown("<div class='section-header'>📅 Season Dates</div>", unsafe_allow_html=True)
    st.caption("Define season date ranges for each year. Season names apply across all years.")
    
    all_names = get_all_season_names_for_resort(working)

    # Global Season Name Adder (outside the year loop)
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        new_season_name = st.text_input(
            "Add new season name (applies to all years)",
            key=rk(resort_id, "new_season_global"),
            placeholder="e.g., Peak Season"
        )
    with col_btn:
        st.markdown("<div style='height: 27px;'></div>", unsafe_allow_html=True) # Spacer
        if st.button("➕ Add Season", key=rk(resort_id, "add_season_all_years_global"), use_container_width=True, type="secondary"):
            name = new_season_name.strip()
            if not name:
                st.error("❌ Name required")
            elif any(name.lower() == n.lower() for n in all_names):
                st.error("❌ Season exists")
            else:
                for y2 in years:
                    y2_obj = ensure_year_structure(working, y2)
                    y2_obj.setdefault("seasons", []).append({
                        "name": name,
                        "periods": [],
                        "day_categories": {}
                    })
                st.success(f"✅ Added '{name}' to all years")
                st.rerun()

    st.markdown("---")

    # Per-Year Date Editor
    year_tabs = st.tabs([f"📆 {year}" for year in years])
    
    for year, year_tab in zip(years, year_tabs):
        with year_tab:
            year_obj = ensure_year_structure(working, year)
            seasons = year_obj.get("seasons", [])

            if not seasons:
                st.info(f"No seasons defined for {year}. Add a global season name above.")
                continue

            for idx, season in enumerate(seasons):
                render_single_season_v2(working, year, season, idx, resort_id)


def render_single_season_v2(working: Dict[str, Any], year: str, season: Dict[str, Any], idx: int, resort_id: str):
    sname = season.get("name", f"Season {idx+1}")
    
    with st.container(border=True):
        st.markdown(f"**🎯 {sname}**")
        periods = season.setdefault("periods", [])

        for r_idx, p in enumerate(periods):
            col1, col2, col3 = st.columns([3, 3, 1])
            with col1:
                new_start = st.date_input(
                    "Start",
                    safe_date(p.get("start") or f"{year}-01-01"),
                    key=rk(resort_id, "season", year, idx, "start", r_idx),
                    label_visibility="collapsed"
                )
            with col2:
                new_end = st.date_input(
                    "End",
                    safe_date(p.get("end") or f"{year}-01-07"),
                    key=rk(resort_id, "season", year, idx, "end", r_idx),
                    label_visibility="collapsed"
                )
            with col3:
                st.markdown("<div style='height: 27px;'></div>", unsafe_allow_html=True) # Spacer
                if st.button("❌", key=rk(resort_id, "season", year, idx, "del_range", r_idx), use_container_width=True):
                    periods.pop(r_idx)
                    st.rerun()

            p["start"] = new_start.isoformat()
            p["end"] = new_end.isoformat()

        col_add, col_del = st.columns([1, 1])
        with col_add:
            if st.button("➕ Add Date Range", key=rk(resort_id, "season", year, idx, "add_range"), use_container_width=True, type="secondary"):
                periods.append({"start": f"{year}-01-01", "end": f"{year}-01-07"})
                st.rerun()
        with col_del:
            if st.button(f"🗑️ Delete '{sname}' (All Years)", key=rk(resort_id, "season_del_all_years", year, idx), use_container_width=True):
                delete_season_across_years(working, sname)
                st.rerun()


# ----------------------------------------------------------------------
# ROOM TYPE MANAGEMENT
# ----------------------------------------------------------------------
def get_all_room_types_for_resort(working: Dict[str, Any]) -> List[str]:
    rooms: Set[str] = set()
    for year_obj in working.get("years", {}).values():
        for season in year_obj.get("seasons", []):
            for cat in season.get("day_categories", {}).values():
                if isinstance(rp := cat.get("room_points", {}), dict):
                    rooms.update(rp.keys())
        for h in year_obj.get("holidays", []):
            if isinstance(rp := h.get("room_points", {}), dict):
                rooms.update(rp.keys())
    return sorted(rooms)


def add_room_type_master(working: Dict[str, Any], room: str, base_year: str):
    room = room.strip()
    if not room:
        return

    years = working.get("years", {})
    
    # Add to seasons in base year
    if base_year in years:
        base_year_obj = ensure_year_structure(working, base_year)
        for season in base_year_obj.get("seasons", []):
            for cat in season.setdefault("day_categories", {}).values():
                cat.setdefault("room_points", {}).setdefault(room, 0)

    # Add to holidays in ALL years
    for year_obj in years.values():
        for h in year_obj.get("holidays", []):
            h.setdefault("room_points", {}).setdefault(room, 0)


def delete_room_type_master(working: Dict[str, Any], room: str):
    for year_obj in working.get("years", {}).values():
        for season in year_obj.get("seasons", []):
            for cat in season.get("day_categories", {}).values():
                if isinstance(rp := cat.get("room_points", {}), dict):
                    rp.pop(room, None)
        for h in year_obj.get("holidays", []):
            if isinstance(rp := h.get("room_points", {}), dict):
                rp.pop(room, None)


# ----------------------------------------------------------------------
# SYNC FUNCTIONS
# ----------------------------------------------------------------------
def sync_season_room_points_across_years(working: Dict[str, Any], base_year: str):
    years = working.get("years", {})
    if not years or base_year not in years:
        return

    # Collect all room types
    canonical_rooms: Set[str] = set()
    for y_obj in years.values():
        for season in y_obj.get("seasons", []):
            for cat in season.get("day_categories", {}).values():
                if isinstance(rp := cat.get("room_points", {}), dict):
                    canonical_rooms |= set(rp.keys())

    if not canonical_rooms:
        return

    base_year_obj = years[base_year]
    base_seasons = base_year_obj.get("seasons", [])

    # Normalize base year
    for season in base_seasons:
        for cat in season.setdefault("day_categories", {}).values():
            rp = cat.setdefault("room_points", {})
            for room in canonical_rooms:
                rp.setdefault(room, 0)
            for room in list(rp.keys()):
                if room not in canonical_rooms:
                    del rp[room]

    # Copy to other years
    base_by_name = {s.get("name", ""): s for s in base_seasons if s.get("name")}
    for year_name, year_obj in years.items():
        if year_name != base_year:
            for season in year_obj.get("seasons", []):
                if (name := season.get("name", "")) in base_by_name:
                    # Only sync the day_categories and room_points, keep periods (dates) local
                    season["day_categories"] = copy.deepcopy(base_by_name[name].get("day_categories", {}))


def sync_holiday_room_points_across_years(working: Dict[str, Any], base_year: str):
    years = working.get("years", {})
    if not years or base_year not in years:
        return

    base_year_obj = ensure_year_structure(working, base_year)
    base_holidays = base_year_obj.get("holidays", [])
    all_rooms = get_all_room_types_for_resort(working)

    # Normalize base year
    for h in base_holidays:
        rp = h.setdefault("room_points", {})
        for room in all_rooms:
            rp.setdefault(room, 0)
        for room in list(rp.keys()):
            if room not in all_rooms:
                del rp[room]

    # Build mapping
    base_by_key = {
        (h.get("global_reference") or h.get("name") or "").strip(): h
        for h in base_holidays
        if (h.get("global_reference") or h.get("name") or "").strip()
    }

    # Copy to other years
    for year_name, year_obj in years.items():
        if year_name != base_year:
            for h in year_obj.get("holidays", []):
                if (key := (h.get("global_reference") or h.get("name") or "").strip()) in base_by_key:
                    h["room_points"] = copy.deepcopy(base_by_key[key].get("room_points", {}))


# ----------------------------------------------------------------------
# MASTER POINTS EDITOR
# ----------------------------------------------------------------------
def render_reference_points_editor_v2(working: Dict[str, Any], years: List[str], resort_id: str):
    st.markdown("<div class='section-header'>🎯 Master Season Room Points</div>", unsafe_allow_html=True)
    st.caption("Edit nightly points for each season day category (Sun-Thu, Fri-Sat). Changes apply to all years automatically.")

    base_year = BASE_YEAR_FOR_POINTS if BASE_YEAR_FOR_POINTS in years else (sorted(years)[0] if years else BASE_YEAR_FOR_POINTS)
    base_year_obj = ensure_year_structure(working, base_year)
    seasons = base_year_obj.get("seasons", [])

    if not seasons:
        st.info(f"💡 No seasons defined yet. Add seasons in the 'Dates & Timeline' tab first.")
        return

    canonical_rooms = get_all_room_types_for_resort(working)

    # Room Type Management is moved to the top of this section
    st.markdown("#### 🏠 Room Type Manager")
    col1, col2 = st.columns(2)

    with col1:
        new_room = st.text_input(
            "Add room type (e.g., 2BR Ocean View)",
            key=rk(resort_id, "room_add_master"),
            placeholder="e.g., 2BR Ocean View",
            label_visibility="collapsed"
        )
        if st.button("➕ Add Room Type", key=rk(resort_id, "room_add_btn_master"), use_container_width=True, type="secondary") and new_room:
            add_room_type_master(working, new_room.strip(), base_year)
            st.success(f"✅ Added {new_room}")
            st.rerun()

    with col2:
        del_room = st.selectbox(
            "Delete room type",
            [""] + get_all_room_types_for_resort(working),
            key=rk(resort_id, "room_del_master"),
            label_visibility="collapsed",
            index=0
        )
        if del_room and st.button("🗑️ Delete Selected Room", key=rk(resort_id, "room_del_btn_master"), use_container_width=True):
            delete_room_type_master(working, del_room)
            st.success(f"✅ Deleted {del_room}")
            st.rerun()
            
    st.markdown("---")
    st.markdown("#### 💰 Nightly Point Editor (Base Year: {base_year})")

    for s_idx, season in enumerate(seasons):
        with st.expander(f"🏖️ {season.get('name', f'Season {s_idx+1}')}", expanded=True):
            dc = season.setdefault("day_categories", {})
            if not dc:
                dc["sun_thu"] = {
                    "day_pattern": ["Sun", "Mon", "Tue", "Wed", "Thu"],
                    "room_points": {}
                }
                dc["fri_sat"] = {
                    "day_pattern": ["Fri", "Sat"],
                    "room_points": {}
                }

            for key, cat in dc.items():
                day_pattern = cat.get("day_pattern", [])
                st.markdown(f"**📅 Day Category: {key}** – ({', '.join(day_pattern) if day_pattern else 'No days set'})")
                
                room_points = cat.setdefault("room_points", {})
                rooms_here = canonical_rooms or sorted(room_points.keys())
                
                for room in rooms_here:
                    room_points.setdefault(room, 0)

                # Use a container to visually group the point inputs
                with st.container(border=True):
                    cols = st.columns(4)
                    for j, room in enumerate(sorted(room_points.keys())):
                        with cols[j % 4]:
                            current_val = int(room_points.get(room, 0) or 0)
                            new_val = st.number_input(
                                room,
                                value=current_val,
                                step=25,
                                key=rk(resort_id, "master_rp", base_year, s_idx, key, room),
                                help=f"Nightly points for {room}"
                            )
                            if new_val != current_val:
                                room_points[room] = int(new_val)

    sync_season_room_points_across_years(working, base_year=base_year)


# ----------------------------------------------------------------------
# HOLIDAY MANAGEMENT (MODIFIED)
# ----------------------------------------------------------------------
def render_holiday_management_v2(working: Dict[str, Any], years: List[str], resort_id: str):
    data = st.session_state.data
    st.markdown("<div class='section-header'>🎄 Holiday Management</div>", unsafe_allow_html=True)
    
    base_year = BASE_YEAR_FOR_POINTS if BASE_YEAR_FOR_POINTS in years else (sorted(years)[0] if years else BASE_YEAR_FOR_POINTS)

    # Fetch all global holiday keys for easier reference
    global_holidays = data.get("global_holidays", {})

    # Per-year holiday assignment
    st.markdown("#### 📋 Assign Global Holidays to Resort Years")
    st.caption("Resort-specific holidays (which hold point values) must link to a date defined in the Global Holiday Calendar. Dates are view-only here.")
    
    for year in years:
        year_obj = ensure_year_structure(working, year)
        holidays = year_obj.get("holidays", [])
        
        # Available Global Holidays for this year
        available_global_keys = sorted(list(global_holidays.get(year, {}).keys()))
        global_options = ["— Select Global Holiday —"] + available_global_keys

        with st.expander(f"🎉 {year} Holiday Assignments", expanded=False):
            
            # Add New Holiday based on a Global Reference
            col1, col2 = st.columns([4, 1])
            with col1:
                selected_global_ref = st.selectbox(
                    "Select Global Holiday to Add",
                    options=global_options,
                    key=rk(resort_id, "new_holiday_select", year),
                )
            with col2:
                if st.button("➕ Add", key=rk(resort_id, "btn_add_holiday", year), use_container_width=True, type="secondary") and selected_global_ref != "— Select Global Holiday —":
                    name = selected_global_ref.strip()
                    # Check for duplicates before adding
                    if any(h.get("global_reference") == name for h in holidays):
                        st.warning(f"⚠️ Holiday '{name}' already added for {year}.")
                    else:
                        holidays.append({
                            "name": name,
                            "global_reference": name,
                            "room_points": {} # Will be synced from base year master points
                        })
                        st.success(f"✅ Added {name}. Define points below.")
                        st.rerun()

            st.markdown("---")
            st.subheader(f"Existing Resort Holidays in {year}")

            for h_idx, h in enumerate(holidays):
                col1, col2, col3 = st.columns([3, 3, 1])
                
                # Get start/end dates from global calendar for display
                global_ref = h.get("global_reference", "")
                global_dates = global_holidays.get(year, {}).get(global_ref, {})
                start_date = global_dates.get("start_date", "N/A")
                end_date = global_dates.get("end_date", "N/A")

                # Display name (editable)
                with col1:
                    new_disp = st.text_input(
                        "Display name",
                        value=h.get("name", ""),
                        key=rk(resort_id, "holiday_name", year, h_idx)
                    )
                    h["name"] = new_disp
                    st.caption(f"Linked Global Ref: **{global_ref}**")
                
                # Global reference (read-only link to global dates)
                with col2:
                    st.markdown(f"**Dates:** {start_date} to {end_date}")
                    st.caption(f"Type: {global_dates.get('type', '—')}")

                with col3:
                    if st.button("❌", key=rk(resort_id, "holiday_del", year, h_idx), use_container_width=True):
                        holidays.pop(h_idx)
                        st.rerun()

    sync_holiday_room_points_across_years(working, base_year=base_year)

    # Master holiday points
    st.markdown("---")
    st.markdown("#### 💰 Master Holiday Points (Base Year: {base_year})")
    st.caption("Edit holiday room points once (using base year). Applied to all years automatically.")
    
    base_year_obj = ensure_year_structure(working, base_year)
    base_holidays = base_year_obj.get("holidays", [])

    if not base_holidays:
        st.info(f"💡 No holidays defined in {base_year}. Assign global holidays above first.")
    else:
        all_rooms = get_all_room_types_for_resort(working)
        
        for h_idx, h in enumerate(base_holidays):
            disp_name = h.get("name", f"Holiday {h_idx+1}")
            key = (h.get("global_reference") or h.get("name") or "").strip()
            
            with st.expander(f"🎊 {disp_name}", expanded=False):
                st.caption(f"Reference key: {key}")
                
                rp = h.setdefault("room_points", {})
                rooms_here = sorted(all_rooms or rp.keys())

                with st.container(border=True):
                    cols = st.columns(4)
                    for j, room in enumerate(rooms_here):
                        rp.setdefault(room, 0)
                        with cols[j % 4]:
                            current_val = int(rp.get(room, 0) or 0)
                            new_val = st.number_input(
                                room,
                                value=current_val,
                                step=25,
                                key=rk(resort_id, "holiday_master_rp", base_year, h_idx, room)
                            )
                            if new_val != current_val:
                                rp[room] = int(new_val)

    sync_holiday_room_points_across_years(working, base_year=base_year)


# ----------------------------------------------------------------------
# RESORT SUMMARY
# ----------------------------------------------------------------------
def compute_weekly_totals_for_season_v2(season: Dict[str, Any], room_types: List[str]) -> Tuple[Dict[str, int], bool]:
    weekly_totals = {room: 0 for room in room_types}
    any_data = False
    valid_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}

    for cat in season.get("day_categories", {}).values():
        pattern = cat.get("day_pattern", [])
        if not (rp := cat.get("room_points", {})) or not isinstance(rp, dict):
            continue
        n_days = len([d for d in pattern if d in valid_days])
        if n_days > 0:
            for room in room_types:
                if room in rp and rp[room] is not None:
                    weekly_totals[room] += int(rp[room]) * n_days
                    any_data = True

    return weekly_totals, any_data


def render_resort_summary_v2(working: Dict[str, Any]):
    st.markdown("<div class='section-header'>📊 Resort Summary: Weekly Point Totals</div>", unsafe_allow_html=True)

    resort_years = working.get("years", {})
    if not resort_years:
        st.info("💡 No data available yet")
        return

    ref_year = next((y for y in sorted(resort_years.keys()) if resort_years[y].get("seasons")), None)
    if not ref_year:
        st.info("💡 No seasons defined yet in the Base Year.")
        return

    room_types = get_all_room_types_for_resort(working)
    if not room_types:
        st.info("💡 No room types defined yet.")
        return

    rows = []
    # Use base year seasons to calculate the totals as points are synced from there
    for season in resort_years[ref_year].get("seasons", []):
        sname = season.get("name", "").strip() or "(Unnamed)"
        weekly_totals, any_data = compute_weekly_totals_for_season_v2(season, room_types)
        if any_data:
            row = {"Season": sname}
            row.update({room: (total if total else "—") for room, total in weekly_totals.items()})
            rows.append(row)

    if rows:
        df = pd.DataFrame(rows, columns=["Season"] + room_types)
        # Apply conditional formatting for better visualization (optional)
        def color_high_points(val):
            if isinstance(val, int) and val > 7500:
                return 'background-color: #FFEBEE; color: #EF5350' # Light red background
            return ''

        st.dataframe(
            df.style.applymap(color_high_points, subset=pd.IndexSlice[:, room_types]), 
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.info("💡 No season rate data available for summary generation.")


# ----------------------------------------------------------------------
# VALIDATION
# ----------------------------------------------------------------------
def validate_resort_data_v2(working: Dict[str, Any], data: Dict[str, Any], years: List[str]) -> List[str]:
    issues = []
    all_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    all_rooms = set(get_all_room_types_for_resort(working))
    global_holidays = data.get("global_holidays", {})

    for year in years:
        year_obj = working.get("years", {}).get(year, {})
        
        # Validate seasons
        for season in year_obj.get("seasons", []):
            sname = season.get("name", "(Unnamed)")
            
            # Check day coverage
            covered_days = set()
            for cat in season.get("day_categories", {}).values():
                pattern_days = {d for d in cat.get("day_pattern", []) if d in all_days}
                if overlap := covered_days & pattern_days:
                    issues.append(f"[{year}] Season '{sname}' has overlapping days: {', '.join(sorted(overlap))}")
                covered_days |= pattern_days

            if missing := all_days - covered_days:
                issues.append(f"[{year}] Season '{sname}' missing days: {', '.join(sorted(missing))}")

            # Check room coverage
            if all_rooms:
                season_rooms = set()
                for cat in season.get("day_categories", {}).values():
                    if isinstance(rp := cat.get("room_points", {}), dict):
                        season_rooms |= set(rp.keys())
                if missing_rooms := all_rooms - season_rooms:
                    issues.append(f"[{year}] Season '{sname}' missing rooms: {', '.join(sorted(missing_rooms))}")

        # Validate holidays
        for h in year_obj.get("holidays", []):
            hname = h.get("name", "(Unnamed)")
            global_ref = h.get("global_reference") or hname
            
            if global_ref not in global_holidays.get(year, {}):
                issues.append(f"[{year}] Holiday '{hname}' references missing global holiday '{global_ref}'")
            
            if all_rooms and isinstance(rp := h.get("room_points", {}), dict):
                if missing_rooms := all_rooms - set(rp.keys()):
                    issues.append(f"[{year}] Holiday '{hname}' missing rooms: {', '.join(sorted(missing_rooms))}")

    return issues


def render_validation_panel_v2(working: Dict[str, Any], data: Dict[str, Any], years: List[str]):
    with st.expander("🔍 Data Validation Report", expanded=False):
        issues = validate_resort_data_v2(working, data, years)
        if issues:
            st.error(f"**Found {len(issues)} critical issue(s):**")
            for issue in issues:
                st.write(f"• {issue}")
        else:
            st.success("✅ All validation checks passed! Data appears consistent.")


# ----------------------------------------------------------------------
# GANTT CHART
# ----------------------------------------------------------------------
def create_gantt_chart_v2(working: Dict[str, Any], year: str, data: Dict[str, Any]) -> go.Figure:
    rows = []
    year_obj = working.get("years", {}).get(year, {})

    # Add seasons
    for season in year_obj.get("seasons", []):
        sname = season.get("name", "(Unnamed)")
        for i, p in enumerate(season.get("periods", []), 1):
            try:
                # Add one day to end_dt to ensure plotly draws the last day correctly
                start_dt = datetime.strptime(p.get("start"), "%Y-%m-%d")
                end_dt = datetime.strptime(p.get("end"), "%Y-%m-%d") + timedelta(days=1) 
                if start_dt < end_dt:
                    rows.append({
                        "Task": f"{sname}", # Simplified Y-axis label
                        "Start": start_dt,
                        "Finish": end_dt,
                        "Type": "Season",
                        "Detail": f"{sname} Period #{i}" # Detail for hover text
                    })
            except:
                continue

    # Add holidays
    gh_year = data.get("global_holidays", {}).get(year, {})
    for h in year_obj.get("holidays", []):
        global_ref = h.get("global_reference") or h.get("name")
        if gh := gh_year.get(global_ref):
            try:
                # Add one day to end_dt to ensure plotly draws the last day correctly
                start_dt = datetime.strptime(gh.get("start_date"), "%Y-%m-%d")
                end_dt = datetime.strptime(gh.get("end_date"), "%Y-%m-%d") + timedelta(days=1)
                if start_dt < end_dt:
                    rows.append({
                        "Task": f"Holiday: {h.get('name', '(Unnamed)')}",
                        "Start": start_dt,
                        "Finish": end_dt,
                        "Type": "Holiday",
                        "Detail": f"{h.get('name')} ({global_ref})"
                    })
            except:
                continue

    if not rows:
        today = datetime.now()
        rows.append({
            "Task": "No Data",
            "Start": today,
            "Finish": today + timedelta(days=1),
            "Type": "No Data",
            "Detail": "No Seasons or Holidays Defined"
        })

    df = pd.DataFrame(rows)
    df["Start"] = pd.to_datetime(df["Start"])
    df["Finish"] = pd.to_datetime(df["Finish"])
    
    # Sort: Holidays always on top, then Seasons, then start date
    type_order = {"Holiday": 0, "Season": 1, "No Data": 2}
    df["Order"] = df["Type"].map(type_order)
    df = df.sort_values(by=["Order", "Task", "Start"], ascending=[True, True, True])

    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="Task",
        color="Type",
        title=f"{working.get('display_name', 'Resort')} – {year} Timeline",
        height=max(400, len(df["Task"].unique()) * 35),
        color_discrete_map={'Season': '#42A5F5', 'Holiday': '#EF5350', 'No Data': '#CFD8DC'} # New theme colors
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(tickformat="%d %b %Y")
    fig.update_traces(
        hovertemplate="<b>%{customdata[0]}</b><br>Start: %{base|%d %b %Y}<br>End: %{x|%d %b %Y}<extra></extra>",
        customdata=df[['Detail']].values
    )
    fig.update_layout(
        showlegend=True,
        xaxis_title="Date",
        yaxis_title="Period / Event",
        font=dict(size=12, color='#37474F'), # Dark text for light theme
        plot_bgcolor='white', 
        paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig


def render_gantt_charts_v2(working: Dict[str, Any], years: List[str], data: Dict[str, Any]):
    st.markdown("<div class='section-header'>📊 Visual Timeline</div>", unsafe_allow_html=True)
    tabs = st.tabs([f"📅 {year}" for year in years])
    for tab, year in zip(tabs, years):
        with tab:
            fig = create_gantt_chart_v2(working, year, data)
            st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------------
# GLOBAL SETTINGS
# ----------------------------------------------------------------------
def render_maintenance_fees_v2(data: Dict[str, Any]):
    rates = data.setdefault("configuration", {}).setdefault("maintenance_rates", {})
    st.caption("Define maintenance fee rates per point for each year")
    
    cols = st.columns(4)
    for i, year in enumerate(sorted(rates.keys())):
        with cols[i % 4]:
            current_rate = float(rates.get(year, 0.0))
            new_rate = st.number_input(
                f"💵 {year} Rate",
                value=current_rate,
                step=0.001,
                format="%.4f",
                key=f"mf_{year}"
            )
            if new_rate != current_rate:
                rates[year] = float(new_rate)
                save_data()

    # Allow adding new years to maintenance rates config
    all_years = get_years_from_data(data)
    current_maint_years = set(rates.keys())
    new_maint_years = sorted(list(set(all_years) - current_maint_years))

    if new_maint_years:
        st.markdown("---")
        st.subheader("➕ Add Maintenance Rate Year")
        cols_add = st.columns(4)
        for i, new_year in enumerate(new_maint_years):
            with cols_add[i % 4]:
                if st.button(f"Add {new_year}", key=f"add_mf_year_{new_year}", use_container_width=True):
                    rates[new_year] = 0.0000
                    save_data()
                    st.rerun()


def render_global_holiday_dates_editor_v2(data: Dict[str, Any], years: List[str]):
    global_holidays = data.setdefault("global_holidays", {})
    
    for year in years:
        with st.expander(f"📆 {year} Global Holiday Definitions", expanded=False):
            holidays = global_holidays.setdefault(year, {})
            
            # Display Existing Holidays
            st.markdown("##### Existing Holidays")
            for i, (name, obj) in enumerate(list(holidays.items())):
                with st.container(border=True):
                    st.markdown(f"**🎉 {name}**")
                    col1, col2, col3 = st.columns([3, 3, 1])
                    with col1:
                        new_start = st.date_input(
                            "Start date",
                            safe_date(obj.get("start_date") or f"{year}-01-01"),
                            key=f"ghs_{year}_{i}",
                            label_visibility="collapsed"
                        )
                    with col2:
                        new_end = st.date_input(
                            "End date",
                            safe_date(obj.get("end_date") or f"{year}-01-07"),
                            key=f"ghe_{year}_{i}",
                            label_visibility="collapsed"
                        )
                    with col3:
                        st.markdown("<div style='height: 27px;'></div>", unsafe_allow_html=True) # Spacer
                        if st.button("🗑️", key=f"ghd_{year}_{i}", use_container_width=True):
                            del holidays[name]
                            save_data()
                            st.rerun()

                    obj["start_date"] = new_start.isoformat()
                    obj["end_date"] = new_end.isoformat()
                    
                    col_type, col_regions = st.columns(2)
                    with col_type:
                        new_type = st.text_input("Type", value=obj.get("type", "other"), key=f"ght_{year}_{i}")
                        obj["type"] = new_type or "other"
                    
                    with col_regions:
                        regions_str = ", ".join(obj.get("regions", []))
                        new_regions = st.text_input("Regions (comma-separated)", value=regions_str, key=f"ghr_{year}_{i}")
                        obj["regions"] = [r.strip() for r in new_regions.split(",") if r.strip()]
                    save_data()

            st.markdown("---")
            st.markdown("##### Add New Global Holiday")
            
            col_name, col_start, col_end, col_add = st.columns([3, 2, 2, 1])
            with col_name:
                new_name = st.text_input(f"New holiday name", key=f"gh_new_name_{year}", placeholder="e.g., New Year")
            with col_start:
                try:
                    default_start = datetime.strptime(f"{year}-01-01", "%Y-%m-%d").date()
                except ValueError:
                    default_start = date.today()
                
                new_start = st.date_input("Start", default_start, key=f"gh_new_start_{year}")
            with col_end:
                try:
                    default_end = (datetime.strptime(f"{year}-01-01", "%Y-%m-%d") + timedelta(days=6)).date()
                except ValueError:
                    default_end = date.today()
                    
                new_end = st.date_input("End", default_end, key=f"gh_new_end_{year}")

            with col_add:
                st.markdown("<div style='height: 27px;'></div>", unsafe_allow_html=True) # Spacer
                if st.button("➕", key=f"gh_add_{year}", use_container_width=True) and new_name and new_name not in holidays:
                    holidays[new_name] = {
                        "start_date": new_start.isoformat(),
                        "end_date": new_end.isoformat(),
                        "type": "other",
                        "regions": ["global"]
                    }
                    save_data()
                    st.rerun()


def render_global_settings_v2(data: Dict[str, Any], years: List[str]):
    st.markdown("<div class='section-header'>⚙️ Global Configuration</div>", unsafe_allow_html=True)
    
    # Use tabs for global settings for clarity
    tab_mf, tab_gh = st.tabs(["💰 Maintenance Fees", "🎅 Global Holiday Dates"])
    
    with tab_mf:
        render_maintenance_fees_v2(data)
    
    with tab_gh:
        render_global_holiday_dates_editor_v2(data, years)


# ----------------------------------------------------------------------
# MAIN APPLICATION
# ----------------------------------------------------------------------
def main():
    setup_page()
    initialize_session_state()

    # Auto-load data file
    if st.session_state.data is None:
        try:
            # Placeholder for attempting to load a local file if available
            pass 
        except Exception as e:
            st.toast(f"⚠️ Auto-load error: {str(e)}", icon="⚠️")

    # Sidebar
    with st.sidebar:
        st.markdown("<div style='text-align: center; padding: 20px;'><h2 style='color: white;'>🏨 MVC Editor</h2></div>", unsafe_allow_html=True)
        handle_file_upload()
        if st.session_state.data:
            create_download_button_v2(st.session_state.data)
            handle_file_verification()
            handle_merge_from_another_file_v2(st.session_state.data)
            
            # Show metrics
            st.markdown("---")
            data = st.session_state.data
            resorts_count = len(data.get("resorts", []))
            years_count = len(get_years_from_data(data))
            
            st.markdown(f"""
                <div class='metric-card'>
                    <div class='metric-value'>{resorts_count}</div>
                    <div class='metric-label'>Resorts</div>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
                <div class='metric-card'>
                    <div class='metric-value'>{years_count}</div>
                    <div class='metric-label'>Years Configured</div>
                </div>
            """, unsafe_allow_html=True)
        
        show_save_indicator()

    # Main content
    st.markdown("<div class='big-font'>MVC Resort Editor V2</div>", unsafe_allow_html=True)

    if not st.session_state.data:
        st.markdown("""
            <div class='info-box'>
                <h3>👋 Welcome!</h3>
                <p>Upload your V2 data.json file from the sidebar to begin editing resort data.</p>
            </div>
        """, unsafe_allow_html=True)
        return

    data = st.session_state.data
    resorts = get_resort_list(data)
    years = get_years_from_data(data)
    current_resort_id = st.session_state.current_resort_id
    previous_resort_id = st.session_state.previous_resort_id

    # UI Flow Step 1: Selection and Creation
    render_resort_grid(resorts, current_resort_id)
    handle_resort_switch_v2(data, current_resort_id, previous_resort_id)
    handle_resort_creation_v2(data, current_resort_id)


    # UI Flow Step 2: Resort Editor (Visible only when a resort is selected)
    working = None
    if current_resort_id:
        working_resorts = st.session_state.working_resorts
        if current_resort_id not in working_resorts:
            resort_obj = find_resort_by_id(data, current_resort_id)
            if resort_obj:
                working_resorts[current_resort_id] = copy.deepcopy(resort_obj)
        working = working_resorts.get(current_resort_id)

    if working:
        name = working.get("display_name", current_resort_id)
        st.markdown(f"### **{name}**")

        render_validation_panel_v2(working, data, years)
        
        # Action Bar: Save and Delete are placed side-by-side
        col_save, col_del_placeholder = st.columns([0.7, 0.3])
        with col_save:
            render_save_button_v2(data, working, current_resort_id)
        with col_del_placeholder:
            handle_resort_deletion_v2(data, current_resort_id)
            # handle_resort_deletion_v2 uses st.stop() when confirming, interrupting the flow correctly

        st.markdown("---")

        # --- High-Level Tabs for Main Editing Content ---
        tab_dates, tab_points, tab_summary = st.tabs(
            ["🗓️ Dates & Timeline", "🎯 Room Points & Rates", "🏠 Summary & Details"]
        )

        with tab_dates:
            # Group 1: Visual Timeline and Season Date Definitions
            render_gantt_charts_v2(working, years, data)
            render_season_dates_editor_v2(working, years, current_resort_id)

        with tab_points:
            # Group 2: Master points and Holiday point management
            render_reference_points_editor_v2(working, years, current_resort_id)
            render_holiday_management_v2(working, years, current_resort_id)

        with tab_summary:
            # Group 3: Final summary table and other specific configurations
            render_resort_summary_v2(working)
            st.markdown("---")
            # Placeholder for other config fields (e.g., timezone, region code)
            st.markdown("#### Resort Metadata")
            working["code"] = st.text_input("Resort Code", value=working.get("code", "RST"), key=rk(current_resort_id, "code_detail"))
            working["region"] = st.text_input("Region", value=working.get("region", "Unknown"), key=rk(current_resort_id, "region_detail"))
            working["timezone"] = st.text_input("Timezone", value=working.get("timezone", "UTC"), key=rk(current_resort_id, "timezone_detail"))


    # UI Flow Step 3: Global Settings (Always accessible)
    render_global_settings_v2(data, years)

    st.markdown("""
    <div class='info-box'>
        V2 MODE • Seasons are synchronized by name across all years • Dates are per year • Master room types & points replicated everywhere
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
