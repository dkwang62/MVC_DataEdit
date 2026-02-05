# browser_persistence_final.py
"""
Production-ready browser persistence for Streamlit Community Cloud.
Fixed version without problematic component keys.
"""

import json
import streamlit as st
from typing import Dict, Any, Optional
import streamlit.components.v1 as components


class BrowserPersistence:
    """Browser-based persistence using localStorage."""
    
    def __init__(self, storage_key: str = "mvc_calculator_settings"):
        self.storage_key = storage_key
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save settings to browser localStorage.
        
        Strategy:
        1. Store in session_state immediately
        2. Write to localStorage via JavaScript
        """
        try:
            # Always save to session state first (immediate)
            st.session_state[f'_persisted_{self.storage_key}'] = settings
            
            # Save to browser localStorage
            settings_json = json.dumps(settings)
            # Escape for safe embedding in JavaScript
            escaped_json = settings_json.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
            
            save_script = f"""
                <script>
                    (function() {{
                        try {{
                            localStorage.setItem('{self.storage_key}', "{escaped_json}");
                            console.log('[MVC] ✅ Settings saved to localStorage');
                        }} catch(e) {{
                            console.error('[MVC] ❌ Save failed:', e);
                        }}
                    }})();
                </script>
            """
            
            # Use components.html without key parameter
            components.html(save_script, height=0)
            return True
            
        except Exception as e:
            print(f"[MVC] Error saving settings: {e}")
            return False
    
    def load_settings(self) -> Optional[Dict[str, Any]]:
        """Load settings from session state (populated from localStorage on first load).
        
        Returns settings if found, None otherwise.
        """
        session_key = f'_persisted_{self.storage_key}'
        
        # Check if already in session state
        if session_key in st.session_state:
            return st.session_state[session_key]
        
        # Try to load from localStorage on first run
        if not st.session_state.get('_localStorage_load_attempted', False):
            self._load_from_browser()
            st.session_state._localStorage_load_attempted = True
        
        # Check again after load attempt
        return st.session_state.get(session_key)
    
    def _load_from_browser(self):
        """Load from browser localStorage into session state."""
        session_key = f'_persisted_{self.storage_key}'
        
        # JavaScript to load and immediately store in a hidden div
        load_script = f"""
            <div id="mvc-settings-loader" style="display:none;"></div>
            <script>
                (function() {{
                    try {{
                        const data = localStorage.getItem('{self.storage_key}');
                        if (data) {{
                            console.log('[MVC] ✅ Found settings in localStorage');
                            // Store in hidden div for Python to read
                            const loader = document.getElementById('mvc-settings-loader');
                            if (loader) {{
                                loader.textContent = data;
                            }}
                        }} else {{
                            console.log('[MVC] ℹ️  No saved settings found');
                        }}
                    }} catch(e) {{
                        console.error('[MVC] ❌ Load failed:', e);
                    }}
                }})();
            </script>
        """
        
        # Render the script
        result = components.html(load_script, height=0)
        
        # Try to parse the result if returned
        if result:
            try:
                settings = json.loads(result)
                st.session_state[session_key] = settings
                print(f"[MVC] ✅ Loaded settings from browser")
            except Exception as e:
                print(f"[MVC] ⚠️  Could not parse loaded settings: {e}")
    
    def clear_settings(self) -> bool:
        """Clear saved settings from both session state and localStorage."""
        try:
            # Clear from session state
            session_key = f'_persisted_{self.storage_key}'
            if session_key in st.session_state:
                del st.session_state[session_key]
            
            # Reset load flag so it can try again
            if '_localStorage_load_attempted' in st.session_state:
                del st.session_state._localStorage_load_attempted
            
            # Clear from localStorage
            clear_script = f"""
                <script>
                    (function() {{
                        try {{
                            localStorage.removeItem('{self.storage_key}');
                            console.log('[MVC] ✅ Settings cleared from localStorage');
                        }} catch(e) {{
                            console.error('[MVC] ❌ Clear failed:', e);
                        }}
                    }})();
                </script>
            """
            
            components.html(clear_script, height=0)
            return True
            
        except Exception as e:
            print(f"[MVC] Error clearing settings: {e}")
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
