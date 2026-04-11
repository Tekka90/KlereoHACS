# GitHub Copilot Instructions — KlereoHACS

## Project Overview

**KlereoHACS** is a Home Assistant custom integration (HACS-installable) for the
[Klereo Connect](https://connect.klereo.fr) swimming-pool management system.  
It polls the Klereo cloud REST API to expose pool **sensors** (probes) and **switches**
(output relays) as first-class Home Assistant entities, configured via a UI config flow.

- **HA domain**: `klereo` (defined in `const.py` and `manifest.json`)
- **HACS repo**: `Tekka90/KlereoHACS`  
- **Cloud endpoint**: `https://connect.klereo.fr/php`
- **IoT class**: `cloud_polling` — all data comes from Klereo servers, never local
- **Platforms**: `sensor`, `switch`

---

## File Map

| File | Role |
|---|---|
| `manifest.json` | Integration metadata, declares `requests` as a pip dependency |
| `const.py` | All constants: domain, API base URL, config keys, update interval |
| `__init__.py` | Entry-point: sets up `KlereoAPI`, creates `DataUpdateCoordinator`, forwards to platforms |
| `klereo_api.py` | Thin synchronous HTTP wrapper around the Klereo REST API |
| `config_flow.py` | UI config flow — collects username, password, poolID |
| `sensor.py` | One `KlereoSensor` (`CoordinatorEntity`) per probe returned by `GetPoolDetails` |
| `switch.py` | One `KlereoOut` (`CoordinatorEntity + SwitchEntity`) per output returned by `GetPoolDetails` |

---

## Klereo REST API Reference

All endpoints are under `https://connect.klereo.fr/php/`.  
All `POST` bodies are `application/x-www-form-urlencoded`.  
After login, every request must carry `Authorization: Bearer <jwt>` in the header.

### 1 — Authentication: `GetJWT.php`

```
POST /GetJWT.php
Content-Type: application/x-www-form-urlencoded

login=<username>
password=<sha1_of_password>   ← plain-text password hashed with SHA-1
version=<client_version>       ← use "100-HA" for this integration
app=api
```

**Response JSON:**
```json
{
  "status": "ok",
  "token": "...",     // deprecated — do NOT use
  "jwt": "...",       // ← use this; valid for 60 minutes
  "access": 10,       // 5=read-only, 10=end-user, 20=pro, 25+=Klereo staff
  "id": 2             // ignorable
}
```

> ⚠️ **JWT lifetime is 60 minutes.** The coordinator polls every 5 minutes (`UPDATE_INTERVAL = 300`).
> The current implementation re-uses the JWT until a request fails, then re-authenticates.
> A proactive refresh before the 60-minute expiry would be more robust (see TODO below).

> ⚠️ The password **must** be SHA-1 hashed before sending. `KlereoAPI.hash_password()` handles this
> via `hashlib.sha1(password.encode()).hexdigest()`. Never send the plain-text password.

---

### 2 — Pool list: `GetIndex.php`

```
POST /GetIndex.php
Authorization: Bearer <jwt>
```

Returns all pools associated with the account. Used to discover `idSystem` (poolID) during
setup (currently the user must enter it manually — improving this is a known TODO).

**Response JSON structure (abbreviated):**
```json
{
  "status": "ok",
  "response": [
    {
      "idSystem": 12345,        // ← the poolID needed for all other calls
      "poolNickname": "Ma piscine",
      "podSerial": "POD-XXXX",
      "device": 0,
      "pin": "1234",
      "access": 10,
      "probes": [
        {
          "index": 0,           // probe index — used to identify the sensor
          "directValue": 26.5,
          "directTime": 45,     // seconds since last measurement
          "filteredValue": 26.3,// ← preferred value (filtered/smoothed)
          "filteredTime": 45
        }
      ],
      "EauCapteur": 1,          // probe index of the main water temperature sensor
      "pHCapteur": 2,           // probe index of the main pH sensor
      "TraitCapteur": 3,        // probe index of the main disinfectant (Redox) sensor
      "PressionCapteur": 4      // probe index of the main pressure sensor
    }
  ]
}
```

---

### 3 — Pool detail: `GetPoolDetails.php`

```
POST /GetPoolDetails.php
Authorization: Bearer <jwt>

poolID=<idSystem>
lang=fr
```

Returns the same structure as `GetIndex`, plus full `outs[]` (output/relay) data.  
This is the endpoint polled by the `DataUpdateCoordinator` every `UPDATE_INTERVAL` seconds.

**`outs[]` array fields:**
```json
{
  "index": 1,         // output index (0–15, see Output Index table below)
  "type": 1,
  "mode": 1,          // current operating mode (0–9, see Mode table below)
  "status": 1,        // desired state: 0=off, 1=on, 2=auto
  "realStatus": 1,    // actual relay state
  "updateTime": 1712000000  // epoch timestamp of last update
}
```

---

### 4 — Control an output: `SetOut.php`

```
POST /SetOut.php
Authorization: Bearer <jwt>

poolID=<idSystem>
outIdx=<output_index>
newMode=<mode>
newState=<state>
comMode=1           ← always 1
```

**Output indices (`outIdx`):**

| Index | Output |
|---|---|
| 0 | Lighting |
| 1 | Filtration |
| 2 | pH corrector *(Pro — mode field N/A)* |
| 3 | Disinfectant / Electrolysis *(Pro — mode field N/A)* |
| 4 | Heating *(mode field N/A)* |
| 5 | Auxiliary 1 |
| 6 | Auxiliary 2 |
| 7 | Auxiliary 3 |
| 8 | Flocculant *(Pro — mode field N/A)* |
| 9–15 | Auxiliary 4–9 / Hybrid disinfectant |

> ⚠️ For outputs **2, 3, 4, 8, 15** the `newMode` field is **not applicable**.
> Only `newState` matters for those outputs.

**`newMode` values (ignored for outputs 2, 3, 4, 8, 15):**

| Value | Mode |
|---|---|
| 0 | Manual |
| 1 | Time slots (schedule) |
| 2 | Timer |
| 3 | Regulated |
| 4 | Sync with filtration |
| 6 | Maintenance |
| 8 | Pulse |
| 9 | PLC/Automate |
| 5, 7 | ⛔ Internal use — do NOT use |

**`newState` values:**

| Value | State |
|---|---|
| 0 | Off |
| 1 | On |
| 2 | Auto |

The current integration always uses `newMode=2` (Timer) when turning on/off. This sets the
output to manual timer mode — **not** automatic. This is intentional for HA control.

**Response:**
```json
{
  "status": "ok",
  "response": [{ "cmdID": 42, "poolID": 12345 }]
}
```

---

### 5 — Set a regulation parameter: `SetParam.php`

> ⚠️ This endpoint was discovered from the Jeedom plugin — it is **not** in the original Klereo
> API doc shared by Klereo. It is implemented in Jeedom and works in practice.

```
POST /SetParam.php
Authorization: Bearer <jwt>

poolID=<idSystem>
paramID=<param_name>   ← e.g. "ConsigneEau", "ConsignePH", "ConsigneRedox", "ConsigneChlore"
newValue=<float>
comMode=1
```

Returns `cmdID` — verify with `WaitCommand`. Access level gates:
- `ConsigneEau` (water/heating setpoint): requires `access >= 10`
- `ConsignePH`, `ConsigneRedox`, `ConsigneChlore`: require `access >= 16`

---

### 6 — Set output auto-off timer: `SetAutoOff.php`

> ⚠️ Also discovered from the Jeedom plugin — not in the original Klereo API doc.

```
POST /SetAutoOff.php
Authorization: Bearer <jwt>

poolID=<idSystem>
outIdx=<output_index>
offDelay=<minutes>     ← 1–600 minutes
comMode=1
```

Sets the timer duration for outputs that support Timer mode (outputs 0, 5–7, 9–14).
Returns `cmdID` — verify with `WaitCommand`.

---

### 7 — Command status: `WaitCommand.php` / `CommandStatus.php`

```
POST /WaitCommand.php        ← blocks until done
POST /CommandStatus.php      ← returns immediately

cmdID=<cmdID>               ← returned by SetOut
```

**Command status codes in response:**

| Code | Meaning |
|---|---|
| 0 | Pending |
| 1 | Executing |
| 9 | ✅ Success |
| 10 | ❌ Command failed |
| 11 | ❌ Bad parameters |
| 12 | ❌ Unknown command |
| 13 | ❌ Insufficient access rights |
| 15 | ❌ Execution timeout |
| 17 | ❌ Pool not connected |
| 18 | ❌ Service unavailable |
| 19 | ❌ Firmware update required |

> The current integration does **not yet call** `WaitCommand` / `CommandStatus` after `SetOut`.
> The switch state is optimistically updated in HA immediately. Adding command verification
> is a desirable improvement.

---

## Data Flow

```
HA startup / reload
      │
      ▼
async_setup_entry()
      │
      ├─ KlereoAPI(username, password, poolid)
      │
      └─ DataUpdateCoordinator (every 300 s)
               │
               ▼
         KlereoAPI.get_pool()
               │
               ├─ if no JWT → GetJWT.php (SHA-1 password, returns jwt)
               │
               └─ GetPoolDetails.php (poolID, lang=fr)
                        │
                        ├─ pool['probes'] → KlereoSensor entities (one per probe)
                        └─ pool['outs']   → KlereoOut entities (one per output)
```

---

## Entity Naming Convention

Entities are named by the current code as:

- **Sensors**: `klereo<poolid>probe<probe_index>` — e.g. `klereo12345probe2`
- **Switches**: `klereo<poolid>out<out_index>` — e.g. `klereo12345out3`

> ⚠️ **Known limitation**: probes and outputs are named generically by index.
> The Klereo API provides `poolNickname` and the `EauCapteur` / `pHCapteur` /
> `TraitCapteur` / `PressionCapteur` fields which map probe indices to their semantic role.
> These should be used to assign meaningful `device_class`, `unit_of_measurement`, and
> human-readable names. This is a top TODO item.

**Probe type → sensor mapping (`probe['type']` field from `GetPoolDetails`):**

The `probe['type']` field is the authoritative source for how to display a probe.
The `EauCapteur` / `pHCapteur` / `TraitCapteur` / `PressionCapteur` fields from `GetPoolDetails`
are index pointers to the *primary* probe for each regulated parameter — useful for labelling.

| `type` | Semantic | HA `device_class` | Unit |
|---|---|---|---|
| 0 | Tech room temperature | `temperature` | `°C` |
| 1 | Air temperature | `temperature` | `°C` |
| 2 | Water level | — | `%` |
| 3 | pH only | `ph` | *(none)* |
| 4 | Redox / ORP only | `voltage` | `mV` |
| 5 | Water temperature | `temperature` | `°C` |
| 6 | Filter pressure | `pressure` | `mbar` |
| 10 | Generic | — | `%` |
| 11 | Flow | — | `m³/h` |
| 12 | Tank level | — | `%` |
| 13 | Cover / curtain position | — | `%` |
| 14 | Chlorine | — | `mg/L` |

**Additional `probe` fields returned by the API:**
- `seuilMin` / `seuilMax` — configured alert thresholds (−2000 = disabled, −1000 = unknown)
- `index` — probe index (also used as the key in `IORename[]`)

**`details['IORename']`** — user-defined custom names for probes and outputs:
```json
{ "ioType": 2, "ioIndex": 1, "name": "My air sensor" }  // ioType 2 = probe
{ "ioType": 1, "ioIndex": 3, "name": "Electrolysis" }   // ioType 1 = output
```
When present, the custom name should override the type-based default name.

**`details['params']`** — pool regulation parameters (a flat key/value object). Key parameters:

| Key | Description | Notes |
|---|---|---|
| `Filtration_TodayTime` | Today's filtration run time (s) | ÷3600 for hours |
| `Filtration_TotalTime` | Total filtration run time (s) | ÷3600 for hours |
| `PHMinus_TodayTime`, `PHMinus_Debit` | pH- pump runtime + flow rate | `time × debit ÷ 36` = mL |
| `PHMinus_TotalTime` | Total pH- runtime | `time × debit ÷ 36000` = L |
| `Elec_GramDone` | Daily chlorine produced by electrolysis (mg) | ÷1000 for grams |
| `ElectroChlore_TodayTime`, `Chlore_Debit` | Chlorine pump runtime + flow | `time × debit ÷ 36` = mL |
| `ElectroChlore_TotalTime` | Total chlorine pump runtime | `time × debit ÷ 36000` = L |
| `Chauff_TodayTime` | Today's heating run time (s) | ÷3600 for hours |
| `Chauff_TotalTime` | Total heating run time (s) | ÷3600 for hours |
| `PoolMode` | Pool regulation mode | 0=Off,1=Eco,2=Comfort,4=Winter,5=Install |
| `TraitMode` | Disinfectant type | 0=None,1=LiqCl,2=Electrolyser,3=KL1,4=O2,5=Br,6=KL2,8=KL3 |
| `pHMode` | pH corrector type | 0=None,1=pH-Minus,2=pH-Plus |
| `HeaterMode` | Heater type | 0=None,1=ON/OFF PAC,2=EasyTherm,3=ON/OFF no setpoint,4=Other |
| `ConsigneEau` | Heating/water setpoint (°C) | −2000=disabled, −1000=unknown |
| `ConsignePH` | pH regulation setpoint | −2000=disabled, −1000=unknown |
| `ConsigneRedox` | Redox regulation setpoint (mV) | −2000=disabled, −1000=unknown |
| `ConsigneChlore` | Chlorine setpoint (mg/L) | −2000=disabled, −1000=unknown |
| `EauMin`/`EauMax` | Valid range for water setpoint | Used as slider bounds |
| `pHMin`/`pHMax` | Valid range for pH setpoint | |
| `OrpMin`/`OrpMax` | Valid range for Redox setpoint | |

**`details['HybrideMode']`** — when `=== 1`, the pool uses hybrid electrolysis + liquid chlorine;
use `details['ExtraParams']['HybChl_TodayTime']` / `HybChl_TotalTime` instead of `ElectroChlore_*`.

**`details['PumpMaxSpeed']`** — when `> 1`, the filtration pump is a variable-speed analogue pump;
the `newState` value in `SetOut` for output 1 should be the target speed (0–PumpMaxSpeed),
not a boolean 0/1.

**`details['plans']`** — array of `{index, plan64}`. `plan64` is a base64-encoded 96-bit schedule
(one bit per 15-minute slot over 24 hours). To decode: base64-decode → unpack hex nibbles →
reverse each nibble's bit order → 96 booleans.

**`pool['alerts']`** — array of `{code, param}` alert objects from `GetIndex`. 62 alert codes
defined (0–61). Full code→message table available in `jeedom-klereo/core/class/klereo.class.php`
`actualizeValues()` method.

> ⚠️ All probes currently use `device_class: "temperature"` and `unit_of_measurement: "°C"`.
> This is **incorrect** for pH and Redox probes. This is a known bug to fix.

---

## Known Bugs & TODOs

See `TODO.md` for the full prioritised list. Summary:

| # | Priority | File | Description |
|---|---|---|---|
| B1 | 🔴 High | `sensor.py` | All probes use `device_class="temperature"` and `unit_of_measurement="°C"` — must use `probe['type']` to assign correct class/unit per probe |
| B2 | 🔴 High | `klereo_api.py` | `get_index()` logs undefined `sensors` — `NameError` at runtime |
| B3 | 🟠 Medium | `klereo_api.py` | JWT never proactively refreshed — expires after 60 min idle |
| B4 | 🟠 Medium | `switch.py` | `async_turn_on/off` never calls `WaitCommand` — no error handling if pool rejects the command |
| B5 | 🟠 Medium | `config_flow.py` | `_test_credentials()` is a no-op — invalid credentials pass silently |
| B6 | 🟡 Low | `sensor.py` | Generic index-based entity names — should use `probe['type']` + `IORename` |
| B7 | 🟡 Low | `config_flow.py` | Pool ID entered manually — should be a dropdown from `GetIndex.php` |
| B8 | 🟡 Low | `klereo_api.py` | `set_device_mode()` not implemented |
| B9 | 🟡 Low | `__init__.py` | No `coordinator.async_shutdown()` in `async_unload_entry` |
| B10 | 🟡 Low | `klereo_api.py` | `SetOut` always uses `newMode=2` (Timer) — should restore previous mode or use Manual |

---

## Coding Conventions

1. **Async boundary**: `KlereoAPI` is a synchronous `requests`-based class. It must always be
   called via `hass.async_add_executor_job(...)` — never `await`ed directly.
2. **Coordinator pattern**: All data reads go through the `DataUpdateCoordinator`. Entities
   must **not** call the API directly for reads — only for writes (turn on/off).
3. **`CoordinatorEntity`**: Both `KlereoSensor` and `KlereoOut` extend `CoordinatorEntity`.
   State properties must read from `self.coordinator.data` — not from cached instance variables.
4. **Constants**: All magic strings and numbers belong in `const.py`. Never inline the domain
   name, server URL, or update interval.
5. **Logging**: Use `LOGGER = logging.getLogger(__name__)` in each module. Use `LOGGER.debug()`
   for per-poll noise, `LOGGER.info()` for setup/teardown, `LOGGER.warning()`/`LOGGER.error()`
   for recoverable/unrecoverable problems.
6. **Error handling**: API calls in `klereo_api.py` should catch `requests.RequestException`
   and raise `homeassistant.exceptions.ConfigEntryAuthFailed` (auth errors) or
   `homeassistant.exceptions.UpdateFailed` (transient errors) so the coordinator handles
   retry and UI error reporting correctly.
7. **`filteredValue` vs `directValue`**: Always use `filteredValue` — it is the smoothed,
   regulation-quality measurement. `directValue` is the raw instantaneous reading.

---

## Additional API Endpoints (from Jeedom plugin)

These endpoints were not in the original Klereo API doc but are used by the Jeedom plugin
and work in practice. They are documented in `TODO.md` with full parameter details.

| Endpoint | Purpose |
|---|---|
| `SetParam.php` | Write a regulation setpoint (`ConsigneEau`, `ConsignePH`, `ConsigneRedox`, `ConsigneChlore`) |
| `SetAutoOff.php` | Set the timer auto-off delay (in minutes) for an output |

Both return a `cmdID` that must be verified with `WaitCommand.php`.

## Server Maintenance Windows

The Klereo API server has scheduled maintenance windows during which it returns
`status: error, detail: maintenance`. The Jeedom plugin defines these windows and skips
all requests during them. KlereoHACS should detect this response and mark entities
as unavailable rather than raising errors:

| Day | Window (local time) |
|---|---|
| Sunday | 01:45 – 04:45 |
| Mon / Tue / Wed / Thu / Sat | 01:30 – 01:35 |

---

## What NOT to Do

- Do **not** call `GetJWT.php` on every poll — only call it when `self.jwt` is `None` or on
  a 401-equivalent error.
- Do **not** use `response.json().get('token')` — the `token` field is deprecated. Use `jwt`.
- Do **not** use `newMode=5` or `newMode=7` in `SetOut` — these are internal Klereo values.
- Do **not** hardcode the pool server URL — always use `KLEREOSERVER` from `const.py`.
- Do **not** add new config keys without also adding them to `const.py` and the config flow
  schema in `config_flow.py`.
- Do **not** store credentials in plain text in HA storage — the config entry stores the
  password as entered; hashing is done at request time in `hash_password()`.
