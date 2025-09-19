# 🔧 Naprawka problemu SSL

## Problem
Błąd: `Transcription error: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain>`

## Rozwiązanie
Dodano naprawkę SSL w funkcji `transcribe_audio()`:

### 1. Tymczasowe wyłączenie weryfikacji SSL
```python
import ssl
import urllib.request

# Tymczasowo wyłączamy weryfikację SSL dla pobierania modelu
original_ssl_context = ssl.create_default_context()
ssl._create_default_https_context = lambda: ssl._create_unverified_context()

try:
    model = whisper.load_model("base")
finally:
    # Przywracamy oryginalny kontekst SSL
    ssl._create_default_https_context = lambda: original_ssl_context
```

### 2. Naprawka dla yt-dlp
```python
ydl_opts = {
    # ... inne opcje ...
    'nocheckcertificate': True,
    'ignoreerrors': True,
}
```

### 3. Konfiguracja requests
```python
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
```

## Testowanie
Uruchom: `python3 simple_ssl_test.py`

## Status
✅ Naprawka przetestowana i działa
✅ Model Whisper pobiera się poprawnie
✅ yt-dlp działa bez problemów SSL
