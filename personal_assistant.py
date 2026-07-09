import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from googleapiclient.discovery import build

from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain.tools import tool, ToolRuntime

from src.google_auth import get_google_credentials
import base64
from pathlib import Path
import uuid
from email.message import EmailMessage


# ============================================================
# 1. CONFIGURATION GENERALE
# ============================================================

load_dotenv()

TIMEZONE_NAME = "Europe/Paris"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

now = datetime.now(TIMEZONE)

CURRENT_DATE = now.date().isoformat()
CURRENT_TIME = now.strftime("%H:%M:%S")

print(f"Date actuelle utilisée par le système : {CURRENT_DATE}")
print(f"Heure actuelle utilisée par le système : {CURRENT_TIME}")
print(f"Fuseau horaire : {TIMEZONE_NAME}")


# ============================================================
# 2. MODELE IA
# ============================================================

model = init_chat_model(
    "gpt-4o-mini",
    model_provider="openai",
    temperature=0,
)


# ============================================================
# 3. CONNEXION GOOGLE CALENDAR
# ============================================================

def get_calendar_service():
    """
    Crée un service Google Calendar API à partir des credentials OAuth.
    """

    creds = get_google_credentials()

    service = build(
        "calendar",
        "v3",
        credentials=creds
    )

    return service

def get_gmail_service():
    """
    Crée un service Gmail API à partir des credentials OAuth.
    """

    creds = get_google_credentials()

    service = build(
        "gmail",
        "v1",
        credentials=creds
    )

    return service


# ============================================================
# 4. VALIDATION DES DATES
# ============================================================

def parse_iso_datetime(value: str) -> datetime:
    """
    Convertit une date ISO en objet datetime Python.

    Exemple attendu :
    2026-05-23T14:00:00+02:00
    """

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"Format datetime invalide : {value}. "
            "Format attendu : 2026-05-23T14:00:00+02:00"
        ) from error

    if parsed.tzinfo is None:
        raise ValueError(
            f"La date doit contenir un fuseau horaire : {value}. "
            "Exemple attendu : 2026-05-23T14:00:00+02:00"
        )

    return parsed


def validate_event_datetimes(start_time: str, end_time: str):
    """
    Vérifie les dates avant d'appeler Google Calendar API.

    Sécurités :
    - format ISO obligatoire
    - fuseau horaire obligatoire
    - date de début pas dans le passé
    - date de fin après date de début
    """

    start_dt = parse_iso_datetime(start_time)
    end_dt = parse_iso_datetime(end_time)

    current_now = datetime.now(TIMEZONE)

    if start_dt < current_now:
        raise ValueError(
            f"La date de début est dans le passé : {start_time}. "
            f"Date actuelle : {current_now.isoformat()}"
        )

    if end_dt <= start_dt:
        raise ValueError(
            f"La date de fin doit être après la date de début. "
            f"Début : {start_time}, fin : {end_time}"
        )

    return start_dt, end_dt


def ask_confirmation(action_description: str) -> bool:
    """
    Validation humaine avant action réelle.
    """

    print("\n================ VALIDATION HUMAINE ================")
    print(action_description)
    print("====================================================")

    answer = input("Confirmer cette action ? (oui/non) : ").strip().lower()

    return answer in ["oui", "o", "yes", "y"]


# ============================================================
# 5. TOOLS CALENDRIER REELS
# ============================================================

@tool
def get_available_time_slots(
    date: str,
    duration_minutes: int
) -> list[str]:
    """
    Check available time slots in the user's primary Google Calendar.

    Args:
        date: Date in ISO format, example: 2026-05-23.
        duration_minutes: Meeting duration in minutes.

    Returns:
        Available time slots between 09:00 and 18:00.
    """

    service = get_calendar_service()

    start_of_day = datetime.fromisoformat(f"{date}T09:00:00+02:00")
    end_of_day = datetime.fromisoformat(f"{date}T18:00:00+02:00")

    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_of_day.isoformat(),
        timeMax=end_of_day.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])

    busy_periods = []

    for event in events:
        start = event.get("start", {}).get("dateTime")
        end = event.get("end", {}).get("dateTime")

        if start and end:
            busy_periods.append({
                "start": datetime.fromisoformat(start),
                "end": datetime.fromisoformat(end),
            })

    available_slots = []
    current_time = start_of_day

    while current_time + timedelta(minutes=duration_minutes) <= end_of_day:
        slot_start = current_time
        slot_end = current_time + timedelta(minutes=duration_minutes)

        is_busy = False

        for busy in busy_periods:
            if slot_start < busy["end"] and slot_end > busy["start"]:
                is_busy = True
                break

        if not is_busy:
            available_slots.append(slot_start.strftime("%H:%M"))

        current_time += timedelta(minutes=30)

    return available_slots


@tool
def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[str],
    location: str = "",
    description: str = "",
    add_google_meet: bool = True
) -> str:
    """
    Create a real Google Calendar event with an optional Google Meet link.

    Args:
        title: Event title.
        start_time: Start datetime in ISO format, example: 2026-05-23T14:00:00+02:00.
        end_time: End datetime in ISO format, example: 2026-05-23T15:00:00+02:00.
        attendees: List of attendee email addresses.
        location: Optional event location.
        description: Optional event description.
        add_google_meet: If True, Google Calendar API creates a real Google Meet link.

    Returns:
        Structured confirmation message with event ID, Calendar link and Meet link.
    """

    try:
        start_dt, end_dt = validate_event_datetimes(start_time, end_time)
    except ValueError as error:
        return f"EVENT_VALIDATION_ERROR: {error}"

    action_description = (
        f"Créer un événement Google Calendar :\n"
        f"Titre       : {title}\n"
        f"Début       : {start_dt.isoformat()}\n"
        f"Fin         : {end_dt.isoformat()}\n"
        f"Invités     : {attendees}\n"
        f"Lieu        : {location}\n"
        f"Description : {description}\n"
        f"Google Meet : {add_google_meet}"
    )

    if not ask_confirmation(action_description):
        return "Création de l'événement annulée par l'utilisateur."

    service = get_calendar_service()

    event_body = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": TIMEZONE_NAME,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": TIMEZONE_NAME,
        },
        "attendees": [{"email": email} for email in attendees],
    }

    if add_google_meet:
        event_body["conferenceData"] = {
            "createRequest": {
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {
                    "type": "hangoutsMeet"
                },
            }
        }

    event = service.events().insert(
        calendarId="primary",
        body=event_body,
        sendUpdates="all",
        conferenceDataVersion=1 if add_google_meet else 0,
    ).execute()

    event_id = event.get("id", "")
    calendar_link = event.get("htmlLink", "")
    meet_link = event.get("hangoutLink", "")

    if not meet_link:
        conference_data = event.get("conferenceData", {})
        entry_points = conference_data.get("entryPoints", [])

        for entry_point in entry_points:
            if entry_point.get("entryPointType") == "video":
                meet_link = entry_point.get("uri", "")
                break

    return (
        "EVENT_CREATED\n"
        f"Event ID: {event_id}\n"
        f"Title: {title}\n"
        f"Start: {start_dt.isoformat()}\n"
        f"End: {end_dt.isoformat()}\n"
        f"Attendees: {attendees}\n"
        f"Location: {location}\n"
        f"Description: {description}\n"
        f"Calendar link: {calendar_link}\n"
        f"Google Meet link: {meet_link}"
    )


# ============================================================
# 6. PROMPT DE L'AGENT CALENDRIER
# ============================================================

CALENDAR_AGENT_PROMPT = f"""
You are a calendar scheduling assistant.

Current real date: {CURRENT_DATE}
Current real time: {CURRENT_TIME}
Timezone: {TIMEZONE_NAME}

Your role:
- Understand calendar and scheduling requests.
- Convert natural language dates into exact ISO datetime format.
- Use the current date above as the only reference for relative dates.
- If the user says "demain", calculate it from {CURRENT_DATE}.
- If the user says "après-demain", calculate it from {CURRENT_DATE}.
- If the user says "lundi prochain", calculate the next Monday after {CURRENT_DATE}.
- If the user says "mardi prochain", calculate the next Tuesday after {CURRENT_DATE}.
- If the user gives a specific date, use that specific date.
- Never create an event in the past.
- If the date or time is ambiguous, ask a clarification question.
- Use Europe/Paris timezone.
- Always use ISO datetime format with timezone, for example: 2026-05-23T14:00:00+02:00.
- If the user gives an email address for a participant, put it in attendees.
- Always include all important event details in your final answer: title, start, end, attendees, location, and Calendar link if available.

- If the user asks for Google Meet, call create_calendar_event with add_google_meet=True.
- If the event is online, set location to "Google Meet".
- Your final answer must include:
  - Title
  - Start
  - End
  - Attendees
  - Location
  - Calendar link
  - Google Meet link if available
- Do not invent a Google Meet link. Only use the link returned by the tool.
"""


# ============================================================
# 7. AGENT CALENDRIER
# ============================================================

calendar_agent = create_agent(
    model=model,
    tools=[
        get_available_time_slots,
        create_calendar_event,
    ],
    system_prompt=CALENDAR_AGENT_PROMPT,
)

# ============================================================
# 8. TOOL EMAIL - GMAIL API
# ============================================================

@tool
def send_email(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] = []
) -> str:
    """
    Send a real email using Gmail API.

    Args:
        to: List of recipient email addresses.
        subject: Email subject.
        body: Email body.
        cc: Optional list of CC email addresses.

    Returns:
        Confirmation message with Gmail message ID.
    """

    action_description = (
        f"Envoyer un email :\n"
        f"À           : {to}\n"
        f"CC          : {cc}\n"
        f"Objet       : {subject}\n\n"
        f"Corps :\n{body}"
    )

    if not ask_confirmation(action_description):
        return "Envoi de l'email annulé par l'utilisateur."

    service = get_gmail_service()

    message = EmailMessage()
    message["To"] = ", ".join(to)
    message["Subject"] = subject

    if cc:
        message["Cc"] = ", ".join(cc)

    message.set_content(body)

    encoded_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode()

    sent_message = service.users().messages().send(
        userId="me",
        body={"raw": encoded_message}
    ).execute()

    message_id = sent_message.get("id", "ID indisponible")

    return (
        "EMAIL_SENT\n"
        f"To: {to}\n"
        f"Subject: {subject}\n"
        f"Message ID: {message_id}"
    )

# ============================================================
# 9. PROMPT DE L'AGENT EMAIL
# ============================================================

EMAIL_AGENT_PROMPT = """
You are an email assistant.

Your role:
- Handle only email-related tasks.
- Compose clear and professional emails.
- Extract recipient email addresses when explicitly provided.
- Do not invent email addresses.
- If the recipient email is missing, ask the user for it.
- Use send_email only when the user clearly asks to send an email.
- Always summarize what was sent in your final answer.

- If the email is about a calendar event, include the exact details returned by the calendar tool.
- Include the Google Calendar link if available.
- Include the Google Meet link only if it is explicitly present.
- Do not write "Google Meet link" if no actual URL was provided.
- Do not change the event time. Use exactly the start and end time returned by the calendar tool.
"""

# ============================================================
# 10. AGENT EMAIL
# ============================================================

email_agent = create_agent(
    model=model,
    tools=[
        send_email,
    ],
    system_prompt=EMAIL_AGENT_PROMPT,
)

# ============================================================
# 11. CONTROLE DU FLUX D'INFORMATIONS
# ============================================================

def message_to_text(message) -> str:
    """
    Convertit un message LangChain en texte lisible.
    """

    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    return str(content)


def build_conversation_context(runtime: ToolRuntime) -> str:
    """
    Récupère l'historique de conversation disponible dans le runtime.

    Cela permet au sous-agent de comprendre les messages précédents,
    par exemple quand l'utilisateur complète une information manquante.
    """

    messages = runtime.state.get("messages", [])

    conversation_lines = []

    for message in messages:
        message_type = getattr(message, "type", "unknown")
        text = message_to_text(message)

        conversation_lines.append(f"{message_type.upper()} : {text}")

    return "\n".join(conversation_lines)

# ============================================================
# 11. UTILITAIRE POUR EXTRAIRE LA REPONSE FINALE
# ============================================================

def extract_final_text(agent_result) -> str:
    """
    Récupère le dernier message texte produit par un agent LangChain.
    """

    messages = agent_result.get("messages", [])

    if not messages:
        return "Aucune réponse générée."

    last_message = messages[-1]
    content = getattr(last_message, "content", "")

    if isinstance(content, str):
        return content

    return str(content)



# ============================================================
# 12. ENCAPSULATION DES SOUS-AGENTS EN TOOLS
# ============================================================

@tool
def schedule_event(
    request: str,
    runtime: ToolRuntime
) -> str:
    """
    Schedule or check calendar events using natural language.

    Use this tool when the user wants to:
    - create a calendar event
    - schedule a meeting
    - check availability
    - plan an appointment
    - add participants to a meeting

    This tool delegates the request to the specialized calendar agent,
    while also passing the full conversation context.
    """

    conversation_context = build_conversation_context(runtime)

    prompt = f"""
You are the specialized calendar sub-agent.

Current real date: {CURRENT_DATE}
Current real time: {CURRENT_TIME}
Timezone: {TIMEZONE_NAME}

FULL CONVERSATION CONTEXT:
{conversation_context}

CALENDAR SUB-REQUEST FROM THE SUPERVISOR:
{request}

Instructions:
- Use the full conversation context to resolve missing information.
- If the user previously asked to create an event and later gives the time or duration, combine both messages.
- Do not restart from zero when the user gives missing information.
- Extract the event title, date, start time, duration, attendees, location and description.
- If enough information is available, call create_calendar_event.
- If information is still missing, ask a precise clarification question.
- Never create an event in the past.
- Use ISO datetime format with timezone when calling tools.
- Always include all important event details in your final answer.
"""

    result = calendar_agent.invoke({
        "messages": [
            {"role": "user", "content": prompt}
        ]
    })

    return extract_final_text(result)

@tool
def manage_email(
    request: str,
    runtime: ToolRuntime
) -> str:
    """
    Compose and send emails using natural language.

    Use this tool when the user wants to:
    - send an email
    - send a reminder
    - notify someone
    - send event details by email

    This tool delegates the request to the specialized email agent,
    while also passing the full conversation context.
    """

    conversation_context = build_conversation_context(runtime)

    prompt = f"""
You are the specialized email sub-agent.

FULL CONVERSATION CONTEXT:
{conversation_context}

EMAIL SUB-REQUEST FROM THE SUPERVISOR:
{request}

Instructions:
- Use the full conversation context to understand what email must be sent.
- If the email concerns a calendar event, include all available event details.
- If the calendar agent returned a Calendar link, include it in the email body.
- Do not invent recipient email addresses.
- If the recipient is missing, ask for it.
- If enough information is available, call send_email.
- Always summarize what was sent in your final answer.
"""

    result = email_agent.invoke({
        "messages": [
            {"role": "user", "content": prompt}
        ]
    })

    return extract_final_text(result)


# ============================================================
# 13. PROMPT DU SUPERVISEUR
# ============================================================

SUPERVISOR_PROMPT = f"""
You are a personal assistant supervisor.

Current real date: {CURRENT_DATE}
Current real time: {CURRENT_TIME}
Timezone: {TIMEZONE_NAME}

You coordinate two specialized sub-agents:
- schedule_event for calendar and scheduling tasks.
- manage_email for email and communication tasks.

Your role:
- Understand the user's global request.
- Split complex requests into smaller tasks.
- Route each task to the correct specialized tool.
- If the request is only about calendar, use schedule_event.
- If the request is only about email, use manage_email.
- If the request contains both calendar and email, use both tools in sequence.
- Do not invent email addresses.
- Do not invent dates.
- Ask for missing information when needed.
- Summarize the final result clearly.

Important workflow:
- If the user asks to create an event and send the event details by email:
  1. First call schedule_event to create the event.
  2. Use the event details returned by schedule_event, including the Calendar link.
  3. Then call manage_email to send those details to the recipient.

  Conversation memory rule:
- The full conversation history is available.
- If the assistant previously asked for missing information and the user now provides it, combine the new answer with the previous request.
- Do not treat follow-up answers as independent new requests.
- Example:
  User: "Create an event next Wednesday called sport à Léo, email romixsop@gmail.com"
  Assistant: "What time and duration?"
  User: "It starts at 13h and lasts 1h on Google Meet"
  You must understand this as the same event request.

Information flow rule:
- When calling schedule_event or manage_email, include enough information in the request.
- For event + email workflows, first call schedule_event.
- Then use the event details returned by schedule_event, including the Calendar link, when calling manage_email.

Event + email workflow:
- If the user asks to create an event and send the details by email:
  1. First call schedule_event.
  2. Wait for the calendar result.
  3. Extract the exact event details from the calendar result.
  4. Then call manage_email with those exact details.
  5. The email must include the Calendar link.
  6. The email must include the Google Meet link only if returned by the calendar result.
  7. Never invent or modify event time, date, or link.
"""

# ============================================================
# 14. AGENT SUPERVISEUR
# ============================================================

supervisor_agent = create_agent(
    model=model,
    tools=[
        schedule_event,
        manage_email,
    ],
    system_prompt=SUPERVISOR_PROMPT,
)

# ============================================================
# 15. MODE INTERACTIF SUPERVISEUR
# ============================================================
def run_supervisor():
    print("\nAssistant personnel multi-agents lancé.")
    print(f"Date actuelle utilisée : {CURRENT_DATE}")
    print(f"Heure actuelle utilisée : {CURRENT_TIME}")
    print(f"Fuseau horaire : {TIMEZONE_NAME}")
    print("Tape 'exit' pour quitter.\n")

    messages = []

    while True:
        user_input = input("Toi > ").strip()

        if user_input.lower() in ["exit", "quit", "q"]:
            print("Fin.")
            break

        messages.append({
            "role": "user",
            "content": user_input
        })

        result = supervisor_agent.invoke({
            "messages": messages
        })

        final_answer = extract_final_text(result)

        print("\nAssistant >")
        print(final_answer)
        print()

        messages.append({
            "role": "assistant",
            "content": final_answer
        })

if __name__ == "__main__":
    run_supervisor()