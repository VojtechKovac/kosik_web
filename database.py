import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./obchod.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ProduktModel(Base):
    __tablename__ = "produkty"
    id = Column(Integer, primary_key=True, index=True)
    nazov = Column(String, unique=True, index=True)
    cena = Column(Float)
    druh = Column(String)
    sklad = Column(Integer)
    povod = Column(String)
    miesto = Column(String)
    znacka = Column(String)

class ObjednavkaModel(Base):
    __tablename__ = "objednavky"
    id = Column(Integer, primary_key=True, index=True)
    zakaznik = Column(String)
    polozky = Column(String)
    celkova_cena = Column(Float)
    stav = Column(String, default="Prijatá ➔ Pripravuje sa")
    datum = Column(DateTime, default=datetime.now)

class RecenziaModel(Base):
    __tablename__ = "recenzie"
    id = Column(Integer, primary_key=True, index=True)
    produkt_nazov = Column(String, index=True)
    hodnotenie = Column(Integer)
    komentar = Column(String)
    autor = Column(String)
    datum = Column(DateTime, default=datetime.now)

class UzivatelModel(Base):
    __tablename__ = "uzivatelia"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    heslo = Column(String)
    body = Column(Integer, default=0)

def init_db():
    Base.metadata.create_all(bind=engine)