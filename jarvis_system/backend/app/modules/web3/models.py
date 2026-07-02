from sqlalchemy import Column, Integer, String, Text
from app.core.database import Base

class WalletMetadata(Base):
    """Stores references to Web3 wallets, utilizing Zero-Knowledge encryption for private keys."""
    __tablename__ = "web3_wallets"
    
    id = Column(Integer, primary_key=True, index=True)
    chain = Column(String, index=True) # e.g., 'ethereum', 'solana'
    public_address = Column(String, unique=True, index=True)
    encrypted_private_key = Column(Text, nullable=False) # Zero-Knowledge encrypted
