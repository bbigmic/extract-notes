# Prosta konfiguracja SSL
import ssl
import urllib3

# Wyłącz ostrzeżenia SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Tymczasowo wyłącz weryfikację SSL dla problematycznych połączeń
ssl._create_default_https_context = ssl._create_unverified_context