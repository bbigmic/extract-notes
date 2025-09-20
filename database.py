import sqlite3
import hashlib
import os
from datetime import datetime
from dotenv import load_dotenv
import urllib.parse

try:
    import psycopg2
    from psycopg2.extras import DictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

load_dotenv()

# Wybór bazy danych w zależności od środowiska
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    """Zwraca połączenie do bazy danych w zależności od środowiska"""
    if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
        # Produkcja - Neon PostgreSQL
        try:
            # Parsuj URL i dodaj wymagane parametry SSL
            result = urllib.parse.urlparse(DATABASE_URL)
            username = result.username
            password = result.password
            database = result.path[1:]
            hostname = result.hostname
            port = result.port

            return psycopg2.connect(
                database=database,
                user=username,
                password=password,
                host=hostname,
                port=port,
                sslmode='require'
            )
        except Exception as e:
            print(f"Error connecting to PostgreSQL: {e}")
            return sqlite3.connect('users.db')
    else:
        # Rozwój - SQLite
        return sqlite3.connect('users.db')

def init_db():
    """Inicjalizuje bazę danych"""
    conn = get_db_connection()
    c = conn.cursor()
    
    if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
        # PostgreSQL
        try:
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    credits INTEGER DEFAULT 3,
                    premium_tokens INTEGER DEFAULT 0,
                    terms_accepted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    title TEXT,
                    transcription TEXT,
                    notes TEXT,
                    custom_notes TEXT,
                    custom_prompt TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        except Exception as e:
            print(f"Error creating PostgreSQL tables: {e}")
            # Fallback to SQLite
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    credits INTEGER DEFAULT 3,
                    premium_tokens INTEGER DEFAULT 0,
                    terms_accepted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    transcription TEXT NOT NULL,
                    notes TEXT,
                    custom_notes TEXT,
                    custom_prompt TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
    else:
        # SQLite
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                credits INTEGER DEFAULT 3,
                premium_tokens INTEGER DEFAULT 0,
                terms_accepted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                transcription TEXT NOT NULL,
                notes TEXT,
                custom_notes TEXT,
                custom_prompt TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
    
    conn.commit()
    conn.close()

def hash_password(password):
    """Haszuje hasło używając SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, email, terms_accepted=False):
    """Rejestruje nowego użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        hashed_password = hash_password(password)
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('INSERT INTO users (username, password, email, terms_accepted) VALUES (%s, %s, %s, %s)',
                     (username, hashed_password, email, terms_accepted))
        else:
            c.execute('INSERT INTO users (username, password, email, terms_accepted) VALUES (?, ?, ?, ?)',
                     (username, hashed_password, email, terms_accepted))
        conn.commit()
        return True
    except (sqlite3.IntegrityError, psycopg2.IntegrityError):
        return False
    finally:
        conn.close()

def verify_user(username, password):
    """Weryfikuje dane logowania użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        if password is None:
            # Przypadek weryfikacji tokena - sprawdzamy tylko username
            if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
                c.execute('SELECT id, username, credits FROM users WHERE username = %s', (username,))
            else:
                c.execute('SELECT id, username, credits FROM users WHERE username = ?', (username,))
        else:
            # Przypadek logowania - sprawdzamy username i hasło
            hashed_password = hash_password(password)
            if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
                c.execute('SELECT id, username, credits FROM users WHERE username = %s AND password = %s',
                         (username, hashed_password))
            else:
                c.execute('SELECT id, username, credits FROM users WHERE username = ? AND password = ?',
                         (username, hashed_password))
        
        user = c.fetchone()
        return user if user else None
    finally:
        conn.close()

def save_transcription(user_id, title, transcription, notes, custom_notes=None, custom_prompt=None):
    """Zapisuje transkrypcję dla użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('''INSERT INTO transcriptions 
                         (user_id, title, transcription, notes, custom_notes, custom_prompt)
                         VALUES (%s, %s, %s, %s, %s, %s)''',
                     (user_id, title, transcription, notes, custom_notes, custom_prompt))
        else:
            c.execute('''INSERT INTO transcriptions 
                         (user_id, title, transcription, notes, custom_notes, custom_prompt)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                     (user_id, title, transcription, notes, custom_notes, custom_prompt))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving transcription: {e}")
        return False
    finally:
        conn.close()

def get_user_transcriptions(user_id):
    """Pobiera wszystkie transkrypcje użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('''
                SELECT id, title, created_at
                FROM transcriptions
                WHERE user_id = %s
                ORDER BY created_at DESC
            ''', (user_id,))
        else:
            c.execute('''
                SELECT id, title, created_at
                FROM transcriptions
                WHERE user_id = ?
                ORDER BY created_at DESC
            ''', (user_id,))
        transcriptions = c.fetchall()
        return transcriptions
    finally:
        conn.close()

def get_transcription(trans_id, user_id):
    """Pobiera konkretną transkrypcję użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''SELECT id, transcription, notes, custom_notes, custom_prompt 
                     FROM transcriptions 
                     WHERE id = ? AND user_id = ?''', (trans_id, user_id))
        result = c.fetchone()
        return result
    except Exception as e:
        print(f"Error getting transcription: {e}")
        return None
    finally:
        conn.close()

def get_user_credits(user_id):
    """Pobiera liczbę dostępnych kredytów użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('SELECT credits FROM users WHERE id = %s', (user_id,))
        else:
            c.execute('SELECT credits FROM users WHERE id = ?', (user_id,))
        result = c.fetchone()
        return result[0] if result else 0
    finally:
        conn.close()

def use_credit(user_id):
    """Używa jeden kredyt użytkownika i dodaje premium token. Zwraca True jeśli operacja się powiodła."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('SELECT credits FROM users WHERE id = %s', (user_id,))
        else:
            c.execute('SELECT credits FROM users WHERE id = ?', (user_id,))
        credits = c.fetchone()[0]
        if credits > 0:
            if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
                c.execute('UPDATE users SET credits = credits - 1, premium_tokens = premium_tokens + 1 WHERE id = %s', (user_id,))
            else:
                c.execute('UPDATE users SET credits = credits - 1, premium_tokens = premium_tokens + 1 WHERE id = ?', (user_id,))
            conn.commit()
            return True
        return False
    finally:
        conn.close()

def add_credits(user_id):
    """Dodaje 30 kredytów do konta użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('UPDATE users SET credits = credits + 30 WHERE id = %s', (user_id,))
        else:
            c.execute('UPDATE users SET credits = credits + 30 WHERE id = ?', (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding credits: {e}")
        return False
    finally:
        conn.close() 

def get_user_premium_tokens(user_id):
    """Pobiera liczbę premium tokens użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('SELECT premium_tokens FROM users WHERE id = %s', (user_id,))
        else:
            c.execute('SELECT premium_tokens FROM users WHERE id = ?', (user_id,))
        result = c.fetchone()
        return result[0] if result else 0
    finally:
        conn.close()

def migrate_database():
    """Dodaje nowe kolumny do istniejących tabel"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            # PostgreSQL
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_tokens INTEGER DEFAULT 0")
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN DEFAULT FALSE")
        else:
            # SQLite
            c.execute("ALTER TABLE users ADD COLUMN premium_tokens INTEGER DEFAULT 0")
            c.execute("ALTER TABLE users ADD COLUMN terms_accepted BOOLEAN DEFAULT FALSE")
        conn.commit()
    except Exception as e:
        print(f"Migration error (columns may already exist): {e}")
    finally:
        conn.close()

# Wywołaj migrację w init_db()
migrate_database() 