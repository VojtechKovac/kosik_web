from fastapi import FastAPI, Request, Form, Response, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import random
from datetime import datetime, timedelta
import os
import uuid
from urllib.parse import quote

# Import z nášho súboru database.py
from database import SessionLocal, ProduktModel, ObjednavkaModel, RecenziaModel, init_db

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# ==========================================
# BEZPEČNOSTNÉ HLAVIČKY (Ochrana pred útokmi)
# ==========================================
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

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

zlavovy_kupon = {
    "jabko345": 10,
    "lidl745": 15,
    "samusko67": 50,
    "milujemmareka": 25
}

def generuj_akcie(db):
    vsetky_produkty = db.query(ProduktModel).all()
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
def domov(request: Request, sprava: str = None):
    db = SessionLocal()
    aktualne_akcie = generuj_akcie(db)
    
    session_id = request.cookies.get("session_id")
    prihlaseny_zakaznik = aktivne_relacie.get(session_id) if session_id else None
    klubove_body = nacitaj_body()
    is_admin = request.cookies.get("is_admin") == "True"

    produkty_db = db.query(ProduktModel).all()
    kategoria_dict = {
        p.nazov: (p.cena, p.druh, p.sklad, p.povod, p.miesto, p.znacka) 
        for p in produkty_db
    }
    
    # Načítanie objednávok a registrovaných používateľov pre admina alebo zákazníka
    zoznam_objednavok = []
    zakaznicke_objednavky = []
    registrovani_uzivatelia = {}
    
    if is_admin:
        zoznam_objednavok = db.query(ObjednavkaModel).order_by(ObjednavkaModel.datum.desc()).all()
        registrovani_uzivatelia = nacitaj_uzivatelov()
    
    if prihlaseny_zakaznik:
        zakaznicke_objednavky = db.query(ObjednavkaModel).filter(ObjednavkaModel.zakaznik == prihlaseny_zakaznik).order_by(ObjednavkaModel.datum.desc()).all()
        
    # Načítanie recenzií a výpočet priemerných hodnotení
    vsetky_recenzie = db.query(RecenziaModel).all()
    recenzie_dict = {}
    priemer_hodnoteni = {}
    
    for r in vsetky_recenzie:
        if r.produkt_nazov not in recenzie_dict:
            recenzie_dict[r.produkt_nazov] = []
        recenzie_dict[r.produkt_nazov].append(r)
        
    for nazov, recs in recenzie_dict.items():
        priemer_hodnoteni[nazov] = round(sum(r.hodnotenie for r in recs) / len(recs), 1)

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
            "klubove_body": klubove_body,
            "sprava": sprava,
            "zoznam_objednavok": zoznam_objednavok,
            "zakaznicke_objednavky": zakaznicke_objednavky,
            "registrovani_uzivatelia": registrovani_uzivatelia,
            "recenzie_dict": recenzie_dict,
            "priemer_hodnoteni": priemer_hodnoteni,
            "request": request
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
    if heslo == admin_heslo:
        response = RedirectResponse(f"/?sprava={quote('Úspešne prihlásený ako administrátor.')}", status_code=303)
        response.set_cookie(key="is_admin", value="True", httponly=True)
        return response
    return RedirectResponse(f"/?sprava={quote('Nesprávne admin heslo!')}", status_code=303)

@app.get("/logout")
def logout():
    response = RedirectResponse(f"/?sprava={quote('Administrátor bol odhlásený.')}", status_code=303)
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
        sprava = "Registrácia klubovej karty prebehla úspešne!"
    else:
        sprava = "Tento email je už zaregistrovaný."

    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    aktivne_relacie[session_id] = email

    response = RedirectResponse(f"/?sprava={quote(sprava)}", status_code=303)
    response.set_cookie(key="session_id", value=session_id, httponly=True)
    return response

@app.post("/login-club-card")
def login_club_card(request: Request, email: str = Form(...), heslo: str = Form(...)):
    email = email.strip().lower()
    uzivatelia = nacitaj_uzivatelov()
    if email in uzivatelia and uzivatelia[email] == heslo:
        session_id = request.cookies.get("session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
        
        aktivne_relacie[session_id] = email
        response = RedirectResponse(f"/?sprava={quote('Úspešne prihlásený do klubovej karty.')}", status_code=303)
        response.set_cookie(key="session_id", value=session_id, httponly=True)
        return response
    
    return RedirectResponse(f"/?sprava={quote('Nesprávny email alebo heslo!')}", status_code=303)

@app.get("/logout-club-card")
def logout_club_card(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in aktivne_relacie:
        del aktivne_relacie[session_id]

    return RedirectResponse(f"/?sprava={quote('Boli ste úspešne odhlásený z klubovej karty.')}", status_code=303)

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
            sprava = "Úspešne ste uplatnili 100 vernostných bodov!"
        else:
            sprava = "Nemáte dostatok bodov (potrebujete aspoň 100)."
    else:
        sprava = "Na uplatnenie bodov musíte byť prihlásený."
    return RedirectResponse(f"/?sprava={quote(sprava)}", status_code=303)

# ENDPOINT PRE SPRÁVU BODOV ZÁKAZNÍKA (ADMIN)
@app.post("/admin-upravit-body")
def admin_upravit_body(request: Request, email: str = Form(...), zmena_bodov: int = Form(...)):
    is_admin = request.cookies.get("is_admin") == "True"
    if is_admin:
        body_dict = nacitaj_body()
        aktualne_body = body_dict.get(email, 0)
        nove_body = max(0, aktualne_body + zmena_bodov)
        body_dict[email] = nove_body
        uloz_body_db(body_dict)
        sprava = f"Body pre zákazníka {email} boli úspešne upravené."
    else:
        sprava = "Nemáte oprávnenie."
    return RedirectResponse(f"/?sprava={quote(sprava)}", status_code=303)

@app.post("/dozaskladnit")
def dozaskladnit(request: Request, polozka: str = Form(...), pocet: int = Form(...)):
    is_admin = request.cookies.get("is_admin") == "True"
    if is_admin and pocet > 0:
        db = SessionLocal()
        produkt = db.query(ProduktModel).filter(ProduktModel.nazov == polozka).first()
        if produkt:
            produkt.sklad += pocet
            db.commit()
            sprava = f"Položka {polozka} úspešne dozaskladnená o {pocet} ks."
        else:
            sprava = "Produkt nebol nájdený."
        db.close()
    else:
        sprava = "Nemáte oprávnenie alebo zadaný počet je neplatný."
    return RedirectResponse(f"/?sprava={quote(sprava)}", status_code=303)

@app.post("/zmenit-stav-objednavky")
def zmenit_stav_objednavky(request: Request, objednavka_id: int = Form(...), stav: str = Form(...)):
    is_admin = request.cookies.get("is_admin") == "True"
    if is_admin:
        db = SessionLocal()
        obj = db.query(ObjednavkaModel).filter(ObjednavkaModel.id == objednavka_id).first()
        if obj:
            obj.stav = stav
            db.commit()
            sprava = f"Stav objednávky #{objednavka_id} bol úspešne zmenený."
        else:
            sprava = "Objednávka nebola nájdená."
        db.close()
    else:
        sprava = "Nemáte oprávnenie."
    return RedirectResponse(f"/?sprava={quote(sprava)}", status_code=303)

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
    
    if "<" in nazov or ">" in nazov or "<" in druh or ">" in druh:
        raise HTTPException(status_code=400, detail="Vstupy nemôžu obsahovať HTML značky!")

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
            sprava = f"Produkt {clean_nazov} bol úspešne pridaný."
        else:
            sprava = "Produkt s týmto názvom už existuje."
        db.close()
    else:
        sprava = "Nedostatočné oprávnenia."
    return RedirectResponse(f"/?sprava={quote(sprava)}", status_code=303)

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
        sprava = f"Položka {polozka} bola vymazaná."
    else:
        sprava = "Nemáte oprávnenie."
            
    return RedirectResponse(f"/?sprava={quote(sprava)}", status_code=303)

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
        sprava = "Všetky produkty boli vymazané."
    else:
        sprava = "Nemáte oprávnenie."
        
    return RedirectResponse(f"/?sprava={quote(sprava)}", status_code=303)

@app.post("/pridat")
def pridat(request: Request, response: Response, polozka: str = Form(...), mnozstvo: int = Form(...)):
    session_id, kosik = daj_kosik_pre_session(request, response)
    
    db = SessionLocal()
    produkt = db.query(ProduktModel).filter(ProduktModel.nazov == polozka).first()
    
    if produkt and 0 < mnozstvo <= produkt.sklad:
        produkt.sklad -= mnozstvo
        kosik[polozka] = kosik.get(polozka, 0) + mnozstvo
        db.commit()
        sprava = f"Do košíka úspešne pridané: {mnozstvo}x {polozka}"
        sukces = True
        aktualny_sklad = produkt.sklad
    else:
        sprava = "Nedostatok tohto tovaru na sklade!"
        sukces = False
        aktualny_sklad = produkt.sklad if produkt else 0
    db.close()

    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header or request.headers.get("x-requested-with") == "XMLHttpRequest":
        return {
            "success": sukces,
            "message": sprava,
            "new_stock": aktualny_sklad
        }

    redir = RedirectResponse(f"/?sprava={quote(sprava)}", status_code=303)
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

    aktualne_akcie = generuj_akcie(db)
    produkty_db = db.query(ProduktModel).all()
    kategoria_dict = {p.nazov: (p.cena, p.druh, p.sklad, p.povod, p.miesto, p.znacka) for p in produkty_db}
    db.close()

    celkova_cena = 0
    item_mnozstvo = kosik.get(polozka, 0)
    item_spolu = 0

    for p_nazov, mnozstvo in kosik.items():
        if p_nazov in kategoria_dict:
            cena = aktualne_akcie[p_nazov][0] if p_nazov in aktualne_akcie else kategoria_dict[p_nazov][0]
            subtotal = cena * mnozstvo
            celkova_cena += subtotal
            if p_nazov == polozka:
                item_spolu = subtotal

    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header or request.headers.get("x-requested-with") == "XMLHttpRequest":
        return {
            "success": True,
            "polozka": polozka,
            "mnozstvo": item_mnozstvo,
            "item_spolu": round(item_spolu, 2),
            "celkova_cena": round(celkova_cena, 2),
            "kosik_prazdny": len(kosik) == 0
        }

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
    kategoria_dict = {
        p.nazov: (p.cena, p.druh, p.sklad, p.povod, p.miesto, p.znacka) 
        for p in produkty_db
    }
    
    celkova_cena = 0
    for polozka, mnozstvo in kosik.items():
        if polozka in kategoria_dict:
            cena = aktualne_akcie[polozka][0] if polozka in aktualne_akcie else kategoria_dict[polozka][0]
            celkova_cena += cena * mnozstvo

    zlava = zlavovy_kupon.get(kupon.strip(), 0)
    if zlava > 0:
        celkova_cena = celkova_cena * (1 - zlava / 100)

    if kosik:
        popis_kosika = ", ".join([f"{mnozstvo}x {polozka}" for polozka, mnozstvo in kosik.items()])
        nova_objednavka = ObjednavkaModel(
            zakaznik=prihlaseny_zakaznik if prihlaseny_zakaznik else "Anonymný zákazník",
            polozky=popis_kosika,
            celkova_cena=round(celkova_cena, 2),
            stav="Prijatá ➔ Pripravuje sa"
        )
        db.add(nova_objednavka)
        db.commit()

    if prihlaseny_zakaznik:
        body_dict = nacitaj_body()
        ziskane_body = int(celkova_cena)
        body_dict[prihlaseny_zakaznik] = body_dict.get(prihlaseny_zakaznik, 0) + ziskane_body
        uloz_body_db(body_dict)

    db.close()
    
    kosik.clear()

    return templates.TemplateResponse(
        request=request,
        name="platba_uspesna.html",
        context={"request": request, "celkova_cena": round(celkova_cena, 2)}
    )

@app.post("/pridat-recenziu")
def pridat_recenziu(request: Request, produkt: str = Form(...), hodnotenie: int = Form(...), komentar: str = Form("")):
    if "<" in komentar or ">" in komentar:
        raise HTTPException(status_code=400, detail="Komentár nemôže obsahovať HTML značky ani špeciálne znaky!")

    session_id = request.cookies.get("session_id")
    prihlaseny_zakaznik = aktivne_relacie.get(session_id) if session_id else None
    
    db = SessionLocal()
    nova_recenzia = RecenziaModel(
        produkt_nazov=produkt,
        hodnotenie=max(1, min(5, hodnotenie)),
        komentar=komentar.strip(),
        autor=prihlaseny_zakaznik if prihlaseny_zakaznik else "Anonymný zákazník"
    )
    db.add(nova_recenzia)
    db.commit()
    db.close()
    
    return RedirectResponse(f"/?sprava={quote('Ďakujeme za tvoje hodnotenie!')}", status_code=303)

@app.get("/produkt/{nazov_produktu}")
def detail_produktu(request: Request, nazov_produktu: str):
    db = SessionLocal()
    produkt = db.query(ProduktModel).filter(ProduktModel.nazov == nazov_produktu).first()
    
    if not produkt:
        db.close()
        raise HTTPException(status_code=404, detail="Produkt nebol nájdený")
        
    recenzie_produktu = db.query(RecenziaModel).filter(RecenziaModel.produkt_nazov == nazov_produktu).all()
    
    priemer = 0
    if recenzie_produktu:
        priemer = round(sum(r.hodnotenie for r in recenzie_produktu) / len(recenzie_produktu), 1)
        
    session_id = request.cookies.get("session_id")
    prihlaseny_zakaznik = aktivne_relacie.get(session_id) if session_id else None
    is_admin = request.cookies.get("is_admin") == "True"

    db.close()
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "nazov": produkt.nazov,
            "udaje": (produkt.cena, produkt.druh, produkt.sklad, produkt.povod, produkt.miesto, produkt.znacka),
            "recenzie": recenzie_produktu,
            "priemer": priemer,
            "is_admin": is_admin,
            "prihlaseny_zakaznik": prihlaseny_zakaznik
        }
    )