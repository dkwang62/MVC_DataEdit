# ... (continuing from where the artifact was cut off)

value", step=0.5)
                    st.session_state.pref_salvage_value = val_salvage
                    salvage = val_salvage
            else:
                life, salvage = 15, 3.0
            owner_params = {
                "disc_mul": 1.0, "inc_m": inc_m, "inc_c": inc_c, "inc_d": inc_d,
                "cap_rate": cap * coc, "dep_rate": (cap - salvage) / life if life > 0 else 0.0,
            }
        else:
            curr_rent = st.session_state.get("renter_rate_val", 0.50)
            renter_rate_input = st.number_input("Cost per Point ($)", value=curr_rent, step=0.01, key="widget_renter_rate")
            if renter_rate_input != curr_rent: st.session_state.renter_rate_val = renter_rate_input
            rate_to_use = renter_rate_input
            st.markdown("##### 🎯 Available Discounts")
            curr_r_tier = st.session_state.get("renter_discount_tier", TIER_NO_DISCOUNT)
            try: r_idx = TIER_OPTIONS.index(curr_r_tier)
            except ValueError: r_idx = 0
            opt = st.radio("Discount tier available:", TIER_OPTIONS, index=r_idx, key="widget_renter_discount_tier")
            st.session_state.renter_discount_tier = opt
            if "Presidential" in opt or "Chairman" in opt: policy = DiscountPolicy.PRESIDENTIAL
            elif "Executive" in opt: policy = DiscountPolicy.EXECUTIVE

        if mode == UserMode.OWNER:
             if "Executive" in opt: policy = DiscountPolicy.EXECUTIVE
             elif "Presidential" in opt or "Chairman" in opt: policy = DiscountPolicy.PRESIDENTIAL
        disc_mul = 0.75 if "Executive" in opt else 0.7 if "Presidential" in opt or "Chairman" in opt else 1.0
        if owner_params: owner_params["disc_mul"] = disc_mul
        st.divider()

    render_page_header("Calc", f"👤 {mode.value}", icon="🏨", badge_color="#059669" if mode == UserMode.OWNER else "#2563eb")

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
    
    res = calc.calculate_breakdown(r_name, room_sel, adj_in, adj_n, mode, rate_to_use, policy, owner_params)
    
    if mode == UserMode.OWNER:
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

    summary_rows = []
    for rt in room_types:
        rt_res = calc.calculate_breakdown(r_name, rt, adj_in, adj_n, mode, rate_to_use, policy, owner_params)
        row = {"Room Type": rt, "Total Points": rt_res.total_points}
        if mode == UserMode.OWNER:
            row["Total Cost"] = rt_res.financial_total
        else:
            row["Total Rent"] = rt_res.financial_total
        summary_rows.append(row)

    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        if mode == UserMode.OWNER and "Total Cost" in summary_df.columns:
            summary_df["Total Cost"] = summary_df["Total Cost"].apply(lambda x: f"${x:,.0f}" if isinstance(x, (int, float)) else x)
        if mode == UserMode.RENTER and "Total Rent" in summary_df.columns:
            summary_df["Total Rent"] = summary_df["Total Rent"].apply(lambda x: f"${x:,.0f}" if isinstance(x, (int, float)) else x)

        st.markdown("### 📊 Room Type Summary (Selected Period)")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
        
        st.markdown("**Select a room type to view detailed breakdown:**")
        btn_cols = st.columns(len(room_types))
        for idx, rt in enumerate(room_types):
            with btn_cols[idx]:
                if st.button(f"📋 {rt}", key=f"btn_detail_{rt}", use_container_width=True):
                    st.session_state.selected_breakdown_room = rt
        
        if "selected_breakdown_room" in st.session_state and st.session_state.selected_breakdown_room in room_types:
            selected_room = st.session_state.selected_breakdown_room
            st.divider()
            st.markdown(f"### 📝 Daily Breakdown: {selected_room}")
            
            selected_res = calc.calculate_breakdown(r_name, selected_room, adj_in, adj_n, mode, rate_to_use, policy, owner_params)
            
            if mode == UserMode.OWNER:
                cols_detail = st.columns(5)
                cols_detail[0].metric("Total Points", f"{selected_res.total_points:,}")
                cols_detail[1].metric("Total Cost", f"${selected_res.financial_total:,.0f}")
                cols_detail[2].metric("Maintenance", f"${selected_res.m_cost:,.0f}")
                if inc_c: cols_detail[3].metric("Capital Cost", f"${selected_res.c_cost:,.0f}")
                if inc_d: cols_detail[4].metric("Depreciation", f"${selected_res.d_cost:,.0f}")
            else:
                cols_detail = st.columns(2)
                cols_detail[0].metric("Total Points", f"{selected_res.total_points:,}")
                cols_detail[1].metric("Total Rent", f"${selected_res.financial_total:,.0f}")
                if selected_res.discount_applied: 
                    st.success(f"Discount Applied: {len(selected_res.discounted_days)} days")
            
            st.dataframe(selected_res.breakdown_df, use_container_width=True, hide_index=True)
    
    if "selected_breakdown_room" not in st.session_state or st.session_state.selected_breakdown_room not in room_types:
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
            st.plotly_chart(create_gantt_chart_from_resort_data(res_data, year_str, st.session_state.data.get("global_holidays", {})), use_container_width=True)
            
    with st.sidebar:
        with st.expander("⚙️ Your Calculator Settings", expanded=False):
            st.info("**Save time by saving your profile.** Store your costs, membership tier, and resort preference to a file. Upload it anytime to instantly restore your setup.")
            st.markdown("###### 📂 Load/Save Settings")
            config_file = st.file_uploader("Load Settings (JSON)", type="json", key="user_cfg_upload")
            
            if config_file:
                 file_sig = f"{config_file.name}_{config_file.size}"
                 if "last_loaded_cfg" not in st.session_state or st.session_state.last_loaded_cfg != file_sig:
                     config_file.seek(0)
                     data = json.load(config_file)
                     apply_settings_from_dict(data)
                     st.session_state.last_loaded_cfg = file_sig
                     st.rerun()

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

def run() -> None:
    main()
