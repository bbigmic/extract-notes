import sqlite3
import hashlib
import os
from datetime import datetime
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv

load_dotenv()

# Wybór bazy danych w zależności od środowiska
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    """Zwraca połączenie do bazy danych w zależności od środowiska"""
    if DATABASE_URL and 'postgres' in DATABASE_URL:
        # Produkcja - PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        return conn
    else:
        # Rozwój - SQLite
        return sqlite3.connect('users.db')

def init_db():
    """Inicjalizuje bazę danych"""
    conn = get_db_connection()
    c = conn.cursor()
    
    if DATABASE_URL and 'postgres' in DATABASE_URL:
        # PostgreSQL
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
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        hashed_password = hash_password(password)
        c.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                 (username, hashed_password, email))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(username, password):
    """Weryfikuje dane logowania użytkownika"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    if password is None:
        # Przypadek weryfikacji tokena - sprawdzamy tylko username
        c.execute('SELECT id, username, credits FROM users WHERE username = ?', (username,))
    else:
        # Przypadek logowania - sprawdzamy username i hasło
        hashed_password = hash_password(password)
        c.execute('SELECT id, username, credits FROM users WHERE username = ? AND password = ?',
                 (username, hashed_password))
    
    user = c.fetchone()
    conn.close()
    return user if user else None

def save_transcription(user_id, title, transcription, notes):
    """Zapisuje transkrypcję dla użytkownika"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
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
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        SELECT id, title, created_at
        FROM transcriptions
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,))
    transcriptions = c.fetchall()
    conn.close()
    return transcriptions

def get_transcription(transcription_id, user_id):
    """Pobiera konkretną transkrypcję użytkownika"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        SELECT title, transcription, notes
        FROM transcriptions
        WHERE id = ? AND user_id = ?
    ''', (transcription_id, user_id))
    transcription = c.fetchone()
    conn.close()
    return transcription

def get_user_credits(user_id):
    """Pobiera liczbę dostępnych kredytów użytkownika"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT credits FROM users WHERE id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def use_credit(user_id):
    """Używa jeden kredyt użytkownika. Zwraca True jeśli operacja się powiodła."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        c.execute('SELECT credits FROM users WHERE id = ?', (user_id,))
        credits = c.fetchone()[0]
        if credits > 0:
            c.execute('UPDATE users SET credits = credits - 1 WHERE id = ?', (user_id,))
            conn.commit()
            return True
        return False
    finally:
        conn.close()

def add_credits(user_id):
    """Dodaje 30 kredytów do konta użytkownika"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        # Dodaj 30 kredytów
        c.execute('UPDATE users SET credits = credits + 30 WHERE id = ?', (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding credits: {e}")
        return False
    finally:
        conn.close() 