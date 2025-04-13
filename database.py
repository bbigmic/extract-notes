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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT,
                    transcription TEXT,
                    notes TEXT,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT,
                transcription TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
    
    conn.commit()
    conn.close()

def hash_password(password):
    """Haszuje hasło używając SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, email):
    """Rejestruje nowego użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        hashed_password = hash_password(password)
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('INSERT INTO users (username, password, email) VALUES (%s, %s, %s)',
                     (username, hashed_password, email))
        else:
            c.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                     (username, hashed_password, email))
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

def save_transcription(user_id, title, transcription, notes):
    """Zapisuje transkrypcję dla użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('''
                INSERT INTO transcriptions (user_id, title, transcription, notes)
                VALUES (%s, %s, %s, %s)
            ''', (user_id, title, transcription, notes))
        else:
            c.execute('''
                INSERT INTO transcriptions (user_id, title, transcription, notes)
                VALUES (?, ?, ?, ?)
            ''', (user_id, title, transcription, notes))
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

def get_transcription(transcription_id, user_id):
    """Pobiera konkretną transkrypcję użytkownika"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if DATABASE_URL and HAS_POSTGRES and 'neon' in DATABASE_URL:
            c.execute('''
                SELECT title, transcription, notes
                FROM transcriptions
                WHERE id = %s AND user_id = %s
            ''', (transcription_id, user_id))
        else:
            c.execute('''
                SELECT title, transcription, notes
                FROM transcriptions
                WHERE id = ? AND user_id = ?
            ''', (transcription_id, user_id))
        transcription = c.fetchone()
        return transcription
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
    """Używa jeden kredyt użytkownika. Zwraca True jeśli operacja się powiodła."""
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
                c.execute('UPDATE users SET credits = credits - 1 WHERE id = %s', (user_id,))
            else:
                c.execute('UPDATE users SET credits = credits - 1 WHERE id = ?', (user_id,))
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