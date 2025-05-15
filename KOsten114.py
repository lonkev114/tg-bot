import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, \
    InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import asyncio
from calendar import monthrange

# ===== Настройка бота =====
logging.basicConfig(level=logging.INFO)
bot = Bot(token="7575468144:AAGKSroDpaRj5-ybUPLYcuPIRviM1P2P58M")
dp = Dispatcher()

# ===== Списки предметов и типов событий =====
SUBJECTS = ["Математика", "Русский язык", "Биология", "География",
            "История", "Обществознание", "Физика", "Химия"]
EVENT_TYPES = ["Контрольная работа", "Самостоятельная работа", "Лабораторная", "Экзамен"]

# ===== База данных =====
Base = declarative_base()


class Homework(Base):
    __tablename__ = "homeworks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    subject = Column(String(100), nullable=False)
    task = Column(String(500), nullable=False)
    deadline = Column(DateTime)
    is_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)


class ScheduleEvent(Base):
    __tablename__ = "schedule_events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    subject = Column(String(100), nullable=False)
    event_type = Column(String(50), nullable=False)
    event_date = Column(DateTime, nullable=False)
    description = Column(String(300))
    created_at = Column(DateTime, default=datetime.now)


engine = create_engine("sqlite:///./school_bot.db")
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ===== Клавиатуры =====
def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Домашние задания")],
            [KeyboardButton(text="📅 Расписание")],
        ],
        resize_keyboard=True
    )


def schedule_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить событие")],
            [KeyboardButton(text="Мои события")],
            [KeyboardButton(text="Календарь")],
            [KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True
    )


def subjects_kb():
    """Клавиатура для выбора предмета"""
    return ReplyKeyboardMarkup(
        keyboard=[
                     [KeyboardButton(text=subject)] for subject in SUBJECTS
                 ] + [[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def event_types_kb():
    """Клавиатура для выбора типа события"""
    return ReplyKeyboardMarkup(
        keyboard=[
                     [KeyboardButton(text=event_type)] for event_type in EVENT_TYPES
                 ] + [[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def cancel_kb():
    """Клавиатура с кнопкой отмены"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )


def generate_calendar(year=None, month=None):
    now = datetime.now()
    if not year: year = now.year
    if not month: month = now.month

    # Создаем заголовок календаря
    month_name = datetime(year, month, 1).strftime('%B %Y')
    keyboard = [
        [InlineKeyboardButton(text=month_name, callback_data="ignore")],
        [
            InlineKeyboardButton(text="Пн", callback_data="ignore"),
            InlineKeyboardButton(text="Вт", callback_data="ignore"),
            InlineKeyboardButton(text="Ср", callback_data="ignore"),
            InlineKeyboardButton(text="Чт", callback_data="ignore"),
            InlineKeyboardButton(text="Пт", callback_data="ignore"),
            InlineKeyboardButton(text="Сб", callback_data="ignore"),
            InlineKeyboardButton(text="Вс", callback_data="ignore")
        ],
    ]

    # Получаем первый день месяца и количество дней
    month_days = monthrange(year, month)[1]
    first_weekday = datetime(year, month, 1).weekday()

    # Создаем строки с днями
    day = 1
    for week in range(6):
        if day > month_days: break
        row = []
        for weekday in range(7):
            if (week == 0 and weekday < first_weekday) or day > month_days:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                row.append(InlineKeyboardButton(
                    text=str(day),
                    callback_data=f"calendar_day_{year}_{month}_{day}"
                ))
                day += 1
        keyboard.append(row)

    # Добавляем кнопки навигации
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    keyboard.append([
        InlineKeyboardButton(text="◀️", callback_data=f"calendar_nav_{prev_year}_{prev_month}"),
        InlineKeyboardButton(text="Сегодня", callback_data=f"calendar_nav_{now.year}_{now.month}"),
        InlineKeyboardButton(text="▶️", callback_data=f"calendar_nav_{next_year}_{next_month}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ===== States (FSM) =====
class AddHomework(StatesGroup):
    subject = State()
    task = State()
    deadline = State()


class AddScheduleEvent(StatesGroup):
    subject = State()
    event_type = State()
    date = State()
    description = State()


# ===== Обработчики команд =====
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Я твой школьный органайзер. Что хочешь сделать?",
        reply_markup=main_menu_kb()
    )


@dp.message(F.text == "📅 Расписание")
async def schedule_menu(message: types.Message):
    await message.answer(
        "Меню расписания:",
        reply_markup=schedule_menu_kb()
    )


@dp.message(F.text == "Календарь")
async def show_calendar(message: types.Message):
    await message.answer(
        "Выбери дату:",
        reply_markup=generate_calendar()
    )


@dp.callback_query(F.data.startswith("calendar_nav_"))
async def calendar_navigation(callback: types.CallbackQuery):
    _, _, year, month = callback.data.split("_")
    await callback.message.edit_reply_markup(
        reply_markup=generate_calendar(int(year), int(month))
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("calendar_day_"))
async def select_date(callback: types.CallbackQuery, state: FSMContext):
    _, _, year, month, day = callback.data.split("_")
    selected_date = datetime(int(year), int(month), int(day))
    await state.update_data(date=selected_date)
    await callback.message.answer(
        f"Выбрана дата: {day}.{month}.{year}\n"
        "Выбери предмет:",
        reply_markup=subjects_kb()
    )
    await state.set_state(AddScheduleEvent.subject)
    await callback.answer()


@dp.message(Command("cancel"))
@dp.message(F.text == "❌ Отмена")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer(
        "Действие отменено",
        reply_markup=schedule_menu_kb()
    )


@dp.message(AddScheduleEvent.subject)
async def select_subject(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_handler(message, state)
        return

    if message.text not in SUBJECTS:
        await message.answer("Пожалуйста, выберите предмет из списка:")
        return

    await state.update_data(subject=message.text)
    await message.answer(
        "Выберите тип события:",
        reply_markup=event_types_kb()
    )
    await state.set_state(AddScheduleEvent.event_type)


@dp.message(AddScheduleEvent.event_type)
async def select_event_type(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_handler(message, state)
        return

    if message.text not in EVENT_TYPES:
        await message.answer("Пожалуйста, выберите тип события из списка:")
        return

    await state.update_data(event_type=message.text)
    await message.answer(
        "Введите описание события (или нажмите /skip чтобы пропустить):",
        reply_markup=cancel_kb()
    )
    await state.set_state(AddScheduleEvent.description)


@dp.message(AddScheduleEvent.description)
async def save_event(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_handler(message, state)
        return

    data = await state.get_data()
    description = None if message.text == "/skip" else message.text

    # Сохраняем событие в БД
    db = SessionLocal()
    try:
        event = ScheduleEvent(
            user_id=message.from_user.id,
            subject=data['subject'],
            event_type=data['event_type'],
            event_date=data['date'],
            description=description
        )
        db.add(event)
        db.commit()

        await message.answer(
            f"✅ Событие добавлено!\n\n"
            f"📚 Предмет: {data['subject']}\n"
            f"📝 Тип: {data['event_type']}\n"
            f"📅 Дата: {data['date'].strftime('%d.%m.%Y')}\n"
            f"📄 Описание: {description if description else 'нет'}",
            reply_markup=schedule_menu_kb()
        )
    except Exception as e:
        db.rollback()
        await message.answer(
            "❌ Ошибка при сохранении события",
            reply_markup=schedule_menu_kb()
        )
        logging.error(f"Error saving event: {e}")
    finally:
        db.close()
        await state.clear()


@dp.message(F.text == "Мои события")
async def show_events(message: types.Message):
    db = SessionLocal()
    try:
        # Берем события начиная с сегодняшнего дня
        today = datetime.now().date()
        events = db.query(ScheduleEvent) \
            .filter(ScheduleEvent.user_id == message.from_user.id) \
            .filter(ScheduleEvent.event_date >= today) \
            .order_by(ScheduleEvent.event_date) \
            .all()

        if not events:
            await message.answer("У вас нет запланированных событий")
            return

        response = ["📅 Ваши ближайшие события:"]
        for event in events:
            response.append(
                f"\n📌 {event.event_date.strftime('%d.%m.%Y')}\n"
                f"📚 {event.subject} - {event.event_type}\n"
                f"📄 {event.description if event.description else 'без описания'}"
            )

        # Разбиваем на несколько сообщений если слишком длинное
        for i in range(0, len(response), 5):
            await message.answer("\n".join(response[i:i + 5]))

    except Exception as e:
        await message.answer("❌ Ошибка при получении событий")
        logging.error(f"Error getting events: {e}")
    finally:
        db.close()


# ===== Проверка БД =====
@dp.message(Command("db_check"))
async def db_check(message: types.Message):
    db = SessionLocal()

    # Получаем статистику
    hw_count = db.query(func.count(Homework.id)).filter(Homework.user_id == message.from_user.id).scalar()
    events_count = db.query(func.count(ScheduleEvent.id)).filter(ScheduleEvent.user_id == message.from_user.id).scalar()

    # Получаем последние 3 записи
    last_hw = db.query(Homework).filter(Homework.user_id == message.from_user.id) \
        .order_by(Homework.created_at.desc()).limit(3).all()
    last_events = db.query(ScheduleEvent).filter(ScheduleEvent.user_id == message.from_user.id) \
        .order_by(ScheduleEvent.created_at.desc()).limit(3).all()

    db.close()

    response = (
        f"📊 Статистика БД:\n"
        f"Домашних заданий: {hw_count}\n"
        f"Событий в расписании: {events_count}\n\n"
        f"Последние задания:\n"
    )

    for hw in last_hw:
        response += f"- {hw.subject}: {hw.task[:20]}... (до {hw.deadline.strftime('%d.%m.%Y') if hw.deadline else 'нет срока'})\n"

    response += "\nПоследние события:\n"
    for event in last_events:
        response += f"- {event.subject}: {event.event_type} ({event.event_date.strftime('%d.%m.%Y')})\n"

    await message.answer(response)


# ===== Запуск бота =====
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())