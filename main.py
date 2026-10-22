from fastapi import FastAPI, Request, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import random
from datetime import datetime, timedelta
import os
import uuid

# Import z nášho nového súboru database.py
from database import SessionLocal, ProduktModel, init_db

app = FastAPI()

templates = Jinja2Templates(directory="templates")

UZIVATELIA_FILE = "uzivatelia.txt"
BODY_FILE = "body.txt"

# Slovník aktívnych relácií pre zákazníkov: { session_id: email_zakaznika }
aktivne_relacie = {}

# Slovník pre nákupné košíky: { session_id: { nazov_produktu: mnozstvo } }
aktivne_kosiky = {}

# Inicializácia databázy a naplnenie počiatočnými produktmi pri štarte
@app.on_event("startup")
def startup_event():
    init_db()
    db = SessionLocal()
    if db.query(ProduktModel).count() == 0:
        povodny_tovar = {
            "cukor": (0.6, "iné", 8, "Slovensko", "Trnava", "Slovlik s.r.o."),
            "maslo": (1.5, "iné", 50, "Česko", "Jižní Morava", "Madeta"),
            "jablko": (0.7, "ovocie", 15, "Slovensko", "Dunajská Streda", "Frucona"),
            "banan": (0.5, "ovocie", 20, "Ekvádor", "Guayas", "Chiquita"),
            "hruska": (0.9, "ovocie", 12, "Taliansko", "Emilia-Romagna", "BioFruit"),
            "marhula": (0.8, "ovocie", 25, "Maďarsko", "Kecskemét", "HungarOvocie"),
            "slivka": (1.0, "ovocie", 18, "Slovensko", "Nitra", "Ovocinár Nitra"),
            "citron": (0.4, "ovocie", 30, "Španielsko", "Málaga", "CitrusSur"),
            "pomaranc": (0.6, "ovocie", 35, "Grécko", "Sparta", "HellasFresh"),
            "jahody": (2.2, "ovocie", 10, "Slovensko", "Dvory nad Žitavou", "Jahodovo"),
            "mrkva": (0.8, "zelenina", 25, "Holandsko", "Utrecht", "AgroGreen"),
            "petrzlen": (0.9, "zelenina", 15, "Poľsko", "Lublin", "Warzywa Polskie"),
            "celer": (0.7, "zelenina", 14, "Slovensko", "Hurbanovo", "Zeleninárstvo Hurbanovo"),
            "zemiak": (0.9, "zelenina", 60, "Slovensko", "Spišská Nová Ves", "Tatry Agrár"),
            "cibula": (0.5, "zelenina", 40, "Slovensko", "Nové Zámky", "Zelenina NZ"),
            "cesnak": (1.8, "zelenina", 22, "Španielsko", "Cordoba", "Andaluza Garlic"),
            "paradajka": (1.5, "zelenina", 18, "Maroko", "Agadir", "Atlas Veg"),
            "uhorka": (1.2, "zelenina", 25, "Španielsko", "Almeria", "SolFresh"),
            "cokolada": (1.2, "sladkosti", 15, "Švajčiarsko", "Bern", "Lindt"),
            "keksik": (0.8, "sladkosti", 30, "Slovensko", "Sereď", "I.D.C. Holding"),
            "bomboni": (3.5, "sladkosti", 8, "Nemecko", "Mníchov", "Milka"),
            "cukriky": (0.9, "sladkosti", 25, "Česko", "Ostrava", "BonPari"),
            "mlieko": (0.5, "iné", 20, "Slovensko", "Žilina", "Rajo"),
            "jogurt": (0.6, "iné", 18, "Slovensko", "Zvolen", "Zvolenská mliekareň"),
            "syr": (2.1, "iné", 12, "Slovensko", "Liptovský Mikuláš", "Liptov"),
            "chlieb": (1.0, "iné", 10, "Slovensko", "Bratislava", "Pekáreň Staré Mesto"),
            "rozok": (0.15, "iné", 100, "Slovensko", "Nitra", "Nitrianske pekárne"),
            "coca cola": (1.8, "iné", 30, "Rakúsko", "Viedeň", "Coca-Cola HBC"),
            "mineralovka": (0.5, "iné", 50, "Slovensko", "Brezová pod Bradlom", "Mattoni")
        }
        for nazov, udaje in povodny_tovar.items():
            novy = ProduktModel(
                nazov=nazov, cena=udaje[0], druh=udaje[1], 
                sklad=udaje[2], povod=udaje[3], miesto=udaje[4], znacka=udaje[5]
            )
            db.add(novy)
        db.commit()
    db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

zlavovy_kupon = {
    "jabko345": 10,
    "lidl745": 15,
    "samusko67": 50,
    "milujemmareka": 25
}

def generuj_akcie(db):
    vsetky_produkty = db.query(ProduktModel).all()
    nazvy = [p.nazov for p in vsetky_produkty]
    vybrane = ["maslo", "banan", "cokolada", "syr", "coca cola", "jahody", "chlieb"]
    akcie = {}
    for p in vybrane:
        produkt = db.query(ProduktModel).filter(ProduktModel.nazov == p).first()
        if produkt:
            zlava_perc = random.choice([15, 20, 25, 30, 35])
            nova_cena = round(produkt.cena * (1 - zlava_perc / 100), 2)
            akcie[p] = (nova_cena, zlava_perc)
    return akcie

dnes = datetime.now()
koniec = dnes + timedelta(days=7)
datum_od = dnes.strftime("%d.%m.%Y")
datum_do = koniec.strftime("%d.%m.%Y")

# Pomocná funkcia pre správu košíka danej relácie
def daj_kosik_pre_session(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id, httponly=True)
    
    if session_id not in aktivne_kosiky:
        aktivne_kosiky[session_id] = {}
        
    return session_id, aktivne_kosiky[session_id]

def nacitaj_uzivatelov():
    uzivatelia = {}
    if os.path.exists(UZIVATELIA_FILE):
        with open(UZIVATELIA_FILE, "r", encoding="utf-8") as f:
            for riadok in f:
                parts = riadok.strip().split(";")
                if len(parts) == 2:
                    uzivatelia[parts[0]] = parts[1]
    return uzivatelia

def uloz_uzivatela(email, heslo):
    with open(UZIVATELIA_FILE, "a", encoding="utf-8") as f:
        f.write(f"{email};{heslo}\n")

def nacitaj_body():
    body = {}
    if os.path.exists(BODY_FILE):
        with open(BODY_FILE, "r", encoding="utf-8") as f:
            for riadok in f:
                parts = riadok.strip().split(";")
                if len(parts) == 2:
                    body[parts[0]] = int(parts[1])
    return body

def uloz_body_db(body_dict):
    with open(BODY_FILE, "w", encoding="utf-8") as f:
        for email, body in body_dict.items():
            f.write(f"{email};{body}\n")


@app.get("/")
def domov(request: Request):
    db = SessionLocal()
    aktualne_akcie = generuj_akcie(db)
    
    session_id = request.cookies.get("session_id")
    prihlaseny_zakaznik = aktivne_relacie.get(session_id) if session_id else None
    klubove_body = nacitaj_body()
    is_admin = request.cookies.get("is_admin") == "True"

    # Prevod databázových modelov na slovník, aby to HTML šablóna nemusela meniť
    produkty_db = db.query(ProduktModel).all()
    kategoria_dict = {
        p.nazov: (p.cena, p.druh, p.sklad, p.povod, p.miesto, p.znacka) 
        for p in produkty_db
    }
    db.close()
    
    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "kategoria": kategoria_dict,
            "is_admin": is_admin,
            "aktualne_akcie": aktualne_akcie,
            "datum_od": datum_od,
            "datum_do": datum_do,
            "prihlaseny_zakaznik": prihlaseny_zakaznik,
            "klubove_body": klubove_body
        }
    )
    if not session_id:
        new_session = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=new_session, httponly=True)
    return response

@app.get("/letak")
def zobraz_letak(request: Request):
    db = SessionLocal()
    aktualne_akcie = generuj_akcie(db)
    produkty_db = db.query(ProduktModel).all()
    kategoria_dict = {
        p.nazov: (p.cena, p.druh, p.sklad, p.povod, p.miesto, p.znacka) 
        for p in produkty_db
    }
    db.close()

    polozky_v_letaku = {k: (kategoria_dict[k], aktualne_akcie[k]) for k in aktualne_akcie if k in kategoria_dict}
    return templates.TemplateResponse(
        request=request,
        name="letak.html",
        context={
            "request": request,
            "polozky_v_letaku": polozky_v_letaku,
            "datum_od": datum_od,
            "datum_do": datum_do
        }
    )

@app.post("/login")
def login(heslo: str = Form(...)):
    admin_heslo = os.getenv("ADMIN_HESLO", "kosik123")
    response = RedirectResponse("/", status_code=303)
    if heslo == admin_heslo:
        response.set_cookie(key="is_admin", value="True", httponly=True)
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(key="is_admin")
    return response

@app.post("/register-club-card")
def register_club_card(request: Request, email: str = Form(...), heslo: str = Form(...)):
    email = email.strip().lower()
    uzivatelia = nacitaj_uzivatelov()
    body_dict = nacitaj_body()

    if email and email not in uzivatelia:
        uloz_uzivatela(email, heslo)
        body_dict[email] = 0
        uloz_body_db(body_dict)

    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    aktivne_relacie[session_id] = email

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(key="session_id", value=session_id, httponly=True)
    return response

@app.post("/login-club-card")
def login_club_card(request: Request, email: str = Form(...), heslo: str = Form(...)):
    email = email.strip().lower()
    uzivatelia = nacitaj_uzivatelov()

    response = RedirectResponse("/", status_code=303)
    if email in uzivatelia and uzivatelia[email] == heslo:
        session_id = request.cookies.get("session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
        
        aktivne_relacie[session_id] = email
        response.set_cookie(key="session_id", value=session_id, httponly=True)
    
    return response

@app.get("/logout-club-card")
def logout_club_card(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in aktivne_relacie:
        del aktivne_relacie[session_id]

    return RedirectResponse("/", status_code=303)

@app.post("/uplatnit-body")
def uplatnit_body(request: Request):
    session_id = request.cookies.get("session_id")
    prihlaseny_zakaznik = aktivne_relacie.get(session_id) if session_id else None

    if prihlaseny_zakaznik:
        body_dict = nacitaj_body()
        body = body_dict.get(prihlaseny_zakaznik, 0)
        if body >= 100:
            body_dict[prihlaseny_zakaznik] = body - 100
            uloz_body_db(body_dict)
    return RedirectResponse("/", status_code=303)

@app.post("/dozaskladnit")
def dozaskladnit(request: Request, polozka: str = Form(...), pocet: int = Form(...)):
    is_admin = request.cookies.get("is_admin") == "True"
    if is_admin and pocet > 0:
        db = SessionLocal()
        produkt = db.query(ProduktModel).filter(ProduktModel.nazov == polozka).first()
        if produkt:
            produkt.sklad += pocet
            db.commit()
        db.close()
    return RedirectResponse("/", status_code=303)

@app.post("/pridat_produkt")
def pridat_produkt(
    request: Request,
    nazov: str = Form(...),
    cena: float = Form(...),
    druh: str = Form(...),
    sklad: int = Form(...),
    povod: str = Form("Slovensko"),
    miesto: str = Form("Lokálna farma"),
    znacka: str = Form("Môj Obchod")
):
    is_admin = request.cookies.get("is_admin") == "True"
    clean_nazov = nazov.strip().lower()
    if is_admin and clean_nazov:
        db = SessionLocal()
        existuje = db.query(ProduktModel).filter(ProduktModel.nazov == clean_nazov).first()
        if not existuje:
            novy = ProduktModel(
                nazov=clean_nazov, cena=cena, druh=druh.lower(), 
                sklad=sklad, povod=povod.strip(), miesto=miesto.strip(), znacka=znacka.strip()
            )
            db.add(novy)
            db.commit()
        db.close()
    return RedirectResponse("/", status_code=303)

@app.post("/vymazat_polozku")
def vymazat_polozku(request: Request, response: Response, polozka: str = Form(...)):
    is_admin = request.cookies.get("is_admin") == "True"
    if is_admin:
        db = SessionLocal()
        produkt = db.query(ProduktModel).filter(ProduktModel.nazov == polozka).first()
        if produkt:
            db.delete(produkt)
            db.commit()
        db.close()

        session_id, kosik = daj_kosik_pre_session(request, response)
        if polozka in kosik:
            kosik.pop(polozka)
            
    return RedirectResponse("/", status_code=303)

@app.post("/vymazat_vsetko")
def vymazat_vsetko(request: Request, response: Response):
    is_admin = request.cookies.get("is_admin") == "True"
    if is_admin:
        db = SessionLocal()
        db.query(ProduktModel).delete()
        db.commit()
        db.close()

        session_id, kosik = daj_kosik_pre_session(request, response)
        kosik.clear()
        
    return RedirectResponse("/", status_code=303)

@app.post("/pridat")
def pridat(request: Request, response: Response, polozka: str = Form(...), mnozstvo: int = Form(...)):
    session_id, kosik = daj_kosik_pre_session(request, response)
    
    db = SessionLocal()
    produkt = db.query(ProduktModel).filter(ProduktModel.nazov == polozka).first()
    
    if produkt and 0 < mnozstvo <= produkt.sklad:
        produkt.sklad -= mnozstvo
        kosik[polozka] = kosik.get(polozka, 0) + mnozstvo
        db.commit()
    db.close()

    redir = RedirectResponse("/", status_code=303)
    redir.set_cookie(key="session_id", value=session_id, httponly=True)
    return redir

@app.post("/upravit")
def upravit(request: Request, response: Response, polozka: str = Form(...), akcia: str = Form(...)):
    session_id, kosik = daj_kosik_pre_session(request, response)
    
    db = SessionLocal()
    produkt = db.query(ProduktModel).filter(ProduktModel.nazov == polozka).first()
    
    if polozka in kosik and produkt:
        if akcia == "pridat":
            if produkt.sklad > 0:
                kosik[polozka] += 1
                produkt.sklad -= 1
                db.commit()
        elif akcia == "odbrat":
            if kosik[polozka] > 1:
                kosik[polozka] -= 1
                produkt.sklad += 1
                db.commit()
            else:
                mnozstvo = kosik.pop(polozka)
                produkt.sklad += mnozstvo
                db.commit()
        elif akcia == "vymazat":
            mnozstvo = kosik.pop(polozka)
            produkt.sklad += mnozstvo
            db.commit()
    db.close()

    redir = RedirectResponse("/kosik", status_code=303)
    redir.set_cookie(key="session_id", value=session_id, httponly=True)
    return redir

@app.get("/kosik")
def zobraz_kosik(request: Request, response: Response):
    session_id, kosik = daj_kosik_pre_session(request, response)
    
    db = SessionLocal()
    aktualne_akcie = generuj_akcie(db)
    produkty_db = db.query(ProduktModel).all()
    kategoria_dict = {
        p.nazov: (p.cena, p.druh, p.sklad, p.povod, p.miesto, p.znacka) 
        for p in produkty_db
    }
    db.close()

    celkova_cena = 0
    for polozka, mnozstvo in kosik.items():
        if polozka in kategoria_dict:
            cena = aktualne_akcie[polozka][0] if polozka in aktualne_akcie else kategoria_dict[polozka][0]
            celkova_cena += cena * mnozstvo

    return templates.TemplateResponse(
        request=request,
        name="kosik.html",
        context={
            "request": request,
            "kosik": kosik,
            "kategoria": kategoria_dict,
            "celkova_cena": celkova_cena,
            "aktualne_akcie": aktualne_akcie
        }
    )

@app.post("/zaplatit")
def zaplatit(request: Request, response: Response, kupon: str = Form("")):
    session_id, kosik = daj_kosik_pre_session(request, response)
    prihlaseny_zakaznik = aktivne_relacie.get(session_id) if session_id else None
    
    db = SessionLocal()
    aktualne_akcie = generuj_akcie(db)
    produkty_db = db.query(ProduktModel).all()