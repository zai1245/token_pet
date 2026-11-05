## 📋 Code Review Report

**File(s) reviewed:** `emojinoko_monitor.py`, `emojinoko_game.py`, `usage_widget.py`, `unity_renderer_bridge.py`, `tokenpet_github_updater.py`, Unity runtime scripts, launcher and package/publish tools.

**Rules applied:** general best practices + `.agents/AGENTS.md`. No `REVIEW_RULES.md` exists. No PyInstaller build was performed, so the legacy server deployment rule does not apply.

**Overall verdict:** ⚠️ Minor issues — identified application defects are fixed and validated (2026-11-05). Live company-service acceptance and credential revocation remain external actions.

### 🔴 Critical Issues

All entries below were fixed in v0.8.10-preview. Locations refer to commit `a643cac`; the physics follow-up is recorded below.

- **Missing XP reward methods** — `emojinoko_monitor.py:3778`. Fruit/slot wins and lollipop purchases could crash. **Suggested fix (implemented):** shared multi-level XP settlement.
- **Concurrent save corruption / lost settings** — `config_store.py:15`, `config_store.py:86`. Pet, statistics and login writes could overwrite each other or truncate JSON. **Suggested fix (implemented):** cross-process locking, atomic replacement, recovery backup and credential removal from both copies.
- **Remember-password / unbounded relogin** — `usage_widget.py:444`, `usage_widget.py:892`, `emojinoko_monitor.py:2204`. Persistence now follows the checkbox; each refresh allows one relogin and one retry. Invalid data preserves the last valid usage.
- **Usage reward accounting** — `emojinoko_monitor.py:2267`. First usage after zero could be skipped; month changes and temporary counter corrections could mis-award rewards. **Suggested fix (implemented):** explicit month/baseline state, high-water counters and fractional coin carry. Offline feeding no longer changes company totals.
- **RPS duplicate payout and cancellation loss** — `emojinoko_monitor.py:3192`, `emojinoko_monitor.py:3314`. Added round guards and one-time entry refund.
- **Unity RPS board JSON mismatch** — `unity_renderer_bridge.py:200`. Arrays are normalized to newline-separated text before serialization.
- **Lost renderer updates / orphan overlay** — `unity_renderer_bridge.py:89`, `unity_renderer_bridge.py:174`, `TokenPetIpcClient.cs:111`, `TokenPetIpcClient.cs:187`. Failed snapshots remain retryable, socket-start errors retain Canvas fallback, malformed messages are ignored, and parent disconnection exits the renderer.
- **Embedded internal AI credential** — `emojinoko_monitor.py:3365`, `emojinoko_game.py` AI configuration. Removed every literal default and added personal-key configuration. Offline fallbacks now report offline status. See owner action below.

Other repaired defects: sakura hairpin slot mismatch; stale shop buttons; multi-slot bonus handling; memo whitespace/size loss and duplicate windows; animation callbacks after window destruction; F7 conflicts between pet and statistics; 64-bit native desktop/monitor handles; generated accessory sprite leaks (`TokenPetEquipmentController.cs:648`); furniture removal while dragging (`TokenPetFurnitureStage.cs:120`); normal launcher accidentally granting developer economy; update rollback, timeout and offline restart behavior.

### ⚠️ Warnings

- **Credential owner action required:** the previously embedded AI credential must be revoked/rotated by its owner. Removing it from current source does not invalidate old commits, published archives or existing copies. No credential values are reproduced here.
- Company LDAP/monthly usage and internal AI endpoints require live authorized access. Their network/error contracts are tested with controlled responses; live end-to-end authentication has not been asserted in this review.

### 💡 Suggestions

- Retain the regression suite before subsequent releases. Review coverage and build verification are recorded below.

### ✅ What looks good

- Python keeps game state authoritative across both renderers and preserves Canvas fallback.
- The HUD remains compact and shows monthly USD cost, including stale/error status.
- Update archives require a SHA-256 match and path-safe extraction before replacement.

| Functional area | Review and verification |
| --- | --- |
| Login / remember / relogin | Checkbox persistence, incomplete response rejection, one retry, malformed responses, closed-window callbacks |
| Monthly usage / USD HUD | Slow responses, timeout recovery, HTTP errors preserve last known values, all models, 64-bit counts, empty month, month transitions, invalid data |
| Economy / XP / consumables | Multi-level rewards, every food and accessory purchase, equipment bonuses, no duplicate payouts |
| Equipment | Catalog slot parity, sakura head slot, shop button refresh, runtime sprite cleanup |
| Furniture / physics / basketball | All spawn/despawn paths, Unity desktop positions, native monitor handles, throw limits, goal and close paths |
| Memos | UUIDs, whitespace/paste preservation, size and trash restoration, duplicate-window prevention |
| Fruit / slots / RPS | Actual windows, settlement once, cancellation refund, timer cleanup |
| AI chat / settings | Personal key, edited-key connection test, send guard, model fallback and UI-thread callbacks |
| Hotkeys / lifecycle | Separate F7/F8 settings, finite startup wait, child callback cancellation, save on exit |
| Unity IPC / fallback | Snapshot contract, retry after failed send, malformed-command recovery, renderer exit after parent disconnect |
| Updater | Semantic versions, protected local settings, interrupted replacement rollback, parent timeout, offline restart |
| Packaging / release tools | Included settings module, compiled renderer version guard, unittest validation command |

Validation results:

- `python -X utf8 -m unittest discover -s tests -v`: **109 tests passed**, including real Windows Canvas/statistics/Unity window operations. No skipped tests in this environment.
- Recompiled all 14 Unity runtime C# files with Roslyn against the installed Mono-player references, then replaced the local managed assembly. No compile errors. Existing CS0649 warnings concern fields populated by Unity JSON serialization.
- Real Unity runtime test verified the v0.8.10-preview handshake, all catalog accessories/consumables, motion profiles and furniture states, multiline boards, 64-bit counts, malformed-message recovery and clean exit after parent disconnect. No application exceptions or missing accessory errors.
- AST inspection found no unresolved `self.method()` calls in the plain Python application classes.
- Package checks reject a stale compiled renderer and verify ZIP integrity plus all manifest SHA-256 hashes. `config_store.py` and this report are included.

Build limitation: Unity Editor is unavailable on this machine. This preview reuses the existing engine/assets and recompiles its managed scripts; it is not a fresh Unity Editor engine/asset build. No art, scene or imported asset changes were made during this review.

### Follow-up: Canvas throw parity — v0.8.11-preview

The earlier Unity-specific throw tuning did not match the original Canvas feel. It used a 1.5x impulse, recency-weighted velocity sampling, different drag/gravity and reduced floor rebounds. Python could also continue a previous fall while Unity held the pet, and the renderer invented a continuing spin from stale pointer velocity.

- Canvas and Unity now call the same release initializer: 0.016 velocity conversion, 0.8 gravity, 0.995 air drag, the original 550 px/s flick threshold and 0.55 floor restitution.
- Both use the last 120 ms of motion, with a 180 ms pause cancelling a stale flick. Unity keeps a 64-sample ring and double-precision timestamps.
- Pointer grab pauses Python movement. Unity ignores queued position/state commands while held and until it receives the matching release acknowledgement. Click release also returns ownership; late landing animation events cannot cancel a newer throw.
- Unity consumes Canvas angular position and spring scale during flight instead of adding another independent spin/stretch animation. Stationary drops have no added launch impulse or angular velocity.
- Recompiled the local production managed renderer. **121 tests passed**, including a 150-frame Canvas/Unity trajectory comparison through floor impacts and final rest. An isolated native Unity probe passed **10 sampling, ownership and rotation checks**. The test probe is never included in the production assembly.

The native probe test requires an installed Mono player and .NET SDK; otherwise that optional test is skipped. It builds and runs in a temporary runtime copy, leaving the production build untouched.
