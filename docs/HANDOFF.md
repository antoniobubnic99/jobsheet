# Handoff — JobSheet, stanje 25. 8. 2026. (nakon faze 6)

Dokument za nastavak rada. Piše što je gotovo, što je sljedeće, i — najvažnije
— koje su zamke već istražene, da se ne istražuju ponovno.

Plan cijelog projekta: `~/.claude/plans/imam-program-i-ante-trea-i-goofy-iverson.md`

---

## Gdje smo

**Faze 1–6 od 7 su gotove.** Aplikacija radi od kraja do kraja, pakira se u
wheel, u sdist i u Windows ZIP s dvoklikom, i ima CI koji sve to čuva.

| Faza | Što | Stanje |
|---|---|---|
| 1 | Jezgra — `Posting`, dedup, datumi, filtri | ✅ `89a3ee4` |
| 2 | Excel koji korisnik oblikuje + sigurnosna ovojnica | ✅ `847f5ce` |
| 3 | Izvori kao pluginovi (14 konektora) | ✅ `25bda91` |
| 4 | SQLite, praćenje prijava, API, CLI, izvoznici | ✅ `d0eea92`, `17a6fc4` |
| 5 | Sučelje — 5 ekrana, hr/en, svijetla/tamna | ✅ `d032379` |
| 6 | Pakiranje, CI, pokretači | ✅ `b8e2bd0`, `0ee4cff`, `e443605`, `3ad7333` |
| 7 | **Objava** | ⬜ **sljedeće** |

**Ništa nije pushano.** Repo i dalje nema `remote`. To je namjerno: push ide
tek u fazi 7, nakon skeniranja na osobne podatke.

### Brojke koje moraju ostati zelene

```
474 Python testa (+15 mrežnih, odvojeno) · 32 frontend testa · ruff čist · mypy čist
```

### Kako to provjeriti

```bash
cd C:\Users\anton\jobsheet
set JOBSHEET_ASSERT_PACKAGED_WEB=1
.venv\Scripts\python -m pytest -q                 # 474, mrežni se ne diraju
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m mypy
cd web && npm run build && npx vitest run          # 32
```

Živi izvori (dira tuđe servere, ne vrtjeti u petlji):

```bash
.venv\Scripts\python -m pytest tests/test_sources_live.py -m network -v
```

### Kako je pokrenuti

```bash
.venv\Scripts\python -m jobsheet.cli               # otvori http://127.0.0.1:8765
.venv\Scripts\python -m jobsheet.cli sources       # popis izvora
```

### Kako napraviti Windows ZIP

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-windows-zip.ps1
# -> build\JobSheet-windows.zip  (~17,6 MB)
```

---

## Što je faza 6 zapravo našla

Tri stvari koje snimljeni testovi po definiciji nisu mogli vidjeti.

### 1. Wheel bez sučelja (POPRAVLJENO, `b8e2bd0`)

Hatchling poštuje `.gitignore`, a `src/jobsheet/web/*` je ondje jer je
izgrađeni artefakt. `pip install .` je proizvodio paket u kojem je od sučelja
bio **samo `.gitkeep`**. Server bi se digao, API bi radio, korisnik bi dobio
stranicu „the interface has not been built" — i ništa u buildu ne bi puklo.

Riješeno `artifacts` unosima za wheel i sdist, zaključano
`tests/test_packaging.py` (gradi pravi wheel i sdist pa gleda unutra).
`JOBSHEET_ASSERT_PACKAGED_WEB=1` pretvara preskakanje u pad — bez toga bi u
CI-ju „frontend nije izgrađen" prošlo kao prolaz.

### 2. Selekcija.gov.hr je bila mrtva (POPRAVLJENO, `0ee4cff`)

Rhetos je počeo vraćati `{"Records": [...]}` umjesto golog niza. Kod je na
dict dizao `SourceError`, pa je izvor **svim korisnicima vraćao nula
rezultata** — a svih 6 snimljenih testova je prolazilo, jer je snimka
zastarjela zajedno sa servisom.

Sada se prihvaćaju oba oblika. Živo provjereno: 557 natječaja, `ZupanijaNaziv`
i dalje ne ide u `region`.

**Ovo je razlog zašto `tests/test_sources_live.py` postoji.**

### 3. Narodne novine su i dalje pokvarene (NIJE POPRAVLJENO)

Označeno `xfail` s punim obrazloženjem u `tests/test_sources_live.py`.

Simptomi, izmjereni 25. 8. 2026.:

- ustanova (`company`) se **nikad** ne nađe — prazna za svaki rezultat
- naslovi dolaze kao krnje rečenice: `'ne može biti primljena osoba'`,
  `'pod rednim brojem'`, `'višeg referenta'`
- broj rezultata je **identičan za 30, 90 i 365 dana** → paginacije nema
- dokumentirano ponašanje bilo je `geodet` → 0 i `geodetski` → 39;
  danas su 2 i 1

Treba ponovno pročitati stranicu rezultata prema sadašnjem markupu. To je
zaseban posao i nije bio dio faze 6. Kad se popravi, `xfail` će postati
`xpass` i test će sam javiti.

### 4. HZZ ispušta naslove (nije kvar, ali treba znati)

26% stavki u feedu ima prazan `<title>`, **i to u nizu** — prvih 15 stavki
zagrebačkog feeda bilo je bez naslova. Naslov postoji samo na stranici oglasa
i `enrich` ga uredno vadi (ima svoj živi test).

Zamka: **filtar po ključnim riječima radi PRIJE enricha** (korak 3 vs korak 4
u `pipeline.py`), pa se te oglase može uhvatiti samo preko opisa. Ako netko
prijavi „HZZ mi ne nalazi X", ovo je prvo mjesto za pogledati.

### 5. `npm run build` je brisao `.gitkeep`

Vite ima `emptyOutDir: true`, pa je svaki build brisao praćeni `.gitkeep` i
ostavljao prljavo stablo. `.gitkeep` je izbačen iz gita, `.gitignore`
pojednostavljen, a CI sada provjerava da build ne dira praćene datoteke.

---

## Što je preostalo — faza 7, objava

### 7.1 Dokumentacija

- **README**: hero GIF (pretraga → dizajner tablice → gotov Excel), bedževi
  (CI, coverage, PyPI, licenca), mermaid dijagram arhitekture, sekcija
  *„Add your own source in 30 lines"* s cijelim primjerom, tablica izvora.
  Za GIF: aplikacija je snimljiva Playwrightom (recept niže).
- **`docs/`** ima samo ovaj file. Treba `ARCHITECTURE.md`, `SOURCES.md`,
  `EXCEL.md` (uključivo priču o 88 kvačica — to je dobra dokumentacija, ne
  anegdota), `CONTRIBUTING.md`.
- **`examples/`** je prazan. Treba `profile.example.json` — neutralan, bez
  Antonijevih ni Antinih kriterija.
- `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, GitHub topics.
  (Predlošci za prijave su gotovi: `.github/ISSUE_TEMPLATE/`.)

### 7.2 Provjera prije prvog pusha ⚠ obavezno

Ovo je razlog zašto se dosad nije pushalo:

- `gitleaks` ili ekvivalent nad `git log -p`
- ručno traženje: `PROFIL.md`, CV, `careers.md`, Antini kriteriji, Desktop
  putanje, e-mail adrese, ime „Ante"
- tek onda `git remote add origin …` i push

### 7.3 Nakon pusha, redom

1. **Uključiti Actions** i pustiti CI da prođe (9 matrix poslova + lint +
   package). Prvi run je i prva provjera da su workflowi točni — pisani su i
   provjereni lokalno koliko se dalo, ali nisu nikad izvršeni na GitHubu.
2. **PyPI trusted publishing**: na PyPI-ju napraviti projekt `jobsheet` i
   dodati GitHub kao trusted publisher (`release.yml`, environment `pypi`).
   Nema tokena za spremiti.
3. **GitHub environment `pypi`** s zaštitom, ako se želi ručno odobrenje.
4. Tek onda `git tag v0.1.0 && git push --tags`.
   `release.yml` sam provjerava da se tag i verzija u `pyproject.toml` slažu.

### 7.4 Neobavezni završni dokaz

Antin ZIP ponovno izgraditi iz `jobsheet` jezgre s hrvatskim presetom i
layoutom „Classic checkboxes". Ako to prođe, generalizacija stvarno radi.

---

## Otvoreno, nije blokada

- **Antonijeva vizualna proba.** Sučelje je provjereno Playwrightom (1440 i
  375 px, obje teme, bez grešaka u konzoli) i sada i kroz raspakiran ZIP, ali
  nitko ga nije *koristio*. Posebno dizajner tablice — živi pregled je stvar
  koja se ili čini ispravnom ili ne.
- **Narodne novine** (gore, §3).
- **Recruitee nema živu metu s oglasima.** Od 20 probanih slugova jedini koji
  odgovara s 200 je `tellent`, i nema otvorenih pozicija. Test to prihvaća
  (`expect_results=False`) jer i dalje dokazuje endpoint i parser. Ako se nađe
  bolji: `JOBSHEET_LIVE_RECRUITEE=<slug>`.
- **Bundle je jedan chunk od 131 kB gzip.** Unutar proračuna za aplikacijsku
  stranicu (< 300 kB), pa nema hitnosti.
- **Workflowi nisu nikad izvršeni na GitHubu** — vidi 7.3.1.

---

## Zamke koje su već istražene — ne istraživati ponovno

Ovo je najvredniji dio dokumenta. Svaka od njih je koštala vremena.

### Pakiranje i posluživanje

- **Hatchling poštuje `.gitignore`.** Vidi §1 gore. `artifacts` u
  `pyproject.toml` i `tests/test_packaging.py` su par — makneš jedno, drugo
  prestaje išta značiti.
- **Redoslijed builda je `npm run build` PA `python -m build`.** Obrnuto daje
  wheel bez sučelja i ništa ne javi.
- **`.js` se na Windowsu servira kao `text/plain`.** Media tipovi idu kroz
  registry, koji instalater zna pokvariti. Preglednik onda odbije pokrenuti
  modul i stranica ostane **prazna, bez ijedne poruke u serverskom logu**.
  Riješeno `mimetypes.add_type` na vrhu `api/app.py`; pokriveno testom
  `test_scripts_are_served_as_javascript`. Ne micati.
- **Embeddable Python ima `._pth` koji zaključa `sys.path` i gasi `site`.**
  Bez dopisivanja `..\lib` ništa se ne uveze. Putanja mora biti relativna —
  korisnik mapu raspakira gdje hoće.
- **Ante je imao samo openpyxl (čisti Python), JobSheet ima prevedena
  proširenja** (pydantic-core, httptools, watchfiles, websockets). Zato
  `pip install --target`, a ne kopiranje site-packagesa, i zato provjera da se
  minor verzija hosta poklapa s ugrađenom.
- **`Start-Process -Environment` traži PowerShell 7.4.** Windows nosi 5.1;
  postaviti `$env:` prije pokretanja i vratiti poslije.

### Testiranje

- **Snimljeni fixture koji je zastario zajedno sa servisom je najgori mogući
  test**: zelen je, a proizvod je mrtav. Zato `tests/test_sources_live.py`.
  Kad živi test padne, popravi se konektor **i osvježi snimka** — inače se
  vraćamo na isto.
- **Živi testovi nikad ne tvrde broj rezultata.** Test koji pada jer je netko
  smanjio broj oglasa je test koji se nauči ignorirati.
- **`addopts = "-m 'not network'"`** — običan `pytest` ne smije nikoga zvati.
- **`registry.load_all()` u testovima vidi i testne duplikate**, jer pola
  suitea registrira lažne izvore u proces. Provjera pokrivenosti izvora zato
  čita **entry pointove**, ne `load_all()`.
- **TestClient šalje `Host: testserver`**, pa ga provjera petlje odbija s 403.
  Svaki test mora koristiti `base_url="http://127.0.0.1:8765"`.
- **CSV s jednim stupcem** piše prazno polje kao `""` — to je ispravan CSV, ne
  bug. Ne pisati testove na jednostupčanim tablicama.
- **`asyncio.create_task` ne radi u sinkronom FastAPI endpointu** (nema petlje
  — sinkroni endpointi idu u threadpool). Zato su `search` endpointi
  `async def`.
- **mypy sužava `sys.platform`** na host i proglašava druge grane mrtvim
  kodom. Pročitati u varijablu: `system: str = sys.platform`.

### CSS i izgled

- **`overflow-x: auto` ne zadržava `<table>`.** Chrome i dalje broji širinu
  tablice u dokumentov scroll, pa se **cijela stranica vuče u stranu na
  mobitelu** iako tablica ispravno skrola unutar sebe. Treba `contain: paint`
  (klasa `.scroll-x` u `global.css`).
  **Ali ploča kanbana namjerno NEMA containment** — odrezao bi karticu čim je
  povučeš preko ruba ploče. Ondje je običan `overflow-x-auto`.
- `whitespace-nowrap` je bio za vodoravnu traku na mobitelu; na desktopu je
  rezao natuknice u traci. Sada `md:whitespace-normal`.

### Baza i model

- **`save_row` NE mijenja status.** To je namjerno: status je korisnikov, a
  ponovno viđen oglas ga ne smije prepisati. Za promjenu statusa ide se kroz
  `Tracker.set_status`, nikad kroz `save_row`.
- **`set_status` na oglasu kojeg baza ne poznaje** rušio se na FOREIGN KEY.
  Događa se stvarno: netko rukom zalijepi redak u Excel, ili vrati stari
  workbook uz novu bazu. Sada `Tracker.knows()` čuva unos, a `merge_from_sheet`
  takav redak posvaja kao `NEW`.
- **`dedup_key` nema shemu** — `example.test/j/1`, ne `https://example.test/j/1`.
  I nije u `model_dump` jer je `property`. Zato postoji `api/serialize.py`;
  svaki endpoint koji vraća redak mora ići kroz njega.
- **`upsert_posting` čuva datume koje je kasniji dohvat izgubio** (`COALESCE`).
  Feedovi ispuštaju polja; brisanje roka koji smo već znali je gubitak
  podataka.

### Izvori

- **HZZ ispušta naslove u nizu** — vidi §4 gore.
- **Selekcija: `ZupanijaNaziv` je sjedište tijela, NE mjesto rada.** 27%
  natječaja imenuje glavni grad dok je posao u Splitu, Osijeku ili na otoku.
  Samo `MjestoRada` / `LokacijaRadnogMjesta` kaže gdje je posao.
- **Selekcija: datumi su .NET `/Date(ms+hhmm)/`.** Ispuštanje offseta pomiče
  svaki datum objave dan unatrag.
- „na neodređeno" **sadrži** „određeno" — blokiranje određenog blokira i
  stalno; zato postoji `employment_type_allowlist`.
- Narodne novine traže cijele riječi (bilo `geodet` → 0, `geodetski` → 39;
  sada pokvareno, §3).
- HZZ: iso-8859-2, ALL-CAPS, višestruko escapeani entiteti, a brojevi feedova
  su HZZ-ovi **abecedni indeksi**, ne službene šifre županija.
- Posao.hr vraća samo 30 najnovijih.
- Sortiranje se radi **nad listom objekata**, nikad nad ćelijama. Ovo je
  razlog postojanja cijele sigurnosne ovojnice.
- **Lever `leverdemo`** je Leverov službeni demo račun — stabilna meta za živi
  test. `netflix`, `brex`, `match` daju 404.

---

## Kako sam gledao sučelje (za GIF u fazi 7 i za buduće provjere)

Playwright je već instaliran u `web/node_modules`, chromium je preuzet.
Postupak koji je uhvatio četiri buga:

1. Pokreni server na zasebnom portu s vlastitim `JOBSHEET_HOME` u `.scratch/`.
2. Napuni bazu s nekoliko oglasa kroz `Database` + `Tracker` (ne kroz mrežu).
3. Skripta koja obiđe svih pet ruta u obje teme na 1440 px, pa `/results` na
   375 px, i **skuplja `console` i `pageerror`** — bez toga se prazna stranica
   ne vidi.
4. Za provjeru vodoravnog prelijevanja: **ne** `documentElement.scrollWidth`
   (lažno pozitivan zbog `overflow-x`), nego bisekcija — sakrij element,
   izmjeri, vrati.

Skripte su bile u `.scratch/` i obrisane su; recept je gore.

---

## Prvi potez u idućoj sesiji

Faza 7. Redoslijed koji ima smisla: prvo **7.2 (skeniranje na osobne
podatke)**, jer o njemu ovisi smije li se išta pushati; pa dokumentacija; pa
push i CI.

Rečenica za pokretanje:

> Nastavi jobsheet od `docs/HANDOFF.md`: faza 7, počni od skeniranja na osobne
> podatke (7.2), pa dokumentacija.
