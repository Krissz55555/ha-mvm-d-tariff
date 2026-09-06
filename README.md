# ⚡ MVM D tarifa – Home Assistant

Nem hivatalos Home Assistant integráció az **MVM D dinamikus tarifa** villamosenergia-árának követéséhez és becsléséhez.

Az integráció célja, hogy a D tarifához kapcsolódó aktuális és day-ahead piaci árakat Home Assistant szenzorokként tegye elérhetővé, így azok automatizálásokhoz, energiafelügyelethez, költségkövetéshez vagy például EV-töltés vezérléséhez is felhasználhatók legyenek.

## ✨ Főbb lehetőségek

- Aktuális becsült **D tarifa teljes ár** (Ft/kWh)
- Aktuális **HUPX nyers piaci ár**
- Teljes napi **96 × 15 perces day-ahead (DAM) ár-előrejelzés**
- Napi minimum, maximum és átlagos előrejelzett ár
- Beépített **24 órás ár-előrejelzési grafikon**
- Beállítható **„Olcsó időszak” binary sensor** automatizálásokhoz
- Opcionális fogyasztásmérő hozzárendelése
- Havi fogyasztás és becsült **D tarifa költség**
- Összehasonlítás az **A1 tarifával**

A teljes napi 96 pontos előrejelzés egyetlen szenzor strukturált adataként érhető el, ezért az integráció nem hoz létre 96 külön entitást.

## 📊 Ár-előrejelzés

A **D tarifa – Mai előrejelzett ár** szenzor a teljes napi day-ahead (DAM) adatsort tartalmazza.

Az integráció saját Home Assistant kártyát is tartalmaz:

**MVM D tarifa – Napi ár-előrejelzés**

A kártya megjeleníti:

- az aktuális előrejelzett árat,
- a napi minimumot,
- a napi átlagot,
- a napi maximumot,
- valamint a teljes 00:00–24:00 közötti ár-előrejelzést.

A grafikon használatához **nem szükséges ApexCharts vagy más külön frontend-kiegészítő**.

## ⚙️ Beállítások

Az integráció hozzáadása után a

**Beállítások → Eszközök és szolgáltatások → MVM D tarifa → Beállítások**

menüpontban módosíthatók a számításhoz használt értékek.

Beállítható többek között:

- kereskedői díj,
- átviteli díj,
- elosztói díj,
- ÁFA,
- A1 referenciaár,
- az „Olcsó D tarifa” határértéke,
- valamint opcionálisan egy Home Assistantban már meglévő fogyasztásmérő energia-szenzor.

### ⚡ Fogyasztásmérő kiválasztása

A havi fogyasztás- és költségszámításhoz az integráció **kWh-alapú energia szenzort** használ.

A kiválasztott entitásnak az elfogyasztott energiát kell mérnie:

- **kWh-alapú energia szenzor:** ✅
- **pillanatnyi teljesítmény (W vagy kW):** ❌

Például megfelelő egy villanyóra, okosmérő vagy fogyasztásmérő olyan Home Assistant entitása, amelynek értéke az összesített elfogyasztott energiát mutatja kWh-ban.

Az integráció a kWh mérőállás változásából számolja az adott hónapban felhasznált energiát.

Ennek alapján létrehozza többek között:

- **D tarifa – Havi mért fogyasztás**
- **D tarifa – Havi költség (becs.)**
- **A1 tarifa – Havi költség**
- **D tarifa – Havi különbség az A1-hez képest**

Így ugyanaz a ténylegesen mért fogyasztás összehasonlítható a becsült D tarifa és az A1 tarifa alapján.

Az **Olcsó időszak** binary sensor akkor kapcsol be, amikor az aktuális becsült D tarifa ára a felhasználó által beállított határérték alatt van. Ez közvetlenül használható Home Assistant automatizálásokban.

## Szenzorok

Az integráció többek között az alábbi entitásokat hozza létre:

- **D tarifa – Aktuális teljes ár (becs.)**
- **D tarifa – HUPX nyers ár**
- **D tarifa – Mai előrejelzett ár**
- **D tarifa – Mai minimum előrejelzett ár**
- **D tarifa – Mai maximum előrejelzett ár**
- **D tarifa – Mai átlagos előrejelzett ár**
- **D tarifa – Olcsó időszak**

Fogyasztásmérő hozzárendelése esetén további költség- és fogyasztási szenzorok is létrejönnek.

A becsült teljes ár az aktuális **HUPX árból**, az **MNB EUR/HUF árfolyamából**, az ismert **kereskedői díjból**, a fogyasztásarányos **rendszerhasználati díjakból** és **27% ÁFÁ-ból** készül.

## ⚠️ Fontos

Az integráció fejlesztés alatt áll.

Az MVM D tarifa minden részlete és elszámolási feltétele jelenleg még nem ismert, ezért az integráció által számított teljes ár **becslés**.

A **rezsicsökkentett fogyasztási keret és annak kedvezményes ára jelenleg nem része a számításnak**.

Az integráció ezért elsősorban az aktuális és várható D tarifa költségének követésére, összehasonlítására és automatizálások készítésére szolgál.

## 📦 Telepítés HACS segítségével

1. Nyisd meg a **HACS → Integrációk** oldalt.
2. Jobb felső sarokban válaszd a **⋮ → Egyedi repók** lehetőséget.
3. Add hozzá ezt a repository-t:

   `https://github.com/Krissz55555/ha-mvm-d-tariff`

4. Típusnak válaszd az **Integráció** lehetőséget.
5. Keresd meg az **MVM D Tariff** integrációt, majd telepítsd.
6. **Indítsd újra a Home Assistantot.**
7. Menj a **Beállítások → Eszközök és szolgáltatások → Integráció hozzáadása** menübe.
8. Keresd meg az **MVM D tarifa** integrációt és add hozzá.

A konfiguráció után a szükséges entitások automatikusan létrejönnek.

## 📈 Napi ár-előrejelzés kártya beállítása

A v0.2.0 saját Home Assistant kártyát tartalmaz. A kártyához **nem szükséges ApexCharts vagy más külön HACS frontend-kiegészítő**.

A kártya használatához egyszer hozzá kell adni a mellékelt JavaScript modult a Home Assistant erőforrásaihoz.

Menj ide:

**Beállítások → Irányítópultok → ⋮ → Erőforrások → Erőforrás hozzáadása**

Add meg az alábbi URL-t:

`/mvm_d_tariff/frontend/mvm-d-tariff-card.js?v=0.2.0`

Típus:

**JavaScript module**

Mentsd el az erőforrást.

Ha a kártya ezután nem jelenik meg azonnal a kártyaválasztóban, frissítsd újra a Home Assistant felületét vagy indítsd újra a Home Assistantot.

Ezután az irányítópult szerkesztésénél válaszd:

**Kártya hozzáadása → MVM D tarifa – Napi ár-előrejelzés**

A kártya ezután használatra kész.

> **Megjegyzés:** a JavaScript erőforrást csak egyszer kell hozzáadni. Az integráció későbbi újratöltésekor vagy a beállítások módosításakor ezt nem kell megismételni.

## Adatforrások

- **HUPX / Energy-Charts** – magyar villamosenergia-piaci és day-ahead adatok
- **Magyar Nemzeti Bank** – hivatalos EUR/HUF árfolyam
- **MVM** – közzétett D tarifa díjtételek

## Státusz

🧪 **Fejlesztési verzió – v0.2.0**

Az integráció működőképes, de a D tarifa végleges elszámolási szabályainak pontosítása miatt a számítás a későbbiekben változhat.

Hibajelzések, tapasztalatok és fejlesztési javaslatok szívesen fogadottak.

---

## Credits

Created and maintained by **Kocsis Krisztián**.

Developed by Kocsis Krisztián with implementation assistance, architecture discussions and documentation support from **ChatGPT (OpenAI)**.

⭐ Ha hasznosnak találod az integrációt, egy GitHub csillaggal támogathatod a projektet.

---

<!-- MVM_D_TARIFF_STATS_START -->
## 📊 MVM D tarifa Statistics

- Repository views: **761**
- Repository clones: **99**
- Tracking since: **2026-08-22**

<!-- MVM_D_TARIFF_STATS_END -->

---

## ☕ Támogatás

Az **MVM D tarifa – Home Assistant** integráció ingyenes és nyílt forráskódú.

Ha hasznosnak találod a projektet, és támogatnád a további fejlesztést, tesztelést és új funkciók elkészítését, meghívhatsz egy kávéra:

☕ [Buy me a coffee](https://buymeacoffee.com/krissz55555)

Köszönöm a támogatást!

---

## Licenc

MIT
