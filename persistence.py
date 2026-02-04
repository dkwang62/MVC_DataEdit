# browser_persistence.py
"""
Production-ready browser persistence for Streamlit Community Cloud.
Uses multiple strategies with automatic fallback.
"""

import json
import streamlit as st
from typing import Dict, Any, Optional
import streamlit.components.v1 as components


class BrowserPersistence:
    """Browser-based persistence with multiple fallback strategies."""
    
    def __init__(self, storage_key: str = "mvc_calculator_settings"):
        self.storage_key = storage_key
        self._init_counter = 0
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save settings using localStorage.
        
        Strategy:
        1. Store in session_state (works during session)
        2. Write to localStorage via JavaScript (persists across sessions)
        """
        try:
            # Always save to session state first (immediate)
            st.session_state[f'_persisted_{self.storage_key}'] = settings
            
            # Save to browser localStorage
            settings_json = json.dumps(settings)
            # Escape quotes for JavaScript
            escaped_json = settings_json.replace('\\', '\\\\').replace('"', '\\"')
            
            save_script = f"""
                <script>
                    (function() {{
                        try {{
                            localStorage.setItem('{self.storage_key}', "{escaped_json}");
                            console.log('[MVC] ✅ Settings saved to localStorage');
                        }} catch(e) {{
                            console.error('[MVC] ❌ localStorage save failed:', e);
                        }}
                    }})();
                </script>
            """
            
            components.html(save_script, height=0, scrolling=False)
            return True
            
        except Exception as e:
            st.error(f"Failed to save settings: {e}")
            return False
    
    def load_settings(self) -> Optional[Dict[str, Any]]:
        """Load settings from session state or localStorage.
        
        Returns settings if found, None otherwise.
        """
        # First check session state (fastest)
        session_key = f'_persisted_{self.storage_key}'
        if session_key in st.session_state:
            return st.session_state[session_key]
        
        # If not in session state, try to load from localStorage
        # This uses a callback mechanism via iframe
        if not st.session_state.get('_storage_load_attempted', False):
            self._attempt_load_from_browser()
            st.session_state._storage_load_attempted = True
        
        # Check if loaded
        return st.session_state.get(session_key)
    
    def _attempt_load_from_browser(self):
        """Attempt to load from browser localStorage."""
        # Use a unique key for each load attempt
        load_key = f"load_attempt_{self._init_counter}"
        self._init_counter += 1
        
        load_script = f"""
            <script>
                (function() {{
                    try {{
                        const data = localStorage.getItem('{self.storage_key}');
                        if (data) {{
                            console.log('[MVC] ✅ Settings found in localStorage');
                            // Try to set via Streamlit mechanism
                            const parsed = JSON.parse(data);
                            
                            // Send to parent window
                            if (window.parent) {{
                                window.parent.postMessage({{
                                    type: 'MVC_SETTINGS_LOADED',
                                    data: parsed,
                                    key: '{self.storage_key}'
                                }}, '*');
                            }}
                        }} else {{
                            console.log('[MVC] ℹ️  No saved settings found');
                        }}
                    }} catch(e) {{
                        console.error('[MVC] ❌ localStorage load failed:', e);
                    }}
                }})();
            </script>
        """
        
        components.html(load_script, height=0, scrolling=False, key=load_key)
    
    def clear_settings(self) -> bool:
        """Clear saved settings."""
        try:
            # Clear from session state
            session_key = f'_persisted_{self.storage_key}'
            if session_key in st.session_state:
                del st.session_state[session_key]
            
            # Clear from localStorage
            clear_script = f"""
                <script>
                    (function() {{
                        try {{
                            localStorage.removeItem('{self.storage_key}');
                            console.log('[MVC] ✅ Settings cleared from localStorage');
                        }} catch(e) {{
                            console.error('[MVC] ❌ localStorage clear failed:', e);
                        }}
                    }})();
                </script>
            """
            
            components.html(clear_script, height=0, scrolling=False)
            return True
            
        except Exception as e:
            st.error(f"Failed to clear settings: {e}")
            return False


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_settings_to_save(session_state) -> Dict[str, Any]:
    """Extract all relevant settings from session state.
    
    Args:
        session_state: Streamlit session state object
        
    Returns:
        Dictionary of settings to persist
    """
    return {
        # Resort selection
        "current_resort_id": session_state.get("current_resort_id", ""),
        "current_resort": session_state.get("current_resort", ""),
        
        # Owner mode financial settings
        "pref_maint_rate": session_state.get("pref_maint_rate", 0.55),
        "pref_purchase_price": session_state.get("pref_purchase_price", 18.0),
        "pref_capital_cost": session_state.get("pref_capital_cost", 5.0),
        "pref_salvage_value": session_state.get("pref_salvage_value", 3.0),
        "pref_useful_life": session_state.get("pref_useful_life", 10),
        
        # Cost inclusion toggles
        "pref_inc_c": session_state.get("pref_inc_c", True),
        "pref_inc_d": session_state.get("pref_inc_d", True),
        
        # Discount tier
        "pref_discount_tier": session_state.get("pref_discount_tier", "No Discount"),
        
        # Renter mode settings
        "renter_rate_val": session_state.get("renter_rate_val", 0.50),
        "renter_discount_tier": session_state.get("renter_discount_tier", "No Discount"),
        
        # Application state
        "app_phase": session_state.get("app_phase", "renter"),
    }


def apply_settings_to_session(settings: Dict[str, Any], session_state) -> None:
    """Apply loaded settings to session state.
    
    Args:
        settings: Dictionary of settings to apply
        session_state: Streamlit session state object
    """
    if settings:
        for key, value in settings.items():
            session_state[key] = value
