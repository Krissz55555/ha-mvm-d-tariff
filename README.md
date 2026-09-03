# ⚡ MVM D tarifa – Home Assistant

Nem hivatalos Home Assistant integráció az **MVM D dinamikus tarifa** aktuális villamosenergia-árának becsléséhez.

Az integráció célja, hogy a D tarifához kapcsolódó aktuális piaci árat Home Assistant szenzorokként tegye elérhetővé, így később automatizálásokhoz, energiafelügyelethez vagy például EV-töltés vezérléséhez is felhasználható legyen.

## Szenzorok

Az integráció jelenleg két szenzort hoz létre:

- **D tarifa – Aktuális teljes ár (becs.)**  
  Becsült aktuális bruttó villamosenergia-ár **Ft/kWh** értékben.

- **D tarifa – HUPX nyers ár**  
  Az aktuális HUPX villamosenergia-piaci ár **Ft/kWh** értékre átszámítva.

A becsült teljes ár jelenleg az aktuális **HUPX árból**, az **MNB EUR/HUF árfolyamából**, az **MVM kereskedői díjából**, a fogyasztásarányos **rendszerhasználati díjakból** és **27% ÁFÁ-ból** készül.

## ⚠️ Fontos

Az integráció fejlesztés alatt áll.

Az MVM D tarifa minden részlete és elszámolási feltétele jelenleg még nem ismert, ezért az integráció által számított teljes ár **becslés**.

A **rezsicsökkentett fogyasztási keret és annak kedvezményes ára jelenleg nem része a számításnak**.

Az integráció ezért elsősorban az aktuális, változó D tarifa költségének követésére szolgál.

## Telepítés HACS segítségével

1. Nyisd meg a **HACS → Integrációk** oldalt.
2. Jobb felső sarokban válaszd a **⋮ → Egyedi repók** lehetőséget.
3. Add hozzá ezt a repository-t:

   `https://github.com/Krissz55555/ha-mvm-d-tariff`

4. Típusnak válaszd az **Integráció** lehetőséget.
5. Keresd meg az **MVM D Tariff** integrációt, majd telepítsd.
6. Indítsd újra a Home Assistantot.
7. Menj a **Beállítások → Eszközök és szolgáltatások → Integráció hozzáadása** menübe.
8. Keresd meg az **MVM D tarifa** integrációt és add hozzá.

A konfiguráció után a szenzorok automatikusan létrejönnek.

## Adatforrások

- **HUPX / Energy-Charts** – aktuális magyar villamosenergia-piaci ár
- **Magyar Nemzeti Bank** – hivatalos EUR/HUF árfolyam
- **MVM** – közzétett D tarifa díjtételek

## Státusz

🧪 **Korai fejlesztési verzió**

Az integráció működőképes, de a D tarifa végleges elszámolási szabályainak pontosítása miatt a számítás a későbbiekben változhat.

Hibajelzések, tapasztalatok és fejlesztési javaslatok szívesen fogadottak.

---

## Credits

Created and maintained by **Kocsis Krisztián**.

Developed by Kocsis Krisztián with implementation assistance, architecture discussions and documentation support from **ChatGPT (OpenAI)**.

⭐ Ha hasznosnak találod az integrációt, egy GitHub csillaggal támogathatod a projektet.

---

## Project Statistics

![GitHub Downloads](https://img.shields.io/github/downloads/Krissz55555/ha-mvm-d-tariff/total?label=Downloads)
![GitHub Stars](https://img.shields.io/github/stars/Krissz55555/ha-mvm-d-tariff?style=flat&label=Stars)

---

## ☕ Támogatás

Az **MVM D tarifa – Home Assistant** integráció ingyenes és nyílt forráskódú.

Ha hasznosnak találod a projektet, és támogatnád a további fejlesztést, tesztelést és új funkciók elkészítését, meghívhatsz egy kávéra:

☕ [Buy me a coffee](https://buymeacoffee.com/krissz55555)

Köszönöm a támogatást!

---

## Licenc

MIT
