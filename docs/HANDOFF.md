# Handoff — JobSheet, stanje 25. 8. 2026.

Ovo je dokument za nastavak rada u idućoj sesiji. Piše što je gotovo, što je
sljedeće, i — najvažnije — koje su zamke već istražene, da se ne istražuju
ponovno.

Plan cijelog projekta: `~/.claude/plans/imam-program-i-ante-trea-i-goofy-iverson.md`

---

## Gdje smo

**Faze 1–5 od 7 su gotove.** Aplikacija radi od kraja do kraja: pokreneš je,
otvori se preglednik, odabereš izvore, pokreneš pretragu, posložiš tablicu,
izvezeš Excel, pratiš prijave.

| Faza | Što | Stanje |
|---|---|---|
| 1 | Jezgra — `Posting`, dedup, datumi, filtri | ✅ `89a3ee4` |
| 2 | Excel koji korisnik oblikuje + sigurnosna ovojnica | ✅ `847f5ce` |
| 3 | Izvori kao pluginovi (14 konektora) | ✅ `25bda91` |
| 4 | SQLite, praćenje prijava, API, CLI, izvoznici | ✅ `d0eea92`, `17a6fc4` |
| 5 | Sučelje — 5 ekrana, hr/en, svijetla/tamna | ✅ `d032379` |
| 6 | **Pakiranje i CI** | ⬜ **sljedeće** |
| 7 | **Objava** | ⬜ |

**Ništa nije pushano.** Repo nema `remote`. To je namjerno: push ide tek u
fazi 7, nakon skeniranja na osobne podatke.

### Brojke koje moraju ostati zelene

```
467 Python testova · 32 frontend testa · ruff čist · mypy čist · bundle 131 kB gzip
```

### Kako to provjeriti

```bash
cd C:\Users\anton\jobsheet
.venv\Scripts\python -m pytest -q                 # 467
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m mypy
cd web && npm run build && npx vitest run          # 32
```

### Kako je pokrenuti

```bash
.venv\Scripts\python -m jobsheet.cli               # otvori http://127.0.0.1:8765
.venv\Scripts\python -m jobsheet.cli sources       # popis izvora
```

---

## Što je preostalo

### Faza 6 — pakiranje i CI

Ovo je sljedeći posao. Ima četiri dijela, poredana po tome što je najkorisnije
prvo napraviti.

#### 6.1 Sučelje mora ući u paket ⚠ *prvo ovo, ovdje je zamka*

`src/jobsheet/web/*` je u `.gitignore` (osim `.gitkeep`), jer je to izgrađeni
artefakt. Ali `hatchling` po zadanome **poštuje `.gitignore`**, pa bi
`pip install .` proizveo paket **bez sučelja** — server bi se digao i pokazao
zamjensku stranicu.

Treba:

- provjeriti što `python -m build` stvarno stavi u wheel
  (`python -c "import zipfile;print(zipfile.ZipFile('dist/…whl').namelist())"`),
- u `pyproject.toml` dodati `[tool.hatch.build.targets.wheel] artifacts` ili
  `force-include` za `src/jobsheet/web`,
- i **testom** to zaključati: build wheela → provjeri da `jobsheet/web/index.html`
  postoji u njemu. Bez testa će se ovo tiho slomiti pri prvom releaseu.

Redoslijed u svakom buildu je: `npm run build` **pa onda** `python -m build`.

#### 6.2 GitHub Actions

`.github/workflows/` je **prazan**. Treba:

- `ci.yml` — `ruff` + `mypy` + `pytest --cov` na 3.11/3.12/3.13 ×
  Ubuntu/Windows/macOS, plus `npm ci && npm run build && npx vitest run`
- `nightly.yml` — ugovorni testovi izvora (`-m network`), **noću, ne na svaki
  push**; marker `network` već postoji u `pyproject.toml`
- `release.yml` — na tag: izgradi frontend, izgradi wheel, objavi na PyPI
  (trusted publishing) i GitHub Releases

`.github/ISSUE_TEMPLATE/` je također prazan.

#### 6.3 Windows ZIP s dvoklikom

Recept postoji i radi — u `C:\Users\anton\AnteTraziPosao\napravi-paket.ps1` i
`app-za-antu\POKRENI - trazi poslove.cmd`. Prenijeti u Python build skriptu:

- ugrađeni CPython (`python-3.13-embed-amd64`), vendorane ovisnosti, izgrađeni
  frontend
- `Start JobSheet.cmd` s lancem `runtime → py -3 → python`
- **smoke test ugrađenim interpreterom prije pakiranja** — taj korak iz Antinog
  buildera vrijedi zadržati doslovno; već je jednom uhvatio pokvaren paket

#### 6.4 macOS/Linux

`pipx install jobsheet` + `.desktop` / `.command` pokretač. Sitno.

---

### Faza 7 — objava

- **README**: hero GIF (pretraga → dizajner tablice → gotov Excel), bedževi
  (CI, coverage, PyPI, licenca), mermaid dijagram arhitekture, sekcija
  *„Add your own source in 30 lines"* s cijelim primjerom, tablica izvora.
  Za GIF: aplikacija je već snimljiva Playwrightom (vidi „Kako sam gledao
  sučelje" niže).
- **`docs/`** je prazan osim ovog filea. Treba `ARCHITECTURE.md`, `SOURCES.md`,
  `EXCEL.md` (uključivo priču o 88 kvačica — to je dobra dokumentacija, ne
  anegdota), `CONTRIBUTING.md`.
- **`examples/`** je prazan. Treba `profile.example.json` — neutralan, bez
  Antonijevih ni Antinih kriterija.
- `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, issue/PR predlošci, GitHub topics.
- **Provjera prije prvog pusha** (obavezno, ovo je razlog zašto se ne pusha):
  - `gitleaks` ili ekvivalent nad `git log -p`
  - ručno traženje: `PROFIL.md`, CV, `careers.md`, Antini kriteriji, Desktop
    putanje, e-mail adrese, ime „Ante"
  - tek onda `git remote add origin …` i push
- **Neobavezni završni dokaz**: Antin ZIP ponovno izgraditi iz `jobsheet` jezgre
  s hrvatskim presetom i layoutom „Classic checkboxes". Ako to prođe,
  generalizacija stvarno radi.

---

## Otvoreno, nije blokada

- **Antonijeva vizualna proba.** Sučelje je provjereno Playwrightom (1440 i
  375 px, obje teme, bez grešaka u konzoli), ali nitko ga nije *koristio*.
  Posebno dizajner tablice — živi pregled je stvar koja se ili čini ispravnom
  ili ne.
- **Nijedan izvor nije pokrenut prema pravom internetu iz nove aplikacije.**
  Konektori imaju fixture-testove, ali ugovorni (`-m network`) nisu vrtjeni.
  Očekivano: HZZ i Posao.hr rade, Selekcija.gov.hr radi, Narodne novine traže
  cijele riječi. **`ZupanijaNaziv` na Selekciji je sjedište tijela, ne mjesto
  rada** — to je već zapisano kao komentar i test.
- **Bundle je jedan chunk od 131 kB gzip.** Unutar proračuna za aplikacijsku
  stranicu (< 300 kB), pa nema hitnosti, ali dijeljenje po ruti bi ga prepolovilo
  ako ikad zatreba.

---

## Zamke koje su već istražene — ne istraživati ponovno

Ovo je najvredniji dio dokumenta. Svaka od njih je koštala vremena.

### Pakiranje i posluživanje

- **`.js` se na Windowsu servira kao `text/plain`.** Media tipovi idu kroz
  registry, koji instalater zna pokvariti. Preglednik onda odbije pokrenuti
  modul i stranica ostane **prazna, bez ijedne poruke u serverskom logu**.
  Riješeno `mimetypes.add_type` na vrhu `api/app.py`; pokriveno testom
  `test_scripts_are_served_as_javascript`. Ne micati.

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
  `Tracker.set_status`, nikad kroz `save_row`. (Ovo me već jednom navelo na
  krivi test.)
- **`set_status` na oglasu kojeg baza ne poznaje** rušio se na FOREIGN KEY.
  Događa se stvarno: netko rukom zalijepi redak u Excel, ili vrati stari
  workbook uz novu bazu. Sada `Tracker.knows()` čuva unos, a `merge_from_sheet`
  takav redak posvaja kao `NEW` pa mu status zapiše kao pravi potez s datumom.
- **`dedup_key` nema shemu** — `example.test/j/1`, ne `https://example.test/j/1`.
  I nije u `model_dump` jer je `property`. Zato postoji `api/serialize.py`;
  svaki endpoint koji vraća redak mora ići kroz njega.
- **`upsert_posting` čuva datume koje je kasniji dohvat izgubio** (`COALESCE`).
  Feedovi ispuštaju polja; brisanje roka koji smo već znali je gubitak podataka.

### Testiranje

- **TestClient šalje `Host: testserver`**, pa ga provjera petlje odbija s 403.
  Svaki test mora koristiti `base_url="http://127.0.0.1:8765"`.
- **CSV s jednim stupcem** piše prazno polje kao `""` — to je ispravan CSV, ne
  bug. Ne pisati testove na jednostupčanim tablicama.
- **`asyncio.create_task` ne radi u sinkronom FastAPI endpointu** (nema petlje —
  sinkroni endpointi idu u threadpool). Zato su `search` endpointi `async def`.
- **mypy sužava `sys.platform`** na host i proglašava druge grane mrtvim kodom.
  Pročitati u varijablu: `system: str = sys.platform`.

### Naslijeđene zamke iz `AnteTraziPosao` (već ugrađene i pokrivene testovima)

- „na neodređeno" **sadrži** „određeno" — blokiranje određenog blokira i stalno;
  zato postoji `employment_type_allowlist`.
- Narodne novine traže cijele riječi: `geodet` → 0 pogodaka, `geodetski` → 39.
- HZZ: iso-8859-2, ALL-CAPS, višestruko escapeani entiteti, a brojevi feedova
  su HZZ-ovi **abecedni indeksi**, ne službene šifre županija.
- Posao.hr vraća samo 30 najnovijih.
- Sortiranje se radi **nad listom objekata**, nikad nad ćelijama. Ovo je razlog
  postojanja cijele sigurnosne ovojnice.

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

Faza 6.1 — provjeriti ide li sučelje u wheel, popraviti `pyproject.toml` i
zaključati testom. To je jedina stvar koja bi, ostavljena, tiho pokvarila prvi
release.

Rečenica za pokretanje:

> Nastavi jobsheet od `docs/HANDOFF.md`: faza 6, počni od 6.1 (sučelje mora ući
> u wheel), pa CI.
