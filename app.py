import streamlit as st
from common.ui import setup_page
import calculator
import editor
from browser_persistence_final import BrowserPersistence, apply_settings_to_session, get_settings_to_save

# Set page config first
setup_page()

def main():
    # --- 0. INITIALIZE BROWSER PERSISTENCE ---
    # Create browser persistence handler
    if "persistence" not in st.session_state:
        st.session_state.persistence = BrowserPersistence()
    
    # Load saved settings on first run
    if "settings_loaded" not in st.session_state:
        saved_settings = st.session_state.persistence.load_settings()
        if saved_settings:
            apply_settings_to_session(saved_settings, st.session_state)
            st.toast("✅ Loaded saved settings from browser", icon="✅")
        st.session_state.settings_loaded = True
    
    # --- 1. SESSION STATE FOR NAVIGATION ---
    # We use 'app_phase' to track: 'renter', 'owner', 'editor'
    if "app_phase" not in st.session_state:
        st.session_state.app_phase = "renter"

    # --- 2. SIDEBAR NAVIGATION CONTROLS ---
    with st.sidebar:
        st.header("Navigation")
        
        # LOGIC: RENTER MODE
        if st.session_state.app_phase == "renter":
            st.info("Currently: **Renter Mode**")
            st.markdown("---")
            if st.button("Go to Owner Mode ➡️", use_container_width=True):
                st.session_state.app_phase = "owner"
                # Auto-save on mode change
                settings = get_settings_to_save(st.session_state)
                st.session_state.persistence.save_settings(settings)
                st.rerun()

        # LOGIC: OWNER MODE
        elif st.session_state.app_phase == "owner":
            if st.button("⬅️ Back to Renter", use_container_width=True):
                st.session_state.app_phase = "renter"
                # Auto-save on mode change
                settings = get_settings_to_save(st.session_state)
                st.session_state.persistence.save_settings(settings)
                st.rerun()
            
            st.markdown("---")
            st.info("Currently: **Owner Mode**")
            st.markdown("---")
            
            if st.button("Go to Editor 🛠️", use_container_width=True):
                st.session_state.app_phase = "editor"
                # Auto-save on mode change
                settings = get_settings_to_save(st.session_state)
                st.session_state.persistence.save_settings(settings)
                st.rerun()

        # LOGIC: EDITOR MODE
        elif st.session_state.app_phase == "editor":
            if st.button("⬅️ Back to Calculator", use_container_width=True):
                st.session_state.app_phase = "owner"
                # Auto-save on mode change
                settings = get_settings_to_save(st.session_state)
                st.session_state.persistence.save_settings(settings)
                st.rerun()
            st.markdown("---")
            st.info("Currently: **Data Editor**")
        
        # Add settings management section
        st.markdown("---")
        st.markdown("### ⚙️ Settings")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Save Now", use_container_width=True, help="Manually save current settings"):
                settings = get_settings_to_save(st.session_state)
                if st.session_state.persistence.save_settings(settings):
                    st.toast("✅ Settings saved!", icon="✅")
                else:
                    st.toast("❌ Save failed", icon="❌")
        
        with col2:
            if st.button("🗑️ Clear", use_container_width=True, help="Clear saved settings"):
                if st.session_state.persistence.clear_settings():
                    st.toast("🗑️ Settings cleared", icon="🗑️")
                    # Clear session state too
                    for key in ["current_resort_id", "current_resort", "pref_maint_rate", 
                               "pref_purchase_price", "pref_capital_cost", "pref_salvage_value",
                               "pref_useful_life", "pref_discount_tier", "renter_rate_val",
                               "renter_discount_tier"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()
                else:
                    st.toast("❌ Clear failed", icon="❌")

    # --- 3. MAIN PAGE ROUTING ---
    if st.session_state.app_phase == "renter":
        # Run calculator in Renter Mode
        calculator.run(forced_mode="Renter")
        
    elif st.session_state.app_phase == "owner":
        # Run calculator in Owner Mode
        calculator.run(forced_mode="Owner")
        
    elif st.session_state.app_phase == "editor":
        editor.run()

if __name__ == "__main__":
    main()
