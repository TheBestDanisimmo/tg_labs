import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

import pytz
from dotenv import load_dotenv
from pathlib import Path
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    JobQueue,
)
try:
    import pandas as pd  # type: ignore
except Exception:  # noqa: BLE001
    pd = None  # Loaded lazily; handlers will validate availability


# Configure logging early
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ----------------------------
# Data access helpers
# ----------------------------

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")


def load_data() -> Dict[str, Any]:
    """Load JSON data from DATA_FILE with basic error handling."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("data.json not found at %s", DATA_FILE)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse data.json: %s", exc)
        return {}


def save_data(data: Dict[str, Any]) -> None:
    """Persist JSON data back to DATA_FILE safely."""
    try:
        tmp_path = DATA_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DATA_FILE)
    except Exception as exc:  # noqa: BLE001 - top-level safety
        logger.error("Failed to save data.json: %s", exc)


def get_timezone() -> pytz.BaseTzInfo:
    tz_name = os.getenv("TIMEZONE", "Europe/Moscow")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        logger.warning("Invalid TIMEZONE '%s', falling back to Europe/Moscow", tz_name)
        return pytz.timezone("Europe/Moscow")


# ----------------------------
# Formatting helpers
# ----------------------------

def bold(text: str) -> str:
    return f"<b>{text}</b>"


def code(text: str) -> str:
    return f"<code>{text}</code>"


# ----------------------------
# Command handlers
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register user for digests and greet."""
    user_first = update.effective_user.first_name if update.effective_user else ""
    data = load_data()
    subscribers: List[int] = data.get("subscribers", [])
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is not None and chat_id not in subscribers:
        subscribers.append(chat_id)
        data["subscribers"] = subscribers
        save_data(data)

    text = (
        f"Привет, {user_first}! Я бот компании {bold('ТралалелоТралала')}\n"
        "Помогу с информацией о компании, контактах, событиях и пришлю дайджест.\n"
        f"Посмотри {code('/help')} для списка команд."
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Доступные команды:\n"
        "/start — приветствие и подписка на дайджесты\n"
        "/help — список команд\n"
        "/company — информация о компании\n"
        "/team — состав команды\n"
        "/contacts — контакты сотрудников\n"
        "/events — предстоящие события\n"
        "/digest — сегодняшний дайджест\n"
        "/departments — отделы из файла сотрудников\n"
        "/staff — список сотрудников (опц. отдел)\n"
        "/find — поиск сотрудников по имени/должности/отделу"
    )
    await update.effective_message.reply_text(text)


async def company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    company_info = data.get("company", {})
    name = company_info.get("name", "Компания")
    industry = company_info.get("industry", "Сфера деятельности")
    text = f"{bold(name)}\nСфера: {industry}"
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


async def team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    team_members = data.get("team", [])
    if not team_members:
        await update.effective_message.reply_text("Нет данных о команде.")
        return
    lines = ["Состав команды:"]
    for member in team_members:
        lines.append(f"- {member.get('name')} — {member.get('role')}")
    await update.effective_message.reply_text("\n".join(lines))


async def contacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    contacts_data = data.get("contacts", {})
    ivan_phone = contacts_data.get("ivanovs_phone", "—")
    oleg_email = contacts_data.get("oleg_email", "—")
    oleg_phone = contacts_data.get("oleg_phone", "—")
    text = (
        f"Ивановы (общий): {code(ivan_phone)}\n"
        f"Олег Арсипов: {code(oleg_email)}, {code(oleg_phone)}"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


def _weekday_name(dt: datetime, tz: pytz.BaseTzInfo) -> str:
    return dt.astimezone(tz).strftime("%A")


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    events_data: List[Dict[str, str]] = data.get("events", [])
    if not events_data:
        await update.effective_message.reply_text("Ближайших событий нет.")
        return
    tz = get_timezone()
    lines = ["Предстоящие события (еженедельно):"]
    # Keep the list short and readable
    for ev in events_data:
        lines.append(
            f"- {ev.get('day')} {ev.get('time')}: {ev.get('title')} — {ev.get('description')}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tz = get_timezone()
    today_weekday_ru = weekday_ru(datetime.now(tz))
    data = load_data()
    digests = data.get("digests", {})
    msg = digests.get(today_weekday_ru)
    if not msg:
        await update.effective_message.reply_text("На сегодня нет дайджеста.")
        return
    await update.effective_message.reply_text(msg)


# ----------------------------
# Employees data (CSV/Excel)
# ----------------------------

EMPLOYEES_CSV = os.path.join(os.path.dirname(__file__), "employees.csv")
EMPLOYEES_XLSX = os.path.join(os.path.dirname(__file__), "employees.xlsx")


def _load_employees_df() -> Optional["pd.DataFrame"]:
    """Load employees from CSV or Excel. Returns None on error.

    Expected columns: name,department,position,email,phone,hire_date
    """
    if pd is None:
        logger.warning("pandas is not installed; CSV/Excel features are unavailable")
        return None
    try:
        if os.path.exists(EMPLOYEES_CSV):
            df = pd.read_csv(EMPLOYEES_CSV)
        elif os.path.exists(EMPLOYEES_XLSX):
            df = pd.read_excel(EMPLOYEES_XLSX)
        else:
            logger.info("No employees file found (CSV/XLSX)")
            return None
        # Normalize columns
        df.columns = [str(c).strip().lower() for c in df.columns]
        required = ["name", "department", "position", "email", "phone", "hire_date"]
        for col in required:
            if col not in df.columns:
                logger.error("Employees file missing column '%s'", col)
                return None
        return df
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load employees file: %s", exc)
        return None


def _fmt_employee_row(row: Dict[str, Any]) -> str:
    return (
        f"- {row.get('name')} — {row.get('position')} ({row.get('department')})\n"
        f"  email: {row.get('email')}, phone: {row.get('phone')}"
    )


def _ilike(series, needle: str):  # type: ignore[no-untyped-def]
    pattern = str(needle).strip().lower()
    return series.astype(str).str.lower().str.contains(pattern, na=False)


async def departments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    df = _load_employees_df()
    if df is None or df.empty:
        await update.effective_message.reply_text("Файл сотрудников не найден или пуст.")
        return
    depts = sorted(d for d in df["department"].dropna().unique())
    if not depts:
        await update.effective_message.reply_text("Отделы не найдены.")
        return
    await update.effective_message.reply_text("Отделы:\n" + "\n".join(f"- {d}" for d in depts))


async def staff(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List staff. Usage: /staff [отдел]"""
    df = _load_employees_df()
    if df is None or df.empty:
        await update.effective_message.reply_text("Файл сотрудников не найден или пуст.")
        return
    args = context.args or []
    filtered = df
    if args:
        dept_query = " ".join(args)
        filtered = df[_ilike(df["department"], dept_query)]
    if filtered.empty:
        await update.effective_message.reply_text("Сотрудники не найдены по заданному фильтру.")
        return
    # Limit to 20 to keep messages short
    rows = filtered.head(20).to_dict(orient="records")
    lines = ["Сотрудники:"] + [_fmt_employee_row(r) for r in rows]
    await update.effective_message.reply_text("\n".join(lines))


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Full-text like search across name/department/position.

    Usage: /find маркет
    """
    df = _load_employees_df()
    if df is None or df.empty:
        await update.effective_message.reply_text("Файл сотрудников не найден или пуст.")
        return
    query = " ".join(context.args or []).strip()
    if not query:
        await update.effective_message.reply_text("Использование: /find <строка поиска>")
        return
    mask = _ilike(df["name"], query) | _ilike(df["department"], query) | _ilike(df["position"], query)
    result = df[mask]
    if result.empty:
        await update.effective_message.reply_text("Ничего не найдено.")
        return
    rows = result.head(20).to_dict(orient="records")
    lines = ["Найдено:"] + [_fmt_employee_row(r) for r in rows]
    await update.effective_message.reply_text("\n".join(lines))


# ----------------------------
# Scheduling: digests and reminders
# ----------------------------

def weekday_ru(dt: datetime) -> str:
    # Monday=0 ... Sunday=6
    mapping = {
        0: "Понедельник",
        1: "Вторник",
        2: "Среда",
        3: "Четверг",
        4: "Пятница",
        5: "Суббота",
        6: "Воскресенье",
    }
    return mapping[dt.weekday()]


def ru_to_py_weekday(ru: str) -> int:
    mapping = {
        "Понедельник": 0,
        "Вторник": 1,
        "Среда": 2,
        "Четверг": 3,
        "Пятница": 4,
        "Суббота": 5,
        "Воскресенье": 6,
    }
    return mapping[ru]


async def send_daily_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    tz = get_timezone()
    today_ru = weekday_ru(datetime.now(tz))
    data = load_data()
    digests = data.get("digests", {})
    msg = digests.get(today_ru)
    if not msg:
        return
    for chat_id in data.get("subscribers", []):
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send digest to %s: %s", chat_id, exc)


async def send_event_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    events_data: List[Dict[str, str]] = data.get("events", [])
    if not events_data:
        return
    job_data = context.job.data or {}
    title = job_data.get("title")
    time_str = job_data.get("time")
    description = job_data.get("description")
    text = f"Напоминание: {title} в {time_str}. {description}"
    for chat_id in data.get("subscribers", []):
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send event reminder to %s: %s", chat_id, exc)


def schedule_jobs(app: Application) -> None:
    tz = get_timezone()
    jq: JobQueue = app.job_queue

    # Daily digest at 09:00 local time
    jq.run_daily(
        send_daily_digest,
        time=time(hour=9, minute=0, tzinfo=tz),
        name="daily_digest",
    )

    # Event reminders 15 minutes before the event time, weekly
    data = load_data()
    for ev in data.get("events", []):
        try:
            weekday_idx = ru_to_py_weekday(ev.get("day", ""))
            ev_time = datetime.strptime(ev.get("time", "00:00"), "%H:%M").time()
            # Subtract 15 minutes for reminder
            dt_dummy = datetime.now(tz).replace(hour=ev_time.hour, minute=ev_time.minute, second=0, microsecond=0)
            remind_dt = dt_dummy - timedelta(minutes=15)
            remind_time = time(hour=remind_dt.hour, minute=remind_dt.minute, tzinfo=tz)
            jq.run_daily(
                send_event_reminder,
                time=remind_time,
                days=(weekday_idx,),
                data={
                    "title": ev.get("title"),
                    "time": ev.get("time"),
                    "description": ev.get("description"),
                },
                name=f"reminder_{weekday_idx}_{ev.get('time')}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to schedule reminder for event %s: %s", ev, exc)


# ----------------------------
# Error handler
# ----------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update: %s", context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "Произошла ошибка. Попробуйте ещё раз позже."
            )
    except Exception:  # noqa: BLE001 - avoid cascading failures
        pass


# ----------------------------
# Entry point
# ----------------------------

def build_application() -> Application:
    # Explicitly load .env from the project directory to avoid CWD issues
    env_path = Path(__file__).with_name('.env')
    load_dotenv(dotenv_path=str(env_path), override=True)
    token = os.getenv("BOT_TOKEN")
    if not token and env_path.exists():
        try:
            with env_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.lstrip('\ufeff').strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("BOT_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                        if token:
                            os.environ["BOT_TOKEN"] = token
                        break
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read .env manually: %s", exc)
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Provide it via environment or .env file.")

    application = ApplicationBuilder().token(token).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("company", company))
    application.add_handler(CommandHandler("team", team))
    application.add_handler(CommandHandler("contacts", contacts))
    application.add_handler(CommandHandler("events", events))
    application.add_handler(CommandHandler("digest", digest))
    # Employees
    application.add_handler(CommandHandler("departments", departments))
    application.add_handler(CommandHandler("staff", staff))
    application.add_handler(CommandHandler("find", find))

    # Errors
    application.add_error_handler(error_handler)

    # Jobs
    schedule_jobs(application)

    return application


def main() -> None:
    app = build_application()
    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()


