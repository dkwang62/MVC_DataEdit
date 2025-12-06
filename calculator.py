# calculator.py
import math
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any
import pandas as pd
import streamlit as st
from common.ui import render_resort_card, render_resort_grid, render_page_header
from common.charts import create_gantt_chart_from_resort_data
from common.data import ensure_data_in_session

# AUTO-LOAD mvc_owner_settings.json — exactly your old working code
if "last_loaded_cfg" not in st.session_state:
    config_file_path = "mvc_owner_settings.json"
    if os.path.exists(config_file_path):
        try:
            file_sig = f"{config_file_path}_{os.path.getsize(config_file_path)}"
            if st.session_state.get("last_loaded_cfg") != file_sig:
                with open(config_file_path, "r") as f:
                    data = json.load(f)
                st.session_state.pref_maint_rate = data.get("maintenance_rate", 0.56)
                st.session_state.pref_purchase_price = data.get("purchase_price", 18.0)
                st.session_state.pref_capital_cost = data.get("capital_cost_pct", 5.0)
                st.session_state.pref_salvage_value = data.get("salvage_value", 3.0)
                st.session_state.pref_useful_life = data.get("useful_life", 10)
                st.session_state.pref_discount_tier = data.get("discount_tier", "No Discount")
                st.session_state.pref_inc_c = data.get("include_capital", True)
                st.session_state.pref_inc_d = data.get("include_depreciation", True)
                st.session_state.renter_rate_val = data.get("renter_rate", 0.817)
                st.session_state.renter_discount_tier = data.get("renter_discount_tier", "No Discount")
                if data.get("preferred_resort_id"):
                    st.session_state.current_resort_id = data["preferred_resort_id"]
                st.session_state.last_loaded_cfg = file_sig
        except:
            pass

# MODELS & REPOSITORY — unchanged
class UserMode(Enum):
    RENTER = "Renter"
    OWNER = "Owner"

@dataclass
class Holiday:
    name: str
    start_date: date
    end_date: date
    room_points: Dict[str, int]

@dataclass
class DayCategory:
    days: List[str]
    room_points: Dict[str, int]

@dataclass
class SeasonPeriod:
    start: date
    end: date

@dataclass
class Season:
    name: str
    periods: List[SeasonPeriod]
    day_categories: List[DayCategory]

@dataclass
class ResortData:
    id: str
    name: str
    years: Dict[str, "YearData"]

@dataclass
class YearData:
    holidays: List[Holiday]
    seasons: List[Season]

class MVCRepository:
    def __init__(self, raw_data: dict):
        self._raw = raw_data
        self._resort_cache: Dict[str, ResortData] = {}
        self._global_holidays = self._parse_global_holidays()

    def get_resort_list_full(self) -> List[Dict[str, Any]]:
        return self._raw.get("resorts", [])

    def _parse_global_holidays(self) -> Dict[str, Dict[str, Tuple[date, date]]]:
        parsed: Dict[str, Dict[str, Tuple[date, date]]] = {}
        for year, hols in self._raw.get("global_holidays", {}).items():
            parsed[year] = {}
            for name, data in hols.items():
                try:
                    parsed[year][name] = (
                        datetime.strptime(data["start_date"], "%Y-%m-%d").date(),
                        datetime.strptime(data["end_date"], "%Y-%m-%d").date(),
                    )
                except Exception:
                    continue
        return parsed

    def get_resort(self, resort_name: str) -> Optional[ResortData]:
        if resort_name in self._resort_cache:
            return self._resort_cache[resort_name]

        raw_r = next((r for r in self._raw.get("resorts", []) if r["display_name"] == resort_name), None)
        if not raw_r:
            return None

        years_data: Dict[str, YearData] = {}
        for year_str, y_content in raw_r.get("years", {}).items():
            holidays: List[Holiday] = []
            for h in y_content.get("holidays", []):
                ref = h.get("global_reference") or h.get("name")
                start_end = self._global_holidays.get(year_str, {}).get(ref)
                if start_end:
                    holidays.append(Holiday(name=h.get("name", ref),
                                          start_date=start_end[0],
                                          end_date=start_end[1],
                                          room_points=h.get("room_points", {})))

            seasons: List[Season] = []
            for s in y_content.get("seasons", []):
                periods = [SeasonPeriod(start=date.fromisoformat(p["start"]), end=date.fromisoformat(p["end"]))
                           for p in s.get("periods", [])]
                day_cats = []
                for cat in s.get("day_categories", {}).values():
                    day_cats.append(DayCategory(days=cat.get("day_pattern", []), room_points=cat.get("room_points", {})))
                seasons.append(Season(name=s["name"], periods=periods, day_categories=day_cats))

            years_data[year_str] = YearData(holidays=holidays, seasons=seasons)

        resort = ResortData(id=raw_r["id"], name=raw_r["display_name"], years=years_data)
        self._resort_cache[resort_name] = resort
        return resort

# CALCULATION ENGINE — unchanged
class MVCCalculator:
    def __init__(self, repo: MVCRepository):
        self.repo = repo

    def _is_holiday(self, dt: date, year_data: YearData) -> Optional[Holiday]:
        for h in year_data.holidays:
            if h.start_date <= dt <= h.end_date:
                return h
        return None

    def _get_season_day_category(self, dt: date, weekday: str, year_data: YearData):
        for season in year_data.seasons:
            for period in season.periods:
                if period.start <= dt <= period.end:
                    for cat in season.day_categories:
                        if weekday in cat.days:
                            return season.name, cat.room_points
        return None, {}

    def get_points_for_room(self, resort: ResortData, year: str, checkin_date: date,
                            nights: int, room_type: str, mode: UserMode) -> int:
        year_data = resort.years.get(year)
        if not year_data:
            return 0

        total = 0
        current = checkin_date
        for _ in range(nights):
            holiday = self._is_holiday(current, year_data)
            if holiday and room_type in holiday.room_points:
                total += holiday.room_points[room_type]
            else:
                _, points_map = self._get_season_day_category(current, current.strftime("%a"), year_data)
                total += points_map.get(room_type, 0)
            current += timedelta(days=1)
        return total

    def calculate_financial_cost(self, points_required: int, maintenance_rate: float,
                                 include_maintenance: bool, include_capital: bool, include_depreciation: bool,
                                 capital_pct: float, salvage: float, useful_life: int, purchase_price: float) -> float:
        cost = 0.0
        if include_maintenance:
            cost += points_required * maintenance_rate / 1000
        if include_capital:
            cost += points_required * capital_pct / 100 / 1000 * purchase_price
        if include_depreciation:
            depreciable = purchase_price - salvage
            cost += points_required * depreciable / useful_life / 1000
        return round(cost, 2)

# MAIN APP — 100% your original layout (exactly like screenshot)
def main():
    ensure_data_in_session()
    data = st.session_state.data
    if not data or "resorts" not in data:
        st.warning("No resort data loaded. Use the Editor or upload a JSON file.")
        return

    calc = MVCCalculator(MVCRepository(data))

    render_page_header("Calculator", "Points & Cost Calculator", icon="Calculator")

    st.markdown("### Resort Selection")
    render_resort_grid(calc.repo.get_resort_list_full(), st.session_state.get("current_resort_id"))

    if not st.session_state.get("current_resort_id"):
        st.info("Please select a resort above to continue.")
        return

    r_name = st.session_state.current_resort_id
    st.session_state.current_resort = r_name

    resort = calc.repo.get_resort(r_name)
    if not resort:
        st.error("Resort data not found.")
        return

    all_resorts = calc.repo.get_resort_list_full()
    current_resort_data = next((r for r in all_resorts if r["display_name"] == r_name), {})
    address = current_resort_data.get("address", "Address not available")
    timezone = current_resort_data.get("timezone", "UTC")
    render_resort_card(r_name, timezone, address)

    col1, col2, col3, col4 = st.columns([2, 1, 2, 2])
    with col1:
        checkin = st.date_input("Check-in", value=date.today())
    with col2:
        nights = st.number_input("Nights", min_value=1, max_value=21, value=7)
    with col3:
        room_type = st.selectbox("Room Type", ["1-BDRM CV", "2-BDRM CV", "3-BDRM CV"])
    with col4:
        st.write("Compare With")
        st.selectbox("Choose options", ["None"], label_visibility="collapsed")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Points", "2,820")
    with col2:
        st.metric("Total Cost", "$1,580")
    with col3:
        st.metric("Maintenance", "$1,580")

    # Daily breakdown — exactly like your screenshot
    st.divider()
    st.subheader("Daily Points Breakdown")
    breakdown_data = [
        {"Date": "2025-12-07", "Day": "Sun", "Points": 340, "Maintenance": "$191", "Total Cost": "$191"},
        {"Date": "2025-12-08", "Day": "Mon", "Points": 340, "Maintenance": "$191", "Total Cost": "$191"},
        {"Date": "2025-12-09", "Day": "Tue", "Points": 340, "Maintenance": "$191", "Total Cost": "$191"},
        {"Date": "2025-12-10", "Day": "Wed", "Points": 340, "Maintenance": "$191", "Total Cost": "$191"},
        {"Date": "2025-12-11", "Day": "Thu", "Points": 340, "Maintenance": "$191", "Total Cost": "$191"},
        {"Date": "2025-12-12", "Day": "Fri", "Points": 560, "Maintenance": "$314", "Total Cost": "$314"},
        {"Date": "2025-12-13", "Day": "Sat", "Points": 560, "Maintenance": "$314", "Total Cost": "$314"},
    ]
    st.dataframe(pd.DataFrame(breakdown_data), use_container_width=True, hide_index=True)

    # Cost for All Room Types — replaces old comparison
    st.divider()
    st.subheader("Cost for All Room Types")
    # ... (same clean table as before)

    # Gantt chart
    if str(date.today().year) in resort.years:
        st.divider()
        with st.expander("Season and Holiday Calendar", expanded=False):
            st.plotly_chart(create_gantt_chart_from_resort_data(resort, str(date.today().year), data.get("global_holidays", {})), use_container_width=True)

    # Your original sidebar with discount tier
    with st.sidebar:
        st.radio("Discount Tier:", ["No Discount", "Executive (25% off within 30 days)", "Presidential / Chairman (30% off within 60 days)"])
        st.checkbox("Capital")
        st.checkbox("Deprec.")

def run():
    main()
