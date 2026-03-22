# SIDEBAR + TOP NAV INTEGRATION - FULL REPLACEMENT
# Keeps sidebar, adds nav as fixed header INSIDE sidebar (always visible, no scroll issues)

import streamlit as st

# Sidebar structure (your existing one + nav at top)
with st.sidebar:
    st.markdown("### UHA IMS")
    st.markdown("---")
    
    # Nav links as buttons (clean, no dropdown hassle)
    if st.button("Dashboard", use_container_width=True):
        st.session_state.page = "dashboard"
        st.rerun()
    if st.button("Import", use_container_width=True):
        st.session_state.page = "import"
        st.rerun()
    if st.button("Inventory", use_container_width=True):
        st.session_state.page = "inventory"
        st.rerun()
    if st.button("PCA", use_container_width=True):
        st.session_state.page = "pca"
        st.rerun()
    st.markdown("---")
    
    # Toggle if you still want it (optional)
    show_extra = st.checkbox("Show Extra Tools", value=False)
    if show_extra:
        st.button("Help")
        st.button("Reports")

# Main content - no top bar needed, sidebar handles nav
# (your dashboard stats, lists, etc. go here)