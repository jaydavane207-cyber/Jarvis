import os
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from cryptography.fernet import Fernet
import base64

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jarvis_local.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Simulated AES-256 Encryption for columns
# In production, use securely stored keys or KMS
ENCRYPTION_KEY = os.getenv("SECRET_KEY", "bXlzZWNyZXRxdWFudHVta2V5MTIzNDU2Nzg5MDEyMzQ1Njc=") 
# Fernet expects 32 url-safe base64-encoded bytes
try:
    fernet = Fernet(ENCRYPTION_KEY.encode() if len(ENCRYPTION_KEY) == 44 else Fernet.generate_key())
except:
    fernet = Fernet(Fernet.generate_key())

def encrypt_data(data: str) -> str:
    if not data:
        return data
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(data: str) -> str:
    if not data:
        return data
    try:
        return fernet.decrypt(data.encode()).decode()
    except:
        return data # Return original if not encrypted properly

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    # The following fields will be encrypted before storage
    encrypted_email = Column(Text)
    encrypted_aadhaar_hash = Column(Text)

    @property
    def email(self):
        return decrypt_data(self.encrypted_email)
        
    @email.setter
    def email(self, value):
        self.encrypted_email = encrypt_data(value)

# Create tables
Base.metadata.create_all(bind=engine)
