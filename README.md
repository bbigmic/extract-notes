# Audio/Video Transcription App

Aplikacja do transkrypcji audio/wideo z funkcją generowania notatek i analizy treści.

## Funkcje

- Transkrypcja plików audio i wideo
- Obsługa linków YouTube
- Generowanie notatek i podsumowań
- System kredytów i płatności
- Wielojęzyczne wsparcie
- Historia transkrypcji

## Wymagane zmienne środowiskowe

```env
# API Keys
OPENAI_API_KEY=your_openai_api_key
STRIPE_SECRET_KEY=your_stripe_secret_key
STRIPE_PUBLISHABLE_KEY=your_stripe_publishable_key

# Database
DATABASE_URL=postgres://user:password@ep-example.region.aws.neon.tech/dbname

# URLs (domyślne wartości dla lokalnego rozwoju)
APP_URL=http://localhost:8501  # W produkcji: https://twoja-app.streamlit.app
API_URL=http://localhost:8000  # W produkcji: https://twoja-api.onrender.com
```

## Instalacja lokalna

1. Sklonuj repozytorium
2. Utwórz wirtualne środowisko:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```
3. Zainstaluj zależności:
   ```bash
   pip install -r requirements.txt
   ```
4. Utwórz plik `.env` z wymaganymi zmiennymi środowiskowymi
5. Uruchom aplikację:
   ```bash
   # Terminal 1 - Backend
   uvicorn api:app --reload
   
   # Terminal 2 - Frontend
   streamlit run app.py
   ```

## Deployment

### Baza danych (Neon)

1. Utwórz konto na [Neon](https://neon.tech)
2. Utwórz nowy projekt
3. W projekcie:
   - Skopiuj connection string
   - Dodaj go jako `DATABASE_URL` w zmiennych środowiskowych
   - Możesz utworzyć osobne branche dla rozwoju i produkcji

### Backend (Render)

1. Utwórz konto na [Render](https://render.com)
2. Połącz z repozytorium GitHub
3. Wybierz "New Web Service"
4. Wybierz repozytorium
5. Ustaw nazwę (np. "transcription-api")
6. Wybierz środowisko "Python"
7. Ustaw zmienne środowiskowe:
   - `DATABASE_URL` (z Neon)
   - `OPENAI_API_KEY`
   - `STRIPE_SECRET_KEY`
   - `STRIPE_PUBLISHABLE_KEY`
   - `APP_URL` (URL twojej aplikacji Streamlit)
8. Kliknij "Create Web Service"

### Frontend (Streamlit Cloud)

1. Utwórz konto na [Streamlit Community Cloud](https://streamlit.io/cloud)
2. Połącz z repozytorium GitHub
3. Wybierz repozytorium
4. Ustaw zmienne środowiskowe:
   - `OPENAI_API_KEY`
   - `STRIPE_SECRET_KEY`
   - `STRIPE_PUBLISHABLE_KEY`
   - `API_URL` (URL twojego API na Render)
   - `APP_URL` (URL twojej aplikacji Streamlit)
5. Kliknij "Deploy"

## Struktura projektu

```
.
├── app.py              # Frontend (Streamlit)
├── api.py              # Backend (FastAPI)
├── auth.py             # Autentykacja
├── database.py         # Operacje na bazie danych
├── requirements.txt    # Zależności
├── Procfile           # Konfiguracja dla Render
├── render.yaml        # Konfiguracja dla Render
└── .env               # Zmienne środowiskowe (lokalnie)
```

## Licencja

MIT 