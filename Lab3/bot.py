import json
import logging
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, JobQueue

try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "data.json")
EMPLOYEES_CSV = os.path.join(BASE_DIR, "employees.csv")
EMPLOYEES_XLSX = os.path.join(BASE_DIR, "employees.xlsx")


def load_data() -> Dict[str, Any]:
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
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception as exc:
        logger.error("Failed to save data.json: %s", exc)


def get_timezone() -> pytz.BaseTzInfo:
    tz_name = os.getenv("TIMEZONE", "Europe/Moscow")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        logger.warning("Invalid TIMEZONE '%s', fallback to Europe/Moscow", tz_name)
        return pytz.timezone("Europe/Moscow")


def bold(text: str) -> str:
    return f"<b>{text}</b>"


def code(text: str) -> str:
    return f"<code>{text}</code>"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


def weekday_ru(dt: datetime) -> str:
    mapping = {0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"}
    return mapping[dt.weekday()]


async def events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    events_data: List[Dict[str, str]] = data.get("events", [])
    if not events_data:
        await update.effective_message.reply_text("Ближайших событий нет.")
        return
    lines = ["Предстоящие события (еженедельно):"]
    for ev in events_data:
        lines.append(f"- {ev.get('day')} {ev.get('time')}: {ev.get('title')} — {ev.get('description')}")
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


# Employees CSV/Excel

def _load_employees_df() -> Optional["pd.DataFrame"]:
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
        df.columns = [str(c).strip().lower() for c in df.columns]
        required = ["name", "department", "position", "email", "phone", "hire_date"]
        for col in required:
            if col not in df.columns:
                logger.error("Employees file missing column '%s'", col)
                return None
        return df
    except Exception as exc:
        logger.error("Failed to load employees file: %s", exc)
        return None


def _fmt_employee_row(row: Dict[str, Any]) -> str:
    return f"- {row.get('name')} — {row.get('position')} ({row.get('department')})\n  email: {row.get('email')}, phone: {row.get('phone')}"


def _ilike(series, needle: str):  # type: ignore
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
    rows = filtered.head(20).to_dict(orient="records")
    lines = ["Сотрудники:"] + [_fmt_employee_row(r) for r in rows]
    await update.effective_message.reply_text("\n".join(lines))


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


# Schedules

def weekday_ru(dt: datetime) -> str:
    mapping = {0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"}
    return mapping[dt.weekday()]


async def send_daily_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    tz = get_timezone()
    today_ru = weekday_ru(datetime.now(tz))
    data = load_data()
    msg = data.get("digests", {}).get(today_ru)
    if not msg:
        return
    for chat_id in data.get("subscribers", []):
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except Exception as exc:
            logger.warning("Failed to send digest to %s: %s", chat_id, exc)


async def send_event_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    events = data.get("events", [])
    if not events:
        return
    job_data = context.job.data or {}
    text = f"Напоминание: {job_data.get('title')} в {job_data.get('time')}. {job_data.get('description')}"
    for chat_id in data.get("subscribers", []):
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as exc:
            logger.warning("Failed to send event reminder to %s: %s", chat_id, exc)


def schedule_jobs(app: Application) -> None:
    tz = get_timezone()
    jq: JobQueue = app.job_queue
    jq.run_daily(send_daily_digest, time=time(hour=9, minute=0, tzinfo=tz), name="daily_digest")
    data = load_data()
    for ev in data.get("events", []):
        try:
            weekdays = {"Понедельник": 0, "Вторник": 1, "Среда": 2, "Четверг": 3, "Пятница": 4, "Суббота": 5, "Воскресенье": 6}
            weekday_idx = weekdays[ev.get("day", "Понедельник")]
            ev_time = datetime.strptime(ev.get("time", "00:00"), "%H:%M").time()
            dt_dummy = datetime.now(tz).replace(hour=ev_time.hour, minute=ev_time.minute, second=0, microsecond=0)
            remind_dt = dt_dummy - timedelta(minutes=15)
            remind_time = time(hour=remind_dt.hour, minute=remind_dt.minute, tzinfo=tz)
            jq.run_daily(
                send_event_reminder,
                time=remind_time,
                days=(weekday_idx,),
                data={"title": ev.get("title"), "time": ev.get("time"), "description": ev.get("description")},
                name=f"reminder_{weekday_idx}_{ev.get('time')}",
            )
        except Exception as exc:
            logger.warning("Failed to schedule reminder for event %s: %s", ev, exc)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update: %s", context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("Произошла ошибка. Попробуйте ещё раз позже.")
    except Exception:
        pass


def build_application() -> Application:
    env_path = Path(__file__).with_name('.env')
    load_dotenv(dotenv_path=str(env_path), override=True)
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Provide it via .env")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("company", company))
    app.add_handler(CommandHandler("team", team))
    app.add_handler(CommandHandler("contacts", contacts))
    app.add_handler(CommandHandler("events", events))
    app.add_handler(CommandHandler("digest", digest))
    app.add_handler(CommandHandler("departments", departments))
    app.add_handler(CommandHandler("staff", staff))
    app.add_handler(CommandHandler("find", find))
    app.add_error_handler(error_handler)
    schedule_jobs(app)
    return app


def main() -> None:
    app = build_application()
    use_webhook = os.getenv("USE_WEBHOOK", "0") == "1"
    if not use_webhook:
        logger.info("Starting in polling mode...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        return

    # Webhook mode with ngrok
    host = os.getenv("WEBHOOK_LISTEN", "0.0.0.0")
    port = int(os.getenv("WEBHOOK_PORT", "8080"))
    path = os.getenv("WEBHOOK_PATH", "/webhook")
    public_base = os.getenv("PUBLIC_URL")  # e.g. https://xxx.ngrok-free.app
    if not public_base:
        raise RuntimeError("PUBLIC_URL must be set for webhook mode (your ngrok URL)")
    webhook_url = public_base.rstrip("/") + path
    logger.info("Starting webhook on %s:%s, url=%s", host, port, webhook_url)
    app.run_webhook(listen=host, port=port, url_path=path.lstrip("/"), webhook_url=webhook_url, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()


