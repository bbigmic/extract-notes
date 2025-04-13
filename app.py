import os
import whisper
import requests
from pydub import AudioSegment
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_audio
import warnings
import subprocess
import torch
import streamlit as st
import tempfile
import time
from datetime import datetime
import yt_dlp
from openai import OpenAI
from dotenv import load_dotenv
import stripe
from database import init_db, register_user, verify_user, save_transcription, get_user_transcriptions, get_transcription, get_user_credits, use_credit, add_credits
import json

# Inicjalizacja bazy danych
init_db()

# Wczytaj zmienne z pliku .env
load_dotenv()

# Konfiguracja Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

# Konfiguracja API
API_URL = os.getenv("API_URL", "http://localhost:8000")
APP_URL = os.getenv("APP_URL", "http://localhost:8501")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Konfiguracja globalna
warnings.filterwarnings("ignore", category=FutureWarning, module="torch")
warnings.filterwarnings("ignore", category=UserWarning, module="whisper.transcribe")

SUPPORTED_AUDIO = (".wav", ".mp3", ".m4a", ".flac")
SUPPORTED_VIDEO = (".mp4", ".mov", ".avi", ".mkv")
MAX_FILE_SIZE_MB = 500  # Maksymalny rozmiar pliku w MB

def login_user(username: str, password: str) -> dict:
    response = requests.post(
        f"{API_URL}/token",
        json={"username": username, "password": password}
    )
    if response.status_code == 200:
        return response.json()
    return None

def register_user(username: str, password: str, email: str) -> bool:
    response = requests.post(
        f"{API_URL}/register",
        json={"username": username, "password": password, "email": email}
    )
    return response.status_code == 200

def verify_token(token: str) -> dict:
    response = requests.get(
        f"{API_URL}/verify-token",
        params={"token": token}
    )
    if response.status_code == 200:
        return response.json()
    return None

def add_credits(user_id: int) -> bool:
    response = requests.post(f"{API_URL}/add-credits/{user_id}")
    return response.status_code == 200

def is_valid_file(file_path):
    try:
        command = ["ffmpeg", "-v", "error", "-i", file_path, "-f", "null", "-"]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def download_video(url):
    output_path = "downloaded_video.mp4"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path
    except Exception as e:
        raise ValueError(f"Failed to download video: {e}")

def convert_to_wav(file_path):
    print(f"Converting file: {file_path}")
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File {file_path} does not exist.")
    
    if not is_valid_file(file_path):
        raise ValueError(f"File {file_path}  is corrupted or unsupported.")
    
    if file_ext in SUPPORTED_AUDIO:
        audio = AudioSegment.from_file(file_path)
        output_path = "converted_audio.wav"
        audio.export(output_path, format="wav")
        return output_path
    elif file_ext in SUPPORTED_VIDEO:
        output_path = "extracted_audio.wav"
        try:
            ffmpeg_extract_audio(file_path, output_path)
        except Exception as e:
            raise ValueError(f"Failed to extract audio: {e}")
        return output_path
    else:
        raise ValueError(f"Unsupported file format: {file_ext}")

def transcribe_audio(audio_path, language):
    print("Transcribing audio...")
    try:
        model = whisper.load_model("large")
        result = model.transcribe(audio_path, language=language if language != "auto" else None)
        return result['text']
    except Exception as e:
        return f"Transcription error: {e}"

def analyze_transcription(transcription, language):
    print("Analyzing key conversation points...")
    prompts = {
        "pl": f"""
        Działaj jako ekspert ds. komunikacji i robienia notatek. Stwórz notatki z treści Transkrypcji w następującym formacie:
        1. **Najważniejsze ustalenia**
        2. **Zadania do wykonania**
        3. **Dodatkowe notatki**
        
        Treść Transkrypcji:
        {transcription}
        """,
        "en": f"""
        Act as an expert in communication and note-taking. Create notes from the Transcription content in the following format:
        1. **Key Decisions**
        2. **Tasks to Complete**
        3. **Additional Notes**
        
        Transcription content:
        {transcription}
        """,
        "de": f"""
        Agiere als Experte für Kommunikation und Notizenmachen. Erstelle Notizen aus dem Inhalt der Transkription im folgenden Format:
        1. **Wichtige Entscheidungen**
        2. **Zu erledigende Aufgaben**
        3. **Zusätzliche Notizen**
        
        Inhalt der Transkription:
        {transcription}
        """,
        "fr": f"""
        Agis en tant qu'expert en communication et en prise de notes. Crée des notes à partir du contenu de la Transcription au format suivant :
        1. **Décisions importantes**
        2. **Tâches à accomplir**
        3. **Notes supplémentaires**
        
        Contenu de la transcription :
        {transcription}
        """,
        "es": f"""
        Actúa como un experto en comunicación y toma de notas. Crea notas del contenido de la Transcripción en el siguiente formato:
        1. **Decisiones Clave**
        2. **Tareas a Completar**
        3. **Notas Adicionales**
        
        Contenido de la transcripción:
        {transcription}
        """
    }

    prompt = prompts.get(language, prompts["en"])

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"OpenAI API error: {e}"

def analyze_with_custom_prompt(transcription, original_notes, custom_prompt, include_previous_notes=False):
    print("Analyzing with a custom prompt...")
    
    combined_prompt = f"""
    Perform the following task: "{custom_prompt}" based on the transcription. Write in language that the task is written in.

    **Transkrypcja:**
    {transcription}
    """

    if include_previous_notes:
        combined_prompt += f"""
    
    **Poprzednie notatki:**
    {original_notes}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": combined_prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"OpenAI API error: {e}"

def save_transcription_and_notes(transcription, notes):
    filename = f"meeting_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    file_path = os.path.join(tempfile.gettempdir(), filename)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("📌 **Transcription:**\n")
        f.write(transcription + "\n\n")
        f.write("📝 **Notes:**\n")
        f.write(notes)
    
    return file_path

def show_user_transcriptions():
    st.sidebar.title("Your Transcriptions")
    transcriptions = get_user_transcriptions(st.session_state.user_id)
    
    if transcriptions:
        for trans_id, title, created_at in transcriptions:
            if st.sidebar.button(f"{title} ({created_at})", key=f"trans_{trans_id}"):
                trans_data = get_transcription(trans_id, st.session_state.user_id)
                if trans_data:
                    st.session_state.transcription = trans_data[1]
                    st.session_state.notes = trans_data[2]
                    st.session_state.processing_completed = True
                    st.rerun()

def create_checkout_session(user_id):
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': '30 Credits Package',
                        'description': '30 credits for transcriptions',
                    },
                    'unit_amount': 400,  # $4.00 w centach
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f'{APP_URL}?session_id={{CHECKOUT_SESSION_ID}}&user_id={user_id}',
            cancel_url=APP_URL,
            client_reference_id=str(user_id),
        )
        return checkout_session
    except Exception as e:
        st.error(f"Error creating checkout session: {e}")
        return None

def handle_successful_payment(session_id, user_id):
    try:
        # Weryfikacja sesji płatności
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid" and session.client_reference_id == str(user_id):
            # Dodaj kredyty
            if add_credits(user_id):
                return True
        return False
    except Exception as e:
        st.error(f"Error processing payment: {e}")
        return False

def main():
    st.title("Audio/Video Transcription and Information Extraction")
    
    # Inicjalizacja zmiennych sesyjnych
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "credits" not in st.session_state:
        st.session_state.credits = 0
    if "token" not in st.session_state:
        st.session_state.token = None
    if "transcription" not in st.session_state:
        st.session_state.transcription = None
    if "notes" not in st.session_state:
        st.session_state.notes = None
    if "custom_notes" not in st.session_state:
        st.session_state.custom_notes = None
    if "summary_file" not in st.session_state:
        st.session_state.summary_file = None
    if "processing_completed" not in st.session_state:
        st.session_state.processing_completed = False

    # Próba odzyskania tokena z query params
    if not st.session_state.authenticated:
        saved_token = st.query_params.get("token", None)
        if saved_token:
            user_data = verify_token(saved_token)
            if user_data:
                st.session_state.token = saved_token
                st.session_state.authenticated = True
                st.session_state.user_id = user_data["user_id"]
                st.session_state.username = user_data["username"]
                st.session_state.credits = user_data["credits"]
                # Zapisz token w URL
                st.query_params["token"] = st.session_state.token
            else:
                # Token wygasł lub jest nieprawidłowy
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.query_params.clear()
                st.rerun()
    
    # Sprawdzanie tokenu przy starcie
    if st.session_state.token:
        user_data = verify_token(st.session_state.token)
        if user_data:
            st.session_state.authenticated = True
            st.session_state.user_id = user_data["user_id"]
            st.session_state.username = user_data["username"]
            st.session_state.credits = user_data["credits"]
            # Zapisz token w URL
            st.query_params["token"] = st.session_state.token
        else:
            # Token wygasł lub jest nieprawidłowy
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.query_params.clear()
            st.rerun()
    
    # Sidebar dla logowania/rejestracji
    with st.sidebar:
        if not st.session_state.get('authenticated', False):
            st.title("Login")
            auth_status = st.radio("Choose option:", ("Login", "Register"))
            
            if auth_status == "Login":
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                
                if st.button("Sign In"):
                    result = login_user(username, password)
                    if result:
                        st.session_state.token = result["access_token"]
                        st.session_state.authenticated = True
                        st.session_state.user_id = result["user_id"]
                        st.session_state.username = result["username"]
                        st.session_state.credits = result["credits"]
                        st.success("Successfully logged in!")
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
            
            else:  # Rejestracja
                with st.form("register_form"):
                    new_username = st.text_input("Username")
                    new_password = st.text_input("Password", type="password")
                    confirm_password = st.text_input("Confirm Password", type="password")
                    email = st.text_input("Email")
                    
                    if st.form_submit_button("Register"):
                        if new_password != confirm_password:
                            st.error("Passwords do not match!")
                        elif register_user(new_username, new_password, email):
                            st.success("Registration successful! You can now log in. You received 3 free credits!")
                        else:
                            st.error("Username or email already exists!")
        else:
            st.title(f"Welcome, {st.session_state.username}!")
            st.write(f"Credits remaining: {st.session_state.credits}")

            # Sekcja zakupu kredytów
            st.title("Buy Credits")
            
            # Przycisk do zakupu kredytów
            if st.button("Buy 30 Credits - $4"):
                checkout_session = create_checkout_session(st.session_state.user_id)
                if checkout_session:
                    st.markdown(f"""
                    <a href="{checkout_session.url}" target="_blank">
                        <button style="
                            background-color: #4CAF50;
                            color: white;
                            padding: 10px 20px;
                            border: none;
                            border-radius: 4px;
                            cursor: pointer;
                            font-size: 16px;">
                            Proceed to Payment
                        </button>
                    </a>
                    """, unsafe_allow_html=True)
                else:
                    st.error("Error creating payment session. Please try again.")

            # Obsługa sukcesu płatności
            if "session_id" in st.query_params and "user_id" in st.query_params:
                session_id = st.query_params["session_id"]
                user_id = int(st.query_params["user_id"])
                if handle_successful_payment(session_id, user_id):
                    st.success("Payment successful! 30 credits have been added to your account.")
                    # Odśwież dane użytkownika
                    user_data = verify_token(st.session_state.token)
                    if user_data:
                        st.session_state.credits = user_data["credits"]
                    # Wyczyść parametry URL po udanej płatności
                    st.query_params.clear()
                    if st.session_state.token:
                        st.query_params["token"] = st.session_state.token
                    st.rerun()
                else:
                    st.error("Error processing payment confirmation.")

            if st.button("Sign Out"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.query_params.clear()
                st.rerun()

    # Główny interfejs aplikacji
    if not st.session_state.authenticated:
        st.warning("🔒 Please log in to use the application")
        st.info("Application features are only available for logged-in users. Use the sidebar to log in or register.")
        
        # Pokazujemy interfejs, ale z zablokowanymi funkcjami
        col1, col2 = st.columns(2)
        with col1:
            st.selectbox(
                "Select transcription language (input)",
                ["auto", "pl", "en", "de", "fr", "es"],
                disabled=True,
                index=2  # Domyślnie wybieramy "en"
            )
        with col2:
            st.selectbox(
                "Select output language (notes)",
                ["pl", "en", "de", "fr", "es"],
                disabled=True,
                index=1  # Domyślnie wybieramy "en"
            )

        st.text_input("Paste YouTube or Instagram link", disabled=True)
        st.file_uploader("Select an audio or video file", type=list(SUPPORTED_AUDIO) + list(SUPPORTED_VIDEO), disabled=True)
        return

    # Sprawdzamy kredyty przed rozpoczęciem nowej transkrypcji
    if not st.session_state.processing_completed and st.session_state.credits <= 0:
        st.error("⚠️ You have no credits remaining. Please contact support to get more credits.")
        return

    # Tworzę dwie kolumny dla wyboru języków
    col1, col2 = st.columns(2)
    
    with col1:
        transcription_language = st.selectbox(
            "Select transcription language (input)",
            ["auto", "pl", "en", "de", "fr", "es"],
            help="Language of the audio/video content",
            index=0  # Domyślnie wybieramy "en"
        )
    
    with col2:
        output_language = st.selectbox(
            "Select output language (notes)",
            ["pl", "en", "de", "fr", "es"],
            help="Language of the generated notes",
            index=0  # Domyślnie wybieramy "en"
        )

    video_url = st.text_input("Paste YouTube or Instagram link")
    uploaded_file = st.file_uploader("Select an audio or video file", type=list(SUPPORTED_AUDIO) + list(SUPPORTED_VIDEO))

    if st.session_state.processing_completed:
        st.text_area("Transcription", st.session_state.transcription, height=300)
        st.text_area("Notes", st.session_state.notes, height=300)
        
        # Pole do wprowadzenia tytułu i przycisk zapisu
        title = st.text_input("Transcription Title")
        if st.button("Save Transcription"):
            if title.strip():
                if save_transcription(st.session_state.user_id, title, st.session_state.transcription, st.session_state.notes):
                    st.success("Transcription has been saved!")
                else:
                    st.error("An error occurred while saving the transcription.")
            else:
                st.warning("Please enter a title for the transcription.")
        
        if st.session_state.summary_file:
            with open(st.session_state.summary_file, "rb") as file:
                st.download_button(
                    "📥 Download Transcription and Notes",
                    data=file,
                    file_name=os.path.basename(st.session_state.summary_file),
                    mime="text/plain"
                )

        # Custom prompt section
        st.header("Extract Custom Information from Transcription")
        custom_prompt = st.text_area("Enter your question or instruction for analysis", height=150)
        use_previous_notes = st.checkbox("Include previous notes in the analysis", help="If checked, the previous notes will be included in the prompt for generating new notes")
        
        if st.button("Extract Information"):
            if custom_prompt.strip():
                progress = st.progress(0)
                status_placeholder = st.empty()
                status_placeholder.text("Analyzing transcription with your instructions...")
                progress.progress(85)
                
                st.session_state.custom_notes = analyze_with_custom_prompt(
                    st.session_state.transcription,
                    st.session_state.notes,
                    custom_prompt,
                    include_previous_notes=use_previous_notes
                )

                progress.progress(100)
                status_placeholder.success("Analysis completed! ✅")
                progress.empty()
            else:
                st.error("Please enter your question or instruction!")

        if st.session_state.custom_notes:
            st.header("Extracted Information")
            st.text_area("Analysis Results", st.session_state.custom_notes, height=300)
        
        return

    if not video_url and not uploaded_file:
        return

    # Dodajemy przycisk do rozpoczęcia przetwarzania
    start_processing = st.button("Start Processing")

    if not st.session_state.processing_completed and start_processing:
        if video_url:
            st.info("Processing video...")
            file_path = download_video(video_url)
        elif uploaded_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as temp_file:
                temp_file.write(uploaded_file.read())
                file_path = temp_file.name
        
        if os.path.getsize(file_path) > MAX_FILE_SIZE_MB * 1024 * 1024:
            st.error("The file is too large! The maximum size is 500 MB.")
            os.remove(file_path)
            return
        
        # Używamy kredytu przed rozpoczęciem przetwarzania
        if not use_credit(st.session_state.user_id):
            st.error("⚠️ You have no credits remaining. Please contact support to get more credits.")
            return
        
        # Aktualizujemy liczbę kredytów w sesji
        st.session_state.credits -= 1
        
        progress = st.progress(0)
        status_placeholder = st.empty()
        try:
            status_placeholder.text("Converting file to WAV format...")
            progress.progress(25)
            audio_path = convert_to_wav(file_path)
            
            status_placeholder.text("Transcribing audio... it can take a few minutes.")
            progress.progress(50)
            st.session_state.transcription = transcribe_audio(audio_path, transcription_language)
            
            status_placeholder.text("Analyzing key conversation points...")
            progress.progress(75)
            st.session_state.notes = analyze_transcription(st.session_state.transcription, output_language)
            
            status_placeholder.text("Saving transcription and notes...")
            progress.progress(100)

            st.session_state.summary_file = save_transcription_and_notes(
                st.session_state.transcription, st.session_state.notes
            )
            
            # Automatycznie zapisujemy transkrypcję z tytułem zawierającym datę
            title = f"Transcription {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            save_transcription(st.session_state.user_id, title, st.session_state.transcription, st.session_state.notes)
            
            st.session_state.processing_completed = True
            status_placeholder.success("Task successfully completed! ✅")
            
            st.rerun()
            
        except Exception as e:
            status_placeholder.error(f"Error: {e}")
        finally:
            os.remove(file_path)
            progress.empty()

if __name__ == "__main__":
    main()
