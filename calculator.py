# calculator.py
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from common.charts import create_gantt_chart_from_resort_data
from common.data import ensure_data_in_session
from common.ui import render_page_header, render_resort_card, render_resort_grid


# ==============================================================================
# DOMAIN MODELS
# ==============================================================================
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
class YearData:
    holidays: List[Holiday]
    seasons: List[Season]


@dataclass
class ResortData:
    id: str
    name: str
    years: Dict[str, YearData]


# ==============================================================================
# REPOSITORY
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
        for year, holidays in self._raw.get("global_holidays", {}).items():
            parsed[year] = {}
            for name, data in holidays.items():
                try:
                    s = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
                    e = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
                    parsed[year][name] = (s, e)
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
            # Holidays
            holidays: List[Holiday] = []
            for h in y_content.get("holidays", []):
                ref = h.get("global_reference") or h.get("name")
                start_end = self._global_holidays.get(year_str, {}).get(ref)
                if start_end:
                    holidays.append(Holiday(
                        name=h.get("name", ref),
                        start_date=start_end[0],
                        end_date=start_end[1],
                        room_points=h.get("room_points", {})
                    ))

            # Seasons
            seasons: List[Season] = []
            for s in y_content.get("seasons", []):
                periods = [
                    SeasonPeriod(
                        start=date.fromisoformat(p["start"]),
                        end=date.fromisoformat(p["end"])
                    ) for p in s.get("periods", [])
                ]
                day_cats = [
                    DayCategory(days=cat.get("day_pattern", []), room_points=cat.get("room_points", {}))
                    for cat in s.get("day_categories", {}).values()
                ]
                seasons.append(Season(name=s["name"], periods=periods, day_categories=day_cats))

            years_data[year_str] = YearData(holidays=holidays, seasons=seasons)

        resort = ResortData(id=raw_r["id"], name=raw_r["display_name"], years=years_data)
        self._resort_cache[resort_name] = resort
        return resort


# ==============================================================================
# CALCULATION ENGINE
# ==============================================================================
class MVCCalculator:
    def __init__(self, repo: MVCRepository):
        self.repo = repo

    def _is_holiday(self, dt: date, year_data: YearData) -> Optional[Holiday]:
        for h in year_data.holidays:
            if h.start_date <= dt <= h.end_date:
                return h
        return None

    def _get_season_points(self, dt: date, weekday_abbr: str, year_data: YearData):
        for season in year_data.seasons:
            for period in season.periods:
                if period.start <= dt <= period.end:
                    for cat in season.day_categories:
                        if weekday_abbr in cat.days:
                            return cat.room_points
        return {}

    def get_points_for_room(self, resort: ResortData, year: str, checkin_date: date,
                            nights: int, room_type: str, mode: UserMode) -> int:
        yd = resort.years.get(year)
        if not yd:
            return 0

        total = 0
        cur = checkin_date
        for _ in range(nights):
            holiday = self._is_holiday(cur, yd)
            if holiday and room_type in holiday.room_points:
                total += holiday.room_points[room_type]
            else:
                points_map = self._get_season_points(cur, cur.strftime("%a"), yd)
                total += points_map.get(room_type, 0)
            cur += timedelta(days=1)
        return total

    def calculate_financial_cost(self, points: int, rate: float,
                                 include_maintenance: bool = True,
                                 include_capital: bool = False,
                                 include_depreciation: bool = False,
                                 capital_pct: float = 5.0,
                                 salvage: float = 3.0,
                                 useful_life: int = 20,
                                 purchase_price: float = 18.0) -> float:
        cost = 0.0
        if include_maintenance:
            cost += points * rate / 1000
        if include_capital:
            cost += points * (capital_pct / 100) / 1000 * purchase_price
        if include_depreciation:
            depreciable = purchase_price - salvage
            cost += points * depreciable / useful_life / 1000
        return round(cost, 2)


# ==============================================================================
# SETTINGS HELPERS
# ==============================================================================
TIER_NO_DISCOUNT = "No Discount"
TIER_EXECUTIVE = "Executive / Select (25% off within 30 days)"
TIER_PRESIDENTIAL = "Presidential / Chairman (30% off within 60 days)"


def apply_settings_from_dict(d: dict):
    st.session_state.pref_maint_rate = d.get("maintenance_rate", 0.56)
    st.session_state.pref_purchase_price = d.get("purchase_price", 18.0)
    st.session_state.pref_capital_cost = d.get("capital_cost_pct", 5.0)
    st.session_state.pref_salvage_value = d.get("salvage_value", 3.0)
    st.session_state.pref_useful_life = d.get("useful_life", 20)
    st.session_state.pref_discount_tier = d.get("discount_tier", TIER_NO_DISCOUNT)
    st.session_state.pref_inc_c = d.get("include_capital", True)
    st.session_state.pref_inc_d = d.get("include_depreciation", True)
    st.session_state.renter_rate_val = d.get("renter_rate", 0.817)
    st.session_state.renter_discount_tier = d.get("renter_discount_tier", TIER_NO_DISCOUNT)
    if d.get("preferred_resort_id"):
        st.session_state.current_resort_id = d["preferred_resort_id"]


# ==============================================================================
# MAIN APP
# ==============================================================================
def main():
    ensure_data_in_session()
    data = st.session_state.data
    if not data or "resorts" not in data:
        st.warning("No resort data loaded. Use the Editor or upload a JSON file.")
        return

    calc = MVCCalculator(MVCRepository(data))

    render_page_header("Calculator", "Points & Cost Calculator", icon="Calculator")

    # Sidebar – Resort selection
    with st.sidebar:
        st.markdown("### Resort Selection")
        render_resort_grid(calc.repo.get_resort_list_full(),
                           st.session_state.get("current_resort_id"))

        if not st.session_state.get("current_resort_id"):
            st.info("Select a resort to begin.")
            return

    resort_name = st.session_state.current_resort
    resort = calc.repo.get_resort(resort_name)
    if not resort:
        st.error("Resort not found.")
        return

    # Resort card
    tz = "UTC"
    if resort.years and "2025" in resort.years and resort.years["2025"].seasons:
        tz = resort.years["2025"].seasons[0].periods[0].start.strftime("%Z") or "UTC"
    render_resort_card(resort_name, tz, "Address not available")

    # Inputs
    col1, col2 = st.columns(2)
    with col1:
        mode = st.radio("Mode", [UserMode.OWNER.value, UserMode.RENTER.value],
                        horizontal=True, key="calc_mode")
        mode = UserMode.OWNER if mode == UserMode.OWNER.value else UserMode.RENTER
    with col2:
        year = st.selectbox("Year", sorted(resort.years.keys()))

    col1, col2 = st.columns(2)
    with col1:
        checkin = st.date_input("Check-in", value=date(int(year), 1, 10),
                                min_value=date(int(year), 1, 1),
                                max_value=date(int(year), 12, 31))
    with col2:
        nights = st.number_input("Nights", 1, 21, 7, step=1)

    # Financial settings
    with st.expander("Financial Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            if mode == UserMode.OWNER:
                rate = st.number_input("Maintenance $/1k pts",
                                       value=st.session_state.get("pref_maint_rate", 0.56),
                                       step=0.01, format="%.3f")
                purchase_price = st.number_input("Purchase price $/pt",
                                                 value=st.session_state.get("pref_purchase_price", 18.0))
                capital_pct = st.number_input("Capital %",
                                              value=st.session_state.get("pref_capital_cost", 5.0))
                inc_cap = st.checkbox("Include Capital", value=st.session_state.get("pref_inc_c", True))
                salvage = st.number_input("Salvage $/pt",
                                          value=st.session_state.get("pref_salvage_value", 3.0))
                life = st.number_input("Useful life (years)",
                                       value=st.session_state.get("pref_useful_life", 20), min_value=1)
                inc_dep = st.checkbox("Include Depreciation", value=st.session_state.get("pref_inc_d", True))
            else:
                rate = st.number_input("Rental $/pt",
                                       value=st.session_state.get("renter_rate_val", 0.817),
                                       step=0.01, format="%.3f")
                inc_cap = inc_dep = False
                purchase_price = salvage = life = capital_pct = 0

    # All Room Types Table
    st.divider()
    st.subheader("Cost for All Room Types")

    year_str = str(year)
    yd = resort.years.get(year_str)
    if not yd:
        st.error("No data for this year.")
        return

    room_types = set()
    for s in yd.seasons:
        for cat in s.day_categories:
            room_types.update(cat.room_points.keys())
    for h in yd.holidays:
        room_types.update(h.room_points.keys())
    room_types = sorted(room_types)

    rows = []
    for rt in room_types:
        pts = calc.get_points_for_room(resort, year_str, checkin, nights, rt, mode)
        cost = calc.calculate_financial_cost(
            pts, rate,
            include_maintenance=True,
            include_capital=inc_cap,
            include_depreciation=inc_dep,
            capital_pct=capital_pct,
            salvage=salvage,
            useful_life=life,
            purchase_price=purchase_price,
        )
        rows.append({
            "Room Type": rt,
            "Points Required": pts,
            "Total Cost ($)": f"${cost:,.2f}"
        })

    df = pd.DataFrame(rows)
    st.dataframe(df.style.format({"Points Required": "{:,}"}), use_container_width=True, hide_index=True)

    if len(df) > 1:
        costs = df["Total Cost ($)"].str.replace("[$,]", "", regex=True).astype(float)
        cheapest = df.iloc[costs.idxmin()]
        expensive = df.iloc[costs.idxmax()]
        c1, c2 = st.columns(2)
        with c1:
            st.success(f"Cheapest → {cheapest['Room Type']}: {cheapest['Total Cost ($)']} ({cheapest['Points Required']:,} pts)")
        with c2:
            st.warning(f"Most Expensive → {expensive['Room Type']}: {expensive['Total Cost ($)']} ({expensive['Points Required']:,} pts)")

    # Gantt calendar
    st.divider()
    with st.expander("Season & Holiday Calendar", expanded=False):
        fig = create_gantt_chart_from_resort_data(resort, year_str, data.get("global_holidays", {}))
        st.plotly_chart(fig, use_container_width=True)

    # Settings persistence
    with st.sidebar:
        with st.expander("Your Settings", expanded=False):
            st.info("Save your profile and reload anytime.")
            uploaded = st.file_uploader("Load settings", type="json", key="cfg_upload")
            if uploaded:
                sig = f"{uploaded.name}_{uploaded.size}"
                if st.session_state.get("last_cfg_sig") != sig:
                    apply_settings_from_dict(json.load(uploaded))
                    st.session_state.last_cfg_sig = sig
                    st.rerun()

            settings = {
                "maintenance_rate": st.session_state.get("pref_maint_rate", 0.56),
                "purchase_price": st.session_state.get("pref_purchase_price", 18.0),
                "capital_cost_pct": st.session_state.get("pref_capital_cost", 5.0),
                "salvage_value": st.session_state.get("pref_salvage_value", 3.0),
                "useful_life": st.session_state.get("pref_useful_life", 20),
                "discount_tier": st.session_state.get("pref_discount_tier", TIER_NO_DISCOUNT),
                "include_capital": st.session_state.get("pref_inc_c", True),
                "include_depreciation": st.session_state.get("pref_inc_d", True),
                "renter_rate": st.session_state.get("renter_rate_val", 0.817),
                "renter_discount_tier": st.session_state.get("renter_discount_tier", TIER_NO_DISCOUNT),
                "preferred_resort_id": st.session_state.current_resort_id or "",
            }
            st.download_button(
                "Save Settings",
                json.dumps(settings, indent=2),
                "mvc_calculator_settings.json",
                "application/json",
                use_container_width=True,
            )


# Required by app.py
def run():
    main()


if __name__ == "__main__":
    run()
