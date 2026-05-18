from passlib.context import CryptContext
from sqlalchemy import create_session, create_engine
import os

pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
new_hash = pwd_context.hash('12345678')

db_url = "postgresql://postgres:postgres@localhost:5432/gst_engine" # Adjust if needed
engine = create_engine(db_url)
with engine.connect() as conn:
    conn.execute("UPDATE users_registry SET password_hash = %s WHERE email = 'alpesh2060@gmail.com'", (new_hash,))
    print("Password reset successfully for alpesh2060@gmail.com")
