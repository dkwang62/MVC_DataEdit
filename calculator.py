import math
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict
import pandas as pd
import plotly.express as px
import streamlit as st
from common.ui import render_resort_card, render_resort_grid, render_page_header
from common.charts import create_gantt_chart_from_resort_data
from common.data import ensure_data_in_session

# ==============================================================================
# LAYER 1: CORE DATA STRUCTURES
# ==============================================================================
class UserMode(Enum):
    RENTER = "Renter"
    OWNER = "Owner"

class DiscountPolicy(Enum):
    NONE = "None"
    EXECUTIVE = "within_30_days" # 25%
    PRESIDENTIAL = "within_60_days" # 30%

@dataclass
class Holiday:
    name: str
    start_date: date
    end_date: date
    room_points: Dict[str, int]

@dataclass
class DayCategory:
    name: str
    days_of_week: List[int] # 0 = Monday ... 6 = Sunday
    room_points: Dict[str, int]

@dataclass
class SeasonPeriod:
    start_date: date
    end_date: date

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

@dataclass
class CalculationResult:
    breakdown_df: pd.DataFrame
    total_points: int
    financial_total: float
    discount_applied: bool
    discounted_days: List[str]
    m_cost: float = 0.0
    c_cost: float = 0.0
    d_cost: float = 0.0

@dataclass
class ComparisonResult:
    pivot_df: pd.DataFrame
    daily_chart_df: pd.DataFrame
    holiday_chart_df: pd.DataFrame

# ==============================================================================
# LAYER 2: REPOSITORY
# ==============================================================================
class MVCRepository:
    def __init__(self, json_data: Dict[str, Any]):
        self.resorts: Dict[str, ResortData] = {}
        self._load_data(json_data)

    def _parse_date(self, date_str: str) -> date:
        return datetime.strptime(date_str, "%Y-%m-%d").date()

    def _load_data(self, data: Dict[str, Any]) -> None:
        for resort_id, resort_info in data.get("resorts", {}).items():
            resort_name = resort_info["name"]
            years_data: Dict[str, YearData] = {}

            for year_str, year_info in resort_info.get("years", {}).items():
                holidays: List[Holiday] = []
                for h in year_info.get("holidays", []):
                    holidays.append(
                        Holiday(
                            name=h["name"],
                            start_date=self._parse_date(h["start_date"]),
                            end_date=self._parse_date(h["end_date"]),
                            room_points=h["room_points"],
                        )
                    )

                seasons: List[Season] = []
                for s in year_info.get("seasons", []):
                    periods: List[SeasonPeriod] = [
                        SeasonPeriod(
                            start_date=self._parse_date(p["start_date"]),
                            end_date=self._parse_date(p["end_date"]),
                        )
                        for p in s.get("periods", [])
                    ]

                    day_categories: List[DayCategory] = []
                    for dc in s.get("day_categories", []):
                        day_categories.append(
                            DayCategory(
                                name=dc["name"],
                                days_of_week=dc["days_of_week"],
                                room_points=dc["room_points"],
                            )
                        )

                    seasons.append(Season(name=s["name"], periods=periods, day_categories=day_categories))

                years_data[year_str] = YearData(holidays=holidays, seasons=seasons)

            self.resorts[resort_name] = ResortData(
                id=resort_id,
                name=resort_name,
                years=years_data,
            )

    def get_resort(self, resort_name: str) -> Optional[ResortData]:
        return self.resorts.get(resort_name)

    def list_resorts(self) -> List[str]:
        return sorted(self.resorts.keys())

    def get_resorts_full(self) -> List[Dict[str, Any]]:
        """
        Returns a list of dicts with minimal resort info used by UI.
        """
        resorts_full = []
        for r_name, resort in self.resorts.items():
            resorts_full.append({
                "id": resort.id,
                "display_name": r_name,
                "resort_name": r_name,
            })
        return resorts_full
    
    def get_resort_info(self, resort_name: str) -> Dict[str, Any]:
        """
        Return user-friendly resort info, such as full name, timezone, address.
        This can be extended without touching the JSON parsing logic above.
        """
        resort = next((r for r in self.get_resorts_full() if r["display_name"] == resort_name), None)
        if resort:
            raw_r = resort
            return {
                "full_name": raw_r.get("resort_name", resort_name),
                "timezone": raw_r.get("timezone", "Unknown"),
                "address": raw_r.get("address", "Address not available"),
            }
        return {
            "full_name": resort_name,
            "timezone": "Unknown",
            "address": "Address not available",
        }

# ==============================================================================
# LAYER 3: SERVICE
# ==============================================================================
class MVCCalculator:
    def __init__(self, repo: MVCRepository):
        self.repo = repo

    def _get_daily_points(self, resort: ResortData, day: date) -> Tuple[Dict[str, int], Optional[Holiday]]:
        year_str = str(day.year)
        if year_str not in resort.years:
            return {}, None
        
        yd = resort.years[year_str]
        
        # Check Holidays
        for h in yd.holidays:
            if h.start_date <= day <= h.end_date:
                return h.room_points, h
        
        # Check Seasons and Day Categories
        for s in yd.seasons:
            for p in s.periods:
                if p.start_date <= day <= p.end_date:
                    for dc in s.day_categories:
                        if day.weekday() in dc.days_of_week:
                            return dc.room_points, None
        
        return {}, None

    def calculate_breakdown(
        self, resort_name: str, room: str, checkin: date, nights: int,
        user_mode: UserMode, rate: float, discount_policy: DiscountPolicy = DiscountPolicy.NONE,
        owner_config: Optional[dict] = None,
    ) -> CalculationResult:
        resort = self.repo.get_resort(resort_name)
        if not resort:
            return CalculationResult(pd.DataFrame(), 0, 0.0, False, [])

        # --- 1. Universal Rate Precision ---
        # Ensure rate is treated identically (2 decimal places) for both modes
        rate = round(float(rate), 2)

        rows: List[Dict[str, Any]] = []
        tot_eff_pts = 0
        tot_financial = 0.0
        tot_m = tot_c = tot_d = 0.0
        disc_applied = False
        disc_days: List[str] = []
        is_owner = user_mode == UserMode.OWNER
        processed_holidays: set[str] = set()
        i = 0
        
        while i < nights:
            d = checkin + timedelta(days=i)
            pts_map, holiday = self._get_daily_points(resort, d)
            
            if holiday and holiday.name not in processed_holidays:
                # Handle full holiday block
                processed_holidays.add(holiday.name)
                raw = pts_map.get(room, 0)
                eff = raw
                holiday_days = (holiday.end_date - holiday.start_date).days + 1
                is_disc = False

                # Discount Logic
                if is_owner:
                    disc_mul = owner_config.get("disc_mul", 1.0) if owner_config else 1.0
                    if disc_mul < 1.0:
                        eff = math.floor(raw * disc_mul)
                        is_disc = True
                else:
                    renter_mul = (
                        0.7 if discount_policy == DiscountPolicy.PRESIDENTIAL
                        else 0.75 if discount_policy == DiscountPolicy.EXECUTIVE
                        else 1.0
                    )
                    if renter_mul < 1.0:
                        eff = math.floor(raw * renter_mul)
                        is_disc = True

                eff *= holiday_days

                if is_disc:
                    disc_applied = True
                    for offset in range(holiday_days):
                        disc_days.append((holiday.start_date + timedelta(days=offset)).strftime("%Y-%m-%d"))

                # Cost Calculation
                cost = 0.0
                m = c = dp = 0.0
                if is_owner and owner_config:
                    m = math.ceil(eff * rate)
                    if owner_config.get("inc_c", False):
                        c = math.ceil(eff * owner_config.get("cap_rate", 0.0))
                    if owner_config.get("inc_d", False):
                        dp = math.ceil(eff * owner_config.get("dep_rate", 0.0))
                    cost = m + c + dp
                else:
                    cost = math.ceil(eff * rate)

                row = {
                    "Date": f"{holiday.name} ({holiday.start_date.strftime('%b %d')} - {holiday.end_date.strftime('%b %d')})",
                    "Day": "", "Points": eff
                }
                
                if is_owner:
                    row["Maintenance"] = m
                    if owner_config.get("inc_c", False):
                        row["Capital Cost"] = c
                    if owner_config.get("inc_d", False):
                        row["Depreciation"] = dp
                    row["Total Cost"] = cost
                else:
                    row[room] = cost
                
                rows.append(row)
                tot_eff_pts += eff
                tot_financial += cost
                tot_m += m
                tot_c += c
                tot_d += dp

                i += holiday_days

            elif not holiday:
                # Handle single day
                raw = pts_map.get(room, 0)
                eff = raw
                is_disc = False

                # Discount Logic
                if is_owner:
                    disc_mul = owner_config.get("disc_mul", 1.0) if owner_config else 1.0
                    if disc_mul < 1.0:
                        eff = math.floor(raw * disc_mul)
                        is_disc = True
                else:
                    renter_mul = (
                        0.7 if discount_policy == DiscountPolicy.PRESIDENTIAL
                        else 0.75 if discount_policy == DiscountPolicy.EXECUTIVE
                        else 1.0
                    )
                    if renter_mul < 1.0:
                        eff = math.floor(raw * renter_mul)
                        is_disc = True

                if is_disc:
                    disc_applied = True
                    disc_days.append(d.strftime("%Y-%m-%d"))

                # Cost Calculation
                cost = 0.0
                m = c = dp = 0.0
                if is_owner and owner_config:
                    m = math.ceil(eff * rate)
                    if owner_config.get("inc_c", False):
                        c = math.ceil(eff * owner_config.get("cap_rate", 0.0))
                    if owner_config.get("inc_d", False):
                        dp = math.ceil(eff * owner_config.get("dep_rate", 0.0))
                    cost = m + c + dp
                else:
                    cost = math.ceil(eff * rate)

                row = {
                    "Date": d.strftime("%Y-%m-%d"),
                    "Day": d.strftime("%a"),
                    "Points": eff
                }
                
                if is_owner:
                    row["Maintenance"] = m
                    if owner_config.get("inc_c", False):
                        row["Capital Cost"] = c
                    if owner_config.get("inc_d", False):
                        row["Depreciation"] = dp
                    row["Total Cost"] = cost
                else:
                    row[room] = cost
                
                rows.append(row)
                tot_eff_pts += eff
                tot_financial += cost
                tot_m += m
                tot_c += c
                tot_d += dp
                i += 1

            else:
                # Fallback if something weird happens
                i += 1

        df = pd.DataFrame(rows)

        # --- 2. Final Total Calculation (UNIFIED) ---
        # Formula: Total = ceil( TotalPoints * SumOfRates )
        # This prevents "rounding of components" errors.
        if user_mode == UserMode.RENTER:
            tot_financial = math.ceil(tot_eff_pts * rate)
        elif user_mode == UserMode.OWNER and owner_config:
            # Calculate raw float components
            raw_maint = tot_eff_pts * rate
            raw_cap = tot_eff_pts * owner_config.get("cap_rate", 0.0) if owner_config.get("inc_c", False) else 0.0
            raw_dep = tot_eff_pts * owner_config.get("dep_rate", 0.0) if owner_config.get("inc_d", False) else 0.0

            # Sum first, then Ceil ONCE
            tot_financial = math.ceil(raw_maint + raw_cap + raw_dep)
            
            # For the sub-metrics, we ceil them individually for display 
            # (Note: These might add up to slightly more than tot_financial due to rounding, 
            # but the Tot Financial will be mathematically correct relative to the Renter formula)
            tot_m = math.ceil(raw_maint)
            tot_c = math.ceil(raw_cap)
            tot_d = math.ceil(raw_dep)

        # Formatting for Display
        if not df.empty:
            fmt_cols = [c for c in df.columns if c not in ["Date", "Day", "Points"]]
            for col in fmt_cols:
                df[col] = df[col].apply(lambda x: f"${x:,.0f}" if isinstance(x, (int, float)) else x)

        return CalculationResult(df, tot_eff_pts, tot_financial, disc_applied, list(set(disc_days)), tot_m, tot_c, tot_d)

    def compare_stays(self, resort_name, rooms, checkin, nights, user_mode, rate, policy, owner_config):
        daily_data = []
        holiday_data = defaultdict(lambda: defaultdict(float))
        val_key = "TotalCostValue" if user_mode == UserMode.OWNER else "RentValue"

        resort = self.repo.get_resort(resort_name)
        if not resort: 
            return ComparisonResult(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

        processed_holidays = {room: set() for room in rooms}

        disc_mul = owner_config["disc_mul"] if owner_config else 1.0
        renter_mul = 1.0
        if not user_mode == UserMode.OWNER:
            if policy == DiscountPolicy.PRESIDENTIAL: renter_mul = 0.7
            elif policy == DiscountPolicy.EXECUTIVE: renter_mul = 0.75

        # Ensure rate matches the main calc logic
        rate = round(float(rate), 2)

        for room in rooms:
            i = 0
            while i < nights:
                d = checkin + timedelta(days=i)
                pts_map, h = self._get_daily_points(resort, d)

                if h and h.name not in processed_holidays[room]:
                    processed_holidays[room].add(h.name)
                    raw = pts_map.get(room, 0)
                    eff = raw
                    
                    if user_mode == UserMode.OWNER:
                        if disc_mul < 1.0: eff = math.floor(raw * disc_mul)
                    else:
                        if renter_mul < 1.0: eff = math.floor(raw * renter_mul)
                    
                    cost = 0.0
                    if user_mode == UserMode.OWNER and owner_config:
                         m = math.ceil(eff * rate)
                         c = math.ceil(eff * owner_config.get("cap_rate", 0.0)) if owner_config.get("inc_c") else 0
                         dp = math.ceil(eff * owner_config.get("dep_rate", 0.0)) if owner_config.get("inc_d") else 0
                         cost = m + c + dp
                    else:
                         cost = math.ceil(eff * rate)
                    
                    daily_data.append({
                        "Day": d.strftime("%a"),
                        "Date": d,
                        "Room Type": room,
                        val_key: cost,
                        "Holiday": h.name
                    })
                    
                    holiday_data[room][h.name] += cost
                    i += (h.end_date - h.start_date).days + 1
                
                elif not h:
                    raw = pts_map.get(room, 0)
                    eff = raw
                    
                    if user_mode == UserMode.OWNER:
                        if disc_mul < 1.0: eff = math.floor(raw * disc_mul)
                    else:
                        if renter_mul < 1.0: eff = math.floor(raw * renter_mul)
                    
                    cost = 0.0
                    if user_mode == UserMode.OWNER and owner_config:
                         m = math.ceil(eff * rate)
                         c = math.ceil(eff * owner_config.get("cap_rate", 0.0)) if owner_config.get("inc_c") else 0
                         dp = math.ceil(eff * owner_config.get("dep_rate", 0.0)) if owner_config.get("inc_d") else 0
                         cost = m + c + dp
                    else:
                         cost = math.ceil(eff * rate)
                    
                    daily_data.append({
                        "Day": d.strftime("%a"),
                        "Date": d,
                        "Room Type": room,
                        val_key: cost,
                        "Holiday": "No"
                    })
                    i += 1
                else:
                    i += 1

        # Build Pivot Table
        template_res = self.calculate_breakdown(resort_name, rooms[0], checkin, nights, user_mode, rate, policy, owner_config)
        final_pivot = []
        if not template_res.breakdown_df.empty:
            for _, row in template_res.breakdown_df.iterrows():
                new_row = {"Date": row["Date"]}
                for room in rooms:
                    day_res = self.calculate_breakdown(resort_name, room, checkin, nights, user_mode, rate, policy, owner_config)
                    day = row["Date"]
                    match = day_res.breakdown_df[day_res.breakdown_df["Date"] == day]
                    val = 0
                    if not match.empty:
                        if user_mode == UserMode.OWNER:
                            pass
                    new_row[room] = f"${val:,.0f}"
                final_pivot.append(new_row)
            
        tot_row = {"Date": "Total Cost" if user_mode == UserMode.OWNER else "Total Rent"}
        for r in rooms:
            room_res = self.calculate_breakdown(
                resort_name, r, checkin, nights, user_mode, rate, policy, owner_config
            )
            tot_row[r] = f"${room_res.financial_total:,.0f}"
        final_pivot.append(tot_row)

        h_chart_rows = []
        for r, h_map in holiday_data.items():
            for h_name, val in h_map.items():
                h_chart_rows.append({"Holiday": h_name, "Room Type": r, val_key: val})

        return ComparisonResult(pd.DataFrame(final_pivot), pd.DataFrame(daily_data), pd.DataFrame(h_chart_rows))

    def adjust_holiday(self, resort_name, checkin, nights):
        resort = self.repo.get_resort(resort_name)
        if not resort or str(checkin.year) not in resort.years: 
            return checkin, nights, False
        
        end = checkin + timedelta(days=nights - 1)
        yd = resort.years[str(checkin.year)]
        overlapping = [h for h in yd.holidays if h.start_date <= end and h.end_date >= checkin]
        
        if not overlapping: 
            return checkin, nights, False

        holiday = overlapping[0]
        new_checkin = holiday.start_date
        new_nights = (holiday.end_date - holiday.start_date).days + 1
        
        return new_checkin, new_nights, True

# ==============================================================================
# MAIN PAGE LOGIC
# ==============================================================================
TIER_NO_DISCOUNT = "No Discount"
TIER_EXECUTIVE = "Executive (25% off within 30 days)"
TIER_PRESIDENTIAL = "Presidential / Chairman (30% off within 60 days)"
TIER_OPTIONS = [TIER_NO_DISCOUNT, TIER_EXECUTIVE, TIER_PRESIDENTIAL]

def apply_settings_from_dict(user_data: dict):
    """Update session state variables from a settings dictionary."""
    try:
        if "maintenance_rate" in user_data: st.session_state.pref_maint_rate = float(user_data["maintenance_rate"])
        if "purchase_price" in user_data: st.session_state.pref_purchase_price = float(user_data["purchase_price"])
        if "capital_cost_pct" in user_data: st.session_state.pref_capital_cost = float(user_data["capital_cost_pct"])
        if "salvage_value" in user_data: st.session_state.pref_salvage_value = float(user_data["salvage_value"])
        if "useful_life" in user_data: st.session_state.pref_useful_life = int(user_data["useful_life"])
        
        if "discount_tier" in user_data:
            raw = str(user_data["discount_tier"])
            if "Executive" in raw: st.session_state.pref_discount_tier = TIER_EXECUTIVE
            elif "Presidential" in raw or "Chairman" in raw: st.session_state.pref_discount_tier = TIER_PRESIDENTIAL
            else: st.session_state.pref_discount_tier = TIER_NO_DISCOUNT
        
        if "include_capital" in user_data: st.session_state.pref_inc_c = bool(user_data["include_capital"])
        if "include_depreciation" in user_data: st.session_state.pref_inc_d = bool(user_data["include_depreciation"])
        
        if "renter_rate" in user_data:
            st.session_state.renter_rate_val = float(user_data["renter_rate"])
            
        if "renter_discount_tier" in user_data:
            raw_r = str(user_data["renter_discount_tier"])
            if "Executive" in raw_r: st.session_state.renter_discount_tier = TIER_EXECUTIVE
            elif "Presidential" in raw_r or "Chairman" in raw_r: st.session_state.renter_discount_tier = TIER_PRESIDENTIAL
            else: st.session_state.renter_discount_tier = TIER_NO_DISCOUNT
            
        if "preferred_resort_id" in user_data:
            rid = str(user_data["preferred_resort_id"])
            st.session_state.pref_resort_id = rid
            st.session_state.current_resort_id = rid
            
        st.session_state.calculator_mode = UserMode.OWNER.value
    except Exception as e:
        st.error(f"Error applying settings: {e}")

def main() -> None:
    # --- 0. INIT STATE ---
    if "current_resort" not in st.session_state: st.session_state.current_resort = None
    if "current_resort_id" not in st.session_state: st.session_state.current_resort_id = None
    if "show_help" not in st.session_state: st.session_state.show_help = False
    
    ensure_data_in_session()
    
    # --- 1. AUTO-LOAD LOCAL FILE ON STARTUP ---
    if "settings_auto_loaded" not in st.session_state:
        local_settings = "mvc_owner_settings.json"
        if os.path.exists(local_settings):
            try:
                with open(local_settings, "r") as f:
                    data = json.load(f)
                    apply_settings_from_dict(data)
                    st.session_state.settings_auto_loaded = True
            except Exception as e:
                st.warning(f"Could not auto-load local settings: {e}")
                st.session_state.settings_auto_loaded = True

    # --- 2. LOAD JSON FROM SESSION ---
    if "mvc_data" not in st.session_state:
        st.error("MVC data not found in session. Please load the data first.")
        return

    mvc_data = st.session_state["mvc_data"]
    repo = MVCRepository(mvc_data)
    calc = MVCCalculator(repo)

    resorts_full = repo.get_resorts_full()
    resort_names = [r["display_name"] for r in resorts_full]

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown("### Mode")
        mode_str = st.radio("Select Mode", [UserMode.RENTER.value, UserMode.OWNER.value], key="calculator_mode")
        mode = UserMode(mode_str)

        st.markdown("### Renter Settings")
        default_renter_rate = st.session_state.get("renter_rate_val", 0.55)
        renter_rate = st.number_input("Renter Rate ($ per point)", min_value=0.01, max_value=5.00, value=float(default_renter_rate), step=0.01, key="renter_rate_val")
        renter_disc_tier = st.selectbox("Renter Discount Tier", TIER_OPTIONS, index=TIER_OPTIONS.index(st.session_state.get("renter_discount_tier", TIER_NO_DISCOUNT)), key="renter_discount_tier")
        
        st.markdown("---")
        st.markdown("### Owner Settings")

        default_maint = st.session_state.get("pref_maint_rate", 0.55)
        default_pp = st.session_state.get("pref_purchase_price", 18.0)
        default_cap_pct = st.session_state.get("pref_capital_cost", 5.0)
        default_salvage = st.session_state.get("pref_salvage_value", 3.0)
        default_life = st.session_state.get("pref_useful_life", 10)

        maint_rate = st.number_input("Maintenance Rate ($ per point)", 0.01, 5.0, float(default_maint), 0.01, key="pref_maint_rate")
        purchase_price = st.number_input("Purchase Price ($ per point)", 1.0, 100.0, float(default_pp), 0.5, key="pref_purchase_price")
        capital_pct = st.number_input("Capital Cost %", 0.0, 50.0, float(default_cap_pct), 0.5, key="pref_capital_cost")
        salvage_val = st.number_input("Salvage Value ($ per point)", 0.0, 50.0, float(default_salvage), 0.5, key="pref_salvage_value")
        useful_life = st.number_input("Useful Life (Years)", 1, 50, int(default_life), 1, key="pref_useful_life")

        include_capital = st.checkbox("Include Capital Cost", value=st.session_state.get("pref_inc_c", True), key="pref_inc_c")
        include_dep = st.checkbox("Include Depreciation", value=st.session_state.get("pref_inc_d", True), key="pref_inc_d")
        
        owner_discount_tier = st.selectbox("Owner Discount Tier", TIER_OPTIONS, index=TIER_OPTIONS.index(st.session_state.get("pref_discount_tier", TIER_NO_DISCOUNT)), key="pref_discount_tier")

        # Owner discount multiplier
        owner_disc_mul = 1.0
        if owner_discount_tier == TIER_EXECUTIVE:
            owner_disc_mul = 0.75
        elif owner_discount_tier == TIER_PRESIDENTIAL:
            owner_disc_mul = 0.70

        if mode == UserMode.OWNER:
            rate_to_use = maint_rate
        else:
            rate_to_use = renter_rate

        # Owner cost configuration
        owner_params = None
        if mode == UserMode.OWNER:
            cap_rate = 0.0
            dep_rate = 0.0
            if include_capital:
                cap_rate = (purchase_price * (capital_pct / 100.0)) / useful_life
            if include_dep:
                dep_base = purchase_price - salvage_val
                dep_rate = dep_base / useful_life if useful_life > 0 else 0.0

            owner_params = {
                "inc_c": include_capital,
                "inc_d": include_dep,
                "cap_rate": cap_rate,
                "dep_rate": dep_rate,
                "disc_mul": owner_disc_mul,
            }

        st.markdown("---")
        st.markdown("### Global Options")
        show_gantt = st.checkbox("Show Seasons & Holidays Chart", value=False)
        st.markdown("---")

        st.markdown("### Config Files")
        uploaded_config = st.file_uploader("Load Owner Settings JSON", type=["json"])
        if uploaded_config is not None:
            try:
                data = json.load(uploaded_config)
                file_sig = getattr(uploaded_config, "name", "") + str(getattr(uploaded_config, "size", "")) + str(getattr(uploaded_config, "type", ""))
                if st.session_state.get("last_loaded_cfg") != file_sig:
                    apply_settings_from_dict(data)
                    st.session_state.last_loaded_cfg = file_sig
                    st.rerun()
            except Exception as e:
                st.error(f"Failed to load config: {e}")
        
        if st.button("Reset to Defaults"):
            for k in ["pref_maint_rate","pref_purchase_price","pref_capital_cost","pref_salvage_value","pref_useful_life","pref_discount_tier","pref_inc_c","pref_inc_d","renter_rate_val","renter_discount_tier"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()

        st.markdown("### Save Current Settings")
        if st.button("Prepare Settings JSON"):
            current_pref_resort = st.session_state.current_resort_id if st.session_state.current_resort_id else ""
            current_settings = {
                "maintenance_rate": st.session_state.get("pref_maint_rate", 0.55),
                "purchase_price": st.session_state.get("pref_purchase_price", 18.0),
                "capital_cost_pct": st.session_state.get("pref_capital_cost", 5.0),
                "salvage_value": st.session_state.get("pref_salvage_value", 3.0),
                "useful_life": st.session_state.get("pref_useful_life", 10),
                "discount_tier": st.session_state.get("pref_discount_tier", TIER_NO_DISCOUNT),
                "include_maintenance": True,
                "include_capital": st.session_state.get("pref_inc_c", True),
                "include_depreciation": st.session_state.get("pref_inc_d", True),
                "renter_rate": st.session_state.get("renter_rate_val", 0.50),
                "renter_discount_tier": st.session_state.get("renter_discount_tier", TIER_NO_DISCOUNT),
                "preferred_resort_id": current_pref_resort
            }
            st.download_button("💾 Save Settings", json.dumps(current_settings, indent=2), "mvc_owner_settings.json", "application/json", use_container_width=True)

    # UPDATED HEADER
    render_page_header("Calc", f"👤 {mode.value}", icon="🏨", badge_color="#059669" if mode == UserMode.OWNER else "#2563eb")

    # Resort Selection
    if resorts_full and st.session_state.current_resort_id is None:
        if "pref_resort_id" in st.session_state and any(r.get("id") == st.session_state.pref_resort_id for r in resorts_full):
            st.session_state.current_resort_id = st.session_state.pref_resort_id
        else:
            st.session_state.current_resort_id = resorts_full[0].get("id")
            
    render_resort_grid(resorts_full, st.session_state.current_resort_id)
    resort_obj = next((r for r in resorts_full if r.get("id") == st.session_state.current_resort_id), None)
    
    if not resort_obj: return
    
    r_name = resort_obj.get("display_name")
    info = repo.get_resort_info(r_name)
    render_resort_card(info["full_name"], info["timezone"], info["address"])
    st.divider()

    c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
    with c1:
        if "calc_checkin" not in st.session_state:
            st.session_state.calc_checkin = date.today()
            st.session_state.calc_initial_default = st.session_state.calc_checkin
            st.session_state.calc_checkin_user_set = False

        checkin = st.date_input("Check-in", value=st.session_state.calc_checkin, key="calc_checkin_widget")
        st.session_state.calc_checkin = checkin
    
    if not st.session_state.calc_checkin_user_set and checkin != st.session_state.calc_initial_default:
        st.session_state.calc_checkin_user_set = True

    with c2: nights = st.number_input("Nights", 1, 60, 7)
    
    if st.session_state.calc_checkin_user_set:
        adj_in, adj_n, adj = calc.adjust_holiday(r_name, checkin, nights)
    else:
        adj_in, adj_n, adj = checkin, nights, False
        
    if adj:
        st.info(f"ℹ️ Adjusted to holiday: {adj_in.strftime('%b %d')} - {(adj_in+timedelta(days=adj_n-1)).strftime('%b %d')}")

    pts, _ = calc._get_daily_points(calc.repo.get_resort(r_name), adj_in)
    if not pts:
        rd = calc.repo.get_resort(r_name)
        if rd and str(adj_in.year) in rd.years:
             yd = rd.years[str(adj_in.year)]
             if yd.seasons: pts = yd.seasons[0].day_categories[0].room_points
    
    room_types = sorted(pts.keys()) if pts else []
    if not room_types:
        st.error("❌ No room data available.")
        return

    with c3: room_sel = st.selectbox("Room Type", room_types)
    with c4: comp_rooms = st.multiselect("Compare With", [r for r in room_types if r != room_sel])
    
    st.divider()

    # Determine policy and owner_params again after main selectors
    # (they have already been computed in sidebar, we just re-use)
    if mode == UserMode.RENTER:
        disc_opt = renter_disc_tier
    else:
        disc_opt = owner_discount_tier
    policy = DiscountPolicy.NONE
    if "Executive" in disc_opt: policy = DiscountPolicy.EXECUTIVE
    elif "Presidential" in disc_opt or "Chairman" in disc_opt: policy = DiscountPolicy.PRESIDENTIAL

    # Ensure owner_params has correct disc_mul in case it changed via selector
    if mode == UserMode.OWNER:
        opt = owner_discount_tier
    else:
        opt = renter_disc_tier
    disc_mul = 0.75 if "Executive" in opt else 0.7 if "Presidential" in opt or "Chairman" in opt else 1.0
    if owner_params:
        owner_params["disc_mul"] = disc_mul

    # RESULT CALCULATION
    res = calc.calculate_breakdown(r_name, room_sel, adj_in, adj_n, mode, rate_to_use, policy, owner_params)
    
    if mode == UserMode.OWNER:
        inc_c = owner_params.get("inc_c", False) if owner_params else False
        inc_d = owner_params.get("inc_d", False) if owner_params else False
        cols = st.columns(5)
        cols[0].metric("Total Points", f"{res.total_points:,}")
        cols[1].metric("Total Cost", f"${res.financial_total:,.0f}")
        cols[2].metric("Maintenance", f"${res.m_cost:,.0f}")
        if inc_c: cols[3].metric("Capital Cost", f"${res.c_cost:,.0f}")
        if inc_d: cols[4].metric("Depreciation", f"${res.d_cost:,.0f}")
    else:
        cols = st.columns(2)
        cols[0].metric("Total Points", f"{res.total_points:,}")
        cols[1].metric("Total Rent", f"${res.financial_total:,.0f}")
        if res.discount_applied: st.success(f"Discount Applied: {len(res.discounted_days)} days")

    # 📊 Room-type summary table for the selected period
    # Computes total points and total $ cost/rent for every room type
    # in this resort over the selected date range, respecting the
    # chosen discount tier and mode (Renter vs Owner).
    summary_rows = []
    for rt in room_types:
        rt_res = calc.calculate_breakdown(
            r_name,
            rt,
            adj_in,
            adj_n,
            mode,
            rate_to_use,
            policy,
            owner_params,
        )
        row = {
            "Room Type": rt,
            "Total Points": rt_res.total_points,
        }
        if mode == UserMode.OWNER:
            row["Total Cost"] = rt_res.financial_total
        else:
            row["Total Rent"] = rt_res.financial_total
        summary_rows.append(row)

    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        if mode == UserMode.OWNER and "Total Cost" in summary_df.columns:
            summary_df["Total Cost"] = summary_df["Total Cost"].apply(
                lambda x: f"${x:,.0f}" if isinstance(x, (int, float)) else x
            )
        if mode == UserMode.RENTER and "Total Rent" in summary_df.columns:
            summary_df["Total Rent"] = summary_df["Total Rent"].apply(
                lambda x: f"${x:,.0f}" if isinstance(x, (int, float)) else x
            )
        st.markdown("### 📊 Room Type Summary (Selected Period)")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.dataframe(res.breakdown_df, use_container_width=True, hide_index=True)

    if comp_rooms:
        st.divider()
        st.markdown("### 🔍 Comparison")
        comp_res = calc.compare_stays(r_name, [room_sel] + comp_rooms, adj_in, adj_n, mode, rate_to_use, policy, owner_params)
        st.dataframe(comp_res.pivot_df, use_container_width=True)
        
        c1, c2 = st.columns(2)
        if not comp_res.daily_chart_df.empty:
             with c1: st.plotly_chart(px.bar(comp_res.daily_chart_df, x="Day", y="TotalCostValue" if mode==UserMode.OWNER else "RentValue", color="Room Type", barmode="group", title="Daily Cost"), use_container_width=True)
        if not comp_res.holiday_chart_df.empty:
             with c2: st.plotly_chart(px.bar(comp_res.holiday_chart_df, x="Holiday", y="TotalCostValue" if mode==UserMode.OWNER else "RentValue", color="Room Type", barmode="group", title="Holiday Cost"), use_container_width=True)

    year_str = str(adj_in.year)
    res_data = calc.repo.get_resort(r_name)
    if res_data and year_str in res_data.years:
        st.divider()
        with st.expander("📅 Season and Holiday Calendar", expanded=False):
            gantt_df = create_gantt_chart_from_resort_data(res_data, year_str)
            if not gantt_df.empty:
                fig = px.timeline(
                    gantt_df, x_start="Start", x_end="End", y="Category", color="Type",
                    title=f"{r_name} - {year_str} Seasons & Holidays"
                )
                fig.update_yaxes(autorange="reversed")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No season/holiday data available for this resort/year.")

def run() -> None:
    main()
