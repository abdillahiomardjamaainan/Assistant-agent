from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/gmail.send",
]


def get_google_credentials():
    """
    Authentifie l'utilisateur avec Google OAuth
    et retourne des credentials utilisables par Google Calendar API.
    """

    credentials_path = Path("credentials.json")
    token_path = Path("token.json")

    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(
            str(token_path),
            SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path),
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())

    return creds