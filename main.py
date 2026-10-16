from fastapi import FastAPI, Request, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import random
from datetime import datetime, timedelta
import os
import uuid

app = FastAPI()

templates = Jinja2Templates(directory="templates")

UZIVATELIA_FILE = "uzivatelia.txt"
BODY_FILE = "body.txt"

# Slovník aktívnych relácií: { session_id: email_zakaznika }
# Toto zabezpečí, že každý prehliadač/okno má svoju vlastnú reláciu a neprepíšete sa navzájom.
aktivne_relacie = {}

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

kategoria = {
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

zlavovy_kupon = {
    "jabko345": 10,
    "lidl745": 15,
    "samusko67": 50,
    "milujemmareka": 25
}

kosik = {}
is_admin = False

def generuj_akcie():
    vybrane = ["maslo", "banan", "cokolada", "syr", "coca cola", "jahody", "chlieb"]
    akcie = {}
    for p in vybrane:
        if p in kategoria:
            puv_cena = kategoria[p][0]
            zlava_perc = random.choice([15, 20, 25, 30, 35])
            nova_cena = round(puv_cena * (1 - zlava_perc / 100), 2)
            akcie[p] = (nova_cena, zlava_perc)
    return akcie

dnes = datetime.now()
koniec = dnes + timedelta(days=7)
datum_od = dnes.strftime("%d.%m.%Y")
datum_do = koniec.strftime("%d.%m.%Y")

aktualne_akcie = generuj_akcie()

@app.get("/")
def domov(request: Request):
    # Zistíme, či tento prehliadač má svoje session_id v cookies
    session_id = request.cookies.get("session_id")
    prihlaseny_zakaznik = aktivne_relacie.get(session_id) if session_id else None
    
    klubove_body = nacitaj_body()
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "kategoria": kategoria,
            "kosik": kosik,
            "is_admin": is_admin,
            "aktualne_akcie": aktualne_akcie,
            "datum_od": datum_od,
            "datum_do": datum_do,
            "prihlaseny_zakaznik": prihlaseny_zakaznik,
            "klubove_body": klubove_body
        }
    )

@app.get("/letak")
def zobraz_letak(request: Request):
    polozky_v_letaku = {k: (kategoria[k], aktualne_akcie[k]) for k in aktualne_akcie if k in kategoria}
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
    global is_admin
    if heslo == "kosik123":
        is_admin = True
    return RedirectResponse("/", status_code=303)

@app.get("/logout")
def logout():
    global is_admin
    is_admin = False
    return RedirectResponse("/", status_code=303)

# --- KLUB CARD TRASY S UNIKÁTNYMI RELÁCIAMI PRE KAŽDÉHO ---
@app.post("/register-club-card")
def register_club_card(request: Request, email: str = Form(...), heslo: str = Form(...)):
    email = email.strip().lower()
    uzivatelia = nacitaj_uzivatelov()
    body_dict = nacitaj_body()

    if email and email not in uzivatelia:
        uloz_uzivatela(email, heslo)
        body_dict[email] = 0
        uloz_body_db(body_dict)

    # Vygenerujeme alebo prevezmeme jedinečné ID relácie pre tento prehliadač
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    aktivne_relacie[session_id] = email

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(key="session_id", value=session_id)
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
        response.set_cookie(key="session_id", value=session_id)
    
    return response

@app.get("/logout-club-card")
def logout_club_card(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in aktivne_relacie:
        del aktivne_relacie[session_id]

    response = RedirectResponse("/", status_code=303)
    return response

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
# ----------------------

@app.post("/dozaskladnit")
def dozaskladnit(polozka: str = Form(...), pocet: int = Form(...)):
    global is_admin
    if is_admin and polozka in kategoria and pocet > 0:
        cena, druh, sklad, povod, miesto, znacka = kategoria[polozka]
        kategoria[polozka] = (cena, druh, sklad + pocet, povod, miesto, znacka)
    return RedirectResponse("/", status_code=303)

@app.post("/pridat_produkt")
def pridat_produkt(
    nazov: str = Form(...),
    cena: float = Form(...),
    druh: str = Form(...),
    sklad: int = Form(...),
    povod: str = Form("Slovensko"),
    miesto: str = Form("Lokálna farma"),
    znacka: str = Form("Môj Obchod")
):
    global is_admin
    if is_admin and nazov.strip():
        kategoria[nazov.strip().lower()] = (cena, druh.lower(), sklad, povod.strip(), miesto.strip(), znacka.strip())
    return RedirectResponse("/", status_code=303)

@app.post("/vymazat_polozku")
def vymazat_polozku(polozka: str = Form(...)):
    global is_admin, kategoria, kosik
    if is_admin:
        if polozka in kategoria:
            kategoria.pop(polozka)
        if polozka in kosik:
            kosik.pop(polozka)
    return RedirectResponse("/", status_code=303)

@app.post("/vymazat_vsetko")
def vymazat_vsetko():
    global is_admin, kategoria, kosik
    if is_admin:
        kategoria.clear()
        kosik.clear()
    return RedirectResponse("/", status_code=303)

@app.post("/pridat")
def pridat(polozka: str = Form(...), mnozstvo: int = Form(...)):
    if polozka in kategoria:
        cena, druh, sklad, povod, miesto, znacka = kategoria[polozka]
        if mnozstvo > 0 and mnozstvo <= sklad:
            if polozka in kosik:
                kosik[polozka] += mnozstvo
            else:
                kosik[polozka] = mnozstvo
            kategoria[polozka] = (cena, druh, sklad - mnozstvo, povod, miesto, znacka)
    return RedirectResponse("/", status_code=303)

@app.post("/upravit")
def upravit(polozka: str = Form(...), akcia: str = Form(...)):
    if polozka in kosik and polozka in kategoria:
        cena, druh, sklad, povod, miesto, znacka = kategoria[polozka]
        if akcia == "pridat":
            if sklad > 0:
                kosik[polozka] += 1
                kategoria[polozka] = (cena, druh, sklad - 1, povod, miesto, znacka)
        elif akcia == "odbrat":
            if kosik[polozka] > 1:
                kosik[polozka] -= 1
                kategoria[polozka] = (cena, druh, sklad + 1, povod, miesto, znacka)
            else:
                mnozstvo = kosik.pop(polozka)
                kategoria[polozka] = (cena, druh, sklad + mnozstvo, povod, miesto, znacka)
        elif akcia == "vymazat":
            mnozstvo = kosik.pop(polozka)
            kategoria[polozka] = (cena, druh, sklad + mnozstvo, povod, miesto, znacka)
    return RedirectResponse("/kosik", status_code=303)

@app.get("/kosik")
def zobraz_kosik(request: Request):
    celkova_cena = 0
    for polozka, mnozstvo in kosik.items():
        cena = aktualne_akcie[polozka][0] if polozka in aktualne_akcie else kategoria[polozka][0]
        celkova_cena += cena * mnozstvo

    return templates.TemplateResponse(
        request=request,
        name="kosik.html",
        context={
            "request": request,
            "kosik": kosik,
            "kategoria": kategoria,
            "celkova_cena": celkova_cena,
            "aktualne_akcie": aktualne_akcie
        }
    )

@app.post("/zaplatit")
def zaplatit(request: Request, kupon: str = Form("")):
    session_id = request.cookies.get("session_id")
    prihlaseny_zakaznik = aktivne_relacie.get(session_id) if session_id else None
    
    celkova_cena = 0
    celkovo_kusov = 0
    
    for polozka, mnozstvo in kosik.items():
        cena = aktualne_akcie[polozka][0] if polozka in aktualne_akcie else kategoria[polozka][0]
        celkova_cena += cena * mnozstvo
        celkovo_kusov += mnozstvo

    if prihlaseny_zakaznik and celkovo_kusov > 0:
        body_dict = nacitaj_body()
        aktualne_body = body_dict.get(prihlaseny_zakaznik, 0)
        body_dict[prihlaseny_zakaznik] = aktualne_body + celkovo_kusov
        uloz_body_db(body_dict)

    zlava = 0
    if kupon in zlavovy_kupon:
        zlava = zlavovy_kupon[kupon]

    cena_po_zlave = celkova_cena * (1 - zlava / 100)

    vysledok = templates.TemplateResponse(
        request=request,
        name="vysledok.html",
        context={
            "cena_po_zlave": cena_po_zlave,
            "zlava": zlava
        }
    )
    kosik.clear()
    return vysledok