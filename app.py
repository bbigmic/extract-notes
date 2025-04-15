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
from datetime import datetime, timedelta
import yt_dlp
import openai
from dotenv import load_dotenv
import stripe
from database import init_db, register_user, verify_user, save_transcription, get_user_transcriptions, get_transcription, get_user_credits, use_credit, add_credits, get_db_connection
import json
from jose import JWTError, jwt
from passlib.context import CryptContext

# Konfiguracja JWT
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-keep-it-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 godziny

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Funkcje autoryzacji przeniesione z auth.py
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

# Funkcje API przeniesione z api.py
def handle_login(username: str, password: str):
    user = verify_user(username, password)
    if not user:
        return None
    
    access_token = create_access_token(data={"sub": username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user[0],
        "username": user[1],
        "credits": user[2]
    }

def handle_register(username: str, password: str, email: str):
    try:
        success = register_user(username, password, email)
        if success:
            return True
        return False
    except Exception as e:
        return False

def handle_verify_token(token: str):
    username = decode_token(token)
    if username is None:
        return None
    user = verify_user(username, None)
    if not user:
        return None
    return {
        "user_id": user[0],
        "username": user[1],
        "credits": user[2]
    }

# Inicjalizacja bazy danych
init_db()

# Wczytaj zmienne z pliku .env
load_dotenv()

# Konfiguracja Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

# Konfiguracja API
APP_URL = os.getenv("APP_URL", "http://localhost:8501")

# Inicjalizacja klienta OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Konfiguracja globalna
warnings.filterwarnings("ignore", category=FutureWarning, module="torch")
warnings.filterwarnings("ignore", category=UserWarning, module="whisper.transcribe")

SUPPORTED_AUDIO = (".wav", ".mp3", ".m4a", ".flac")
SUPPORTED_VIDEO = (".mp4", ".mov", ".avi", ".mkv")
MAX_FILE_SIZE_MB = 500  # Maksymalny rozmiar pliku w MB

def is_valid_file(file_path):
    try:
        command = ["ffmpeg", "-v", "error", "-i", file_path, "-f", "null", "-"]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def download_video(url):
    print(f"Downloading from URL: {url}")
    with tempfile.NamedTemporaryFile(suffix='.%(ext)s', delete=False) as temp_video:
        output_template = temp_video.name
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': output_template,
            'quiet': False,  # Włączamy logi dla debugowania
            'no_warnings': False,
            'extract_flat': False,
            'ignoreerrors': True,
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 3,
            'verbose': True,  # Włączamy tryb verbose dla debugowania
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
            }],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            }
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    print("Starting download...")
                    info = ydl.extract_info(url, download=True)
                    if info is None:
                        raise ValueError("Could not extract video information")
                    
                    # Pobierz faktyczną ścieżkę pliku
                    output_path = ydl.prepare_filename(info)
                    output_path = output_path.rsplit('.', 1)[0] + '.wav'
                    
                    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                        raise ValueError("Download failed - empty or missing file")
                    
                    print(f"Download completed successfully. File saved as: {output_path}")
                    return output_path
                    
                except Exception as e:
                    print(f"Download error: {str(e)}")
                    raise ValueError(f"Failed to download: {str(e)}")
        except Exception as e:
            print(f"YDL error: {str(e)}")
            if os.path.exists(output_template):
                os.unlink(output_template)
            raise ValueError(f"Failed to download video: {str(e)}")

def convert_to_wav(file_path):
    print(f"Converting file: {file_path}")
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File {file_path} does not exist.")
    
    if not is_valid_file(file_path):
        raise ValueError(f"File {file_path} is corrupted or unsupported.")
    
    # Używamy NamedTemporaryFile do utworzenia unikalnej nazwy pliku
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
        output_path = temp_wav.name
        
        if file_ext in SUPPORTED_AUDIO:
            audio = AudioSegment.from_file(file_path)
            audio.export(output_path, format="wav")
        elif file_ext in SUPPORTED_VIDEO:
            try:
                ffmpeg_extract_audio(file_path, output_path)
            except Exception as e:
                if os.path.exists(output_path):
                    os.unlink(output_path)
                raise ValueError(f"Failed to extract audio: {e}")
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")
        
        return output_path

def transcribe_audio(audio_path, language):
    print("Transcribing audio...")
    try:
        print(f"Loading Whisper model...")
        model = whisper.load_model("base")  # Zmieniam na model "base" zamiast "large" dla szybszego przetwarzania
        print(f"Model loaded successfully. Starting transcription of file: {audio_path}")
        
        # Sprawdzamy czy plik istnieje i ma odpowiedni rozmiar
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        file_size = os.path.getsize(audio_path)
        print(f"Audio file size: {file_size / (1024*1024):.2f} MB")
        
        # Dodajemy parametry dla whisper, aby lepiej kontrolować proces
        result = model.transcribe(
            audio_path,
            language=language if language != "auto" else None,
            fp16=False,  # Wyłączamy fp16 dla lepszej kompatybilności
            verbose=True  # Włączamy szczegółowe logi
        )
        
        if not result or 'text' not in result:
            raise ValueError("Transcription result is empty or invalid")
            
        print("Transcription completed successfully")
        return result['text']
    except Exception as e:
        print(f"Error during transcription: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Transcription error: {str(e)}"

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
        client = openai.OpenAI()
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
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": combined_prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"OpenAI API error: {e}"

def save_transcription_and_notes(transcription, notes):
    # Tworzymy folder dla plików tymczasowych aplikacji, jeśli nie istnieje
    app_temp_dir = os.path.join(tempfile.gettempdir(), "transcription_app")
    os.makedirs(app_temp_dir, exist_ok=True)
    
    filename = f"meeting_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    file_path = os.path.join(app_temp_dir, filename)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("📌 **Transcription:**\n")
        f.write(transcription + "\n\n")
        f.write("📝 **Notes:**\n")
        f.write(notes)
    
    return file_path

def generate_title_from_transcription(transcription, max_words=3):
    """Generuje tytuł z pierwszych słów transkrypcji i aktualnej daty"""
    words = transcription.split()
    title_words = words[:max_words]
    title = " ".join(title_words)
    if len(words) > max_words:
        title += "..."
    
    # Dodaj datę w formacie "DD.MM.YYYY HH:MM"
    current_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    return f"{title} | {current_date}"

def show_user_transcriptions():
    st.sidebar.title("Your Transcriptions")
    transcriptions = get_user_transcriptions(st.session_state.user_id)
    
    if transcriptions:
        for trans_id, title, created_at in transcriptions:
            button_label = title
            if st.sidebar.button(button_label, key=f"trans_{trans_id}"):
                trans_data = get_transcription(trans_id, st.session_state.user_id)
                if trans_data:
                    st.session_state.transcription = trans_data[1]
                    st.session_state.notes = trans_data[2]
                    st.session_state.custom_notes = trans_data[3]
                    st.session_state.custom_prompt = trans_data[4]
                    st.session_state.processing_completed = True
                    st.rerun()

def create_checkout_session(user_id):
    try:
        # Zachowaj token z aktualnej sesji
        current_token = st.query_params.get("token", "")
        success_url = f'{APP_URL}?session_id={{CHECKOUT_SESSION_ID}}&user_id={user_id}'
        if current_token:
            success_url += f'&token={current_token}'
            
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
            success_url=success_url,
            cancel_url=f'{APP_URL}?token={current_token}' if current_token else APP_URL,
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
            # Dodaj kredyty bezpośrednio używając funkcji z database.py
            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute("UPDATE users SET credits = credits + 30 WHERE id = ?", (user_id,))
                conn.commit()
                # Aktualizuj dane użytkownika w sesji
                user = verify_user(st.session_state.username, None)
                if user:
                    st.session_state.credits = user[2]
                return True
            except Exception as e:
                print(f"Database error: {e}")
                return False
            finally:
                conn.close()
        return False
    except Exception as e:
        st.error(f"Error processing payment: {str(e)}")
        return False

def update_credits_display():
    if st.session_state.authenticated:
        st.sidebar.markdown(f"### Credits remaining: {st.session_state.credits}")

def main():
    st.set_page_config(
        page_title="Transcription & Notes Generator & Information Extraction App",
        page_icon="🎯",
        layout="wide"
    )

    st.title("Audio/Video Transcription & Notes Generator & Information Extraction")
    
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
    if "custom_prompt" not in st.session_state:
        st.session_state.custom_prompt = None
    if "summary_file" not in st.session_state:
        st.session_state.summary_file = None
    if "processing_completed" not in st.session_state:
        st.session_state.processing_completed = False
    if "credits_container" not in st.session_state:
        st.session_state.credits_container = None

    # Próba odzyskania tokena z query params
    if not st.session_state.authenticated:
        saved_token = st.query_params.get("token", None)
        if saved_token:
            user_data = handle_verify_token(saved_token)
            if user_data:
                st.session_state.token = saved_token
                st.session_state.authenticated = True
                st.session_state.user_id = user_data["user_id"]
                st.session_state.username = user_data["username"]
                st.session_state.credits = user_data["credits"]
                st.query_params["token"] = st.session_state.token
            else:
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.query_params.clear()
                st.rerun()
    
    # Sprawdzanie tokenu przy starcie
    if st.session_state.token:
        user_data = handle_verify_token(st.session_state.token)
        if user_data:
            st.session_state.authenticated = True
            st.session_state.user_id = user_data["user_id"]
            st.session_state.username = user_data["username"]
            st.session_state.credits = user_data["credits"]
            st.query_params["token"] = st.session_state.token
        else:
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
                    result = handle_login(username, password)
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
                        elif handle_register(new_username, new_password, email):
                            st.success("Registration successful! You can now log in. You received 3 free credits!")
                        else:
                            st.error("Username or email already exists!")
        else:
            st.title(f"Welcome, {st.session_state.username}!")
            # Kontener na kredyty, który będzie aktualizowany
            credits_container = st.empty()
            credits_container.markdown(f"### Credits remaining: {st.session_state.credits}")
            st.session_state.credits_container = credits_container

            # Sekcja zakupu kredytów
            st.title("Buy Credits")
            
            # Przycisk do zakupu kredytów
            if st.button("Buy 30 Credits - $4", type="primary"):
                checkout_session = create_checkout_session(st.session_state.user_id)
                if checkout_session:
                    # Automatyczne przekierowanie do strony płatności
                    st.markdown(f'<meta http-equiv="refresh" content="0;url={checkout_session.url}">', unsafe_allow_html=True)
                    st.info("Redirecting to payment page...")
                else:
                    st.error("Error creating payment session. Please try again.")

            # Obsługa sukcesu płatności
            if "session_id" in st.query_params and "user_id" in st.query_params:
                session_id = st.query_params["session_id"]
                user_id = int(st.query_params["user_id"])
                if handle_successful_payment(session_id, user_id):
                    st.success("Payment successful! 30 credits have been added to your account.")
                    # Zachowujemy token i usuwamy tylko parametry płatności
                    params_to_keep = {"token": st.query_params.get("token")} if "token" in st.query_params else {}
                    st.query_params.clear()
                    for key, value in params_to_keep.items():
                        st.query_params[key] = value
                    st.rerun()
                else:
                    st.error("Error processing payment confirmation.")
                    # Zachowujemy token i usuwamy tylko parametry płatności
                    params_to_keep = {"token": st.query_params.get("token")} if "token" in st.query_params else {}
                    st.query_params.clear()
                    for key, value in params_to_keep.items():
                        st.query_params[key] = value

            if st.button("Sign Out"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.query_params.clear()
                st.rerun()

            # Pokaż historię transkrypcji
            show_user_transcriptions()

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
        st.error("⚠️ You have no credits remaining. Please refill your credits with button on the left sidebar.")
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
        
        # Automatycznie generuj tytuł z pierwszych słów transkrypcji i daty
        default_title = generate_title_from_transcription(st.session_state.transcription)
        title = st.text_input("Transcription Title", value=default_title)
        
        if st.button("Save Transcription with New Title"):
            if title.strip():
                if save_transcription(st.session_state.user_id, title, st.session_state.transcription, st.session_state.notes):
                    st.success("Transcription has been saved!")
                    st.rerun()  # Odświeżamy stronę, aby zaktualizować historię
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
            # Sprawdzamy czy użytkownik ma wystarczającą liczbę kredytów
            if st.session_state.credits <= 0:
                st.error("⚠️ You have no credits remaining. Please refill your credits with button on the left sidebar.")
                return

            if custom_prompt.strip():
                # Używamy kredytu przed rozpoczęciem analizy
                if not use_credit(st.session_state.user_id):
                    st.error("⚠️ You have no credits remaining. Please contact support to get more credits.")
                    return
                
                # Aktualizujemy liczbę kredytów w sesji i wyświetlanie
                st.session_state.credits -= 1
                if st.session_state.credits_container:
                    st.session_state.credits_container.markdown(f"### Credits remaining: {st.session_state.credits}")
                
                try:
                    progress = st.progress(0)
                    status_placeholder = st.empty()
                    status_placeholder.text("Analyzing transcription with your instructions...")
                    progress.progress(85)
                    
                    st.session_state.custom_prompt = custom_prompt  # Zapisujemy prompt w sesji
                    st.session_state.custom_notes = analyze_with_custom_prompt(
                        st.session_state.transcription,
                        st.session_state.notes,
                        custom_prompt,
                        include_previous_notes=use_previous_notes
                    )

                    progress.progress(100)
                    status_placeholder.success("Analysis completed! ✅")
                    progress.empty()
                except Exception as e:
                    # W przypadku błędu zwracamy kredyt
                    st.session_state.credits += 1
                    if st.session_state.credits_container:
                        st.session_state.credits_container.markdown(f"### Credits remaining: {st.session_state.credits}")
                    st.error(f"Error during analysis: {str(e)}")
            else:
                st.error("Please enter your question or instruction!")

        if st.session_state.custom_notes:
            st.header("Extracted Information")
            st.text_area("Analysis Results", st.session_state.custom_notes, height=300)
            
            # Sekcja zapisywania analizy
            st.subheader("Save Analysis")
            custom_title = st.text_input(
                "Title for Custom Analysis",
                value=f"Custom Analysis | {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                key="custom_analysis_title"
            )
            
            if st.button("Save Custom Analysis", type="primary"):
                if not custom_title.strip():
                    st.error("Please enter a title for your analysis.")
                else:
                    if save_transcription(
                        st.session_state.user_id,
                        custom_title,
                        st.session_state.transcription,
                        st.session_state.notes,
                        st.session_state.custom_notes,
                        st.session_state.custom_prompt
                    ):
                        st.success("Custom analysis has been saved!")
                        st.rerun()  # Odświeżamy stronę, aby zaktualizować historię
                    else:
                        st.error("An error occurred while saving the custom analysis.")

        return

    if not video_url and not uploaded_file:
        return

    # Dodajemy przycisk do rozpoczęcia przetwarzania
    start_processing = st.button("Start Processing")

    if not st.session_state.processing_completed and start_processing:
        temp_files = []  # Lista plików do wyczyszczenia
        progress = None
        status_placeholder = None
        
        try:
            if video_url:
                st.info("Processing video...")
                try:
                    file_path = download_video(video_url)
                    if not file_path or not os.path.exists(file_path):
                        st.error("Failed to download the video. Please check the URL and try again.")
                        return
                    temp_files.append(file_path)
                except Exception as e:
                    st.error(f"Error downloading video: {str(e)}")
                    return
            elif uploaded_file:
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as temp_file:
                        temp_file.write(uploaded_file.read())
                        file_path = temp_file.name
                        temp_files.append(file_path)
                except Exception as e:
                    st.error(f"Error processing uploaded file: {str(e)}")
                    return
            
            if not os.path.exists(file_path):
                st.error("File not found. Please try again.")
                return
                
            if os.path.getsize(file_path) > MAX_FILE_SIZE_MB * 1024 * 1024:
                st.error(f"The file is too large! The maximum size is {MAX_FILE_SIZE_MB} MB.")
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
                temp_files.append(audio_path)
                
                status_placeholder.text("Transcribing audio... it can take a few minutes.")
                progress.progress(50)
                st.session_state.transcription = transcribe_audio(audio_path, transcription_language)
                
                status_placeholder.text("Analyzing key conversation points...")
                progress.progress(75)
                st.session_state.notes = analyze_transcription(st.session_state.transcription, output_language)
                
                status_placeholder.text("Saving transcription and notes...")
                progress.progress(100)

                # Nie dodajemy pliku podsumowania do temp_files
                st.session_state.summary_file = save_transcription_and_notes(
                    st.session_state.transcription, st.session_state.notes
                )
                
                # Automatycznie zapisujemy transkrypcję z wygenerowanym tytułem
                auto_title = generate_title_from_transcription(st.session_state.transcription)
                save_transcription(st.session_state.user_id, auto_title, st.session_state.transcription, st.session_state.notes)
                
                st.session_state.processing_completed = True
                status_placeholder.success("Task successfully completed! ✅")
                
                st.rerun()
            except Exception as e:
                if status_placeholder:
                    status_placeholder.error(f"Error during processing: {str(e)}")
                else:
                    st.error(f"Error during processing: {str(e)}")
                # Zwracamy kredyt w przypadku błędu
                st.session_state.credits += 1
                if st.session_state.credits_container:
                    st.session_state.credits_container.markdown(f"### Credits remaining: {st.session_state.credits}")
                return
                
        except Exception as e:
            st.error(f"Unexpected error: {str(e)}")
        finally:
            # Czyszczenie tylko plików audio/wideo
            for temp_file in temp_files:
                try:
                    if temp_file and os.path.exists(temp_file):
                        os.unlink(temp_file)
                except Exception as e:
                    print(f"Error removing temporary file {temp_file}: {e}")
            if progress:
                progress.empty()

if __name__ == "__main__":
    main()
