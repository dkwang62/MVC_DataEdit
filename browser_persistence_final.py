# browser_persistence_final.py
"""
Hybrid persistence: Query params (reliable) + localStorage (clean URLs).
Best of both worlds for Streamlit Community Cloud.
"""

import json
import streamlit as st
from typing import Dict, Any, Optional
import base64


class BrowserPersistence:
    """Hybrid persistence using query params + localStorage."""
    
    def __init__(self, storage_key: str = "s"):  # Short key to minimize URL length
        self.storage_key = storage_key
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save settings to both query params and localStorage.
        
        Priority:
        1. Session state (immediate)
        2. Query parameters (reliable, persists in bookmarks)
        3. localStorage via HTML (optional, cleaner URLs when revisiting)
        """
        try:
            # 1. Save to session state
            st.session_state._persisted_settings = settings
            
            # 2. Encode and save to query params (this is the reliable method)
            settings_json = json.dumps(settings, separators=(',', ':'))
            encoded = base64.urlsafe_b64encode(settings_json.encode()).decode()
            st.query_params[self.storage_key] = encoded
            
            # 3. Also save to localStorage (optional enhancement)
            self._save_to_localStorage(settings_json)
            
            return True
            
        except Exception as e:
            print(f"[MVC] Save error: {e}")
            return False
    
    def _save_to_localStorage(self, settings_json: str):
        """Attempt to save to localStorage (best effort)."""
        try:
            import streamlit.components.v1 as components
            escaped = settings_json.replace('\\', '\\\\').replace("'", "\\'")
            
            script = f"""
                <script>
                try {{
                    localStorage.setItem('mvc_settings', '{escaped}');
                    console.log('[MVC] Saved to localStorage');
                }} catch(e) {{ }}
                </script>
            """
            components.html(script, height=0)
        except:
            pass  # Silent fail - query params are the primary method
    
    def load_settings(self) -> Optional[Dict[str, Any]]:
        """Load settings from query params or session state.
        
        Order of precedence:
        1. Session state (already loaded)
        2. Query parameters (most reliable)
        3. None (first time user)
        """
        # Check session state first
        if '_persisted_settings' in st.session_state:
            return st.session_state._persisted_settings
        
        # Try to load from query parameters
        if self.storage_key in st.query_params:
            try:
                encoded = st.query_params[self.storage_key]
                settings_json = base64.urlsafe_b64decode(encoded.encode()).decode()
                settings = json.loads(settings_json)
                
                # Cache in session state
                st.session_state._persisted_settings = settings
                return settings
                
            except Exception as e:
                print(f"[MVC] Load error: {e}")
        
        return None
    
    def clear_settings(self) -> bool:
        """Clear all saved settings."""
        try:
            # Clear session state
            if '_persisted_settings' in st.session_state:
                del st.session_state._persisted_settings
            
            # Clear query params
            if self.storage_key in st.query_params:
                del st.query_params[self.storage_key]
            
            # Clear localStorage (best effort)
            try:
                import streamlit.components.v1 as components
                script = """
                    <script>
                    try { localStorage.removeItem('mvc_settings'); } catch(e) {}
                    </script>
                """
                components.html(script, height=0)
            except:
                pass
            
            return True
            
        except Exception as e:
            print(f"[MVC] Clear error: {e}")
            return False


def get_settings_to_save(session_state) -> Dict[str, Any]:
    """Extract settings from session state."""
    return {
        "current_resort_id": session_state.get("current_resort_id", ""),
        "current_resort": session_state.get("current_resort", ""),
        "pref_maint_rate": session_state.get("pref_maint_rate", 0.55),
        "pref_purchase_price": session_state.get("pref_purchase_price", 18.0),
        "pref_capital_cost": session_state.get("pref_capital_cost", 5.0),
        "pref_salvage_value": session_state.get("pref_salvage_value", 3.0),
        "pref_useful_life": session_state.get("pref_useful_life", 10),
        "pref_inc_c": session_state.get("pref_inc_c", True),
        "pref_inc_d": session_state.get("pref_inc_d", True),
        "pref_discount_tier": session_state.get("pref_discount_tier", "No Discount"),
        "renter_rate_val": session_state.get("renter_rate_val", 0.50),
        "renter_discount_tier": session_state.get("renter_discount_tier", "No Discount"),
        "app_phase": session_state.get("app_phase", "renter"),
    }


def apply_settings_to_session(settings: Dict[str, Any], session_state) -> None:
    """Apply settings to session state."""
    if settings:
        for key, value in settings.items():
            session_state[key] = value
