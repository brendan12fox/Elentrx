"""Login and signup screens."""

from __future__ import annotations

import sqlite3

import streamlit as st

from src.auth.users import (
    access_code_valid,
    authenticate,
    create_user,
    signup_allowed,
    user_count,
    username_exists,
)
from src.ui.brand import render_auth_logo
from src.ui.styles import inject_styles


def _login_success(user) -> None:
    st.session_state.authenticated = True
    st.session_state.user_id = user.id
    st.session_state.username = user.username
    st.session_state.pop("signup_unlocked", None)
    st.rerun()


def render_auth_page() -> None:
    inject_styles()
    first_user = user_count() == 0
    can_signup = signup_allowed() or first_user

    st.markdown(
        """
<div class="auth-backdrop">
  <div class="auth-glow auth-glow-a"></div>
  <div class="auth-glow auth-glow-b"></div>
</div>
        """,
        unsafe_allow_html=True,
    )

    render_auth_logo()

    st.markdown(
        """
<div class="auth-shell">
  <div class="auth-hero">
    <ul class="auth-features">
      <li>Hourly trial scans across biotech sectors</li>
      <li>ML favorability scores + AI research briefs</li>
      <li>Email alerts with live market context</li>
    </ul>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    _, col, _ = st.columns([1, 1.15, 1])
    with col:
        st.markdown('<div class="auth-card-label">Account</div>', unsafe_allow_html=True)

        if first_user:
            st.info("Create the first admin account to get started.")
            _render_signup_form(is_first_admin=True, require_access_code=False)
            return

        if not can_signup:
            st.markdown("##### Sign in")
            _render_login_form()
            st.caption("New accounts are invite-only. Contact your admin for access.")
            return

        tab = st.radio(
            "Auth mode",
            ["Sign in", "Create account"],
            horizontal=True,
            key="auth_mode",
            label_visibility="collapsed",
        )
        if tab == "Create account":
            _render_gated_signup()
        else:
            _render_login_form()


def _render_login_form() -> None:
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", placeholder="your username")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            user = authenticate(username, password)
            if user:
                _login_success(user)
            st.error("Invalid username or password.")


def _render_gated_signup() -> None:
    """New users must enter the access code before creating an account."""
    if not st.session_state.get("signup_unlocked"):
        st.markdown("##### Enter access code")
        st.caption("You'll need an invite code before creating an account.")
        with st.form("access_code_form", clear_on_submit=False):
            code = st.text_input("Access code", placeholder="Enter your invite code")
            submitted = st.form_submit_button(
                "Continue",
                type="primary",
                use_container_width=True,
            )
            if submitted:
                if access_code_valid(code):
                    st.session_state.signup_unlocked = True
                    st.rerun()
                st.error("Invalid access code.")
        return

    st.success("Access code accepted — create your account to start receiving hit alerts.")
    _render_signup_form(is_first_admin=False, require_access_code=True)


def _render_signup_form(*, is_first_admin: bool, require_access_code: bool) -> None:
    title = "Create admin account" if is_first_admin else "Create account"
    st.markdown(f"##### {title}")
    if not is_first_admin:
        st.caption("Your email will be subscribed to favorable trial-hit alerts.")

    with st.form("signup_form", clear_on_submit=False):
        username = st.text_input("Username", placeholder="letters and numbers")
        email = st.text_input("Email", placeholder="you@email.com")
        password = st.text_input("Password", type="password", placeholder="min. 8 characters")
        confirm = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button(
            "Get started" if is_first_admin else "Create account & subscribe",
            type="primary",
            use_container_width=True,
        )
        if not submitted:
            return

        # Re-check access code on submit so the session unlock can't be bypassed.
        if require_access_code and not st.session_state.get("signup_unlocked"):
            st.error("Enter a valid access code before creating an account.")
            return

        username_clean = username.strip().lower()
        email_clean = email.strip()
        if len(username_clean) < 3:
            st.error("Username must be at least 3 characters.")
        elif len(password) < 8:
            st.error("Password must be at least 8 characters.")
        elif password != confirm:
            st.error("Passwords do not match.")
        elif not email_clean or "@" not in email_clean:
            st.error("A valid email is required so we can send hit alerts.")
        elif username_exists(username_clean):
            st.error("Username already taken — try another or sign in.")
        else:
            try:
                user = create_user(
                    username=username_clean,
                    password=password,
                    email=email_clean,
                    alert_email=email_clean,
                    is_admin=is_first_admin,
                )
                _login_success(user)
            except sqlite3.IntegrityError:
                st.error("Username already taken.")
