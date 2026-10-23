import os
from sqlalchemy import create_engine, Column, String, Float, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# URL k databáze (Render ti ju poskytne cez environmentálnu premennú DATABASE_URL)
# Pre lokálne testovanie sa použije lokálna SQLite databáza
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./obchod.db")

# Úprava pre Render PostgreSQL URL, aby explicitly použilo psycopg2 ovládač
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Definícia tabuľky pre produkty
class ProduktModel(Base):
    __tablename__ = "produkty"

    nazov = Column(String, primary_key=True, index=True)
    cena = Column(Float, nullable=False)
    druh = Column(String, nullable=False)
    sklad = Column(Integer, nullable=False)
    povod = Column(String, default="Slovensko")
    miesto = Column(String, default="Lokálna farma")
    znacka = Column(String, default="Môj Obchod")

# Vytvorenie tabuliek v databáze
def init_db():
    Base.metadata.create_all(bind=engine)