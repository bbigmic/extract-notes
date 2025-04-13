from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import timedelta
from auth import create_access_token, decode_token, ACCESS_TOKEN_EXPIRE_MINUTES, verify_password
from database import verify_user, register_user, get_user_credits, add_credits
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Konfiguracja CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("APP_URL", "http://localhost:8501")],  # Adres Streamlit
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserLogin(BaseModel):
    username: str
    password: str

class UserRegister(BaseModel):
    username: str
    password: str
    email: str

@app.post("/token")
async def login(user_data: UserLogin):
    user = verify_user(user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_data.username}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user[0],
        "username": user[1],
        "credits": user[2]
    }

@app.post("/register")
async def register(user_data: UserRegister):
    try:
        success = register_user(user_data.username, user_data.password, user_data.email)
        if success:
            return {"message": "User registered successfully"}
        else:
            raise HTTPException(
                status_code=400,
                detail="Username or email already exists"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.get("/verify-token")
async def verify_token(token: str):
    username = decode_token(token)
    if username is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )
    user = verify_user(username, None)  # Tylko sprawdzenie czy użytkownik istnieje
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )
    return {
        "user_id": user[0],
        "username": user[1],
        "credits": user[2]
    }

@app.post("/add-credits/{user_id}")
async def add_user_credits(user_id: int):
    try:
        success = add_credits(user_id)
        if success:
            return {"message": "Credits added successfully"}
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to add credits"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) 