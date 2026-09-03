# MVM D tarifa – Home Assistant

Nem hivatalos Home Assistant integráció az MVM D dinamikus tarifa aktuális árának becsléséhez.

## Szenzorok

- **D tarifa – Aktuális teljes ár (becs.)** – becsült bruttó Ft/kWh ár
- **D tarifa – HUPX nyers ár** – aktuális HUPX ár Ft/kWh-ra átszámítva

A becsült teljes ár jelenleg az aktuális HUPX árból, az MNB EUR/HUF árfolyamából, az MVM kereskedői díjából, a fogyasztásarányos rendszerhasználati díjakból és 27% ÁFÁ-ból készül.

## Fontos

Az integráció fejlesztés alatt áll. Az MVM D tarifa minden részlete és elszámolási feltétele még nem ismert, ezért a teljes ár **becslés**.

A **rezsicsökkentett fogyasztási keret és annak kedvezményes ára jelenleg nem része a számításnak**.

Az éves/fix alapdíjak sincsenek beleszámítva, mert a szenzor az aktuális 1 kWh becsült változó költségét mutatja.

Ez egy közösségi projekt, nem hivatalos MVM-integráció.

## Telepítés HACS-ból teszteléshez

1. HACS → Integrációk → jobb felső három pont → **Egyéni tárolók / Custom repositories**.
2. Add hozzá a GitHub repository URL-jét **Integration** típussal.
3. Telepítsd az **MVM D Tariff** integrációt.
4. Indítsd újra a Home Assistantot.
5. Beállítások → Eszközök és szolgáltatások → Integráció hozzáadása → **MVM D Tariff**.

## Adatforrások

- HUPX / Energy-Charts – aktuális magyar negyedórás day-ahead ár
- Magyar Nemzeti Bank – hivatalos EUR/HUF árfolyam
- MVM – közzétett D tarifa és díjtételek

## Licenc

MIT
