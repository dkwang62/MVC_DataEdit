import streamlit as st
import json
import os

# Set page config first - before any other Streamlit command
st.set_page_config(
    page_title="MVC Tools",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Marriott Vacation Club – internal tools"},
)

from common.ui import setup_page
import editor
import calculator

def main():
    # Inject CSS manually to ensure styling
    st.markdown(
        """
    <style>
        :root {
            --primary-color: #008080;
            --border-color: #E5E7EB;
            --card-bg: #FFFFFF;
            --bg-color: #F9FAFB;
            --text-color: #111827;
        }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        section[data-testid="stSidebar"] {
            background-color: var(--card-bg);
            border-right: 1px solid var(--border-color);
        }
        section[data-testid="stSidebar"] .block-container {
            gap: 0rem !important;
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
        }
        [data-testid="stExpander"] {
            margin-bottom: 0.5rem !important;
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            background-color: #ffffff;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        section[data-testid="stSidebar"] h3 {
            margin-top: 1.5rem !important;    
            margin-bottom: 0.5rem !important; 
            font-size: 1.0rem !important;
            font-weight: 600 !important;
            color: var(--primary-color) !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        section[data-testid="stSidebar"] hr {
            margin: 1.5rem 0 1rem 0 !important;
        }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # --- 1. SESSION STATE FOR NAVIGATION ---
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
                st.rerun()

        # LOGIC: OWNER MODE
        elif st.session_state.app_phase == "owner":
            if st.button("⬅️ Back to Renter", use_container_width=True):
                st.session_state.app_phase = "renter"
                st.rerun()
            
            st.markdown("---")
            st.info("Currently: **Owner Mode**")
            st.markdown("---")
            
            if st.button("Go to Editor 🛠️", use_container_width=True):
                st.session_state.app_phase = "editor"
                st.rerun()

        # LOGIC: EDITOR MODE
        elif st.session_state.app_phase == "editor":
            if st.button("⬅️ Back to Calculator", use_container_width=True):
                st.session_state.app_phase = "owner"
                st.rerun()
            st.markdown("---")
            st.info("Currently: **Data Editor**")

    # --- 3. MAIN PAGE ROUTING ---
    if st.session_state.app_phase == "renter":
        calculator.run(forced_mode="Renter")
        
    elif st.session_state.app_phase == "owner":
        calculator.run(forced_mode="Owner")
        
    elif st.session_state.app_phase == "editor":
        editor.run()

if __name__ == "__main__":
    main()
