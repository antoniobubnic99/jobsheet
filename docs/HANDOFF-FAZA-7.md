# Handoff — faza 7, objava

Stanje: **faze 1–6 gotove, ništa nije pushano.** Repo nema `remote`.
Zadnji commit: `a248bb0`. Opće stanje projekta i sve zamke: `docs/HANDOFF.md`.

Ovaj dokument pokriva samo objavu. Pisan je nakon **stvarnog izviđačkog
skeniranja** (25. 8. 2026.), pa dio posla koji bi inače bio „provjeri ima li
čega" već ima odgovor.

---

## 0. Što je skeniranje već našlo

Ovo nije pretpostavka — pokrenuto je nad radnim stablom i nad **cijelom
poviješću** (`git log -p --all`).

### Dobre vijesti

- **Nema tajni.** Nijedan API ključ, token ni lozinka. To nije sreća nego
  posljedica dizajna: nijedan izvor ne traži vjerodajnice.
- **Nema Antinih podataka.** Ni `PROFIL.md`, ni CV, ni `careers.md`, ni
  njegovi kriteriji, ni ijedna njegova adresa. Ništa od toga nikad nije ušlo
  u ovaj repo.
- **Nema Desktop putanja ni tuđih e-mail adresa.**
- 125 datoteka ikad u povijesti, 10 commita, jedan autor.

### Što ipak treba odluku

| Nalaz | Gdje | Ozbiljnost |
|---|---|---|
| `docs/HANDOFF.md` je **interni dokument** — spominje „Ante", „Antini kriteriji", i putanju do privatnog plana `~/.claude/plans/imam-program-i-ante-trea-i-goofy-iverson.md` | radno stablo **i povijest** | odluka, ne curenje |
| Commit `3ad7333` u poruci spominje Antu i njegov builder | povijest | odluka |
| `antonio.bubnic.ets@gmail.com` kao autor svih 10 commita | povijest | očekivano, ali svjesno |
| `authors = [{ name = "Antonio Bubnić" }]`, GitHub URL-ovi | `pyproject.toml` | namjerno, ostaje |
| User-Agent nosi ime i URL repoa | `src/jobsheet/core/http.py:33` | namjerno i pristojno, ostaje |

**Procjena:** rizik curenja je **nizak**. Nema ničega povjerljivog — „Ante" je
samo ime bez prezimena i kontakta, putanja plana je lokalna, a e-mail je
Antonijev vlastiti i ionako stoji na javnom GitHub profilu.

**Prava odluka nije sigurnosna nego uređivačka:** `docs/HANDOFF.md` čita se
kao privatne radne bilješke, a ne kao dokumentacija projekta.

---

## 1. Odluka o `docs/HANDOFF.md` ⚠ prvo ovo

Tri opcije, poredane po tome koliko posla traže:

**A. Ostaviti kako jest.** Najbrže. Posjetitelj repoa vidi radne bilješke na
hrvatskom u kojima piše „Ante je imao samo openpyxl". Nije sramota — mnogi
projekti imaju `NOTES.md` — ali nije ni ono što se želi kao prvi dojam.

**B. Preseliti u `docs/internal/` i gitignorati** (isto rješenje kao u
[[project-grad-drzava-rijeka]]). Radno stablo postaje čisto, **povijest
ostaje**. Dovoljno za sve praktične svrhe.

**C. Prepisati povijest** (`git filter-repo`) da HANDOFF.md nikad nije
postojao. Jedina opcija koja stvarno briše trag. Repo nema remote, nema
suradnika i ima 10 commita — dakle ovo je **trenutak kad je to najjeftinije**
i nikad više neće biti ovako lako.

**Preporuka: B**, uz *jedan* prijelaz kroz commit poruku `3ad7333` da se
„Ante" zamijeni neutralnim „prethodni projekt". Ako se ide na C, ide se sada,
prije prvog pusha — poslije je to prepisivanje javne povijesti.

Što god se odabere, **korisni sadržaj HANDOFF-a se ne baca** — zamke iz njega
idu u `docs/ARCHITECTURE.md` i `CONTRIBUTING.md`, gdje ionako pripadaju.

---

## 2. Automatsko skeniranje (svejedno pokrenuti)

Ručno grepanje je našlo ono što je tražilo. Alat traži ono što se ne zna
tražiti.

```bash
# gitleaks nad cijelom poviješću
docker run --rm -v C:\Users\anton\jobsheet:/repo zricethezav/gitleaks:latest \
    detect --source /repo --no-banner
# ili: winget install gitleaks && gitleaks detect --source .
```

Očekivanje: čisto. Ako nešto javi, gotovo sigurno je lažno pozitivan (token
u testnom fixtureu) — provjeriti, ne rotirati napamet.

---

## 3. Dokumentacija

`docs/` ima samo handoffe. `examples/` je prazan. To je najveći dio faze 7.

### 3.1 README — jedino što će većina ikad pročitati

- **Hero GIF**: pretraga → dizajner tablice → gotov Excel. Aplikacija je
  snimljiva Playwrightom, recept je na dnu `docs/HANDOFF.md`.
- **Bedževi**: CI, coverage, PyPI, licenca.
- **Mermaid dijagram** arhitekture.
- **„Add your own source in 30 lines"** s cijelim primjerom — ovo je sekcija
  koja projekt čini *alatom*, a ne skriptom. Izvori su pluginovi preko
  entry-pointa `jobsheet.sources`; treba to pokazati, ne opisati.
- **Tablica izvora**: 14 konektora, koji su globalni a koji hrvatski.
  ⚠ Narodne novine označiti kao „known issue", ne prešutjeti (§5).

### 3.2 `docs/`

| File | Sadržaj |
|---|---|
| `ARCHITECTURE.md` | slojevi, `Posting` kao jedini model, zašto sigurnosna ovojnica oko Excela, sigurnosni model sučelja (127.0.0.1 + Host + token u stranici) |
| `SOURCES.md` | kako napisati izvor, `SourceManifest`, `fetch` vs `enrich`, i **obavezno**: zašto svaki novi izvor mora dobiti metu u `test_sources_live.py` |
| `EXCEL.md` | zašto korisnik sam oblikuje tablicu; **priča o 88 kvačica** — to je dobra dokumentacija, ne anegdota: objašnjava zašto se sortira nad listom objekata a nikad nad ćelijama |
| `CONTRIBUTING.md` | postaviti okolinu, `-m network`, „popravi konektor **i osvježi snimku**" |

### 3.3 `examples/`

`profile.example.json` — **neutralan**. Ni Antonijevi ni Antini kriteriji.
Izmisliti nekog tko traži „junior data analyst, Zagreb ili remote".

### 3.4 Sitno

`CODE_OF_CONDUCT.md` (Contributor Covenant), `CHANGELOG.md` (Keep a
Changelog, `0.1.0` = prvo izdanje), GitHub topics.
Predlošci za prijave su **gotovi** — `.github/ISSUE_TEMPLATE/`.

---

## 4. Push i CI — redoslijed

Workflowi su napisani i logika im je provjerena lokalno, ali **nikad nisu
izvršeni na GitHubu**. Prvi run je i njihov prvi pravi test.

```bash
cd C:\Users\anton\jobsheet
git remote add origin git@github.com:antoniobubnic99/jobsheet.git
git push -u origin main
```

Zatim, redom:

1. **Actions → pustiti CI.** Očekuje se 12 poslova: `frontend`, `lint`,
   9× `test` (3.11–3.13 × Ubuntu/Windows/macOS), `package`.
   Ako nešto pukne, najvjerojatniji kandidati su verzije actiona i to što
   `package` posao pretpostavlja bash na ubuntuu.
2. **Ne dirati `nightly.yml` dok CI nije zelen.** Vrti se u 04:20 UTC i
   **past će na Narodnim novinama po dizajnu** (xfail → to je uredan prolaz;
   pravi pad bi bio nešto drugo).
3. **PyPI trusted publishing** — na PyPI-ju napraviti projekt `jobsheet`,
   dodati GitHub kao trusted publisher: repo `antoniobubnic99/jobsheet`,
   workflow `release.yml`, environment `pypi`. **Nema tokena za spremiti.**
4. **GitHub environment `pypi`**, po želji s ručnim odobrenjem.
5. Provjeriti da je ime `jobsheet` slobodno na PyPI-ju. Ako nije — promijeniti
   ime **prije** prvog izdanja, jer poslije je to seljenje.
6. Tek onda:
   ```bash
   git tag v0.1.0 && git push --tags
   ```
   `release.yml` sam provjerava da se tag i verzija u `pyproject.toml`
   slažu i **odbija objaviti** ako sučelje nije u distribuciji.

⚠ Verzija je sada `0.1.0.dev0`. Za pravo izdanje promijeniti u `0.1.0`,
inače PyPI to tretira kao razvojno izdanje koje `pip install jobsheet` neće
uzeti.

---

## 5. Narodne novine — reći, ne prešutjeti

NN je pokvaren i to je zapisano (`xfail` s punim obrazloženjem u
`tests/test_sources_live.py`, §3 u `docs/HANDOFF.md`).

Za objavu postoje dva poštena puta:

- **Označiti ga u README-u kao known issue** i pustiti da stoji. Otvoreni
  `xfail` s objašnjenjem je znak zdravog projekta, ne slabog.
- **Ili popraviti prije objave.** Treba ponovno pročitati stranicu rezultata
  prema sadašnjem markupu; simptomi su izmjereni i zapisani. Nije velik posao,
  ali je **zaseban** — ne miješati ga s objavom.

Ono što se **ne smije** je maknuti test da popis izvora izgleda čišće.

---

## 6. Neobavezni završni dokaz

Antin ZIP ponovno izgraditi iz `jobsheet` jezgre, s hrvatskim presetom i
layoutom „Classic checkboxes". Ako to prođe, generalizacija stvarno radi — a
to je jedina tvrdnja koju cijeli projekt zapravo postavlja.

Radi se **lokalno, ne objavljuje se.**

---

## 7. Redoslijed koji ima smisla

1. §1 — odluka o HANDOFF.md *(blokira sve ostalo, jer mijenja povijest)*
2. §2 — gitleaks
3. §3 — dokumentacija *(najveći dio posla)*
4. §4.1–4.5 — push, CI zelen, PyPI postavljen
5. verzija `0.1.0.dev0` → `0.1.0`, pa tag
6. §6 — završni dokaz, kad se stigne

---

## Rečenica za pokretanje iduće sesije

> Nastavi jobsheet, faza 7 po `docs/HANDOFF-FAZA-7.md`. Skeniranje je već
> odrađeno i čisto — počni od §1 (odluka o HANDOFF.md), pa dokumentacija.
> Preporuka je opcija B.
