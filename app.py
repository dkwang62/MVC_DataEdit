import streamlit as st
import json
import copy
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
# ----------------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------------
YEARS = ["2025", "2026"]
DAY_TYPES = ["Mon-Thu", "Fri-Sat", "Sun", "Sun-Thu"]
HOLIDAY_SEASON_KEY = "Holiday Week"
DEFAULT_POINTS = {
    "Mon-Thu": 100,
    "Fri-Sat": 200,
    "Sun": 150,
    "Sun-Thu": 120
}
DEFAULT_HOLIDAY_POINTS = {
    "Doubles": 1750,
    "King": 1750,
    "King City": 1925,
    "2-Bedroom": 3500,
}
INPUT_FILENAME = "data_v1.json"
OUTPUT_FILENAME = "data_v2.json"
# ----------------------------------------------------------------------
# PAGE CONFIG & STYLES
# ----------------------------------------------------------------------
def setup_page():
    st.set_page_config(page_title="MVC Resort Editor", layout="wide")
    st.markdown("""
    <style>
        .big-font { font-size: 42px !important; font-weight: bold; color: #1f77b4; }
        .stButton>button { min-height: 50px; font-weight: bold; }
        .success-box { background: #d4edda; padding: 20px; border-radius: 12px; border: 2px solid #c3e6cb; margin: 20px 0; font-weight: bold; text-align: center; font-size: 18px; }
        .rename-input { margin: 5px 0; }
        .section-header { border-bottom: 2px solid #1f77b4; padding-bottom: 10px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)
# ----------------------------------------------------------------------
# SESSION STATE MANAGEMENT
# ----------------------------------------------------------------------
def initialize_session_state():
    """Initialize all session state variables"""
    defaults = {
        'refresh_trigger': False,
        'last_upload_sig': None,
        'delete_confirm': False,
        'data': None,
        'current_resort': None,
        'previous_resort': None,
        'working_resorts': {},
        'editing_season': None,
        'editing_room': None,
        'last_save_time': None
    }
 
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
def save_data():
    """Update last save time (history managed by callers)."""
    st.session_state.last_save_time = datetime.now()
def show_save_indicator():
    """Show a small save indicator."""
    if st.session_state.last_save_time:
        elapsed = (datetime.now() - st.session_state.last_save_time).total_seconds()
        if elapsed < 2: # Show for 2 seconds after save
            st.sidebar.success("✓ Saved", icon="✅")
def reset_state_for_new_file():
    """Clear all file-specific session state when a new file is loaded."""
    # keep last_upload_sig OUTSIDE this reset (we set it after successful load)
    keys_to_reset = [
        "data",
        "current_resort",
        "previous_resort",
        "working_resorts",
        "editing_season",
        "editing_room",
        "delete_confirm",
        "last_save_time",
    ]
    for k in keys_to_reset:
        st.session_state[k] = None if k != "working_resorts" else {}
# ----------------------------------------------------------------------
# DATA MANAGEMENT
# ----------------------------------------------------------------------
def safe_date(date_str: Optional[str], default: str = "2025-01-01") -> datetime.date:
    """Safely converts a date string to a datetime.date object."""
    if not date_str or not isinstance(date_str, str):
        return datetime.strptime(default, "%Y-%m-%d").date()
 
    try:
        return datetime.fromisoformat(date_str.strip()).date()
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return datetime.strptime(default, "%Y-%m-%d").date()
def is_duplicate_resort_name(name: str, resorts: List[str]) -> bool:
    """Check if resort name already exists (case-insensitive)."""
    name_clean = name.strip().lower()
    return any(r.strip().lower() == name_clean for r in resorts)
# ----------------------------------------------------------------------
# FILE UPLOAD/DOWNLOAD COMPONENTS
# ----------------------------------------------------------------------
def handle_file_upload():
    """Handle JSON file upload with signature tracking."""
    uploaded = st.file_uploader("Upload data_v1.json", type="json", key="file_uploader")
 
    if uploaded:
        size = getattr(uploaded, "size", 0)
        current_sig = f"{uploaded.name}:{size}"
     
        if current_sig != st.session_state.last_upload_sig:
            try:
                raw_data = json.load(uploaded)
                # 🔴 NEW: clear any old-file state
                reset_state_for_new_file()
                st.session_state.data = raw_data
                st.session_state.last_upload_sig = current_sig
                resorts_list = raw_data.get("resorts_list", [])
                st.success(f"✅ Loaded {len(resorts_list)} resorts")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error loading file: {e}")
def convert_v1_to_v2_schema(v1_data: Dict) -> Dict:
    """
    Convert your existing v1 structure (resorts_list + season_blocks +
    reference_points + holiday_weeks + global_dates + maintenance_rates)
    into the v2 structure (schema_version + metadata + configuration +
    room_type_catalog + global_holidays + resorts[]).
    """
    from datetime import datetime

    # Top-level shell
    v2: Dict[str, Any] = {
        "schema_version": "2.0.0",
        "metadata": {
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "data_year_range": [int(YEARS[0]), int(YEARS[-1])],
            "description": "Marriott Vacation Club points and pricing data (auto-converted from v1)",
            "maintainer": "MVC Resort Editor",
        },
        "configuration": {
            # Directly from v1
            "maintenance_rates": v1_data.get("maintenance_rates", {}),
            # You can fill these if you want later
            "discount_policies": {},
            "default_values": {},
        },
        # Build a simple catalog from your v1 room_view_legend
        "room_type_catalog": {
            code: {
                "display_name": name,
                "category": "standard",   # you can refine categories later
            }
            for code, name in v1_data.get("room_view_legend", {}).items()
        },
        "global_holidays": {},
        "resorts": [],
        "migration_notes": {
            "source_schema": v1_data.get("$schema", "v1"),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
    }

    # ---- global_holidays from v1.global_dates ----
    for year, holidays in v1_data.get("global_dates", {}).items():
        year_dict: Dict[str, Any] = {}
        for holiday_name, date_pair in holidays.items():
            start, end = date_pair
            year_dict[holiday_name] = {
                "start_date": start,
                "end_date": end,
                "type": "custom_holiday",   # we don't know the real type; safe default
                "regions": ["global"],
            }
        v2["global_holidays"][year] = year_dict

    # Helper: map v1 day-type labels to v2 keys + patterns
    def map_day_type(dt: str) -> Tuple[str, List[str]]:
        if dt == "Fri-Sat":
            return "fri_sat", ["Fri", "Sat"]
        if dt == "Sun-Thu":
            return "sun_thu", ["Sun", "Mon", "Tue", "Wed", "Thu"]
        if dt == "Mon-Thu":
            return "mon_thu", ["Mon", "Tue", "Wed", "Thu"]
        if dt == "Sun":
            return "sun", ["Sun"]
        # Fallback: generic name, empty pattern
        key = dt.lower().replace(" ", "_").replace("-", "_")
        return key, []

    # ---- resorts: seasons + holidays ----
    for resort_name in v1_data.get("resorts_list", []):
        resort_obj: Dict[str, Any] = {
            "id": resort_name.strip().lower().replace(" ", "-"),  # e.g. "Aruba Ocean" -> "aruba-ocean"
            "display_name": resort_name,
            # quick-and-dirty code from initials, e.g. "Aruba Ocean" -> "AO"
            "code": "".join(w[0].upper() for w in resort_name.split() if w),
            # these can be refined with a lookup table later if you care
            "region": "Unknown",
            "timezone": "UTC",
            "years": {},
        }

        season_blocks_resort = v1_data.get("season_blocks", {}).get(resort_name, {})
        ref_points_resort = v1_data.get("reference_points", {}).get(resort_name, {})
        holiday_weeks_resort_all = v1_data.get("holiday_weeks", {}).get(resort_name, {})

        for year in YEARS:
            seasons_out: List[Dict[str, Any]] = []
            holidays_out: List[Dict[str, Any]] = []

            # ---- seasons: from season_blocks + reference_points ----
            sblocks_year = season_blocks_resort.get(year, {})
            for season_name, ranges in sblocks_year.items():
                season_ref = ref_points_resort.get(season_name, {})

                season_obj: Dict[str, Any] = {
                    "name": season_name,
                    "periods": [{"start": s, "end": e} for s, e in ranges],
                    "day_categories": {},
                }

                for day_type, rooms_dict in season_ref.items():
                    # Only actual day-type keys; ignore holidays here
                    if day_type in ("Fri-Sat", "Sun-Thu", "Mon-Thu", "Sun"):
                        key, pattern = map_day_type(day_type)
                        season_obj["day_categories"][key] = {
                            "day_pattern": pattern,
                            "room_points": rooms_dict,
                        }

                seasons_out.append(season_obj)

            # ---- holidays: from reference_points["Holiday Week"] + holiday_weeks ----
            holiday_section = ref_points_resort.get("Holiday Week", {})
            holiday_weeks_resort_year = holiday_weeks_resort_all.get(year, {})

            for holiday_name, room_points in holiday_section.items():
                ref = holiday_weeks_resort_year.get(holiday_name)

                # If stored as "global:HolidayName", strip the prefix so it matches global_holidays keys
                if isinstance(ref, str) and ref.startswith("global:"):
                    global_ref = ref.split(":", 1)[1]
                else:
                    # fallback: just use the same name
                    global_ref = holiday_name

                holidays_out.append(
                    {
                        "name": holiday_name,
                        "global_reference": global_ref,
                        "room_points": room_points,
                    }
                )

            if seasons_out or holidays_out:
                year_obj: Dict[str, Any] = {}
                if seasons_out:
                    year_obj["seasons"] = seasons_out
                if holidays_out:
                    year_obj["holidays"] = holidays_out
                resort_obj["years"][year] = year_obj

        v2["resorts"].append(resort_obj)

    return v2
def create_download_button(data: Dict):
    """Create download button for current data (v1 → v2)."""
    if data:
        # Convert current in-memory v1 structure to v2 structure
        v2_data = convert_v1_to_v2_schema(copy.deepcopy(data))

        json_data = json.dumps(v2_data, indent=2, ensure_ascii=False)
        st.download_button(
            label="📥 Download v2 Data",
            data=json_data,
            file_name=OUTPUT_FILENAME,
            mime="application/json",
            key="download_btn",
            help="Download converted v2 schema (based on current v1 edits)",
        )
# ----------------------------------------------------------------------
# VERIFY DOWNLOADED FILE
# ----------------------------------------------------------------------
def handle_file_verification():
    """Handle verification of downloaded file against current memory."""
    st.sidebar.markdown("### Verify Downloaded File")
    verify_upload = st.sidebar.file_uploader(
        "Upload data.json to verify",
        type="json",
        key="verify_uploader"
    )
 
    if verify_upload:
        try:
            uploaded_data = json.load(verify_upload)
            # Generate compact JSON strings with sorted keys for comparison
            current_json = json.dumps(st.session_state.data, sort_keys=True, ensure_ascii=False)
            uploaded_json = json.dumps(uploaded_data, sort_keys=True, ensure_ascii=False)
         
            if current_json == uploaded_json:
                st.sidebar.success("✅ The uploaded file matches the current data in memory.")
            else:
                st.sidebar.error("❌ The uploaded file does NOT match. Download again after confirming changes are saved.")
        except json.JSONDecodeError:
            st.sidebar.error("❌ Invalid JSON file uploaded.")
        except Exception as e:
            st.sidebar.error(f"❌ Error: {str(e)}")
# ----------------------------------------------------------------------
# RESORT MANAGEMENT COMPONENTS
# ----------------------------------------------------------------------
def render_resort_grid(resorts: List[str], current_resort: str):
    """Render the resort selection grid."""
    st.subheader("🏨 Select Resort")
    cols = st.columns(6)
 
    for i, resort in enumerate(resorts):
        with cols[i % 6]:
            button_type = "primary" if current_resort == resort else "secondary"
            if st.button(resort, key=f"resort_btn_{i}", type=button_type):
                st.session_state.current_resort = resort
                st.session_state.delete_confirm = False
                st.rerun()
def handle_resort_creation(data: Dict, resorts: List[str]):
    """Handle creation of new resorts."""
    with st.expander("➕ Add New Resort", expanded=True):
        new_name = st.text_input("Resort Name", placeholder="Pulse San Francisco", key="new_resort_name")
        col1, col2 = st.columns(2)
     
        with col1:
            if st.button("Create Blank", key="create_blank_btn") and new_name:
                new_name_clean = new_name.strip()
                if not new_name_clean:
                    st.error("Resort name cannot be empty")
                elif is_duplicate_resort_name(new_name_clean, resorts):
                    st.error("❌ Resort name already exists")
                else:
                    create_blank_resort(data, new_name_clean)
             
        with col2:
            if st.button("Clone Current", key="copy_current_btn", type="primary") and st.session_state.current_resort and new_name:
                new_name_clean = new_name.strip()
                if not new_name_clean:
                    st.error("Resort name cannot be empty")
                elif is_duplicate_resort_name(new_name_clean, resorts):
                    st.error("❌ Resort name already exists")
                else:
                    clone_resort(data, st.session_state.current_resort, new_name_clean)
def create_blank_resort(data: Dict, new_name: str):
    """Create a new blank resort."""
    data.setdefault("resorts_list", []).append(new_name)
    data.setdefault("season_blocks", {})[new_name] = {year: {} for year in YEARS}
    data.setdefault("reference_points", {})[new_name] = {}
    data.setdefault("holiday_weeks", {})[new_name] = {year: {} for year in YEARS}
    st.session_state.current_resort = new_name
    save_data()
    st.rerun()
def clone_resort(data: Dict, source: str, target: str):
    """Clone an existing resort."""
    data.setdefault("resorts_list", []).append(target)
    season_blocks = data.get("season_blocks", {})
    ref_points = data.get("reference_points", {})
    holiday_weeks = data.get("holiday_weeks", {})
    data.setdefault("season_blocks", {})[target] = copy.deepcopy(
        season_blocks.get(source, {year: {} for year in YEARS})
    )
    data.setdefault("reference_points", {})[target] = copy.deepcopy(
        ref_points.get(source, {})
    )
    data.setdefault("holiday_weeks", {})[target] = copy.deepcopy(
        holiday_weeks.get(source, {year: {} for year in YEARS})
    )
    st.session_state.current_resort = target
    save_data()
    st.success(f"✅ Cloned **{source}** → **{target}**")
    st.rerun()
def handle_resort_deletion(data: Dict, current_resort: str):
    """Handle resort deletion with confirmation."""
    if not st.session_state.delete_confirm:
        if st.button("🗑️ Delete Resort", key="delete_resort_init", type="secondary"):
            st.session_state.delete_confirm = True
            st.rerun()
    else:
        st.warning(f"⚠️ Are you sure you want to permanently delete **{current_resort}**?")
        col1, col2 = st.columns(2)
     
        with col1:
            if st.checkbox("I understand — this cannot be undone", key=f"delete_confirm_check_{current_resort}"):
                if st.button("🔥 DELETE FOREVER", key=f"delete_resort_final_{current_resort}", type="primary"):
                    delete_resort(data, current_resort)
                 
        with col2:
            if st.button("❌ Cancel", key=f"delete_cancel_{current_resort}"):
                st.session_state.delete_confirm = False
                st.rerun()
 
    if st.session_state.delete_confirm:
        st.stop()
def delete_resort(data: Dict, resort: str):
    """Delete a resort from all data structures."""
    for category in ["season_blocks", "reference_points", "holiday_weeks"]:
        data.get(category, {}).pop(resort, None)
    data["resorts_list"].remove(resort)
    st.session_state.current_resort = None
    st.session_state.delete_confirm = False
    if resort in st.session_state.working_resorts:
        del st.session_state.working_resorts[resort]
    save_data()
    st.rerun()
# ----------------------------------------------------------------------
# SEASON MANAGEMENT
# ----------------------------------------------------------------------
def get_all_seasons(working: Dict) -> List[str]:
    """Get all unique seasons used across years and categories."""
    seasons: Set[str] = set()
    season_blocks = working.get("season_blocks", {})
    ref_points = working.get("reference_points", {})
    for year in YEARS:
        seasons.update(season_blocks.get(year, {}).keys())
    seasons.update(ref_points.keys())
    return sorted(seasons)
def handle_season_renaming(working: Dict):
    """Handle renaming of seasons."""
    st.subheader("🏷️ Rename Seasons")
    st.caption("Applies to all years & sections")
 
    seasons = get_all_seasons(working)
 
    for old_name in seasons:
        if old_name == HOLIDAY_SEASON_KEY:
            continue
         
        col1, col2 = st.columns([3, 1])
        with col1:
            new_name = st.text_input(f"Rename **{old_name}** →", value=old_name, key=f"rename_season_{old_name}")
        with col2:
            if st.button("Apply", key=f"apply_rename_season_{old_name}") and new_name != old_name and new_name:
                rename_season(working, old_name, new_name)
def rename_season(working: Dict, old_name: str, new_name: str):
    """Rename a season across all data structures."""
    if new_name == HOLIDAY_SEASON_KEY:
        st.error("❌ Cannot rename to reserved season name 'Holiday Week'")
        return
    # Update season blocks
    season_blocks = working.get("season_blocks", {})
    for year in YEARS:
        year_block = season_blocks.get(year, {})
        if old_name in year_block:
            year_block[new_name] = year_block.pop(old_name)
    # Update reference points only
    ref_points = working.get("reference_points", {})
    if old_name in ref_points:
        ref_points[new_name] = ref_points.pop(old_name)
    st.success(f"✅ Renamed **{old_name}** → **{new_name}**")
    st.rerun()
def handle_season_operations(working: Dict):
    """Handle adding and deleting seasons - ADDED confirmation."""
    st.subheader("➕➖ Add / Delete Season")
    seasons = get_all_seasons(working)
 
    col1, col2 = st.columns(2)
 
    with col1:
        new_season = st.text_input("New Season Name", key="new_season_input")
        if st.button("Add Season", key="add_season_btn") and new_season:
            if new_season.strip() and not any(s.lower() == new_season.lower() for s in seasons):
                add_season(working, new_season.strip())
            else:
                st.error("Season name already exists or is invalid")
 
    with col2:
        del_season = st.selectbox("Delete Season", [""] + seasons, key="del_season_select")
        if del_season:
            if st.button("Delete Season", key="delete_season_btn"):
                # Confirmation for destructive operation
                if st.session_state.get(f"confirm_delete_season_{del_season}"):
                    delete_season(working, del_season)
                    st.session_state[f"confirm_delete_season_{del_season}"] = False
                else:
                    st.session_state[f"confirm_delete_season_{del_season}"] = True
                    st.warning(f"Are you sure you want to delete season '{del_season}'?")
                    if st.button("Confirm Delete", key=f"confirm_del_season_{del_season}"):
                        delete_season(working, del_season)
                        st.session_state[f"confirm_delete_season_{del_season}"] = False
                        st.rerun()
def add_season(working: Dict, season: str):
    """Add a new season to all years and categories."""
    season = season.strip()
    if not season:
        st.error("Season name cannot be empty")
        return
    if season == HOLIDAY_SEASON_KEY:
        st.error("❌ Reserved season name 'Holiday Week' cannot be used")
        return
    season_blocks = working.setdefault("season_blocks", {})
    for year in YEARS:
        season_blocks.setdefault(year, {})[season] = []
    working.setdefault("reference_points", {})[season] = {}
    st.success(f"✅ Added **{season}**")
    st.rerun()
def delete_season(working: Dict, season: str):
    """Delete a season from all data structures."""
    season_blocks = working.get("season_blocks", {})
    for year in YEARS:
        season_blocks.get(year, {}).pop(season, None)
    ref_points = working.get("reference_points", {})
    ref_points.pop(season, None)
    st.success(f"✅ Deleted **{season}**")
    st.rerun()
# ----------------------------------------------------------------------
# ROOM TYPE MANAGEMENT
# ----------------------------------------------------------------------
def get_all_room_types(working: Dict) -> List[str]:
    """Get all unique room types used in the resort."""
    rooms: Set[str] = set()
    ref_points = working.get("reference_points", {})
    for season_data in ref_points.values():
        for day_or_room in season_data.values():
            if isinstance(day_or_room, dict):
                rooms.update(day_or_room.keys())
    return sorted(rooms)
def handle_room_renaming(working: Dict):
    """Handle renaming of room types with automatic Reference Points propagation."""
    st.subheader("🚪 Rename Room Types")
    st.caption("Applies everywhere including Reference Points")
 
    rooms = get_all_room_types(working)
 
    for old_room in rooms:
        col1, col2 = st.columns([3, 1])
        with col1:
            new_room = st.text_input(f"Rename **{old_room}** →", value=old_room, key=f"rename_room_{old_room}")
        with col2:
            if st.button("Apply", key=f"apply_rename_room_{old_room}") and new_room != old_room and new_room:
                # Show confirmation for major changes
                if old_room in get_all_room_types(working): # Double-check it still exists
                    rename_room_type(working, old_room, new_room)
                else:
                    st.error("Room type no longer exists or was already renamed")
def rename_room_type(working: Dict, old_name: str, new_name: str):
    """Enhanced room renaming with comprehensive propagation to Reference Points."""
    new_name = new_name.strip()
    if not new_name:
        st.error("Room name cannot be empty")
        return
    if any(r == new_name for r in get_all_room_types(working)):
        st.error("❌ Room name already exists")
        return

    ref_points = working.get("reference_points", {})
    renamed_count = 0

    for season, content in ref_points.items():
        if season == HOLIDAY_SEASON_KEY:
            for holiday, rooms in content.items():
                if old_name in rooms:
                    rooms[new_name] = rooms.pop(old_name)
                    renamed_count += 1
        else:
            for day_type, rooms in content.items():
                if isinstance(rooms, dict) and old_name in rooms:
                    rooms[new_name] = rooms.pop(old_name)
                    renamed_count += 1

    st.success(f"✅ Renamed room '{old_name}' → '{new_name}' in {renamed_count} places")
    st.rerun()
# ----------------------------------------------------------------------
# ... (the rest of the code remains unchanged, including the main() function with the updated auto-load block) ...
# In main(), replace the auto-load with:
if st.session_state.data is None:
    try:
        with open(INPUT_FILENAME, "r") as f:
            raw_data = json.load(f)
            st.session_state.data = raw_data
            resorts_list = raw_data.get("resorts_list", [])
            st.info(f"✅ Automatically loaded {len(resorts_list)} resorts from {INPUT_FILENAME}")
    except FileNotFoundError:
        st.info(f"No {INPUT_FILENAME} found for automatic load. Please upload a file.")
    except Exception as e:
        st.error(f"❌ Error automatically loading {INPUT_FILENAME}: {e}")

# The full code would include all the truncated parts, but since the query has truncations, assume the rest is as-is.
if __name__ == "__main__":
    main()
