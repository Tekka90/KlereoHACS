# Klereo Connect — Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

A Home Assistant custom integration (HACS-installable) for the
[Klereo Connect](https://connect.klereo.fr) swimming-pool management system.

It polls the Klereo cloud REST API and exposes:

- **Probe sensors** — temperature, pH, Redox, pressure, flow… (one entity per probe, correct `device_class` and unit auto-assigned from probe type)
- **Params sensors** — filtration/heating run times, chemical consumption, setpoints
- **Enum sensors** — pool mode, disinfectant type, pH corrector type, heater type
- **Alert sensors** — active alert count + human-readable alert descriptions
- **Output switches** — filtration, lighting, electrolysis, heating, auxiliaries…
- **Number entities** — writable setpoints (water temp, pH, Redox, chlorine) and timer delays
- **Select entity** — variable-speed pump speed (when supported by the pool hardware)

All entities are configured through the HA UI — no YAML required.

---

## Prerequisites

- A [Klereo Connect](https://connect.klereo.fr) account
- A Klereo-compatible pool controller (Klereo Care, Premium, Kompact, or Kalypso Pro)
- The controller must be connected to the Klereo cloud (internet access required)
- Home Assistant 2024.1 or newer

---

## Installation

### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations → Custom repositories**
3. Add `https://github.com/Tekka90/KlereoHACS` with category **Integration**
4. Search for **Klereo** and click **Download**
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration → Klereo Connect**
7. Enter your Klereo username and password — your pools are discovered automatically
8. Select your pool from the dropdown and click **Submit**

### Manual installation

1. Copy the `klereo/` folder into your `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration → Klereo Connect**

---

## Configuration

All configuration is done through the UI. After adding the integration:

1. **Step 1 — Credentials**: Enter your Klereo username and password. The integration
   authenticates against `GetJWT.php` and fetches your pool list from `GetIndex.php`.
2. **Step 2 — Pool selection**: Choose your pool from the dropdown (shows
   `poolNickname (idSystem)` for each pool on your account).

No YAML configuration is required or supported.

---

## Exposed Entities

### Probe sensors

One sensor is created per probe returned by `GetPoolDetails`. The `device_class` and unit
are assigned automatically from the probe's `type` field:

| `probe.type` | Meaning | `device_class` | Unit |
|---|---|---|---|
| 0 | Tech room temperature | `temperature` | °C |
| 1 | Air temperature | `temperature` | °C |
| 2 | Water level | — | % |
| 3 | pH | `ph` | *(none)* |
| 4 | Redox / ORP | `voltage` | mV |
| 5 | Water temperature | `temperature` | °C |
| 6 | Filter pressure | `pressure` | mbar |
| 10 | Generic | — | % |
| 11 | Flow rate | — | m³/h |
| 12 | Tank level | — | % |
| 13 | Cover / curtain position | — | % |
| 14 | Chlorine | — | mg/L |

Each probe sensor also exposes `filteredTime` and `type` as extra state attributes.

### Params sensors (numeric)

Derived from `GetPoolDetails` → `params`. Each sensor is **only created if the
corresponding data is present** in the API response, so pools without heating or
electrolysis will simply not have those sensors.

| Entity name | Source field(s) | Unit | `state_class` |
|---|---|---|---|
| Filtration Today | `Filtration_TodayTime` ÷ 3600 | h | `total_increasing` |
| Filtration Total | `Filtration_TotalTime` ÷ 3600 | h | `total_increasing` |
| pH- Consumed Today | `PHMinus_TodayTime × PHMinus_Debit ÷ 36` | mL | `total_increasing` |
| pH- Consumed Total | `PHMinus_TotalTime × PHMinus_Debit ÷ 36000` | L | `total_increasing` |
| Chlorine Production Today | `Elec_GramDone ÷ 1000` | g | `total_increasing` |
| Liquid Chlorine Consumed Today | `ElectroChlore_TodayTime × Chlore_Debit ÷ 36` | mL | `total_increasing` |
| Liquid Chlorine Consumed Total | `ElectroChlore_TotalTime × Chlore_Debit ÷ 36000` | L | `total_increasing` |
| Heating Today | `Chauff_TodayTime` ÷ 3600 | h | `total_increasing` |
| Heating Total | `Chauff_TotalTime` ÷ 3600 | h | `total_increasing` |
| Heating Setpoint | `ConsigneEau` | °C | `measurement` |
| pH Setpoint | `ConsignePH` | *(none)* | `measurement` |
| Redox Setpoint | `ConsigneRedox` | mV | `measurement` |
| Chlorine Setpoint | `ConsigneChlore` | mg/L | `measurement` |

### Params sensors (enum / string)

Also derived from `params`. Only created when the key is present in the API response.

| Entity name | `params` key | Possible values |
|---|---|---|
| Pool Mode | `PoolMode` | Off, Eco, Comfort, Winter, Install |
| Disinfectant Type | `TraitMode` | None, Liquid chlorine, Electrolyser, KL1, Active oxygen, Bromine, KL2, KL3 |
| pH Corrector Type | `pHMode` | None, pH-Minus, pH-Plus |
| Heater Type | `HeaterMode` | None, ON/OFF heat pump, EasyTherm, ON/OFF no setpoint, Other heat pump |

### Output switches

One switch per output returned by `GetPoolDetails`. Outputs are named `klereo<poolid>out<n>`.

| Index | Output |
|---|---|
| 0 | Lighting |
| 1 | Filtration |
| 2 | pH corrector |
| 3 | Disinfectant / Electrolysis |
| 4 | Heating |
| 5–7 | Auxiliary 1–3 |
| 8 | Flocculant |
| 9–14 | Auxiliary 4–9 |
| 15 | Hybrid disinfectant |

The `is_on` state reflects `out['status'] != 0`, meaning the switch reports **on** for both
manually-forced (`status=1`) and schedule/timer-driven (`status=2`) outputs. An output
running on a time-slot schedule will correctly show as on even though no manual command
was issued.

Each switch also exposes the following extra state attributes:

| Attribute | Type | Example | Description |
|---|---|---|---|
| `Mode` | int | `1` | Raw mode code from the API |
| `control_mode` | string | `time_slots` | Human-readable operating mode (see table below) |
| `Status` | int | `2` | Raw status code from the API |
| `status_reason` | string | `auto` | Human-readable status (`off` / `on` / `auto`) |
| `RealStatus` | int | `1` | Physical relay state reported by the controller |
| `Type` | int | `1` | Output type code |
| `Time` | int | `1712000000` | Epoch timestamp of last change |
| `offDelay` | int | `60` | Current timer auto-off delay in minutes (timer-capable outputs only) |
| `schedule` | list | `["08:00-10:00", "18:00-20:00"]` | Active periods decoded from the time-slot schedule |

**`control_mode` values:**

| Value | Meaning |
|---|---|
| `manual` | Output forced on/off by the user |
| `time_slots` | Running according to a programmed schedule |
| `timer` | Running for a fixed duration |
| `regulation` | Controlled by a regulation loop (pH, Redox…) |
| `clone` | Mirrors another output |
| `pulse` | Pulse mode |
| `auto` | PLC / automate mode |

**`status_reason` values:**

| Value | Meaning |
|---|---|
| `off` | Output is off |
| `on` | Output is manually forced on |
| `auto` | Output is on because of a schedule, timer, or regulation |

### Number entities — writable setpoints

Writable `number` entities are created for each regulation setpoint that is enabled on your
pool. Writing a value calls `SetParam.php` and waits for confirmation.

| Entity | `params` key | Unit | Step | Access required |
|---|---|---|---|---|
| Heating setpoint | `ConsigneEau` | °C | 0.5 | `access ≥ 10` |
| pH setpoint | `ConsignePH` | — | 0.1 | `access ≥ 16` |
| Redox setpoint | `ConsigneRedox` | mV | 1 | `access ≥ 16` |
| Chlorine setpoint | `ConsigneChlore` | mg/L | 0.1 | `access ≥ 16` |

Min/max bounds are read dynamically from `params` (`EauMin`/`EauMax`, `pHMin`/`pHMax`,
`OrpMin`/`OrpMax`). Entities with sentinel values (−2000 = disabled, −1000 = unknown)
are hidden from HA.

### Number entities — timer delay

For outputs that support Timer mode (`[0, 5, 6, 7, 9, 10, 11, 12, 13, 14]`), a writable
`number` entity controls the auto-off delay (1–600 minutes) via `SetAutoOff.php`.
Setting the delay does **not** activate timer mode — it only changes the duration used
when timer mode is active.

### Select entity — variable-speed pump

When `PumpMaxSpeed > 1` (variable-speed / analogue pump), the filtration switch is
**replaced** by a `select` entity with options: `Off`, `Speed 1`, …, `Full speed`.
The number of speed options is determined entirely by `PumpMaxSpeed` from the API.
Selecting a speed calls `SetOut.php` with `newState=<speed index>`.

### Alert sensors

| Entity | Description |
|---|---|
| Alert Count | Number of currently active alerts (integer) |
| Active Alerts | Human-readable description of all active alerts joined by ` \|\| ` |

Alert data comes from the `alerts[]` array in `GetIndex.php` and is updated every
coordinator cycle.

### Pool metadata sensors

| Entity | Source field | Values |
|---|---|---|
| Product | `ProductIdx` | Care/Premium, Kompact M5, Kompact Plus M5, Kalypso Pro Salt, Kompact M9, Kompact Plus M9, Kompact Plus M2 |
| Pump Type | `PumpType` | Generic, KlereoFlô RS485, Pentair, None |
| Electrolyser Range | `isLowSalt` | 5 g/h, 2 g/h |

---

## Klereo API Reference

All endpoints: `https://connect.klereo.fr/php/`  
All requests: `POST`, `Content-Type: application/x-www-form-urlencoded`  
Authentication: `Authorization: Bearer <jwt>` header on all requests after login

### Authentication — `GetJWT.php`

```
POST /GetJWT.php

login=<username>
password=<sha1_of_password>    ← SHA-1 hash of the plain-text password
version=100-HA
app=api
```

Response:
```json
{
  "status": "ok",
  "jwt": "eyJ...",    ← use this — valid for 60 minutes
  "token": "...",     ← deprecated, do not use
  "access": 10        ← 5=read-only, 10=end-user, 20=pro, 25+=Klereo staff
}
```

> The password must be SHA-1 hashed: `echo -n "mypassword" | openssl sha1`

### Pool list — `GetIndex.php`

```
POST /GetIndex.php
Authorization: Bearer <jwt>
```

Returns all pools for the authenticated account. Each entry contains:
- `idSystem` — unique pool ID (use this as `poolID` in all other calls)
- `poolNickname` — display name
- `probes[]` — array of sensor readings
- `EauCapteur`, `pHCapteur`, `TraitCapteur`, `PressionCapteur` — probe indices for water
  temperature, pH, disinfectant (Redox), and pressure respectively
- `outs[]` — array of output/relay states

### Pool detail — `GetPoolDetails.php`

```
POST /GetPoolDetails.php
Authorization: Bearer <jwt>

poolID=<idSystem>
lang=fr
```

Same response structure as `GetIndex` plus full `outs[]` detail. This is the endpoint
polled by the coordinator every 5 minutes.

**Probe fields:**

| Field | Description |
|---|---|
| `index` | Probe index (used to match `EauCapteur` etc.) |
| `filteredValue` | Smoothed measurement — **use this for display** |
| `directValue` | Raw instantaneous measurement |
| `filteredTime` | Seconds since `filteredValue` was recorded |
| `directTime` | Seconds since `directValue` was recorded |

**Output (`outs[]`) fields:**

| Field | Description |
|---|---|
| `index` | Output index (0–15, see table below) |
| `mode` | Current operating mode (0=manual, 1=time_slots, 2=timer, 3=regulation, 9=auto…) |
| `status` | Current state: `0`=off, `1`=on (manual), `2`=auto (running on schedule/timer/regulation) |
| `realStatus` | Physical relay state as reported by the controller hardware |
| `updateTime` | Epoch timestamp of last change |

> **Note:** `is_on` is derived from `status != 0`. An output running on a schedule reports
> `status=2` (auto) — this is correctly treated as on. `realStatus` is exposed as an extra
> attribute but is **not** used to determine the HA switch state.

### Control an output — `SetOut.php`

```
POST /SetOut.php
Authorization: Bearer <jwt>

poolID=<idSystem>
outIdx=<output_index>
newMode=<mode>
newState=<state>
comMode=1
```

**Output indices:**

| Index | Output |
|---|---|
| 0 | Lighting |
| 1 | Filtration |
| 2 | pH corrector *(Pro — `newMode` N/A)* |
| 3 | Disinfectant / Electrolysis *(Pro — `newMode` N/A)* |
| 4 | Heating *(`newMode` N/A)* |
| 5–7 | Auxiliary 1–3 |
| 8 | Flocculant *(Pro — `newMode` N/A)* |
| 9–14 | Auxiliary 4–9 |
| 15 | Hybrid disinfectant *(Pro — `newMode` N/A)* |

**`newMode` values** *(not applicable for outputs 2, 3, 4, 8, 15):*

| Value | Mode |
|---|---|
| 0 | Manual |
| 1 | Time slots (schedule) |
| 2 | Timer |
| 3 | Regulated |
| 4 | Sync with filtration |
| 6 | Maintenance |
| 8 | Pulse |
| 9 | PLC / Automate |

**`newState` values:**

| Value | State |
|---|---|
| 0 | Off |
| 1 | On |
| 2 | Auto |

Response includes `cmdID` which can be used to verify execution.

### Command status — `WaitCommand.php` / `CommandStatus.php`

```
POST /WaitCommand.php      ← blocks until command completes
POST /CommandStatus.php    ← returns immediately

cmdID=<cmdID>
```

Status codes in response `response[].status`:
`0`=pending, `1`=running, `9`=✅ success, `10`=❌ failed, `13`=❌ access denied,
`17`=❌ pool not connected, `19`=❌ firmware update required.

### Alternative: REST sensors in `configuration.yaml`

For simple read-only setups without this component, Klereo sensors can be added directly
to Home Assistant as REST sensors:

```yaml
sensor:
  # Klereo JWT token — refresh every 50 minutes (token valid 60 min)
  # Password must be SHA-1 encoded: echo -n "MYPASSWORD" | openssl sha1
  - platform: rest
    name: KlereoToken
    scan_interval: 3000
    resource: https://connect.klereo.fr/php/GetJWT.php
    method: POST
    headers:
      Content-Type: "application/x-www-form-urlencoded; charset=UTF-8"
    payload: "login=USERNAME&password=SHA1PASSWORD&version=100-HA&app=api"
    value_template: "{{ value_json.token }}"
    json_attributes:
      - jwt

rest:
  - resource: https://connect.klereo.fr/php/GetIndex.php
    scan_interval: 300
    headers:
      Authorization: "Bearer {{ state_attr('sensor.klereotoken', 'jwt') }}"
    sensor:
      - name: "Klereo Air Temperature"
        unique_id: klereo_air_temperature
        value_template: "{{ value_json.response[0].probes[0].filteredValue }}"
        device_class: temperature
        unit_of_measurement: "°C"
      - name: "Klereo Water Temperature"
        unique_id: klereo_water_temperature
        value_template: "{{ value_json.response[0].probes[1].filteredValue }}"
        device_class: temperature
        unit_of_measurement: "°C"
      - name: "Klereo pH"
        unique_id: klereo_ph
        value_template: "{{ value_json.response[0].probes[2].filteredValue }}"
        device_class: ph
      - name: "Klereo Redox"
        unique_id: klereo_redox
        value_template: "{{ value_json.response[0].probes[3].filteredValue }}"
        device_class: voltage
        unit_of_measurement: "mV"
```

---

## Development & Testing

The project uses `pytest` with a local `.venv`. All test dependencies are in
`requirements-test.txt`.

```bash
# First-time setup (creates venv, installs deps, copies HA stub into site-packages)
bash setup_test_env.sh

# Run unit tests (no network, no credentials needed)
.venv/bin/pytest tests/unit/

# Run live read-only API tests (validates real API responses, sends NO commands)
cp .env.example .env     # fill in KLEREO_USERNAME / KLEREO_PASSWORD / KLEREO_POOLID
.venv/bin/pytest tests/live/

# Run everything
.venv/bin/pytest
```

### Test layout

| Path | What it covers |
|---|---|
| `tests/unit/test_klereo_api.py` | All `KlereoAPI` methods — HTTP payloads, auth header, SHA-1 hashing, JWT auto-refresh, error handling |
| `tests/unit/test_sensor.py` | `KlereoFilteredSensor`, `KlereoDirectSensor`, `KlereoParamSensor`, `KlereoEnumSensor` — `native_value`, `unique_id`, `device_info`, probe type map, `IORename` overrides, alert sensors, diagnostic sensors |
| `tests/unit/test_switch.py` | `KlereoOut` — `is_on` (manual, auto/schedule, off), `control_mode`, `status_reason`, `device_info`, `async_turn_on/off` |
| `tests/live/test_api_live.py` | Real API — `GetJWT`, `GetIndex`, `GetPoolDetails` structure, setpoint sanity checks |
| `tests/fixtures.py` | Shared sample API response dicts used by unit tests |

Live tests are **automatically skipped** when credentials are absent — CI is always green
without a `.env` file.

---

## Todo / Roadmap

See [`TODO.md`](./TODO.md) for the full prioritised list of bugs, improvements, and
planned features (including features inspired by the Jeedom Klereo plugin).

---

## Known Limitations

- **Cloud polling only** — all data comes from the Klereo cloud API. Local/LAN access is
  not supported by the Klereo hardware.
- **5-minute update interval** — entities reflect the state as of the last API poll.
  There is no push/webhook mechanism.
- **Maintenance windows** — the Klereo API server is offline for short windows each night
  (Sunday 01:45–04:45, Mon–Sat 01:30–01:35 except Monday). Entities will become
  unavailable during these windows and recover automatically afterwards.
- **Time-slot schedules are read-only** — the `schedule` attribute decodes the current
  programmed schedule for display. Writing schedules back requires a `SetPlan` endpoint
  that is not yet documented by Klereo.
- **Pro outputs** (pH corrector, disinfectant, flocculant, hybrid disinfectant) require
  `access ≥ 20` (professional account) to control.
- **pH/Redox/Chlorine setpoints** require `access ≥ 16` to write.

---

## Disclaimer

This integration is provided **as-is**, without any warranties or guarantees of any kind.
Klereo and its developers cannot be held responsible for any damage, malfunction, or issues
arising from the installation or usage of this integration.

Use at your own risk. Back up your Home Assistant configuration before installing.
This integration is community-driven and is **not officially endorsed or supported by Klereo**.

---

## Acknowledgements

- [Laurent Dousset (@ldousset-klr)](https://github.com/ldousset-klr/KlereoHACS) — original
  KlereoHACS integration that this project is forked from
- [MrWaloo / jeedom-klereo](https://github.com/MrWaloo/jeedom-klereo) — Jeedom plugin whose
  source code documented many undiscovered API endpoints and edge cases used in this integration


