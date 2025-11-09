from flask import Blueprint, redirect, request, url_for, session, flash
from flask_login import login_user, logout_user, login_required
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
import os
import pathlib
from models import db, User

auth_bp = Blueprint('auth', __name__)

# Google OAuth configuration
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Remove in production with HTTPS
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'  # Allow scope changes from Google

def get_google_provider_cfg():
    """Get Google OAuth provider configuration."""
    import requests
    from config import Config
    return requests.get(Config.GOOGLE_DISCOVERY_URL).json()


@auth_bp.route('/login')
def login():
    """Initiate Google OAuth login flow."""
    from config import Config
    import logging

    # Log the redirect URI being used
    redirect_uri = url_for('auth.callback', _external=True)
    logging.info(f"OAuth Login - Redirect URI: {redirect_uri}")
    logging.info(f"OAuth Login - Request URL: {request.url}")
    logging.info(f"OAuth Login - Request Host: {request.host}")

    # Get Google's OAuth endpoints
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    # Create flow instance
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": Config.GOOGLE_CLIENT_ID,
                "client_secret": Config.GOOGLE_CLIENT_SECRET,
                "auth_uri": authorization_endpoint,
                "token_uri": google_provider_cfg["token_endpoint"],
                "redirect_uris": [url_for('auth.callback', _external=True)],
            }
        },
        scopes=["openid", "email", "profile"]
    )

    flow.redirect_uri = url_for('auth.callback', _external=True)

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )

    # Store state in session for CSRF protection
    session['state'] = state

    return redirect(authorization_url)


@auth_bp.route('/callback')
def callback():
    """Handle Google OAuth callback."""
    from config import Config

    # Verify state for CSRF protection
    if request.args.get('state') != session.get('state'):
        flash('Invalid state parameter', 'error')
        return redirect(url_for('main.index'))

    # Get authorization code
    code = request.args.get('code')

    # Get Google's OAuth endpoints
    google_provider_cfg = get_google_provider_cfg()

    # Create flow instance
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": Config.GOOGLE_CLIENT_ID,
                "client_secret": Config.GOOGLE_CLIENT_SECRET,
                "auth_uri": google_provider_cfg["authorization_endpoint"],
                "token_uri": google_provider_cfg["token_endpoint"],
                "redirect_uris": [url_for('auth.callback', _external=True)],
            }
        },
        scopes=["openid", "email", "profile"]
    )

    flow.redirect_uri = url_for('auth.callback', _external=True)

    # Exchange authorization code for tokens
    flow.fetch_token(code=code)

    # Get user info from ID token
    credentials = flow.credentials
    id_info = id_token.verify_oauth2_token(
        credentials.id_token,
        google_requests.Request(),
        Config.GOOGLE_CLIENT_ID,
        clock_skew_in_seconds=60  # Add tolerance for clock differences
    )

    # Extract user information
    google_id = id_info['sub']
    email = id_info['email']
    name = id_info.get('name', '')
    profile_pic = id_info.get('picture', '')

    # Check if user exists, if not create new user
    user = User.query.filter_by(google_id=google_id).first()

    if not user:
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            profile_pic=profile_pic
        )
        db.session.add(user)
        db.session.commit()
    else:
        # Update user info if changed
        user.name = name
        user.profile_pic = profile_pic
        db.session.commit()

    # Log in the user
    login_user(user)

    flash('Успешный вход в систему!', 'success')
    return redirect(url_for('main.dashboard'))


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('main.index'))
