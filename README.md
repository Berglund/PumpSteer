# PumpSteer

PumpSteer är en anpassad Home Assistant-integration för att dynamiskt optimera din värmepump genom att manipulera insignalen från utomhustemperatursensorn. Den låter dig spara energi och pengar genom att anpassa din uppvärmningsstrategi baserat på elpriser, inomhustemperatur, väderprognoser och termisk tröghet.

-----

# Ansvarsfriskrivning

Jag är inte expert på programmering, energihantering eller automation. Denna setup är baserad på mina personliga erfarenheter och experiment. Jag kan inte garantera att den fungerar för alla, och jag tar inget ansvar för problem eller skador som kan uppstå vid användning av denna konfiguration eller kod.

**Använd den på egen risk och testa noggrant i din egen miljö.**

-----

## ✅ Funktioner

- 🔧 Smart virtuell styrning av utomhustemperatur
- 🌡️ Dynamisk komfortstyrning med:
  - Inomhustemperatur
  - Målinomhustemperatur
  - Prognos för elpris
  - Temperaturprognos (kommaseparerad lista)
  - Termisk tröghet
  - ~~PI-reglering (integralfel)~~
- 💸 Elprisanpassning via Nordpool eller annan sensor
- ~~🚀 Pre-boost-läge: lagrar värme före pristoppar~~
- 🧊 Bromsläge: minimerar uppvärmning vid höga priser
- ☀️ Sommarläge: inaktiverar all styrning vid varma temperaturer
- 🏝️ Semesterläge: tillfällig temperatursänkning under frånvaro
- 🧠 Självanpassning till husets tröghet
- 🎛️ Finjustering via hjälpentiteter (`input_number`, `input_text`, `input_boolean`, `input_datetime`)
- 🖼️ Extra sensorer via `template:` för UI-visualisering

> 💡 **Notis**: Semesterläge är endast aktivt när utomhustemperaturen är under sommartröskeln.

-----

## 🔧 Installation via HACS (Custom Repository)

Om PumpSteer ännu inte finns i HACS:

1. Gå till **HACS > ⋮ > Custom Repositories**
2. Lägg till: `https://github.com/JohanAlvedal/PumpSteer`
3. Välj **Integration** som kategori
4. Installera PumpSteer
5. Starta om Home Assistant
6. Följ installationsguiden och välj hjälpentiteter

-----

## 📦 Hjälpentiteter (via `pumpsteer_package.yaml`)

Följande entiteter används av PumpSteer och kan justeras i UI:

| Typ | Entitet | Funktion |
|-----|---------|----------|
| `input_number` | `indoor_target_temperature` | Mål för inomhustemperatur |
| `input_number` | `pumpsteer_summer_threshold` | Tröskel för att aktivera sommarläge |
| `input_number` | `pumpsteer_aggressiveness` | Komfort vs besparing (0–5) |
| `input_number` | `house_inertia` | Hur trögt huset reagerar (0–10) |
| `input_number` | `pumpsteer_integral_gain` | Justerar PI-regleringens känslighet |
| `input_number` | `integral_temp_error` | Ackumulerad temperaturavvikelse |
| `input_text` | `hourly_forecast_temperatures` | Prognostemperaturer (24 CSV-värden) |
| `input_boolean` | `holiday_mode` | Aktiverar semesterläge |
| `input_datetime` | `holiday_start` / `holiday_end` | Semesterns intervall (automatisk aktivering) |

-----

## 🧪 Prognosformat

`input_text.hourly_forecast_temperatures` måste innehålla 24 kommaseparerade temperaturer (°C):

```text
-3.5,-4.2,-5.0,-4.8,... (totalt 24 värden)

-----

## 💬 Loggning och Felsökning

  - Varningar och fel loggas i standardloggen för Home Assistant.
  - Om nödvändig sensordata inte är tillgänglig, kommer PumpSteer att visa `unavailable` och försöka igen automatiskt.
  - Husets tröghetsvärde beräknas och uppdateras automatiskt om du inte anger en manuell åsidosättning via ett `input_number`.

-----

## En notering från utvecklaren

Denna integration har byggts av en amatörutvecklare med kraftfull assistans av Googles Gemini och Copilot. Det är resultatet av en passion för smarta hem, mycket trial and error, och många, många Home Assistant restarts.

Vänligen betrakta detta som en **betaprodukt** i ordets sannaste bemärkelse.

Om du är kunnig inom detta område välkomnas konstruktiv feedback, förslag och bidrag varmt. Var tålmodig, då detta är ett lärande projekt.

-----

## 🔗 Länkar

  - [Ärendehanterare](https://github.com/JohanAlvedal/pumpsteer/issues)

-----

© Johan Älvedal

