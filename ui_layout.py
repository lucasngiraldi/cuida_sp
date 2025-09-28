import streamlit as st
from ui_components import inject_css_once

def app_shell(title: str = None, subtitle: str = None, breadcrumb: str = None):
    inject_css_once()
    if title:
        st.caption(title)
