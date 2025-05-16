import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, \
    InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import asyncio
from calendar import monthrange
import random
import os

# ===== Настройка бота =====
logging.basicConfig(level=logging.INFO)
bot = Bot(token="BOT_TOKEN")
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
            [KeyboardButton(text="💡 Мотивация")],
            [KeyboardButton(text="➕ Добавить мотивацию")]
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


def homework_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить задание")],
            [KeyboardButton(text="Мои задания")],
            [KeyboardButton(text="Завершенные")],
            [KeyboardButton(text="Отметить выполнение")],
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

class AddMotivation(StatesGroup):
    waiting_for_file = State()

class MarkHomeworkDone(StatesGroup):
    waiting_for_id = State()

# Пути к папкам с мотивацией
MOTIVATION_IMG_DIR = "motivational_content/img"
MOTIVATION_VIDEO_DIR = "motivational_content/video"

# ===== Обработчики команд =====
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Я твой школьный органайзер. Что хочешь сделать?",
        reply_markup=main_menu_kb()
    )

@dp.message(F.text == "📚 Домашние задания")
async def homework_menu(message: types.Message):
    await message.answer(
        "Меню домашних заданий:",
        reply_markup=homework_menu_kb()
    )

@dp.message(F.text == "📅 Расписание")
async def schedule_menu(message: types.Message):
    await message.answer(
        "Меню расписания:",
        reply_markup=schedule_menu_kb()
    )

@dp.message(F.text == "💡 Мотивация")
async def motivation_from_button(message: types.Message):
    await send_motivation(message)

@dp.message(F.text == "➕ Добавить мотивацию")
async def ask_for_motivation_upload(message: types.Message, state: FSMContext):
    await message.answer("Пришли мне картинку, GIF или видео, которые ты хочешь добавить как мотивацию.")
    await state.set_state(AddMotivation.waiting_for_file)

@dp.message(AddMotivation.waiting_for_file)
async def receive_motivation_file(message: types.Message, state: FSMContext):
    try:
        file = None
        file_path = ""

        if message.photo:
            file = await bot.get_file(message.photo[-1].file_id)
            file_path = f"{MOTIVATION_IMG_DIR}/user_{message.from_user.id}_{file.file_unique_id}.jpg"
        elif message.video:
            file = await bot.get_file(message.video.file_id)
            file_path = f"{MOTIVATION_VIDEO_DIR}/user_{message.from_user.id}_{file.file_unique_id}.mp4"
        elif message.animation:  # Это обработка GIF
            file = await bot.get_file(message.animation.file_id)
            file_path = f"{MOTIVATION_VIDEO_DIR}/user_{message.from_user.id}_{file.file_unique_id}.gif"
        else:
            await message.answer("Пожалуйста, отправь картинку, GIF или видео.")
            return

        # Создаем папки если их нет
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        await bot.download_file(file.file_path, destination=file_path)
        await message.answer("✅ Мотивация добавлена! Спасибо!", reply_markup=main_menu_kb())
    except Exception as e:
        logging.error(f"Ошибка при получении мотивации: {e}")
        await message.answer("❌ Ошибка при загрузке файла.")
    finally:
        await state.clear()

@dp.message(Command("motivate"))
async def send_motivation(message: types.Message):
    try:
        # Получаем все доступные файлы
        all_files = []
        if os.path.exists(MOTIVATION_IMG_DIR):
            all_files.extend([("img", f) for f in os.listdir(MOTIVATION_IMG_DIR)])
        if os.path.exists(MOTIVATION_VIDEO_DIR):
            all_files.extend([("video", f) for f in os.listdir(MOTIVATION_VIDEO_DIR)])

        if not all_files:
            await message.answer("Мотивационные материалы скоро добавятся!")
            return

        # Выбираем случайный файл
        content_type, filename = random.choice(all_files)
        file_path = f"{MOTIVATION_IMG_DIR if content_type == 'img' else MOTIVATION_VIDEO_DIR}/{filename}"

        if content_type == "img":
            await message.reply_photo(
                FSInputFile(file_path),
                caption="💪 Ты справишься! Вот мотивация для тебя!"
            )
        else:
            # Для видео и GIF
            if filename.lower().endswith('.gif'):
                await message.reply_animation(
                    FSInputFile(file_path),
                    caption="🎬 Держи мотивирующую GIFку!"
                )
            else:
                await message.reply_video(
                    FSInputFile(file_path),
                    caption="🔥 Время показать, на что ты способен!"
                )

    except Exception as e:
        logging.error(f"Ошибка отправки мотивации: {e}")
        await message.answer("Что-то пошло не так 😢")

@dp.message(F.text == "Календарь")
async def show_calendar(message: types.Message):
    await message.answer(
        "Выбери дату:",
        reply_markup=generate_calendar()
    )

@dp.message(F.text == "Назад")
async def go_back_to_main_menu(message: types.Message):
    await message.answer("Возвращаюсь в главное меню:", reply_markup=main_menu_kb())

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

    current_state = await state.get_state()

    if current_state == "AddHomework:deadline":
        await state.update_data(deadline=selected_date)
        await callback.message.answer("Введите задание:", reply_markup=cancel_kb())
        await state.set_state(AddHomework.task)
    elif current_state == "AddScheduleEvent:date":
        await state.update_data(date=selected_date)
        await callback.message.answer("Выберите предмет:", reply_markup=subjects_kb())
        await state.set_state(AddScheduleEvent.subject)
    else:
        # Если дата выбрана без контекста (например, из меню календаря)
        await callback.message.answer("Выберите действие для этой даты:", reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Добавить задание"), KeyboardButton(text="Добавить событие")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        ))

    await callback.answer(f"Выбрана дата: {day}.{month}.{year}")

@dp.message(F.text == "Добавить событие")
async def add_schedule_event_start(message: types.Message, state: FSMContext):
    await message.answer("Выберите дату события (или нажмите 'Календарь'):",
                         reply_markup=ReplyKeyboardMarkup(
                             keyboard=[
                                 [KeyboardButton(text="Календарь")],
                                 [KeyboardButton(text="❌ Отмена")]
                             ],
                             resize_keyboard=True
                         ))
    await state.set_state(AddScheduleEvent.date)

# ===== Обработчики для домашних заданий =====
@dp.message(F.text == "Добавить задание")
async def add_homework_start(message: types.Message, state: FSMContext):
    await message.answer("Выберите предмет:", reply_markup=subjects_kb())
    await state.set_state(AddHomework.subject)

@dp.message(AddHomework.subject)
async def select_homework_subject(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_handler(message, state)
        return

    if message.text not in SUBJECTS:
        await message.answer("Пожалуйста, выберите предмет из списка:")
        return

    await state.update_data(subject=message.text)
    await message.answer(
        "Выберите дату выполнения (или нажмите 'Календарь' для выбора даты):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Календарь")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )
    )
    await state.set_state(AddHomework.deadline)

@dp.message(AddHomework.deadline)
async def select_homework_deadline(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_handler(message, state)
        return
    elif message.text == "Календарь":
        await message.answer("Выберите дату выполнения:", reply_markup=generate_calendar())
        return

    try:
        deadline = datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(deadline=deadline)
        await message.answer("Введите задание:", reply_markup=cancel_kb())
        await state.set_state(AddHomework.task)
    except ValueError:
        await message.answer("Пожалуйста, введите дату в формате ДД.ММ.ГГГГ или выберите из календаря")

@dp.message(AddHomework.task)
async def save_homework(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_handler(message, state)
        return

    data = await state.get_data()
    task = message.text

    db = SessionLocal()
    try:
        homework = Homework(
            user_id=message.from_user.id,
            subject=data['subject'],
            task=task,
            deadline=data.get('deadline')
        )
        db.add(homework)
        db.commit()

        response = (f"✅ Домашнее задание добавлено!\n\n"
                    f"📚 Предмет: {data['subject']}\n"
                    f"📝 Задание: {task}\n")

        if data.get('deadline'):
            response += f"📅 Срок выполнения: {data['deadline'].strftime('%d.%m.%Y')}"
        else:
            response += "⏰ Срок выполнения: не указан"

        await message.answer(response, reply_markup=homework_menu_kb())
    except Exception as e:
        db.rollback()
        await message.answer("❌ Ошибка при сохранении задания", reply_markup=homework_menu_kb())
        logging.error(f"Error saving homework: {e}")
    finally:
        db.close()
        await state.clear()

@dp.message(F.text == "Мои задания")
async def show_homeworks(message: types.Message):
    db = SessionLocal()
    try:
        homeworks = db.query(Homework) \
            .filter(Homework.user_id == message.from_user.id) \
            .filter(Homework.is_done == False) \
            .order_by(Homework.deadline.asc() if Homework.deadline is not None else Homework.created_at.asc()) \
            .all()

        if not homeworks:
            await message.answer("У вас нет активных домашних заданий")
            return

        response = ["📚 Ваши домашние задания:"]
        now = datetime.now()

        for hw in homeworks:
            if hw.deadline:
                time_left = hw.deadline - now
                total_seconds = int(time_left.total_seconds())

                if total_seconds <= 0:
                    time_passed = -total_seconds
                    days_passed = time_passed // 86400
                    hours_passed = (time_passed % 86400) // 3600
                    deadline_str = f"⌛️ Просрочено: {days_passed}д {hours_passed}ч"
                else:
                    days_left = total_seconds // 86400
                    hours_left = (total_seconds % 86400) // 3600
                    deadline_str = f"⏳ Осталось: {days_left}д {hours_left}ч"
            else:
                deadline_str = "🕰 Без срока"

            response.append(
                f"\n📌 {hw.subject}\n"
                f"📝 {hw.task[:50]}{'...' if len(hw.task) > 50 else ''}\n"
                f"{deadline_str}"
            )

        for i in range(0, len(response), 5):
            await message.answer("\n".join(response[i:i + 5]))

    except Exception as e:
        await message.answer("❌ Ошибка при получении заданий")
        logging.error(f"Error getting homeworks: {e}")
    finally:
        db.close()

@dp.message(F.text == "Завершенные")
async def show_completed_homeworks(message: types.Message):
    db = SessionLocal()
    try:
        homeworks = db.query(Homework) \
            .filter(Homework.user_id == message.from_user.id) \
            .filter(Homework.is_done == True) \
            .order_by(Homework.deadline.asc() if Homework.deadline is not None else Homework.created_at.asc()) \
            .all()

        if not homeworks:
            await message.answer("У вас нет завершенных домашних заданий")
            return

        response = ["✅ Завершенные задания:"]
        for hw in homeworks:
            deadline_str = f"до {hw.deadline.strftime('%d.%m.%Y')}" if hw.deadline else "без срока"
            response.append(
                f"\n📌 {hw.subject}\n"
                f"📝 {hw.task[:50]}{'...' if len(hw.task) > 50 else ''}\n"
                f"⏳ {deadline_str}"
            )

        for i in range(0, len(response), 5):
            await message.answer("\n".join(response[i:i + 5]))

    except Exception as e:
        await message.answer("❌ Ошибка при получении заданий")
        logging.error(f"Error getting homeworks: {e}")
    finally:
        db.close()

@dp.message(F.text == "Отметить выполнение")
async def mark_as_done_start(message: types.Message, state: FSMContext):
    db = SessionLocal()
    try:
        homeworks = db.query(Homework) \
            .filter(Homework.user_id == message.from_user.id) \
            .filter(Homework.is_done == False) \
            .order_by(Homework.deadline.asc() if Homework.deadline is not None else Homework.created_at.asc()) \
            .all()

        if not homeworks:
            await message.answer("У вас нет активных заданий для отметки")
            return

        response = ["📝 Выберите номер задания для отметки как выполненное:\n"]
        for i, hw in enumerate(homeworks, 1):
            deadline_str = f"до {hw.deadline.strftime('%d.%m.%Y')}" if hw.deadline else "без срока"
            response.append(
                f"{i}. {hw.subject}: {hw.task[:50]}{'...' if len(hw.task) > 50 else ''} ({deadline_str})"
            )

        response.append("\nНапишите номер задания, которое вы выполнили:")

        await message.answer("\n".join(response), reply_markup=ReplyKeyboardRemove())
        await state.update_data(homeworks=[hw.id for hw in homeworks])
        await state.set_state(MarkHomeworkDone.waiting_for_id)

    except Exception as e:
        await message.answer("❌ Ошибка при получении заданий")
        logging.error(f"Error getting homeworks: {e}")
    finally:
        db.close()

@dp.message(MarkHomeworkDone.waiting_for_id)
async def mark_homework_done(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Действие отменено", reply_markup=homework_menu_kb())
        return

    try:
        task_num = int(message.text)
        data = await state.get_data()
        homeworks_ids = data.get('homeworks', [])

        if task_num < 1 or task_num > len(homeworks_ids):
            await message.answer("Пожалуйста, введите корректный номер задания")
            return

        homework_id = homeworks_ids[task_num - 1]

        db = SessionLocal()
        try:
            homework = db.query(Homework).filter(Homework.id == homework_id).first()
            if homework:
                homework.is_done = True
                db.commit()
                await message.answer(f"✅ Задание '{homework.subject}' отмечено как выполненное!",
                                   reply_markup=homework_menu_kb())
            else:
                await message.answer("❌ Задание не найдено", reply_markup=homework_menu_kb())
        except Exception as e:
            db.rollback()
            await message.answer("❌ Ошибка при обновлении задания", reply_markup=homework_menu_kb())
            logging.error(f"Error updating homework: {e}")
        finally:
            db.close()

    except ValueError:
        await message.answer("Пожалуйста, введите номер задания цифрами")
        return

    await state.clear()

@dp.message(Command("cancel"))
@dp.message(F.text == "❌ Отмена")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return


    await state.clear()
    if current_state.startswith("AddHomework"):
        await message.answer("Действие отменено", reply_markup=homework_menu_kb())
    else:
        await message.answer("Действие отменено", reply_markup=schedule_menu_kb())

@dp.message(AddScheduleEvent.date)
async def select_event_date(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_handler(message, state)
        return
    elif message.text == "Календарь":
        await message.answer("Выберите дату:", reply_markup=generate_calendar())
        return

    try:
        event_date = datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(date=event_date)
        await message.answer("Выберите предмет:", reply_markup=subjects_kb())
        await state.set_state(AddScheduleEvent.subject)
    except ValueError:
        await message.answer("Пожалуйста, введите дату в формате ДД.ММ.ГГГГ или выберите из календаря.")

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

async def check_upcoming_events():
    while True:
        db = SessionLocal()
        try:
            tomorrow = datetime.now() + timedelta(days=1)
            events = db.query(ScheduleEvent) \
                .filter(ScheduleEvent.event_date >= datetime.now()) \
                .filter(ScheduleEvent.event_date <= tomorrow) \
                .all()

            for event in events:
                await bot.send_message(
                    event.user_id,
                    f"📢 Завтра {event.event_type} по {event.subject}! Время готовиться! 💪"
                )
                # Имитируем сообщение для вызова send_motivation
                fake_message = types.Message(
                    chat=types.Chat(id=event.user_id),
                    from_user=types.User(id=event.user_id)
                )
                await send_motivation(fake_message)

        except Exception as e:
            logging.error(f"Ошибка проверки событий: {e}")
        finally:
            db.close()
            await asyncio.sleep(3600)  # Проверка каждый час

async def on_startup():
    asyncio.create_task(check_upcoming_events())

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    asyncio.run(main())
