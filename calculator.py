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
# LAYER 1: DOMAIN MODELS
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

        raw_r = next(
            (r for r in self._raw.get("resorts", []) if r["display_name"] == resort_name),
            None,
        )
        if not raw_r:
            return None

        years_data: Dict[str, YearData] = {}
        for year_str, y_content in raw_r.get("years", {}).items():
            holidays: List[Holiday] = []
            for h in y_content.get("holidays", []):
                ref = h.get("global_reference")
                if ref and ref in self._global_holidays.get(year_str, {}):
                    g_dates = self._global_holidays[year_str][ref]
                    holidays.append(
                        Holiday(
                            name=h.get("name", ref),
                            start_date=g_dates[0],
                            end_date=g_dates[1],
                            room_points=h.get("room_points", {}),
                        )
                    )

            seasons: List[Season] = []
            for s in y_content.get("seasons", []):
                periods: List[SeasonPeriod] = []
                for p in s.get("periods", []):
                    try:
                        periods.append(
                            SeasonPeriod(
                                start=datetime.strptime(p["start"], "%Y-%m-%d").date(),
                                end=datetime.strptime(p["end"], "%Y-%m-%d").date(),
                            )
                        )
                    except Exception:
                        continue
                
                day_cats: List[DayCategory] = []
                for cat in s.get("day_categories", {}).values():
                    day_cats.append(
                        DayCategory(
                            days=cat.get("day_pattern", []),
                            room_points=cat.get("room_points", {}),
                        )
                    )
                seasons.append(Season(name=s["name"], periods=periods, day_categories=day_cats))
            
            years_data[year_str] = YearData(holidays=holidays, seasons=seasons)

        resort_obj = ResortData(
            id=raw_r["id"], name=raw_r["display_name"], years=years_data
        )
        self._resort_cache[resort_name] = resort_obj
        return resort_obj

    def get_resort_info(self, resort_name: str) -> Dict[str, str]:
        raw_r = next(
            (r for r in self._raw.get("resorts", []) if r["display_name"] == resort_name),
            None,
        )
        if raw_r:
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
        
        # Check Seasons
        dow_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        dow = dow_map[day.weekday()]
        
        for s in yd.seasons:
            for p in s.periods:
                if p.start <= day <= p.end:
                    for cat in s.day_categories:
                        if dow in cat.days:
                            return cat.room_points, None
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

                if is_disc:
                    disc_applied = True
                    for j in range(holiday_days):
                        disc_days.append((holiday.start_date + timedelta(days=j)).strftime("%Y-%m-%d"))

                # Cost Calculation (Daily - for display only)
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

                row = {"Date": d.strftime("%Y-%m-%d"), "Day": d.strftime("%a"), "Points": eff}
                
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
                i += 1
            else:
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
            
            raw_cap = 0.0
            if owner_config.get("inc_c", False):
                raw_cap = tot_eff_pts * owner_config.get("cap_rate", 0.0)
                
            raw_dep = 0.0
            if owner_config.get("inc_d", False):
                raw_dep = tot_eff_pts * owner_config.get("dep_rate", 0.0)

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

                # --- Calculation Logic (Simplified for Compare) ---
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

        for _, tmpl_row in template_res.breakdown_df.iterrows():
            d_str = tmpl_row["Date"]
            new_row = {"Date": d_str}
            for room in rooms:
                val = 0.0
                if "(" in str(d_str): # Holiday
                    h_name = str(d_str).split(" (")[0]
                    val = holiday_data[room].get(h_name, 0.0)
                else: # Regular Day
                    try:
                        d_obj = datetime.strptime(str(d_str), "%Y-%m-%d").date()
                        val = next((x[val_key] for x in daily_data if x["Date"] == d_obj and x["Room Type"] == room), 0.0)
                    except: pass
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

        s = min(h.start_date for h in overlapping)
        e = max(h.end_date for h in overlapping)
        adj_s = min(checkin, s)
        adj_e = max(end, e)
        return adj_s, (adj_e - adj_s).days + 1, True

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
                    st.toast("✅ Auto-loaded local settings!", icon="⚙️")
            except Exception:
                pass
        st.session_state.settings_auto_loaded = True

    # --- 2. DEFAULTS ---
    if "pref_maint_rate" not in st.session_state: st.session_state.pref_maint_rate = 0.55
    if "pref_purchase_price" not in st.session_state: st.session_state.pref_purchase_price = 18.0
    if "pref_capital_cost" not in st.session_state: st.session_state.pref_capital_cost = 5.0
    if "pref_salvage_value" not in st.session_state: st.session_state.pref_salvage_value = 3.0
    if "pref_useful_life" not in st.session_state: st.session_state.pref_useful_life = 10
    if "pref_discount_tier" not in st.session_state: st.session_state.pref_discount_tier = TIER_NO_DISCOUNT
    
    st.session_state.pref_inc_m = True
    if "pref_inc_c" not in st.session_state: st.session_state.pref_inc_c = True
    if "pref_inc_d" not in st.session_state: st.session_state.pref_inc_d = True
    
    if "calculator_mode" not in st.session_state: st.session_state.calculator_mode = UserMode.RENTER.value
    if "renter_rate_val" not in st.session_state: st.session_state.renter_rate_val = 0.50
    if "renter_discount_tier" not in st.session_state: st.session_state.renter_discount_tier = TIER_NO_DISCOUNT

    # Checkin state
    today = datetime.now().date()
    initial_default = today + timedelta(days=1)
    if "calc_initial_default" not in st.session_state:
        st.session_state.calc_initial_default = initial_default
        st.session_state.calc_checkin = initial_default
        st.session_state.calc_checkin_user_set = False

    if not st.session_state.data:
        st.warning("⚠️ Please open the Editor and upload/merge data_v2.json first.")
        return

    repo = MVCRepository(st.session_state.data)
    calc = MVCCalculator(repo)
    resorts_full = repo.get_resort_list_full()

    with st.sidebar:
        st.divider()
        st.markdown("### 👤 User Profile")
        
        # MODE SELECTOR
        mode_sel = st.radio(
            "Calc mode:", 
            [m.value for m in UserMode],
            key="calculator_mode",
            horizontal=True,
            label_visibility="collapsed"
        )
        mode = UserMode(mode_sel)
        
        owner_params = None
        policy = DiscountPolicy.NONE
        rate_to_use = 0.50
        st.divider()
        
        if mode == UserMode.OWNER:
            # OWNER PROXY
            current_val = st.session_state.get("pref_maint_rate", 0.55)
            val_rate = st.number_input(
                "Annual Maintenance Fee ($/point)",
                value=current_val,
                key="widget_maint_rate",
                step=0.01, min_value=0.0
            )
            if val_rate != current_val:
                st.session_state.pref_maint_rate = val_rate
            
            rate_to_use = val_rate
            current_tier = st.session_state.get("pref_discount_tier", TIER_NO_DISCOUNT)
            try: t_idx = TIER_OPTIONS.index(current_tier)
            except ValueError: t_idx = 0
            
            opt = st.radio("Discount Tier:", TIER_OPTIONS, index=t_idx, key="widget_discount_tier")
            st.session_state.pref_discount_tier = opt
            
            st.divider()
            
            col_chk2, col_chk3 = st.columns(2)
            inc_m = True
            
            with col_chk2:
                inc_c = st.checkbox("Capital", value=st.session_state.get("pref_inc_c", True), key="widget_inc_c")
                st.session_state.pref_inc_c = inc_c
            with col_chk3:
                inc_d = st.checkbox("Deprec.", value=st.session_state.get("pref_inc_d", True), key="widget_inc_d")
                st.session_state.pref_inc_d = inc_d
