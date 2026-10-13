# Tryon Quail Hatchery

Public beta **0.1.0**: a HACS custom integration that prepares the supplied
Pyscript hatch tracker, all 27 helpers, the illustrated dashboard and reusable
card, artwork, JSON storage, and a daily status/milestone notification blueprint.

[Add custom repository to HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=Tryon-Electronics&repository=tryon-quail-hatchery&category=integration)

This is a **custom repository**, not a claim of inclusion in the default HACS
catalog. Package/source and preservation tests pass; the full dashboard and
Pyscript lifecycle still require testing in a live Home Assistant instance.
Use a backup and a test instance for the first community release.

[Branded installation guide (PDF)](docs/installation-guide.pdf)

## What you get

- Active batches, candling/lockdown/hatch dates, progress and egg counts.
- Batch editor, recorded results, archives, lifetime hatch statistics.
- Permanent color/number bird tags, sex/status/notes, duplicate-tag validation.
- Atomic JSON writes, backup of previous data, and legacy-schema migration.
- Mushroom dashboard and reusable YAML card with Browser Mod editor popups.
- Configurable daily status and milestone reminders using your own notify action.
- Safe installer: existing hatch data is never replaced; edited files are preserved.

Helpers belong to Home Assistant configuration, not to the hatch-record JSON.
The bundled `packages/incubator.yaml` creates all 27 helpers in one place.
`batches.json` holds your batch and tag records. The fresh seed is `[]`.
The example database is fictional and is not loaded by default.

## Install with HACS

1. In HACS install **Pyscript**, **Mushroom**, **Auto Entities**, **Card Mod**,
   and **Browser Mod**. Configure Pyscript in Devices & services and enable
   **Allow all imports** because the tracker imports `os` for local JSON files.
   Browser Mod must be configured and its browser connection enabled for popups.
   Follow each dependency's resource/setup instructions; this package does not
   download or configure other people's integrations for you.
2. HACS > menu > Custom repositories: add
   `https://github.com/Tryon-Electronics/tryon-quail-hatchery`, category **Integration**.
   Download **Tryon Quail Hatchery**, then restart Home Assistant so the integration is available.
3. Settings > Devices & services > Add integration > **Tryon Quail Hatchery**.
   Read and confirm the setup screen. The integration writes the bundle files and
   reports any conflicts through a persistent notification.
4. Merge these entries into your existing `configuration.yaml`. Do not add a
   second `homeassistant:` or `lovelace:` block. If packages are already enabled,
   retain the existing include convention; see the migration notes below.

```yaml
homeassistant:
  packages: !include_dir_named packages

lovelace:
  dashboards:
    quail-hatchery:
      mode: yaml
      title: Quail Hatchery
      icon: mdi:egg-easter
      show_in_sidebar: true
      filename: dashboards/quail-hatchery.yaml
```

5. Check Home Assistant configuration, then restart. Open **Quail Hatchery** and
   add a test batch through the dashboard. For a storage dashboard instead, paste
   the full dashboard YAML in its raw configuration editor. You can also paste
   `cards/quail-hatchery-card.yaml` into a Manual card on an existing dashboard.
6. Settings > Automations & scenes > Blueprints: create an automation from
   **Incubator - Daily Status & Milestone Alerts**. Set your notify action(s) and
   preferred time. This is intentionally opt-in; no real phone is preselected.

If you initially configured Pyscript using YAML instead of the UI, configure
`allow_all_imports: true` there instead. Do not mix the two configuration methods.
The tracker is a regular file at `/config/pyscript/incubator.py`; no Pyscript
`apps:` entry is required. Sensors refresh at startup, hourly and after edits.

### Existing hatchery installation

Back up `incubator_data/batches.json`, its backup, helpers and dashboard first.
The canonical helper file is `packages/incubator.yaml`; do not enable a second
copy under another name or leave duplicate UI helpers with the same IDs.
If an existing script/helper file differs, the installer keeps it and stages
the new version as `<filename>.quail-update`. Review and replace it manually
only after backup. Do not run two copies of the incubator script: their services
and sensor IDs would collide. Existing JSON is preserved, even when invalid;
an error must be repaired rather than replaced with an empty database.

For `!include_dir_merge_named packages`, wrap the helper YAML under an
`incubator:` key before use. The shipped file assumes `!include_dir_named`.
For a selected-file package layout, include the helper file using your existing
convention instead of enabling another directory include.

## Installed paths

| Path under `/config/` | Use |
| --- | --- |
| `pyscript/incubator.py` | Tracker services, refresh and JSON persistence |
| `packages/incubator.yaml` | All text/number/select/boolean helpers |
| `dashboards/quail-hatchery.yaml` | Full supplied dashboard |
| `cards/quail-hatchery-card.yaml` | Reusable dashboard section as a YAML card |
| `www/tryon-quail-hatchery/quail-family-bg.png` | Dashboard artwork |
| `blueprints/automation/incubator/incubator_notifications.yaml` | Opt-in alerts |
| `incubator_data/batches.json` | Your live database; created only if absent |
| `incubator_data/batches.backup.json` | Created by Pyscript after valid writes/migration |
| `tryon_quail_hatchery/examples/batches.example.json` | Fictional schema example |
| `tryon_quail_hatchery/automations/incubator_notifications.example.yaml` | Generic automation example |
| `tryon_quail_hatchery/installed-files.json` | Installer hashes and conflict report |

## Notifications

The user-supplied automation referenced a blueprint but did not contain its
implementation. This repository supplies a new distributable blueprint with
the same path and `phone_notification_target` input. It sends the daily summary
and milestones due **today**, once at the chosen time. With daily summaries
disabled, it sends only if candling, lockdown or expected hatch is due. It skips
sending if the data-status sensor reports an error. It is not an environmental
temperature/humidity safety monitor and it does not resend missed past days.

Create the automation through the Blueprint UI, or merge this into your existing
automation list and replace the generic notify name before enabling it:

```yaml
- alias: Incubator - Daily Status & Milestone Alerts
  initial_state: false
  use_blueprint:
    path: incubator/incubator_notifications.yaml
    input:
      phone_notification_target:
        - notify.mobile_app_your_phone
      notification_time: "09:00:00"
      daily_summary: true
```

## Updates and removal

After a HACS update, restart. Installer-owned files that still match the previous
bundle are updated with `.quail-backup` copies; files edited by you are kept with
`.quail-update` replacements. Review updates, check configuration and restart
again if YAML helpers changed. Data files are outside `custom_components` and
are preserved across HACS updates. Do not extract a manual ZIP over live JSON.

Removing the integration intentionally leaves your data and configuration in
place. To stop the tracker, disable your alert automation, remove the dashboard
registration and helper include, then rename the Pyscript file so it no longer
ends in `.py`. Check configuration and restart. Keep the JSON data for recovery.
Only delete files after you have backed them up and intentionally retired the build.

## Development and validation

Run `python -m unittest discover -s tests -v` with PyYAML and Jinja2 available.
The tests cover helper/service completeness, migration and JSON preservation,
installer updates/conflicts, path confinement, blueprint templates and alert behavior.
They use a simulated state/service layer and do not replace a live HA/Pyscript test.

The tracker baseline is the owner-provided `incubator (2).py`. A packaging fix
reads legacy `Survival` before adding the `hatched` default so old data migrates
correctly. The original supplied batch JSON is used only for local validation;
it is not included in the public repository or installation seed.

Primary references: [HACS integration structure](https://hacs.dev/docs/publish/integration/),
[Home Assistant packages](https://www.home-assistant.io/docs/configuration/packages/),
[Pyscript configuration](https://hacs-pyscript.readthedocs.io/en/latest/reference.html),
[Blueprint selectors](https://www.home-assistant.io/docs/blueprint/selectors/).
