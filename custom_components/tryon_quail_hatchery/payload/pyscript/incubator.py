# Tryon Quail Hatchery v0.1.0
# Source: owner-supplied incubator (2).py; legacy Survival migration corrected.
import json
import os
import re

from datetime import datetime, timedelta


# ===============================================================
# CONFIGURATION
# ===============================================================

DATA_DIR = "/config/incubator_data"
DATA_FILE = f"{DATA_DIR}/batches.json"
BACKUP_FILE = f"{DATA_DIR}/batches.backup.json"

DATE_FORMAT = "%Y-%m-%d"

DEFAULT_INCUBATION_DAYS = 18
DEFAULT_LOCKDOWN_DAY = 14
DEFAULT_CANDLE_DAY = 7


# ===============================================================
# QUAIL IDENTIFICATION TAGS
# ===============================================================

TAG_COLOR_INFO = {
    "Red": {"emoji": "🔴", "hex": "#e53935"},
    "Orange": {"emoji": "🟠", "hex": "#fb8c00"},
    "Yellow": {"emoji": "🟡", "hex": "#fdd835"},
    "Green": {"emoji": "🟢", "hex": "#43a047"},
    "Blue": {"emoji": "🔵", "hex": "#1e88e5"},
    "Purple": {"emoji": "🟣", "hex": "#8e24aa"},
    "Pink": {"emoji": "🩷", "hex": "#ec407a"},
    "White": {"emoji": "⚪", "hex": "#eeeeee"},
    "Black": {"emoji": "⚫", "hex": "#212121"},
}

TAG_SEX_OPTIONS = [
    "Unknown",
    "Male",
    "Female",
]

TAG_STATUS_OPTIONS = [
    "Active",
    "Sold",
    "Rehomed",
    "Deceased",
    "Retired",
]

NEW_TAG_OPTION = "➕ Add New Tag"


log.info("INCUBATOR TRACKER LOADED")


# ===============================================================
# FILE HELPERS
# ===============================================================

@pyscript_executor
def write_file_sync(path, content):

    os.makedirs(
        os.path.dirname(path),
        exist_ok=True
    )

    temp_path = f"{path}.tmp"

    with open(
        temp_path,
        "w",
        encoding="utf-8"
    ) as file:
        file.write(content)

    # Atomic replacement reduces the chance of leaving
    # a partially written batches.json file.
    os.replace(
        temp_path,
        path
    )


@pyscript_executor
def read_file_sync(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        return file.read()


@pyscript_executor
def file_exists_sync(path):

    return os.path.exists(path)


# ===============================================================
# DATA FILE
# ===============================================================

async def ensure_file():

    exists = await file_exists_sync(
        DATA_FILE
    )

    if not exists:

        log.info(
            "Creating incubator batches.json"
        )

        await write_file_sync(
            DATA_FILE,
            "[]"
        )


def migrate_batch_schema(batch):

    if not isinstance(batch, dict):
        return False

    changed = False
    legacy_hatched = number(batch.get("Survival"), 0) if "hatched" not in batch and "Survival" in batch else None

    defaults = {
        "name": f"Batch {batch.get('id', '')}".strip(),
        "species": "Unknown",
        "eggs": 0,
        "incubation_days": DEFAULT_INCUBATION_DAYS,
        "lockdown_day": DEFAULT_LOCKDOWN_DAY,
        "candle_day": DEFAULT_CANDLE_DAY,
        "hatched": 0,
        "infertile": 0,
        "losses": 0,
        "notes": "",
        "results_saved_at": "",
        "results_updated_at": "",
        "archived": False,
        "archived_at": "",
        "created_at": "",
        "updated_at": "",
        "tags": [],
    }

    for key, value in defaults.items():
        if key not in batch:
            batch[key] = value
            changed = True

    # Keep legacy Survival for compatibility, but hatch results are authoritative.
    if legacy_hatched is not None:
        batch["hatched"] = legacy_hatched
        changed = True

    # Normalize legacy non-zero-padded dates such as 2026-7-11.
    start_text = str(batch.get("start", "")).strip()
    if start_text:
        try:
            normalized = datetime.strptime(start_text, DATE_FORMAT).strftime(DATE_FORMAT)
            if normalized != start_text:
                batch["start"] = normalized
                changed = True
        except Exception:
            pass

    before_tags = json.dumps(batch.get("tags", []), sort_keys=True, default=str)
    ensure_batch_tags(batch)
    after_tags = json.dumps(batch.get("tags", []), sort_keys=True, default=str)
    if before_tags != after_tags:
        changed = True

    return changed


def migrate_batches_schema(batches):

    changed = False

    for batch in batches:
        if migrate_batch_schema(batch):
            changed = True

    return changed



async def load_batches():

    await ensure_file()

    try:

        contents = await read_file_sync(
            DATA_FILE
        )

        if not contents or not contents.strip():
            set_data_status(
                "batches.json is empty.",
                "warning",
                0
            )
            return []

        # Accept UTF-8 BOM and accidental non-breaking spaces copied by editors.
        cleaned = contents.lstrip("\ufeff").replace("\u00a0", " ")

        batches = json.loads(
            cleaned
        )

        if not isinstance(
            batches,
            list
        ):
            raise ValueError(
                "Top-level batches.json value must be a JSON list."
            )

        changed = migrate_batches_schema(
            batches
        )

        if changed:
            # Preserve the exact pre-migration source before writing the new schema.
            await write_file_sync(
                BACKUP_FILE,
                contents
            )

            await write_file_sync(
                DATA_FILE,
                json.dumps(
                    batches,
                    indent=2,
                    ensure_ascii=False
                )
            )

            log.info(
                f"Migrated incubator data schema; backup saved to {BACKUP_FILE}"
            )

        set_data_status(
            f"Loaded {len(batches)} incubator batch(es).",
            "ok",
            len(batches)
        )

        return batches

    except Exception as err:

        log.error(
            f"Loading incubator batches failed: {err}"
        )

        # IMPORTANT: None means DATA ERROR, not an empty incubator.
        # update_sensors() will stop without deleting existing dynamic entities.
        set_data_status(
            f"Could not read batches.json: {err}",
            "error",
            -1
        )

        return None


async def save_batches(batches):

    try:

        # Back up the last known-good file before every valid write.
        exists = await file_exists_sync(DATA_FILE)
        if exists:
            current = await read_file_sync(DATA_FILE)
            if current and current.strip():
                await write_file_sync(
                    BACKUP_FILE,
                    current
                )

        await write_file_sync(
            DATA_FILE,
            json.dumps(
                batches,
                indent=2,
                ensure_ascii=False
            )
        )

    except Exception as err:

        log.error(
            f"Saving incubator batches failed: {err}"
        )

        raise


# ===============================================================
# GENERAL HELPERS
# ===============================================================

def number(value, default=0):

    try:
        return int(
            float(value)
        )

    except Exception:
        return default


def parse_batch_id(value):

    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    # Supports:
    #
    # 3
    # sensor.incubator_batch_3
    # sensor.incubator_archive_3

    if "_" in value:

        try:

            return int(
                value.rsplit(
                    "_",
                    1
                )[1]
            )

        except Exception:
            pass

    try:

        return int(
            value
        )

    except Exception:

        log.error(
            f"Invalid incubator batch ID: {value}"
        )

        return None


def normalize_start_date(start):

    start = str(
        start or ""
    ).strip()

    # Blank = today
    if not start:

        return datetime.now().strftime(
            DATE_FORMAT
        )

    # Validate
    datetime.strptime(
        start,
        DATE_FORMAT
    )

    return start


def find_batch(
    batches,
    batch_id
):

    for batch in batches:

        if number(
            batch.get("id"),
            -1
        ) == batch_id:

            return batch

    return None


def timestamp_now():

    return datetime.now().isoformat(
        timespec="seconds"
    )


def slugify(value):

    text = str(value or "").strip().lower()

    text = re.sub(
        r"[^a-z0-9]+",
        "_",
        text
    )

    return text.strip("_") or "tag"


def normalize_tag_color(value):

    value = str(value or "").strip()

    for color in TAG_COLOR_INFO:
        if color.lower() == value.lower():
            return color

    return value or "Unknown"


def tag_color_emoji(color):

    return TAG_COLOR_INFO.get(
        normalize_tag_color(color),
        {}
    ).get(
        "emoji",
        "🏷️"
    )


def tag_color_hex(color):

    return TAG_COLOR_INFO.get(
        normalize_tag_color(color),
        {}
    ).get(
        "hex",
        "#78909c"
    )


def tag_identifier(color, number_value):

    color = normalize_tag_color(color)
    number_text = str(number_value or "").strip().upper()

    return f"{color.upper()}-{number_text}"


def ensure_batch_tags(batch):

    raw_tags = batch.get(
        "tags",
        []
    )

    if not isinstance(raw_tags, list):
        raw_tags = []

    normalized = []

    batch_id = number(
        batch.get("id"),
        0
    )

    used_uids = set()

    next_index = 1

    for item in raw_tags:

        if not isinstance(item, dict):
            continue

        color = normalize_tag_color(
            item.get(
                "color",
                "Unknown"
            )
        )

        tag_number = str(
            item.get(
                "number",
                ""
            )
        ).strip().upper()

        if not tag_number:
            continue

        uid = str(
            item.get(
                "uid",
                ""
            )
        ).strip()

        if not uid or uid in used_uids:

            while f"{batch_id}-{next_index}" in used_uids:
                next_index += 1

            uid = f"{batch_id}-{next_index}"
            next_index += 1

        used_uids.add(uid)

        sex = str(
            item.get(
                "sex",
                "Unknown"
            )
        ).strip().title()

        if sex not in TAG_SEX_OPTIONS:
            sex = "Unknown"

        status = str(
            item.get(
                "status",
                "Active"
            )
        ).strip().title()

        if status not in TAG_STATUS_OPTIONS:
            status = "Active"

        normalized.append({
            "uid": uid,
            "tag_id": tag_identifier(
                color,
                tag_number
            ),
            "color": color,
            "color_emoji": tag_color_emoji(color),
            "color_hex": tag_color_hex(color),
            "number": tag_number,
            "sex": sex,
            "status": status,
            "notes": str(
                item.get(
                    "notes",
                    ""
                )
            ).strip(),
            "assigned_at": str(
                item.get(
                    "assigned_at",
                    ""
                )
            ).strip(),
            "updated_at": str(
                item.get(
                    "updated_at",
                    ""
                )
            ).strip(),
        })

    batch["tags"] = normalized

    return normalized


def next_tag_uid(batch):

    batch_id = number(
        batch.get("id"),
        0
    )

    highest = 0

    for tag in ensure_batch_tags(batch):

        uid = str(
            tag.get(
                "uid",
                ""
            )
        )

        prefix = f"{batch_id}-"

        if uid.startswith(prefix):

            try:
                highest = max(
                    highest,
                    int(
                        uid[len(prefix):]
                    )
                )
            except Exception:
                pass

    return f"{batch_id}-{highest + 1}"


def tag_option_label(tag):

    return (
        f"{tag_color_emoji(tag.get('color'))} "
        f"{tag.get('color', 'Unknown')} "
        f"{tag.get('number', '')} • "
        f"{tag.get('status', 'Active')} "
        f"[{tag.get('uid', '')}]"
    )


def find_tag_record(
    batches,
    tag_uid
):

    tag_uid = str(
        tag_uid or ""
    ).strip()

    if not tag_uid:
        return None, None

    for batch in batches:

        for tag in ensure_batch_tags(batch):

            if str(
                tag.get(
                    "uid",
                    ""
                )
            ) == tag_uid:

                return batch, tag

    return None, None


def parse_tag_uid(value):

    value = str(
        value or ""
    ).strip()

    if not value:
        return ""

    if value.startswith(
        "sensor.quail_tag_"
    ):

        try:
            attributes = state.getattr(
                value
            ) or {}

            uid = str(
                attributes.get(
                    "tag_uid",
                    ""
                )
            ).strip()

            if uid:
                return uid

        except Exception:
            pass

    return value


def active_tag_conflict(
    batches,
    color,
    tag_number,
    exclude_uid=""
):

    wanted = tag_identifier(
        color,
        tag_number
    )

    exclude_uid = str(
        exclude_uid or ""
    ).strip()

    for batch in batches:

        for tag in ensure_batch_tags(batch):

            if (
                str(
                    tag.get(
                        "uid",
                        ""
                    )
                )
                == exclude_uid
            ):
                continue

            if (
                tag.get(
                    "tag_id"
                ) == wanted
                and
                tag.get(
                    "status",
                    "Active"
                ) == "Active"
            ):
                return batch, tag

    return None, None


def build_tag_summary(tags):

    parts = []

    for tag in tags:

        parts.append(
            f"{tag_color_emoji(tag.get('color'))} "
            f"{tag.get('color', '')} "
            f"{tag.get('number', '')}"
        )

    return ", ".join(parts)


# ===============================================================
# STATUS SENSORS
# ===============================================================

def set_data_status(message, severity="ok", batch_count=0):

    icon = "mdi:database-check"

    if severity == "warning":
        icon = "mdi:database-alert"
    elif severity == "error":
        icon = "mdi:database-remove"

    state.set(
        "sensor.incubator_data_status",
        value=severity,
        new_attributes={
            "friendly_name": "Incubator Data Status",
            "message": str(message),
            "batch_count": batch_count,
            "data_file": DATA_FILE,
            "backup_file": BACKUP_FILE,
            "icon": icon
        }
    )


def set_editor_status(
    message,
    severity="info"
):

    icon = "mdi:information"

    if severity == "success":
        icon = "mdi:check-circle"

    elif severity == "warning":
        icon = "mdi:alert"

    elif severity == "error":
        icon = "mdi:alert-circle"


    state.set(
        "sensor.incubator_editor_status",
        value=severity,
        new_attributes={

            "friendly_name":
                "Incubator Editor Status",

            "message":
                str(message),

            "icon":
                icon
        }
    )


def set_add_status(
    message,
    severity="info"
):

    icon = "mdi:information"

    if severity == "success":
        icon = "mdi:check-circle"

    elif severity == "warning":
        icon = "mdi:alert"

    elif severity == "error":
        icon = "mdi:alert-circle"


    state.set(
        "sensor.incubator_add_status",
        value=severity,
        new_attributes={

            "friendly_name":
                "Incubator Add Batch Status",

            "message":
                str(message),

            "icon":
                icon
        }
    )


def set_tag_status(
    message,
    severity="info"
):

    icon = "mdi:tag-outline"

    if severity == "success":
        icon = "mdi:tag-check"

    elif severity == "warning":
        icon = "mdi:tag-alert"

    elif severity == "error":
        icon = "mdi:alert-circle"

    state.set(
        "sensor.incubator_tag_status",
        value=severity,
        new_attributes={
            "friendly_name":
                "Incubator Quail Tag Status",
            "message":
                str(message),
            "icon":
                icon
        }
    )


# ===============================================================
# HELPER SETTERS
# ===============================================================

def set_text_helper(
    entity_id,
    value
):

    text = str(
        value or ""
    )

    # Home Assistant entity states are limited in length.
    text = text[:255]

    service.call(
        "input_text",
        "set_value",
        blocking=True,
        entity_id=entity_id,
        value=text
    )


def set_number_helper(
    entity_id,
    value
):

    service.call(
        "input_number",
        "set_value",
        blocking=True,
        entity_id=entity_id,
        value=number(
            value,
            0
        )
    )


def set_boolean_helper(
    entity_id,
    value
):

    service.call(
        "input_boolean",
        "turn_on"
        if value
        else "turn_off",
        blocking=True,
        entity_id=entity_id
    )


def set_select_helper(
    entity_id,
    value
):

    service.call(
        "input_select",
        "select_option",
        blocking=True,
        entity_id=entity_id,
        option=str(value)
    )


def set_select_options_helper(
    entity_id,
    options
):

    service.call(
        "input_select",
        "set_options",
        blocking=True,
        entity_id=entity_id,
        options=[
            str(option)
            for option in options
        ]
    )


def refresh_tag_picker(batch):

    tags = ensure_batch_tags(batch)

    options = [
        NEW_TAG_OPTION
    ]

    for tag in tags:
        options.append(
            tag_option_label(tag)
        )

    set_select_options_helper(
        "input_select.incubator_tag_pick",
        options
    )

    set_select_helper(
        "input_select.incubator_tag_pick",
        NEW_TAG_OPTION
    )


def clear_tag_editor_helpers():

    set_text_helper(
        "input_text.incubator_tag_edit_id",
        ""
    )

    set_text_helper(
        "input_text.incubator_tag_number",
        ""
    )

    set_text_helper(
        "input_text.incubator_tag_notes",
        ""
    )

    set_select_helper(
        "input_select.incubator_tag_color",
        "Blue"
    )

    set_select_helper(
        "input_select.incubator_tag_sex",
        "Unknown"
    )

    set_select_helper(
        "input_select.incubator_tag_status_value",
        "Active"
    )


def load_tag_into_helpers(tag):

    set_text_helper(
        "input_text.incubator_tag_edit_id",
        tag.get(
            "uid",
            ""
        )
    )

    set_text_helper(
        "input_text.incubator_tag_number",
        tag.get(
            "number",
            ""
        )
    )

    set_text_helper(
        "input_text.incubator_tag_notes",
        tag.get(
            "notes",
            ""
        )
    )

    set_select_helper(
        "input_select.incubator_tag_color",
        tag.get(
            "color",
            "Blue"
        )
    )

    set_select_helper(
        "input_select.incubator_tag_sex",
        tag.get(
            "sex",
            "Unknown"
        )
    )

    set_select_helper(
        "input_select.incubator_tag_status_value",
        tag.get(
            "status",
            "Active"
        )
    )


# ===============================================================
# HATCH OUTCOME CALCULATIONS
# ===============================================================

def calculate_outcome(batch):

    eggs = max(
        0,
        number(
            batch.get(
                "eggs",
                0
            )
        )
    )


    hatched = max(
        0,
        number(
            batch.get(
                "hatched",
                0
            )
        )
    )


    infertile = max(
        0,
        number(
            batch.get(
                "infertile",
                0
            )
        )
    )


    losses = max(
        0,
        number(
            batch.get(
                "losses",
                0
            )
        )
    )


    accounted = (
        hatched
        +
        infertile
        +
        losses
    )


    unaccounted = max(
        eggs - accounted,
        0
    )


    # -----------------------------------------------------------
    # Overall hatch percentage:
    #
    # Hatched / total eggs set
    # -----------------------------------------------------------

    if eggs > 0:

        hatch_percentage = round(
            hatched
            /
            eggs
            *
            100,
            1
        )

    else:

        hatch_percentage = 0


    # -----------------------------------------------------------
    # Fertility
    # -----------------------------------------------------------

    fertile_eggs = max(
        eggs - infertile,
        0
    )


    if eggs > 0:

        fertility_percentage = round(
            fertile_eggs
            /
            eggs
            *
            100,
            1
        )

    else:

        fertility_percentage = 0


    # -----------------------------------------------------------
    # Hatch rate among fertile eggs
    # -----------------------------------------------------------

    if fertile_eggs > 0:

        fertile_hatch_percentage = round(
            hatched
            /
            fertile_eggs
            *
            100,
            1
        )

    else:

        fertile_hatch_percentage = 0


    return {

        "eggs":
            eggs,

        "hatched":
            hatched,

        "infertile":
            infertile,

        "losses":
            losses,

        "accounted":
            accounted,

        "unaccounted":
            unaccounted,

        "fertile_eggs":
            fertile_eggs,

        "hatch_percentage":
            hatch_percentage,

        "fertility_percentage":
            fertility_percentage,

        "fertile_hatch_percentage":
            fertile_hatch_percentage,

        "valid":
            accounted <= eggs,

        "complete":
            eggs > 0
            and
            accounted == eggs
    }


# ===============================================================
# INCUBATION STATUS
# ===============================================================

def get_status(
    day,
    candle_day,
    lockdown_day,
    incubation_days
):

    if day < 1:
        return "Scheduled"

    if day == candle_day:
        return "Candling"

    if day < lockdown_day:
        return "Incubating"

    if day < incubation_days:
        return "Lockdown"

    if day == incubation_days:
        return "Hatching"

    return "Complete"


# ===============================================================
# UPDATE ALL HOME ASSISTANT SENSORS
# ===============================================================

async def update_sensors():

    batches = await load_batches()

    if batches is None:
        log.error(
            "Incubator sensor refresh aborted because batches.json could not be loaded."
        )
        return

    today = datetime.now().date()

    desired_entities = set()
    desired_tag_entities = set()

    active_batches = 0
    active_eggs = 0

    archived_batches = 0

    next_hatch = None
    next_lockdown = None

    historical_hatched = 0
    historical_eggs = 0
    historical_batches = 0

    total_tag_records = 0
    active_tag_records = 0
    untagged_chicks = 0


    # -----------------------------------------------------------
    # DEFAULT STATUS SENSORS
    # -----------------------------------------------------------

    if not state.exist(
        "sensor.incubator_editor_status"
    ):

        set_editor_status(
            "Tap a batch to edit it.",
            "info"
        )


    if not state.exist(
        "sensor.incubator_add_status"
    ):

        set_add_status(
            "Ready to add a batch.",
            "info"
        )

    if not state.exist(
        "sensor.incubator_tag_status"
    ):

        set_tag_status(
            "Choose a batch, then add or edit a quail tag.",
            "info"
        )


    # -----------------------------------------------------------
    # PROCESS BATCHES
    # -----------------------------------------------------------

    for batch in batches:

        try:

            batch_id = number(
                batch.get(
                    "id"
                ),
                -1
            )

            if batch_id < 0:
                continue


            archived = bool(
                batch.get(
                    "archived",
                    False
                )
            )


            start = datetime.strptime(
                batch["start"],
                DATE_FORMAT
            ).date()


            incubation_days = max(
                1,
                number(
                    batch.get(
                        "incubation_days",
                        DEFAULT_INCUBATION_DAYS
                    ),
                    DEFAULT_INCUBATION_DAYS
                )
            )


            lockdown_day = max(
                1,
                min(
                    number(
                        batch.get(
                            "lockdown_day",
                            DEFAULT_LOCKDOWN_DAY
                        ),
                        DEFAULT_LOCKDOWN_DAY
                    ),
                    incubation_days
                )
            )


            candle_day = max(
                1,
                min(
                    number(
                        batch.get(
                            "candle_day",
                            DEFAULT_CANDLE_DAY
                        ),
                        DEFAULT_CANDLE_DAY
                    ),
                    max(
                        1,
                        lockdown_day - 1
                    )
                )
            )


            # ===================================================
            # INCUBATION DATES
            #
            # Start date = Day 1.
            # Therefore Day 18 is start + 17 days.
            # ===================================================

            day = (
                today - start
            ).days + 1


            candle_date = (
                start
                +
                timedelta(
                    days=candle_day - 1
                )
            )


            lockdown_date = (
                start
                +
                timedelta(
                    days=lockdown_day - 1
                )
            )


            hatch_date = (
                start
                +
                timedelta(
                    days=incubation_days - 1
                )
            )


            days_to_candle = (
                candle_date - today
            ).days


            days_to_lockdown = (
                lockdown_date - today
            ).days


            days_to_hatch = (
                hatch_date - today
            ).days


            cycle_status = get_status(
                day,
                candle_day,
                lockdown_day,
                incubation_days
            )


            # ===================================================
            # INCUBATION PROGRESS
            # ===================================================

            progress_day = max(
                0,
                min(
                    day,
                    incubation_days
                )
            )


            progress = round(
                progress_day
                /
                incubation_days
                *
                100,
                1
            )


            # ===================================================
            # RESULTS
            # ===================================================

            outcome = calculate_outcome(
                batch
            )

            tags = ensure_batch_tags(
                batch
            )

            tag_count = len(
                tags
            )

            batch_active_tags = 0

            for tag in tags:

                if tag.get(
                    "status",
                    "Active"
                ) == "Active":

                    batch_active_tags += 1

            batch_untagged = max(
                outcome["hatched"]
                -
                tag_count,
                0
            )

            total_tag_records += tag_count
            active_tag_records += batch_active_tags
            untagged_chicks += batch_untagged


            # ===================================================
            # ENTITY TYPE
            # ===================================================

            if archived:

                entity_id = (
                    f"sensor.incubator_archive_{batch_id}"
                )

                entity_state = "Archived"

                archived_batches += 1

            else:

                entity_id = (
                    f"sensor.incubator_batch_{batch_id}"
                )

                entity_state = max(
                    0,
                    day
                )

                active_batches += 1

                active_eggs += (
                    outcome["eggs"]
                )


            desired_entities.add(
                entity_id
            )


            # ===================================================
            # CREATE / UPDATE ENTITY
            # ===================================================

            state.set(
                entity_id,
                value=entity_state,
                new_attributes={

                    "friendly_name":
                        batch.get(
                            "name",
                            f"Batch {batch_id}"
                        ),

                    "batch_id":
                        batch_id,

                    "species":
                        batch.get(
                            "species",
                            "Unknown"
                        ),

                    "eggs":
                        outcome["eggs"],

                    "hatched":
                        outcome["hatched"],

                    "infertile":
                        outcome["infertile"],

                    "losses":
                        outcome["losses"],

                    "accounted":
                        outcome["accounted"],

                    "unaccounted":
                        outcome["unaccounted"],

                    "fertile_eggs":
                        outcome["fertile_eggs"],

                    "hatch_percentage":
                        outcome[
                            "hatch_percentage"
                        ],

                    "fertility_percentage":
                        outcome[
                            "fertility_percentage"
                        ],

                    "fertile_hatch_percentage":
                        outcome[
                            "fertile_hatch_percentage"
                        ],

                    "results_valid":
                        outcome["valid"],

                    "results_complete":
                        outcome["complete"],

                    "results_recorded":
                        bool(
                            batch.get(
                                "results_saved_at",
                                ""
                            )
                        ),

                    "results_saved_at":
                        batch.get(
                            "results_saved_at",
                            ""
                        ),

                    "results_updated_at":
                        batch.get(
                            "results_updated_at",
                            ""
                        ),

                    "notes":
                        batch.get(
                            "notes",
                            ""
                        ),

                    "tag_count":
                        tag_count,

                    "active_tag_count":
                        batch_active_tags,

                    "untagged_chicks":
                        batch_untagged,

                    "tag_summary":
                        build_tag_summary(tags),

                    "tags":
                        tags,

                    "status":
                        (
                            "Archived"
                            if archived
                            else cycle_status
                        ),

                    "cycle_status":
                        cycle_status,

                    "archived":
                        archived,

                    "archived_at":
                        batch.get(
                            "archived_at",
                            ""
                        ),

                    "created_at":
                        batch.get(
                            "created_at",
                            ""
                        ),

                    "updated_at":
                        batch.get(
                            "updated_at",
                            ""
                        ),

                    "progress":
                        progress,

                    "start_date":
                        str(start),

                    "candle_day":
                        candle_day,

                    "candle_date":
                        str(candle_date),

                    "days_to_candle":
                        days_to_candle,

                    "lockdown_day":
                        lockdown_day,

                    "lockdown_date":
                        str(lockdown_date),

                    "days_to_lockdown":
                        days_to_lockdown,

                    "incubation_days":
                        incubation_days,

                    "hatch_date":
                        str(hatch_date),

                    "days_to_hatch":
                        days_to_hatch,

                    "icon":
                        (
                            "mdi:archive"
                            if archived
                            else "mdi:egg"
                        )
                }
            )

            # ===================================================
            # INDIVIDUAL QUAIL TAG SENSORS
            # ===================================================

            for tag in tags:

                tag_entity_id = (
                    "sensor.quail_tag_"
                    +
                    slugify(
                        tag.get(
                            "uid",
                            "tag"
                        )
                    )
                )

                desired_tag_entities.add(
                    tag_entity_id
                )

                tag_display = (
                    f"{tag_color_emoji(tag.get('color'))} "
                    f"{tag.get('color', 'Unknown')} "
                    f"{tag.get('number', '')}"
                )

                state.set(
                    tag_entity_id,
                    value=tag.get(
                        "status",
                        "Active"
                    ),
                    new_attributes={
                        "friendly_name":
                            tag_display,
                        "tag_uid":
                            tag.get(
                                "uid",
                                ""
                            ),
                        "tag_id":
                            tag.get(
                                "tag_id",
                                ""
                            ),
                        "color":
                            tag.get(
                                "color",
                                "Unknown"
                            ),
                        "color_emoji":
                            tag_color_emoji(
                                tag.get(
                                    "color"
                                )
                            ),
                        "color_hex":
                            tag_color_hex(
                                tag.get(
                                    "color"
                                )
                            ),
                        "number":
                            tag.get(
                                "number",
                                ""
                            ),
                        "sex":
                            tag.get(
                                "sex",
                                "Unknown"
                            ),
                        "status":
                            tag.get(
                                "status",
                                "Active"
                            ),
                        "notes":
                            tag.get(
                                "notes",
                                ""
                            ),
                        "assigned_at":
                            tag.get(
                                "assigned_at",
                                ""
                            ),
                        "updated_at":
                            tag.get(
                                "updated_at",
                                ""
                            ),
                        "batch_id":
                            batch_id,
                        "batch_name":
                            batch.get(
                                "name",
                                f"Batch {batch_id}"
                            ),
                        "species":
                            batch.get(
                                "species",
                                "Unknown"
                            ),
                        "hatch_date":
                            str(
                                hatch_date
                            ),
                        "archived_batch":
                            archived,
                        "icon":
                            "mdi:tag"
                    }
                )


            # ===================================================
            # UPCOMING EVENTS
            # ===================================================

            if not archived:

                # ------------------------------------------------
                # NEXT HATCH
                # ------------------------------------------------

                if days_to_hatch >= 0:

                    candidate = {

                        "days":
                            days_to_hatch,

                        "date":
                            hatch_date,

                        "batch_name":
                            batch.get(
                                "name",
                                f"Batch {batch_id}"
                            ),

                        "batch_id":
                            batch_id
                    }


                    if (
                        next_hatch is None
                        or
                        candidate["days"]
                        <
                        next_hatch["days"]
                    ):

                        next_hatch = candidate


                # ------------------------------------------------
                # NEXT LOCKDOWN
                # ------------------------------------------------

                if days_to_lockdown >= 0:

                    candidate = {

                        "days":
                            days_to_lockdown,

                        "date":
                            lockdown_date,

                        "batch_name":
                            batch.get(
                                "name",
                                f"Batch {batch_id}"
                            ),

                        "batch_id":
                            batch_id
                    }


                    if (
                        next_lockdown is None
                        or
                        candidate["days"]
                        <
                        next_lockdown["days"]
                    ):

                        next_lockdown = candidate


            # ===================================================
            # HISTORICAL STATISTICS
            #
            # Only archived batches with recorded results affect
            # lifetime statistics.
            # ===================================================

            if (
                archived
                and
                batch.get(
                    "results_saved_at"
                )
            ):

                historical_batches += 1

                historical_eggs += (
                    outcome["eggs"]
                )

                historical_hatched += (
                    outcome["hatched"]
                )


        except Exception as err:

            log.error(
                f"Batch update failed for {batch}: {err}"
            )


    # ===========================================================
    # REMOVE STALE DYNAMIC ENTITIES
    # ===========================================================

    try:

        for entity_id in state.names(
            "sensor"
        ):

            dynamic_incubator_entity = (
                entity_id.startswith(
                    "sensor.incubator_batch_"
                )
                or
                entity_id.startswith(
                    "sensor.incubator_archive_"
                )
            )


            if (
                dynamic_incubator_entity
                and
                entity_id not in desired_entities
            ):

                state.delete(
                    entity_id
                )


    except Exception as err:

        log.warning(
            f"Unable to clean stale incubator sensors: {err}"
        )

    try:

        for entity_id in state.names(
            "sensor"
        ):

            if (
                entity_id.startswith(
                    "sensor.quail_tag_"
                )
                and
                entity_id not in desired_tag_entities
            ):

                state.delete(
                    entity_id
                )

    except Exception as err:

        log.warning(
            f"Unable to clean stale quail tag sensors: {err}"
        )


    # ===========================================================
    # ACTIVE SUMMARY
    # ===========================================================

    state.set(
        "sensor.incubator_active_batches",
        value=active_batches,
        new_attributes={

            "friendly_name":
                "Active Incubator Batches",

            "icon":
                "mdi:egg-multiple"
        }
    )


    state.set(
        "sensor.incubator_total_eggs",
        value=active_eggs,
        new_attributes={

            "friendly_name":
                "Active Eggs",

            "icon":
                "mdi:egg"
        }
    )


    state.set(
        "sensor.incubator_archived_batches",
        value=archived_batches,
        new_attributes={

            "friendly_name":
                "Archived Batches",

            "icon":
                "mdi:archive"
        }
    )


    # ===========================================================
    # LIFETIME STATISTICS
    # ===========================================================

    state.set(
        "sensor.incubator_total_hatched",
        value=historical_hatched,
        new_attributes={

            "friendly_name":
                "Total Hatched",

            "recorded_batches":
                historical_batches,

            "icon":
                "mdi:bird"
        }
    )


    if historical_eggs > 0:

        lifetime_rate = round(
            historical_hatched
            /
            historical_eggs
            *
            100,
            1
        )

    else:

        lifetime_rate = 0


    state.set(
        "sensor.incubator_lifetime_hatch_rate",
        value=lifetime_rate,
        new_attributes={

            "friendly_name":
                "Lifetime Hatch Rate",

            "recorded_batches":
                historical_batches,

            "eggs":
                historical_eggs,

            "hatched":
                historical_hatched,

            "unit_of_measurement":
                "%",

            "icon":
                "mdi:percent"
        }
    )

    state.set(
        "sensor.incubator_total_tags",
        value=total_tag_records,
        new_attributes={
            "friendly_name":
                "Quail Identification Tags",
            "active_tags":
                active_tag_records,
            "icon":
                "mdi:tag-multiple"
        }
    )

    state.set(
        "sensor.incubator_active_tags",
        value=active_tag_records,
        new_attributes={
            "friendly_name":
                "Active Tagged Quail",
            "total_tag_records":
                total_tag_records,
            "icon":
                "mdi:bird"
        }
    )

    state.set(
        "sensor.incubator_untagged_chicks",
        value=untagged_chicks,
        new_attributes={
            "friendly_name":
                "Hatched Chicks Needing Tags",
            "icon":
                "mdi:tag-off"
        }
    )


    # ===========================================================
    # NEXT HATCH
    # ===========================================================

    if next_hatch:

        state.set(
            "sensor.incubator_next_hatch",
            value=next_hatch["days"],
            new_attributes={

                "friendly_name":
                    "Next Hatch",

                "batch_name":
                    next_hatch[
                        "batch_name"
                    ],

                "batch_id":
                    next_hatch[
                        "batch_id"
                    ],

                "date":
                    str(
                        next_hatch[
                            "date"
                        ]
                    ),

                "unit_of_measurement":
                    "days",

                "icon":
                    "mdi:egg-easter"
            }
        )

    else:

        state.set(
            "sensor.incubator_next_hatch",
            value="unknown",
            new_attributes={

                "friendly_name":
                    "Next Hatch",

                "icon":
                    "mdi:egg-easter"
            }
        )


    # ===========================================================
    # NEXT LOCKDOWN
    # ===========================================================

    if next_lockdown:

        state.set(
            "sensor.incubator_next_lockdown",
            value=next_lockdown["days"],
            new_attributes={

                "friendly_name":
                    "Next Lockdown",

                "batch_name":
                    next_lockdown[
                        "batch_name"
                    ],

                "batch_id":
                    next_lockdown[
                        "batch_id"
                    ],

                "date":
                    str(
                        next_lockdown[
                            "date"
                        ]
                    ),

                "unit_of_measurement":
                    "days",

                "icon":
                    "mdi:lock-clock"
            }
        )

    else:

        state.set(
            "sensor.incubator_next_lockdown",
            value="unknown",
            new_attributes={

                "friendly_name":
                    "Next Lockdown",

                "icon":
                    "mdi:lock-clock"
            }
        )


# ===============================================================
# ADD BATCH INTERNAL FUNCTION
# ===============================================================

async def add_batch(
    name=None,
    species="Coturnix",
    eggs=0,
    start=None,
    incubation_days=18,
    lockdown_day=14,
    candle_day=7
):

    batches = await load_batches()


    # -----------------------------------------------------------
    # NORMALIZE / VALIDATE
    # -----------------------------------------------------------

    start = normalize_start_date(
        start
    )


    eggs = number(
        eggs,
        0
    )


    incubation_days = number(
        incubation_days,
        DEFAULT_INCUBATION_DAYS
    )


    lockdown_day = number(
        lockdown_day,
        DEFAULT_LOCKDOWN_DAY
    )


    candle_day = number(
        candle_day,
        DEFAULT_CANDLE_DAY
    )


    if eggs <= 0:

        raise ValueError(
            "Egg count must be greater than zero."
        )


    if incubation_days <= 0:

        raise ValueError(
            "Incubation days must be greater than zero."
        )


    if (
        lockdown_day <= 0
        or
        lockdown_day > incubation_days
    ):

        raise ValueError(
            "Lockdown day must be between Day 1 and hatch day."
        )


    if (
        candle_day <= 0
        or
        candle_day >= lockdown_day
    ):

        raise ValueError(
            "Candling day must be before lockdown day."
        )


    name = str(
        name or ""
    ).strip()


    species = str(
        species or "Unknown"
    ).strip()


    # -----------------------------------------------------------
    # GET NEXT ID
    # -----------------------------------------------------------

    existing_ids = []


    for batch in batches:

        try:

            existing_ids.append(
                int(
                    batch.get(
                        "id"
                    )
                )
            )

        except Exception:
            pass


    new_id = max(
        existing_ids,
        default=0
    ) + 1


    now = timestamp_now()


    # -----------------------------------------------------------
    # CREATE BATCH
    # -----------------------------------------------------------

    batches.append({

        "id":
            new_id,

        "name":
            name
            or
            f"Batch {new_id}",

        "species":
            species
            or
            "Unknown",

        "eggs":
            eggs,

        "start":
            start,

        "incubation_days":
            incubation_days,

        "lockdown_day":
            lockdown_day,

        "candle_day":
            candle_day,

        "hatched":
            0,

        "infertile":
            0,

        "losses":
            0,

        "notes":
            "",

        "tags":
            [],

        "results_saved_at":
            "",

        "results_updated_at":
            "",

        "archived":
            False,

        "archived_at":
            "",

        "created_at":
            now,

        "updated_at":
            now
    })


    await save_batches(
        batches
    )


    await update_sensors()


    log.info(
        f"Added incubator batch {new_id}"
    )


    return new_id


# ===============================================================
# ADD BATCH SERVICES
# ===============================================================

@service
async def incubator_add_batch(
    name=None,
    species="Coturnix",
    eggs=0,
    start=None,
    incubation_days=18,
    lockdown_day=14,
    candle_day=7
):

    try:

        new_id = await add_batch(
            name=name,
            species=species,
            eggs=eggs,
            start=start,
            incubation_days=incubation_days,
            lockdown_day=lockdown_day,
            candle_day=candle_day
        )


        set_add_status(
            f"Batch #{new_id} created successfully.",
            "success"
        )


    except Exception as err:

        log.error(
            f"Unable to add incubator batch: {err}"
        )

        set_add_status(
            str(err),
            "error"
        )


@service
async def incubator_add_from_helpers():

    try:

        new_id = await add_batch(

            name=state.get(
                "input_text.incubator_batch_name"
            ),

            species=state.get(
                "input_text.incubator_species"
            ),

            start=state.get(
                "input_text.incubator_start_date"
            ),

            eggs=state.get(
                "input_number.incubator_eggs"
            ),

            incubation_days=state.get(
                "input_number.incubator_days"
            ),

            lockdown_day=state.get(
                "input_number.incubator_lockdown"
            ),

            candle_day=state.get(
                "input_number.incubator_candle"
            )
        )


        set_add_status(
            f"Batch #{new_id} created successfully.",
            "success"
        )


    except Exception as err:

        log.error(
            f"Unable to add batch from helpers: {err}"
        )

        set_add_status(
            str(err),
            "error"
        )


# ===============================================================
# LOAD BATCH INTO EDITOR
# ===============================================================

@service
async def incubator_load_batch_for_edit(
    id=None
):

    batch_id = parse_batch_id(
        id
    )


    if batch_id is None:

        set_editor_status(
            "Unable to determine the batch ID.",
            "error"
        )

        return


    batches = await load_batches()


    batch = find_batch(
        batches,
        batch_id
    )


    if batch is None:

        set_editor_status(
            f"Batch {batch_id} was not found.",
            "error"
        )

        return


    # -----------------------------------------------------------
    # TEXT FIELDS
    # -----------------------------------------------------------

    set_text_helper(
        "input_text.incubator_edit_id",
        batch_id
    )


    set_text_helper(
        "input_text.incubator_edit_name",
        batch.get(
            "name",
            f"Batch {batch_id}"
        )
    )


    set_text_helper(
        "input_text.incubator_edit_species",
        batch.get(
            "species",
            ""
        )
    )


    set_text_helper(
        "input_text.incubator_edit_start_date",
        batch.get(
            "start",
            ""
        )
    )


    set_text_helper(
        "input_text.incubator_edit_notes",
        batch.get(
            "notes",
            ""
        )
    )


    # -----------------------------------------------------------
    # INCUBATION NUMBERS
    # -----------------------------------------------------------

    set_number_helper(
        "input_number.incubator_edit_eggs",
        batch.get(
            "eggs",
            0
        )
    )


    set_number_helper(
        "input_number.incubator_edit_days",
        batch.get(
            "incubation_days",
            DEFAULT_INCUBATION_DAYS
        )
    )


    set_number_helper(
        "input_number.incubator_edit_lockdown",
        batch.get(
            "lockdown_day",
            DEFAULT_LOCKDOWN_DAY
        )
    )


    set_number_helper(
        "input_number.incubator_edit_candle",
        batch.get(
            "candle_day",
            DEFAULT_CANDLE_DAY
        )
    )


    # -----------------------------------------------------------
    # HATCH RESULTS
    # -----------------------------------------------------------

    set_number_helper(
        "input_number.incubator_edit_hatched",
        batch.get(
            "hatched",
            0
        )
    )


    set_number_helper(
        "input_number.incubator_edit_infertile",
        batch.get(
            "infertile",
            0
        )
    )


    set_number_helper(
        "input_number.incubator_edit_losses",
        batch.get(
            "losses",
            0
        )
    )


    # -----------------------------------------------------------
    # ARCHIVE STATUS
    # -----------------------------------------------------------

    set_boolean_helper(
        "input_boolean.incubator_edit_archived",
        bool(
            batch.get(
                "archived",
                False
            )
        )
    )

    refresh_tag_picker(
        batch
    )

    clear_tag_editor_helpers()


    set_editor_status(
        (
            "Editing "
            +
            batch.get(
                "name",
                f"Batch {batch_id}"
            )
        ),
        "info"
    )


# ===============================================================
# APPLY EDITOR VALUES TO A BATCH
# ===============================================================

def apply_editor_values(
    batch
):

    name = str(
        state.get(
            "input_text.incubator_edit_name"
        )
        or ""
    ).strip()


    species = str(
        state.get(
            "input_text.incubator_edit_species"
        )
        or ""
    ).strip()


    start = normalize_start_date(
        state.get(
            "input_text.incubator_edit_start_date"
        )
    )


    notes = str(
        state.get(
            "input_text.incubator_edit_notes"
        )
        or ""
    ).strip()


    eggs = number(
        state.get(
            "input_number.incubator_edit_eggs"
        )
    )


    incubation_days = number(
        state.get(
            "input_number.incubator_edit_days"
        )
    )


    lockdown_day = number(
        state.get(
            "input_number.incubator_edit_lockdown"
        )
    )


    candle_day = number(
        state.get(
            "input_number.incubator_edit_candle"
        )
    )


    hatched = number(
        state.get(
            "input_number.incubator_edit_hatched"
        )
    )


    infertile = number(
        state.get(
            "input_number.incubator_edit_infertile"
        )
    )


    losses = number(
        state.get(
            "input_number.incubator_edit_losses"
        )
    )


    # -----------------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------------

    if eggs <= 0:

        raise ValueError(
            "Egg count must be greater than zero."
        )


    if incubation_days <= 0:

        raise ValueError(
            "Incubation days must be greater than zero."
        )


    if (
        lockdown_day <= 0
        or
        lockdown_day > incubation_days
    ):

        raise ValueError(
            "Lockdown day must be before or on hatch day."
        )


    if (
        candle_day <= 0
        or
        candle_day >= lockdown_day
    ):

        raise ValueError(
            "Candling day must be before lockdown."
        )


    if min(
        hatched,
        infertile,
        losses
    ) < 0:

        raise ValueError(
            "Hatch result values cannot be negative."
        )


    accounted = (
        hatched
        +
        infertile
        +
        losses
    )


    if accounted > eggs:

        difference = (
            accounted - eggs
        )

        raise ValueError(
            (
                "Hatched + infertile + losses "
                f"exceeds eggs set by {difference}."
            )
        )

    tag_count = len(
        ensure_batch_tags(
            batch
        )
    )

    if hatched < tag_count:

        raise ValueError(
            (
                f"This batch has {tag_count} quail tag record(s). "
                f"Hatched chicks cannot be reduced below {tag_count}."
            )
        )


    # -----------------------------------------------------------
    # APPLY VALUES
    # -----------------------------------------------------------

    batch["name"] = (
        name
        or
        f"Batch {batch['id']}"
    )


    batch["species"] = (
        species
        or
        "Unknown"
    )


    batch["start"] = start

    batch["eggs"] = eggs

    batch[
        "incubation_days"
    ] = incubation_days

    batch[
        "lockdown_day"
    ] = lockdown_day

    batch[
        "candle_day"
    ] = candle_day

    batch["hatched"] = hatched

    batch["infertile"] = infertile

    batch["losses"] = losses

    batch["notes"] = notes

    batch[
        "updated_at"
    ] = timestamp_now()


    # -----------------------------------------------------------
    # RESULTS TIMESTAMPS
    # -----------------------------------------------------------

    start_date = datetime.strptime(
        start,
        DATE_FORMAT
    ).date()


    hatch_date = (
        start_date
        +
        timedelta(
            days=incubation_days - 1
        )
    )


    if (
        accounted > 0
        or
        datetime.now().date()
        >= hatch_date
    ):

        if not batch.get(
            "results_saved_at"
        ):

            batch[
                "results_saved_at"
            ] = timestamp_now()


        batch[
            "results_updated_at"
        ] = timestamp_now()


    return calculate_outcome(
        batch
    )


# ===============================================================
# SAVE EDITED BATCH
# ===============================================================

@service
async def incubator_save_edit_from_helpers():

    batch_id = parse_batch_id(
        state.get(
            "input_text.incubator_edit_id"
        )
    )


    if batch_id is None:

        set_editor_status(
            "No batch is currently loaded.",
            "error"
        )

        return


    batches = await load_batches()


    batch = find_batch(
        batches,
        batch_id
    )


    if batch is None:

        set_editor_status(
            f"Batch {batch_id} no longer exists.",
            "error"
        )

        return


    try:

        outcome = apply_editor_values(
            batch
        )


        await save_batches(
            batches
        )


        await update_sensors()


        if outcome["complete"]:

            accounting_text = (
                "All eggs accounted for"
            )

        else:

            accounting_text = (
                f"{outcome['unaccounted']} "
                "egg(s) unaccounted"
            )


        set_editor_status(
            (
                f"Saved {batch['name']} • "
                f"Hatch rate "
                f"{outcome['hatch_percentage']}% • "
                f"{accounting_text}"
            ),
            "success"
        )


    except Exception as err:

        log.error(
            f"Saving batch edit failed: {err}"
        )


        set_editor_status(
            str(err),
            "error"
        )


# ===============================================================
# QUAIL IDENTIFICATION TAG SERVICES
# ===============================================================

@service
async def incubator_clear_tag_editor():

    clear_tag_editor_helpers()

    set_tag_status(
        "Ready to add a new quail identification tag.",
        "info"
    )


@service
async def incubator_load_selected_tag_for_edit():

    batch_id = parse_batch_id(
        state.get(
            "input_text.incubator_edit_id"
        )
    )

    if batch_id is None:

        set_tag_status(
            "Open a batch before editing tags.",
            "error"
        )
        return

    batches = await load_batches()

    batch = find_batch(
        batches,
        batch_id
    )

    if batch is None:

        set_tag_status(
            "The selected batch could not be found.",
            "error"
        )
        return

    selected = str(
        state.get(
            "input_select.incubator_tag_pick"
        )
        or
        NEW_TAG_OPTION
    )

    if selected == NEW_TAG_OPTION:

        clear_tag_editor_helpers()

        set_tag_status(
            "Ready to add a new quail identification tag.",
            "info"
        )
        return

    for tag in ensure_batch_tags(batch):

        if tag_option_label(tag) == selected:

            load_tag_into_helpers(
                tag
            )

            set_tag_status(
                (
                    f"Editing "
                    f"{tag_color_emoji(tag.get('color'))} "
                    f"{tag.get('color')} "
                    f"{tag.get('number')}."
                ),
                "info"
            )
            return

    set_tag_status(
        "That tag is no longer available. Reload the batch and try again.",
        "warning"
    )


@service
async def incubator_load_tag_for_edit(
    id=None
):

    tag_uid = parse_tag_uid(
        id
    )

    if not tag_uid:

        set_tag_status(
            "Unable to determine the tag record.",
            "error"
        )
        return

    batches = await load_batches()

    batch, tag = find_tag_record(
        batches,
        tag_uid
    )

    if batch is None or tag is None:

        set_tag_status(
            "Quail tag record not found.",
            "error"
        )
        return

    set_text_helper(
        "input_text.incubator_edit_id",
        batch.get(
            "id",
            ""
        )
    )

    refresh_tag_picker(
        batch
    )

    load_tag_into_helpers(
        tag
    )

    try:
        set_select_helper(
            "input_select.incubator_tag_pick",
            tag_option_label(tag)
        )
    except Exception:
        pass

    set_tag_status(
        (
            f"Editing "
            f"{tag_color_emoji(tag.get('color'))} "
            f"{tag.get('color')} "
            f"{tag.get('number')}."
        ),
        "info"
    )


@service
async def incubator_save_tag_from_helpers():

    batch_id = parse_batch_id(
        state.get(
            "input_text.incubator_edit_id"
        )
    )

    if batch_id is None:

        set_tag_status(
            "Open a batch before adding a tag.",
            "error"
        )
        return

    batches = await load_batches()

    batch = find_batch(
        batches,
        batch_id
    )

    if batch is None:

        set_tag_status(
            "The selected batch could not be found.",
            "error"
        )
        return

    color = normalize_tag_color(
        state.get(
            "input_select.incubator_tag_color"
        )
    )

    tag_number = str(
        state.get(
            "input_text.incubator_tag_number"
        )
        or
        ""
    ).strip().upper()

    sex = str(
        state.get(
            "input_select.incubator_tag_sex"
        )
        or
        "Unknown"
    ).strip().title()

    status = str(
        state.get(
            "input_select.incubator_tag_status_value"
        )
        or
        "Active"
    ).strip().title()

    notes = str(
        state.get(
            "input_text.incubator_tag_notes"
        )
        or
        ""
    ).strip()

    edit_uid = str(
        state.get(
            "input_text.incubator_tag_edit_id"
        )
        or
        ""
    ).strip()

    if not tag_number:

        set_tag_status(
            "Enter the number printed on the quail tag.",
            "error"
        )
        return

    if color not in TAG_COLOR_INFO:

        set_tag_status(
            "Choose a valid tag color.",
            "error"
        )
        return

    if sex not in TAG_SEX_OPTIONS:
        sex = "Unknown"

    if status not in TAG_STATUS_OPTIONS:
        status = "Active"

    tags = ensure_batch_tags(
        batch
    )

    existing = None

    if edit_uid:

        for tag in tags:

            if tag.get(
                "uid"
            ) == edit_uid:
                existing = tag
                break

        if existing is None:

            set_tag_status(
                "The tag being edited no longer exists.",
                "error"
            )
            return

    outcome = calculate_outcome(
        batch
    )

    if existing is None:

        if outcome["hatched"] <= 0:

            set_tag_status(
                "Record at least one hatched chick before assigning tags.",
                "warning"
            )
            return

        if len(tags) >= outcome["hatched"]:

            set_tag_status(
                (
                    f"All {outcome['hatched']} hatched chick(s) "
                    "already have tag records."
                ),
                "warning"
            )
            return

    if status == "Active":

        conflict_batch, conflict_tag = active_tag_conflict(
            batches,
            color,
            tag_number,
            exclude_uid=edit_uid
        )

        if conflict_tag is not None:

            set_tag_status(
                (
                    f"{tag_color_emoji(color)} {color} {tag_number} "
                    f"is already active in "
                    f"{conflict_batch.get('name', 'another batch')}."
                ),
                "error"
            )
            return

    now = timestamp_now()

    if existing is None:

        existing = {
            "uid":
                next_tag_uid(
                    batch
                ),
            "assigned_at":
                now
        }

        tags.append(
            existing
        )

    existing["color"] = color
    existing["color_emoji"] = tag_color_emoji(color)
    existing["color_hex"] = tag_color_hex(color)
    existing["number"] = tag_number
    existing["tag_id"] = tag_identifier(
        color,
        tag_number
    )
    existing["sex"] = sex
    existing["status"] = status
    existing["notes"] = notes
    existing["updated_at"] = now

    if not existing.get(
        "assigned_at"
    ):
        existing["assigned_at"] = now

    batch["tags"] = tags
    batch["updated_at"] = now

    await save_batches(
        batches
    )

    await update_sensors()

    refresh_tag_picker(
        batch
    )

    load_tag_into_helpers(
        existing
    )

    try:
        set_select_helper(
            "input_select.incubator_tag_pick",
            tag_option_label(existing)
        )
    except Exception:
        pass

    set_tag_status(
        (
            f"Saved "
            f"{tag_color_emoji(color)} "
            f"{color} {tag_number}."
        ),
        "success"
    )


@service
async def incubator_delete_tag_from_helpers():

    tag_uid = str(
        state.get(
            "input_text.incubator_tag_edit_id"
        )
        or
        ""
    ).strip()

    if not tag_uid:

        set_tag_status(
            "No quail tag is currently loaded.",
            "warning"
        )
        return

    batches = await load_batches()

    batch, tag = find_tag_record(
        batches,
        tag_uid
    )

    if batch is None or tag is None:

        set_tag_status(
            "The quail tag record no longer exists.",
            "warning"
        )
        return

    display = (
        f"{tag_color_emoji(tag.get('color'))} "
        f"{tag.get('color')} "
        f"{tag.get('number')}"
    )

    batch["tags"] = [
        item
        for item in ensure_batch_tags(batch)
        if item.get(
            "uid"
        ) != tag_uid
    ]

    batch["updated_at"] = timestamp_now()

    await save_batches(
        batches
    )

    await update_sensors()

    refresh_tag_picker(
        batch
    )

    clear_tag_editor_helpers()

    set_tag_status(
        f"Deleted tag record {display}.",
        "warning"
    )


# ===============================================================
# ARCHIVE / RESTORE CURRENT EDITOR BATCH
#
# This SAVES editor changes before changing archive status.
# ===============================================================

@service
async def incubator_toggle_archive_from_helpers():

    batch_id = parse_batch_id(
        state.get(
            "input_text.incubator_edit_id"
        )
    )


    if batch_id is None:

        set_editor_status(
            "No batch is currently loaded.",
            "error"
        )

        return


    batches = await load_batches()


    batch = find_batch(
        batches,
        batch_id
    )


    if batch is None:

        set_editor_status(
            "Batch not found.",
            "error"
        )

        return


    try:

        # Save all current editor fields first.
        outcome = apply_editor_values(
            batch
        )


        was_archived = bool(
            batch.get(
                "archived",
                False
            )
        )


        if was_archived:

            # Restore
            batch[
                "archived"
            ] = False

            batch[
                "archived_at"
            ] = ""

        else:

            # Archive
            batch[
                "archived"
            ] = True

            batch[
                "archived_at"
            ] = timestamp_now()


        batch[
            "updated_at"
        ] = timestamp_now()


        await save_batches(
            batches
        )


        await update_sensors()


        set_boolean_helper(
            "input_boolean.incubator_edit_archived",
            not was_archived
        )


        if was_archived:

            set_editor_status(
                f"{batch['name']} restored to active batches.",
                "success"
            )

        else:

            if outcome["complete"]:

                extra = (
                    "All eggs accounted for."
                )

            else:

                extra = (
                    f"{outcome['unaccounted']} "
                    "egg(s) are still unaccounted."
                )


            set_editor_status(
                (
                    f"{batch['name']} archived. "
                    f"{extra}"
                ),
                "success"
            )


    except Exception as err:

        log.error(
            f"Archive operation failed: {err}"
        )


        set_editor_status(
            str(err),
            "error"
        )


# ===============================================================
# DIRECT ARCHIVE SERVICE
# ===============================================================

@service
async def incubator_archive_batch(
    id=None
):

    batch_id = parse_batch_id(
        id
    )


    if batch_id is None:
        return


    batches = await load_batches()


    batch = find_batch(
        batches,
        batch_id
    )


    if batch is None:
        return


    batch["archived"] = True

    batch[
        "archived_at"
    ] = timestamp_now()

    batch[
        "updated_at"
    ] = timestamp_now()


    await save_batches(
        batches
    )


    await update_sensors()


# ===============================================================
# DELETE BATCH
# ===============================================================

@service
async def incubator_delete_batch(
    id=None
):

    batch_id = parse_batch_id(
        id
    )


    if batch_id is None:

        log.error(
            "Delete called without a valid batch ID"
        )

        return


    batches = await load_batches()


    original_count = len(
        batches
    )


    batches = [

        batch

        for batch in batches

        if number(
            batch.get(
                "id"
            ),
            -1
        )
        != batch_id
    ]


    if len(
        batches
    ) == original_count:

        log.warning(
            f"Batch {batch_id} was not found"
        )

        return


    await save_batches(
        batches
    )


    await update_sensors()


    log.info(
        f"Deleted incubator batch {batch_id}"
    )


# ===============================================================
# DELETE CURRENT EDITOR BATCH
# ===============================================================

@service
async def incubator_delete_edit_batch():

    batch_id = parse_batch_id(
        state.get(
            "input_text.incubator_edit_id"
        )
    )


    if batch_id is None:

        set_editor_status(
            "No batch is currently loaded.",
            "error"
        )

        return


    await incubator_delete_batch(
        id=batch_id
    )


    set_editor_status(
        f"Batch #{batch_id} permanently deleted.",
        "warning"
    )


# ===============================================================
# MANUAL REFRESH
# ===============================================================

@service
async def incubator_refresh():

    await update_sensors()


# ===============================================================
# AUTOMATIC REFRESH
# ===============================================================

@time_trigger("startup")
@time_trigger("cron(0 * * * *)")
async def refresh():

    log.info(
        "Refreshing incubator sensors"
    )

    await update_sensors()