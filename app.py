import json
import streamlit as st

from google import genai
from google.genai import types
from twilio.rest import Client

from prompts import (
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
    SUMMARY_REQUEST_PROMPT,
)

MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash-lite",
]

MODEL_NAME = MODEL_CANDIDATES[0]


st.set_page_config(
    page_title="MacroSnap",
    page_icon="🥗",
    layout="centered"
)


st.markdown(
    """
    <style>

    /* Main page width */
    .block-container {
        max-width: 900px;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Centered onboarding */
    .onboarding-container {
        max-width: 720px;
        margin: 0 auto;
    }

    /* Logo */
    .macro-logo {
        text-align: center;
        font-size: 48px;
        font-weight: 700;
        margin-top: 20px;
        margin-bottom: 5px;
    }

    /* Subtitle */
    .macro-subtitle {
        text-align: center;
        color: #666666;
        font-size: 16px;
        margin-bottom: 45px;
    }

    /* Welcome */
    .welcome-title {
        font-size: 30px;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .welcome-text {
        font-size: 16px;
        margin-bottom: 25px;
    }

    /* Form card */
    .form-card {
        border: 1px solid #d9d9d9;
        border-radius: 10px;
        padding: 25px;
        margin-top: 10px;
    }

    /* Top chat header */
    .chat-logo {
        font-size: 34px;
        font-weight: 700;
    }

    .chat-subtitle {
        color: #777777;
        font-size: 14px;
    }

    </style>
    """,
    unsafe_allow_html=True
)

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]

TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]

TWILIO_WHATSAPP_FROM = st.secrets[
    "TWILIO_WHATSAPP_FROM"
]

TWILIO_CONTENT_SID = st.secrets[
    "TWILIO_CONTENT_SID"
]

@st.cache_resource
def get_gemini_client():

    return genai.Client(
        api_key=GEMINI_API_KEY
    )


gemini_client = get_gemini_client()

@st.cache_resource
def get_twilio_client():

    return Client(
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN
    )


twilio_client = get_twilio_client()



def render_message(message):

    with st.chat_message(message["role"]):

        if message["kind"] == "text":

            st.write(
                message["content"]
            )

        elif message["kind"] == "image":

            st.image(
                message["content"]
            )


def add_message(
    role,
    kind,
    content
):

    st.session_state.messages.append(
        {
            "role": role,
            "kind": kind,
            "content": content
        }
    )

    render_message(
        st.session_state.messages[-1]
    )



def remember_chat_turn(
    parts,
    response_text
):

    history_parts = []

    for part in parts:

        if isinstance(
            part,
            types.Part
        ):

            history_parts.append(
                part
            )

        else:

            history_parts.append(
                types.Part.from_text(
                    text=part
                )
            )

    st.session_state.chat_history.extend(
        [
            types.Content(
                role="user",
                parts=history_parts
            ),

            types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=response_text
                    )
                ]
            )
        ]
    )
def ask_gemini(parts):

    current_model = (
        st.session_state.model_name
    )

    candidate_order = [
        current_model
    ] + [
        model
        for model in MODEL_CANDIDATES
        if model != current_model
    ]

    saw_transient_error = False

    for model_name in candidate_order:

        try:

            if model_name == current_model:

                chat = (
                    st.session_state.chat
                )

            else:

                chat = (
                    gemini_client.chats.create(

                        model=model_name,

                        config=(
                            types.GenerateContentConfig(
                                system_instruction=(
                                    SYSTEM_PROMPT
                                )
                            )
                        ),

                        history=(
                            st.session_state.chat_history
                        )
                    )
                )

            response = chat.send_message(
                parts
            )

            st.session_state.chat = chat

            st.session_state.model_name = (
                model_name
            )

            remember_chat_turn(
                parts,
                response.text
            )

            return response.text

        except Exception as error:

            status_code = getattr(
                error,
                "code",
                None
            )

            if status_code is None:

                status_code = getattr(
                    error,
                    "status_code",
                    None
                )

            status_code = str(
                status_code
            )

            # Temporary errors
            if status_code in {
                "429",
                "500",
                "502",
                "503",
                "504"
            }:

                saw_transient_error = True

                continue

            # Model unavailable
            if status_code in {
                "403",
                "404"
            }:

                continue

            st.error(
                "Sorry, something went wrong. "
                "Please try again."
            )

            return None

    if saw_transient_error:

        st.warning(
            "All configured Gemini models are "
            "temporarily busy. Please try again "
            "in a moment."
        )

    else:

        st.error(
            "None of the configured Gemini models "
            "is available for this API key."
        )

    return None


def create_whatsapp_summary():

    try:

        summary_chat = (
            gemini_client.chats.create(

                model=(
                    st.session_state.model_name
                ),

                config=(
                    types.GenerateContentConfig(
                        system_instruction=(
                            SYSTEM_PROMPT
                        )
                    )
                ),

                history=(
                    st.session_state.chat_history
                )
            )
        )

        response = (
            summary_chat.send_message(
                SUMMARY_REQUEST_PROMPT
            )
        )

        return response.text

    except Exception as error:

        st.error(
            "Could not create WhatsApp summary: "
            f"{error}"
        )

        return None

def send_whatsapp(
    to_number,
    user_name,
    summary
):

    try:

        to_number = (
            to_number.strip()
        )

        if to_number.startswith(
            "whatsapp:"
        ):

            to_number = (
                to_number.replace(
                    "whatsapp:",
                    "",
                    1
                )
            )

        whatsapp_to = (
            f"whatsapp:{to_number}"
        )

        content_variables = json.dumps(
            {
                "1": user_name,
                "2": summary.strip()
            },
            ensure_ascii=False
        )

        message = (
            twilio_client.messages.create(

                from_=(
                    f"whatsapp:"
                    f"{TWILIO_WHATSAPP_FROM}"
                ),

                to=whatsapp_to,

                content_sid=(
                    TWILIO_CONTENT_SID
                ),

                content_variables=(
                    content_variables
                )
            )
        )

        return True, message.sid

    except Exception as error:

        return False, str(error)


if "onboarded" not in st.session_state:

    # Center the entire onboarding area
    left_space, center_space, right_space = st.columns(
        [1, 3, 1]
    )

    with center_space:

    
        st.markdown(
            """
            <div class="macro-logo">
                🥗 MacroSnap
            </div>

            <div class="macro-subtitle">
                Snap it. Track it. Understand it.
            </div>
            """,
            unsafe_allow_html=True
        )

        
        st.markdown(
            """
            <div class="welcome-title">
                👋 Welcome!
            </div>

            <div class="welcome-text">
                Enter your details once and start chatting
                with your AI nutrition buddy.
            </div>
            """,
            unsafe_allow_html=True
        )

        

        with st.form(
            "onboarding_form"
        ):

            name = st.text_input(
                "Your name",
                placeholder="Vidya"
            )

            whatsapp_number = st.text_input(
                "WhatsApp number",
                placeholder="+91XXXXXXXXXX"
            )

            submitted = (
                st.form_submit_button(
                    "Let's Get Started 🚀",
                    use_container_width=True
                )
            )


        if submitted:

            if (
                not name.strip()
                or not whatsapp_number.strip()
            ):

                st.warning(
                    "Please fill in both your "
                    "name and WhatsApp number."
                )

            else:

                st.session_state.name = (
                    name.strip()
                )

                st.session_state.whatsapp_number = (
                    whatsapp_number.strip()
                )

                st.session_state.chat = (
                    gemini_client.chats.create(

                        model=MODEL_NAME,

                        config=(
                            types.GenerateContentConfig(
                                system_instruction=(
                                    SYSTEM_PROMPT
                                )
                            )
                        )
                    )
                )

                st.session_state.model_name = (
                    MODEL_NAME
                )

                st.session_state.chat_history = []

                st.session_state.messages = []

                st.session_state.whatsapp_summary = (
                    None
                )

                st.session_state.onboarded = True

                st.rerun()

    st.stop()


header_left, header_right = st.columns(
    [4, 1]
)

with header_left:

    st.markdown(
        """
        <div class="chat-logo">
            🥗 MacroSnap
        </div>

        <div class="chat-subtitle">
            Snap it. Track it. Text yourself the results.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.caption(
        f"Logged in as {st.session_state.name}"
    )


with header_right:

    st.write("")

    send_button = st.button(
        "📱 Send to WhatsApp",
        use_container_width=True
    )



if send_button:

    if not st.session_state.chat_history:

        st.warning(
            "Please discuss at least one meal "
            "before sending a WhatsApp summary."
        )

    else:

    
        with st.spinner(
            "Summarizing your day..."
        ):

            summary = (
                create_whatsapp_summary()
            )

        if summary:

            st.session_state.whatsapp_summary = (
                summary
            )

        
            with st.spinner(
                "Sending to WhatsApp..."
            ):

                success, result = (
                    send_whatsapp(

                        st.session_state.whatsapp_number,

                        st.session_state.name,

                        summary
                    )
                )

            if success:

                st.success(
                    "✅ Your meal summary was "
                    "sent to WhatsApp!"
                )

            else:

                st.error(
                    "❌ WhatsApp message could "
                    "not be sent."
                )

                st.caption(
                    f"Twilio error: {result}"
                )


if st.session_state.get(
    "whatsapp_summary"
):

    st.info(
        "Summary prepared:"
    )

    st.write(
        st.session_state.whatsapp_summary
    )

if not st.session_state.messages:

    add_message(

        "assistant",

        "text",

        WELCOME_MESSAGE_TEMPLATE.format(
            name=st.session_state.name
        )
    )

else:

    for message in (
        st.session_state.messages
    ):

        render_message(
            message
        )


user_input = st.chat_input(
    "Ask a question, or attach a photo of your meal",
    accept_file=True,
    file_type=[
        "jpg",
        "jpeg",
        "png"
    ]
)

if user_input:

    photo = (
        user_input.files[0]
        if user_input.files
        else None
    )

    text = user_input.text

    parts = []


    if photo is not None:

        photo_bytes = (
            photo.getvalue()
        )

        add_message(
            "user",
            "image",
            photo_bytes
        )

        parts.append(
            types.Part.from_bytes(

                data=photo_bytes,

                mime_type=photo.type
            )
        )


    # -----------------------------------------------------
    # TEXT
    # -----------------------------------------------------

    if text:

        add_message(
            "user",
            "text",
            text
        )

        parts.append(
            text
        )

    elif photo is not None:

        parts.append(
            "What is this meal? "
            "Give me the calories and macros."
        )


   
    with st.spinner(
        "Crunching the numbers..."
    ):

        answer = ask_gemini(
            parts
        )


    if answer is not None:

        add_message(
            "assistant",
            "text",
            answer
        )