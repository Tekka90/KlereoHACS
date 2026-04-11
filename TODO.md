# KlereoHACS — TODO / Roadmap

> Items are grouped by priority. Check them off as they are completed.
> Cross-references with bugs listed in `.github/copilot-instructions.md` are noted as **B#**.

---

## 🔴 High Priority — Correctness Bugs

- [x] **[B1] Fix device_class / unit for all probe types**
  - `sensor.py`: every probe currently returns `device_class="temperature"` and
    `unit_of_measurement="°C"`.
  - The `probe['type']` field (or the `EauCapteur` / `pHCapteur` / `TraitCapteur` /
    `PressionCapteur` index fields from `GetPoolDetails`) must be used to assign the correct
    class and unit per probe.
  - Mapping to apply (from Jeedom `getSensorTypes()`):
    | `probe['type']` | Semantic | HA `device_class` | Unit |
    |---|---|---|---|
    | 0 | Tech room temp | `temperature` | `°C` |
    | 1 | Air temperature | `temperature` | `°C` |
    | 2 | Water level | `moisture` / `volume` | `%` |
    | 3 | pH only | `ph` | *(none)* |
    | 4 | Redox/ORP only | `voltage` | `mV` |
    | 5 | Water temperature | `temperature` | `°C` |
    | 6 | Filter pressure | `pressure` | `mbar` |
    | 10 | Generic | — | `%` |
    | 11 | Flow | — | `m³/h` |
    | 12 | Tank level | — | `%` |
    | 13 | Cover/curtain position | — | `%` |
    | 14 | Chlorine | — | `mg/L` |

- [x] **[B2] Fix `NameError` in `get_index()` (`klereo_api.py`)**
  - `LOGGER.info(f"Successfully obtained GetIndex: {sensors}")` — `sensors` is undefined.
  - Replace with `index` (the variable that was just assigned).

- [x] **[B5] Implement `_test_credentials()` in the config flow**
  - Currently a `pass` — invalid username/password silently succeeds during setup.
  - Should call `get_jwt()` (executor job) and raise `InvalidAuth` on failure.

---

## 🟠 Medium Priority — Reliability & Robustness

- [ ] **[B3] Proactive JWT refresh before 60-minute expiry**
  - Currently the JWT is re-acquired only when `self.jwt` is `None` (i.e., on first call after
    startup). If HA runs for more than 60 minutes the token expires silently.
  - Jeedom stores `login_dt` and re-authenticates when within 55 minutes of issue time.
  - Implement the same: store `self.jwt_acquired_at = datetime.now()` and call `get_jwt()`
    again when `(now - jwt_acquired_at) > timedelta(minutes=55)`.

- [ ] **[B4] Add `WaitCommand` / `CommandStatus` verification after `SetOut`**
  - `turn_on_device` and `turn_off_device` call `SetOut.php` but never check the returned
    `cmdID` against `WaitCommand.php`.
  - The switch state is optimistically updated in HA — if the pool controller rejects the
    command (e.g. pool not connected, access denied) the HA state becomes wrong.
  - After `SetOut`, call `WaitCommand` and raise a `HomeAssistantError` if status ≠ 9.
  - Force a coordinator refresh after a successful command so real state is reflected.

- [ ] **[B8] Implement `set_device_mode()` in `KlereoAPI`**
  - Currently an empty stub.
  - Signature: `set_device_mode(self, outIdx, mode, state=2)` — calls `SetOut.php` with
    the chosen `newMode` and `newState=2` (Auto).

- [ ] **Add proper exception handling in `klereo_api.py`**
  - Wrap all `requests.post()` calls in try/except.
  - Raise `homeassistant.exceptions.ConfigEntryAuthFailed` on HTTP 401 / `status: error` +
    auth-related `detail`.
  - Raise `homeassistant.exceptions.UpdateFailed` for all other errors so the coordinator
    marks entities as unavailable instead of crashing.

---

## 🟡 Low Priority — Features & UX

- [ ] **[B6] Use semantic names for sensors and switches**
  - Sensors are currently named `klereo<id>probe<n>` and switches `klereo<id>out<n>`.
  - Use `probe['type']` (mapped via `getSensorTypes`) and the user-configurable rename fields
    from `details['IORename']` (array with `ioType`, `ioIndex`, `name`) if present.
  - Fall back to the type-based name if no custom rename is defined.
  - Output names from `getOutInfo` style mapping:
    `0`=Lighting, `1`=Filtration, `2`=pH corrector, `3`=Disinfectant, `4`=Heating,
    `5–7`=Aux 1–3, `8`=Flocculant, `9–14`=Aux 4–9, `15`=Hybrid disinfectant.

- [ ] **[B7] Auto-discover pool ID via `GetIndex.php` in the config flow**
  - Currently the user must manually enter `poolID` via browser DevTools.
  - After entering username + password, call `GetIndex.php` and present a dropdown selector
    populated with `poolNickname (idSystem)` entries.

- [ ] **Group all entities under a single HA Device per pool**
  - Add a `DeviceInfo` to `KlereoSensor` and `KlereoOut` using `poolNickname` as the device
    name, `idSystem` as the identifier, and `podSerial` as the hardware serial.

- [ ] **Expose `both` `filteredValue` and `directValue` as separate sensor attributes**
  - Currently only `filteredValue` is returned as the state.
  - `directValue` (instantaneous) should be available as an extra state attribute.
  - Already done partially via `extra_state_attributes` — ensure both fields are always present.

- [ ] **[B9] Proper cleanup in `async_unload_entry`**
  - Currently only removes `hass.data[DOMAIN][entry_id]`.
  - Should also call `coordinator.async_shutdown()` to cancel the background update loop.

- [ ] **[B10] Restore original output mode on turn-off instead of always using `newMode=2`**
  - `turn_on_device` / `turn_off_device` always send `newMode=2` (Timer).
  - Should store and restore the previous `mode` from `coordinator.data['outs']`, or default
    to `newMode=0` (Manual) which is safer.

---

## 🔵 New Features (inspired by Jeedom plugin)

These features exist in `jeedom-klereo` but are not yet implemented in KlereoHACS:

- [x] **Expose `params`-based sensors from `GetPoolDetails`**
  The `details['params']` object contains many useful metrics not currently exposed:
  | Param key | Description | Unit |
  |---|---|---|
  | `Filtration_TodayTime` | Today's filtration run time | h (÷3600) |
  | `Filtration_TotalTime` | Total filtration run time | h (÷3600) |
  | `PHMinus_TodayTime` × `PHMinus_Debit` ÷ 36 | pH- consumed today | mL |
  | `PHMinus_TotalTime` × `PHMinus_Debit` ÷ 36000 | pH- consumed total | L |
  | `Elec_GramDone` ÷ 1000 | Daily chlorine production (electrolysis) | g |
  | `ElectroChlore_TodayTime` × `Chlore_Debit` ÷ 36 | Liquid chlorine consumed today | mL |
  | `ElectroChlore_TotalTime` × `Chlore_Debit` ÷ 36000 | Liquid chlorine consumed total | L |
  | `Chauff_TodayTime` | Today's heating run time | h (÷3600) |
  | `Chauff_TotalTime` | Total heating run time | h (÷3600) |
  | `ConsigneEau` | Heating setpoint | °C |
  | `ConsignePH` | pH regulation setpoint | pH |
  | `ConsigneRedox` | Redox regulation setpoint | mV |
  | `ConsigneChlore` | Chlorine regulation setpoint | mg/L |

- [x] **Expose `params`-based string/enum sensors**
  | Param key | Description | Values |
  |---|---|---|
  | `PoolMode` | Pool regulation mode | 0=Off, 1=Eco, 2=Comfort, 4=Winter, 5=Install |
  | `TraitMode` | Disinfectant type | 0=None, 1=Liquid chlorine, 2=Electrolyser, 3=KL1, 4=Active oxygen, 5=Bromine, 6=KL2, 8=KL3 |
  | `pHMode` | pH corrector type | 0=None, 1=pH-Minus, 2=pH-Plus |
  | `HeaterMode` | Heater type | 0=None, 1=ON/OFF heat pump, 2=EasyTherm, 3=ON/OFF no setpoint, 4=Other heat pump |

- [ ] **Implement `SetParam.php` — write regulation setpoints**
  - New API endpoint discovered from Jeedom (not in the original Klereo doc):
    ```
    POST /SetParam.php
    Authorization: Bearer <jwt>

    poolID=<idSystem>
    paramID=<param_name>   e.g. "ConsigneEau", "ConsignePH", "ConsigneRedox", "ConsigneChlore"
    newValue=<float>
    comMode=1
    ```
  - Returns `cmdID` — must be verified with `WaitCommand`.
  - Expose as HA `number` entities (one per setpoint, with min/max from `params['EauMin']`
    / `params['EauMax']` etc.).
  - Access level gates: `ConsigneEau` requires `access >= 10`; pH/Redox/Chlore require
    `access >= 16`.

- [ ] **Implement `SetAutoOff.php` — configure timer delay per output**
  - New API endpoint discovered from Jeedom:
    ```
    POST /SetAutoOff.php
    Authorization: Bearer <jwt>

    poolID=<idSystem>
    outIdx=<output_index>
    offDelay=<minutes>     (1–600)
    comMode=1
    ```
  - Returns `cmdID` — verify with `WaitCommand`.
  - Expose as HA `number` entities for outputs that support Timer mode (0, 5–7, 9–14).

- [ ] **Expose `alerts` and `alertCount` from `GetIndex`**
  - `pool['alerts']` is an array of `{code, param}` objects.
  - Expose `alertCount` as a sensor and `alerts` as a human-readable string sensor using the
    alert code table from `jeedom-klereo/core/class/klereo.class.php`.
  - Full alert code → message mapping is available in the Jeedom source (62 codes, 0–61).

- [ ] **Expose pool metadata sensors**
  - `ProductIdx` — pool product range (0=Care/Premium, 1=Kompact M5, 3=Kompact Plus M5,
    4=Kalypso Pro Salt, 5=Kompact M9, 6=Kompact Plus M9, 7=Kompact Plus M2)
  - `PumpType` — filtration pump type (0=Generic, 1=KlereoFlô RS485, 2=Pentair bus, 7=None)
  - `isLowSalt` — electrolyser range (0=5g/h range, 1=2g/h range)
  - `access` — account access level for this pool

- [ ] **Support variable-speed (analogic) filtration pumps**
  - When `details['PumpMaxSpeed'] > 1`, the filtration output is an analogue pump.
  - In this case expose a `number` entity (0 to `PumpMaxSpeed`) instead of a boolean switch
    for the filtration output, and send the speed value as `newState` in `SetOut`.

- [ ] **Support output `offDelay` attribute**
  - `out['offDelay']` is returned per output — expose as an extra attribute on the switch
    entity, and implement a `number` entity to write it via `SetAutoOff.php`.

- [ ] **Support `IORename` — user-defined probe and output names**
  - `details['IORename']` array: `{ioType: 1|2, ioIndex: n, name: "..."}` (1=output, 2=probe)
  - When present, override the default type-based entity name with the user's custom name.

- [ ] **Expose `plans` (time-slot schedules)**
  - `details['plans']` contains `{index, plan64}` entries — base64-encoded 96-bit schedule
    (one bit per 15-minute slot over 24 hours).
  - Jeedom decodes with `plan2arr()` (unpack nibbles, reverse bit order per nibble).
  - Expose as extra attribute on filtration/aux switch entities at minimum.
  - Writing schedules back via API would require a `SetPlan`-style endpoint (unknown — research needed).

- [ ] **Add API server maintenance window awareness**
  - Jeedom skips all API calls during defined maintenance windows (Sun 01:45–04:45,
    Mon/Tue/Wed/Thu/Sat 01:30–01:35).
  - KlereoHACS should detect `status: error, detail: maintenance` responses and mark entities
    as unavailable rather than erroring, then retry after the window ends.

- [ ] **Handle `HybrideMode` (hybrid disinfection)**
  - `details['HybrideMode'] === 1` indicates a hybrid electrolysis + liquid chlorine system.
  - In this mode use `ExtraParams['HybChl_TodayTime']` / `HybChl_TotalTime` instead of the
    regular `ElectroChlore_*` params for chlorine consumption sensors.

---

## ✅ Done

- [x] Basic JWT authentication (`GetJWT.php`)
- [x] Pool detail polling via `GetPoolDetails.php` every 5 minutes
- [x] Probe sensors exposed as HA entities
- [x] Output switches exposed as HA entities with on/off control via `SetOut.php`
- [x] UI config flow (username, password, poolID)
- [x] HACS-compatible structure with `manifest.json`
