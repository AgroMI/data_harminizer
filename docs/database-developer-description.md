# Adatbazis fejlesztoi leiras

## Cel es szerep

Az alkalmazas adatbazis-modellje egy retegzett adattarhazi mintat kovet. A cel nem egy altalanos vallalati warehouse megvalositasa, hanem egy szakdolgozati demonstrator tamogatasa, amelyben az Excel-alapu agrar megfigyelesek nyers feltoltesbol, ellenorzott ETL-folyamaton at, kanonikus es biztonsagosan lekerdezheto szerkezetbe kerulnek.

Az adatmodell ot logikai retegre bonthato:

- `raw`: a feltoltesi workflow es az eredeti fajl tartos megorzese
- `staging`: az atmeneti, ellenorzott es tisztitott megfigyelesek retege
- `harmonized`: a veglegesitett, kanonikus tenyadatok retege
- `safe`: olvasasi, lekerdezesre optimalizalt nezet
- `ops`: az MCP stilusu es SQL alapu olvasasi muveletek auditnaploja

## Logikai adatfolyam

1. A felhasznalo egy Excel-allomanyt tolt fel.
2. Az eredeti fajl a `raw.artifacts` tablaban tarolodik a kapcsolodo metaadatokkal egyutt.
3. A feltolteshez tartozo munkamenet a `raw.upload_sessions` tablaban jon letre, ahol a rendszer a feldolgozott `preview_json` allapotot is tarolja.
4. A preview-bol az ETL-folyamat strukturalt megfigyeleseket allit elo a `staging.observations` tablaba.
5. A commit lepes utan a rekordok a `harmonized.observations` tablaba kerulnek, ahol mar kanonikus mezokkel, normalizalt mertekegysegekkel es minosegi jelzokkel szerepelnek.
6. Az alkalmazas lekerdezo komponensei nem kozvetlenul a harmonized tablat, hanem a `safe.harmonized_observations_v1` nezetet hasznaljak.
7. Az MCP es query muveletek naplozasa az `ops.mcp_tool_audit_log` tablaba tortenik.

## Tablaszintu leiras

### `raw.artifacts`

Ez a tabla tarolja a feltoltott allomany eredeti binaris tartalmat (`raw_content`), valamint a visszakereshetoseghez es reprodukalhatosaghoz szukseges metaadatokat. Ilyen peldaul a fajlnev, MIME-tipus, meret, SHA-256 hash, parser verzio, illetve a sheet manifest.

Fejlesztoi szempontbol ennek a tablanak ket fo szerepe van:

- bizonyithatoan megorzi az eredeti bemenetet
- lehetove teszi a kesobbi ujrafeldolgozast es provenance elemzest

### `raw.upload_sessions`

Ez a tabla kepviseli a feltoltesi workflow uzleti egyseget. Egy rekord egy feltoltesi sessionnek felel meg. A tabla allapotmezot (`status`) es a javithato elozeti szerkezetet tartalmazo `preview_json` mezot is tarolja. Az `artifact_id` opcionalis kulso kulcskent kapcsolja a sessiont az eredeti fajlhoz.

Tervezesi szempontbol ez a tabela valasztja el egymastol:

- az eredeti binaris forrast
- a feldolgozasi folyamat futasi allapotat
- a felhasznalo altal modositott preview reprezentaciot

### `staging.observations`

Ez a reteg a preview-bol levezetett, de meg atmeneti allapotban levo megfigyeleseket tartalmazza. A rekordok megoriznek minden fontos lineage informaciot:

- melyik feltoltesbol szarmaznak
- melyik munkalaprol (`source_sheet`)
- melyik sorbol (`source_row_index`)
- melyik oszlopbol (`source_column`)

Emellett ebben a tablaban jelennek meg a szemantikus transzformacio eredmenyei is:

- kanonikus dimenziok: `plot_id`, `variety`, `treatment`, `location`
- mert adatok: `variable`, `value`, `unit`
- normalizalt mertekegysegek: `normalized_value`, `normalized_unit`
- minosegi allapot: `validation_status`, `quality_flags`

A staging tabla lenyege, hogy az ETL-folyamat koztes eredmenye ellenorizheto es tesztelheto legyen.

### `harmonized.observations`

Ez a projekt legfontosabb tenyadat-tabla. Strukturaja hasonlit a staging reteghez, de mar a commitolt, kanonikus allapotot kepviseli. Az osszetett primer kulcs biztositja, hogy ugyanazon feltoltesen belul ugyanaz a forrascella ne keruljon tobbszor tarolasra.

Ez a tabla tamogatja:

- a harmonized REST lekerdezeseket
- a kontrollalt NL query reteget
- a biztonsagos text-to-SQL futtatast
- a forraskovetes es minosegi elemzes megorzeset

Az indexek kulonosen a `variable`, `variety`, `treatment`, `location`, `observation_date`, `normalized_unit`, `validation_status` es `quality_flags` mezokre epulnek, mert ezek a legjellemzobb szuro- es keresofeltetelek.

### `safe.harmonized_observations_v1`

Ez nem fizikai tabla, hanem egy olvasasi nezet. Celja, hogy a `harmonized.observations` komplexebb szerkezetebol egy stabil, szandekosan korlatozott, lekerdezesbarat feluletet adjon. A nezet tipizaltan es biztonsagos formaban teszi elerheto azokat az oszlopokat, amelyekre az alkalmazas lekerdezo retegeinek szuksege van.

Fontos architekturális dontes, hogy az AI tamogatott lekerdezesek nem a teljes adatbazison futnak, hanem ezen a vedett absztrakcios retegen.

### `ops.mcp_tool_audit_log`

Az audit tabla az alkalmazas szerszam- es lekerdezesfuttatasi muveleteit naplozza. Tarolja az idobelyeget, korrelacios azonositot, a hivott eszkoz nevet, a sikeresseget, a kerelmet, a valaszt, az esetleges hibat, a futasi idot es adott esetben az SQL nyomait is.

Ez a tabla fejlesztoi es uzemeltetesi szempontbol kulcsfontossagu, mert tamogatja:

- a hibakeresest
- a teljesitmenymerest
- a lekerdezesek reprodukalhatosagat
- a read-only mukodes ellenorzeset

## Kapcsolatok es integritasi szabalyok

Az adatmodellben a legfontosabb kapcsolatok a kovetkezok:

- `raw.upload_sessions.artifact_id -> raw.artifacts.id`
- `staging.observations.upload_session_id -> raw.upload_sessions.id`
- `harmonized.observations.upload_session_id -> raw.upload_sessions.id`
- `safe.harmonized_observations_v1 -> harmonized.observations` nezetkapcsolat

Az integritast a kovetkezo megoldasok tamogatjak:

- kulso kulcsok a session es artifact kapcsolatokra
- `ON DELETE CASCADE` viselkedes a sessionhoz tartozo `staging` es `harmonized` rekordoknal
- osszetett primer kulcs a harmonized tenyadatok egyedisegere
- `CHECK` megszoritasok, peldaul pozitiv sorszamra vagy ervenyes hash-hosszra
- alapertelmezett `jsonb` ertekek a stabil feldolgozhatosaghoz

## Tervezesi indoklas

Az adatmodell szandekosan nem teljesen normalizalt, mert a demonstrator egyik fo celja a gyors, atlathato es reprodukalhato adatfeldolgozas. Emiatt a `staging` es `harmonized` reteg tartalmaz expliciten kiemelt dimenziooszlopokat, meg akkor is, ha azok egy resze a `dimensions_json` mezoben is kifejezheto lenne. Ez a kettos reprezentacio ket ok miatt indokolt:

- egyszerubb lekerdezeseket es indexelest tesz lehetove
- a szakdolgozati demonstracio szamara jobban ertelmezhetove teszi a kanonikus adatmodellt

Szinten tudatos dontes, hogy az alkalmazas az AI altal tamogatott lekerdezeseket a `safe` nezetre korlatozza. Ezzel a rendszer egy szukitett, ellenorzott olvasasi szerzodest hoz letre a nyers tarolas es az intelligens lekerdezes kozott.

## Szakdolgozatba beillesztheto rovid leiras

Az alkalmazas adatbazisa retegzett szerkezetu. A `raw` schema tarolja az eredeti feltoltott Excel-allomanyt es a feldolgozasi munkamenet metaadatait, a `staging` schema az atmeneti, ellenorzott megfigyeleseket tartalmazza, mig a `harmonized` schema a commitolt, kanonikus tenyadatok taroloja. A lekerdezo komponensek nem kozvetlenul a harmonized tablakat hasznaljak, hanem a `safe.harmonized_observations_v1` olvasasi nezetet, amely stabil es biztonsagos interfeszt ad a termeszetes nyelvu lekerdezesek es a kontrollalt text-to-SQL folyamat szamara. Az uzemeltetesi es visszakovethetosegi szempontokat az `ops.mcp_tool_audit_log` audit tabla tamogatja.
