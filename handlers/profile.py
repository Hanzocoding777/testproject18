import logging
import re
import aiohttp
from typing import Dict, List, Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, Application
)

from handlers.utils import process_team_roles
from constants import *

logger = logging.getLogger(__name__)

# Клавиатуры для личного кабинета
def get_profile_inline_keyboard():
    """Inline клавиатура для личного кабинета."""
    keyboard = [
        [InlineKeyboardButton("👥 Мои команды", callback_data="profile_teams")],
        [InlineKeyboardButton("➕ Создать команду", callback_data="profile_create_team")],
        [InlineKeyboardButton("🔍 Проверить статус регистрации", callback_data="profile_check_status")],
        [InlineKeyboardButton("◀️ В главное меню", callback_data="profile_main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_profile_inline_button():
    """Inline кнопка возврата в личный кабинет."""
    keyboard = [[InlineKeyboardButton("◀️ Назад в личный кабинет", callback_data="profile_back")]]
    return InlineKeyboardMarkup(keyboard)

# Обычные клавиатуры (для ввода текста)
def get_back_to_profile_keyboard():
    """Клавиатура с кнопкой Назад в личный кабинет."""
    keyboard = [
        [KeyboardButton("◀️ Назад в личный кабинет")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_profile_keyboard():
    """Обычная клавиатура для личного кабинета."""
    keyboard = [
        [KeyboardButton("👥 Мои команды")],
        [KeyboardButton("➕ Создать команду")],
        [KeyboardButton("🔍 Проверить статус регистрации")],
        [KeyboardButton("◀️ В главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Обработчики личного кабинета
async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню личного кабинета."""
    user = update.effective_user
    
    message_text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"Добро пожаловать, {user.first_name}!\n\n"
        f"Здесь вы можете управлять своими командами, создавать новые и проверять статус регистрации."
    )
    
    # Если это callback_query, редактируем сообщение
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text=message_text,
            reply_markup=get_profile_inline_keyboard(),
            parse_mode="HTML"
        )
    else:
        # Если это обычное сообщение, отправляем новое
        await update.message.reply_text(
            text=message_text,
            reply_markup=get_profile_inline_keyboard(),
            parse_mode="HTML"
        )
    
    return PROFILE_MENU

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться в главное меню из личного кабинета."""
    query = update.callback_query
    await query.answer()
    
    # Создаем главную клавиатуру
    from main import get_main_keyboard  # Импортируем здесь, чтобы избежать циклических импортов
    
    # Удаляем сообщение с кнопками профиля
    await query.message.delete()
    
    # Отправляем новое сообщение с главным меню
    await query.message.reply_text(
        "Вы вернулись в главное меню. Выберите нужное действие:",
        reply_markup=get_main_keyboard()
    )
    
    return ConversationHandler.END

async def show_my_teams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список команд пользователя."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    user_id = query.from_user.id
    
    # Получаем команды пользователя
    teams = db.get_user_teams(user_id)
    
    if not teams:
        await query.edit_message_text(
            "🔍 У вас пока нет созданных команд.\n\n"
            "Вы можете создать новую команду, нажав на кнопку \"➕ Создать команду\".",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    # Формируем сообщение со списком команд
    message = "👥 <b>Ваши команды:</b>\n\n"
    
    for idx, team in enumerate(teams, 1):
        status_emoji = "📝" if team["status"] == "draft" else "⏳" if team["status"] == "pending" else "✅" if team["status"] == "approved" else "❌"
        message += f"{idx}. {status_emoji} <b>{team['team_name']}</b>\n"
        
        # Добавляем краткую информацию о команде
        player_count = len(team["players"])
        message += f"   Участников: {player_count}\n"
        message += f"   Статус: {TEAM_STATUS.get(team['status'], 'Неизвестно')}\n\n"
    
    # Создаем инлайн-клавиатуру для выбора команды
    keyboard = []
    for team in teams:
        keyboard.append([
            InlineKeyboardButton(f"{team['team_name']} ({len(team['players'])} игроков)", callback_data=f"view_team_{team['id']}")
        ])
    
    # Добавляем кнопку назад
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="profile_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message + "\nВыберите команду для просмотра подробной информации:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    return PROFILE_MENU

async def view_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Просмотр информации о конкретной команде."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    user_id = query.from_user.id
    
    # Извлекаем ID команды из callback_data
    team_id = int(query.data.split("_")[2])
    
    # Получаем информацию о команде
    team = db.get_team_by_id(team_id)
    
    if not team:
        await query.edit_message_text(
            "Команда не найдена или была удалена.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")
            ]])
        )
        return PROFILE_MENU
    
    # Проверяем, является ли пользователь участником/капитаном команды
    is_member = any(p.get("telegram_id") == user_id for p in team["players"])
    is_captain = any(p.get("is_captain", False) and p.get("telegram_id") == user_id for p in team["players"])
    
    if not is_member:
        await query.edit_message_text(
            "У вас нет доступа к просмотру этой команды.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")
            ]])
        )
        return PROFILE_MENU
    
    # Форматируем информацию о команде
    message = await format_team_info(team, is_captain=is_captain)
    
    # Сохраняем ID текущей команды в контексте
    context.user_data["current_team_id"] = team_id
    
    # Создаем клавиатуру действий
    keyboard = []
    
    # Добавляем кнопки для игроков
    player_buttons = []
    for player in team["players"]:
        player_buttons.append(
            InlineKeyboardButton(
                f"{player['nickname']} (@{player['telegram_username']})",
                callback_data=f"player_{player['id']}"
            )
        )
    
    # Добавляем каждого игрока отдельной кнопкой
    for button in player_buttons:
        keyboard.append([button])
    
    # Добавляем кнопки действий для капитана
    if is_captain:
        action_buttons = []
        
        # Кнопка редактирования названия (для любых статусов)
        action_buttons.append(
            InlineKeyboardButton("✏️ Изменить название", callback_data="edit_team_name")
        )
        
        # Кнопка добавления игрока (для любых статусов)
        action_buttons.append(
            InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")
        )
        
        # Кнопка регистрации на турнир (только для черновиков)
        if team["status"] == "draft":
            action_buttons.append(
                InlineKeyboardButton("📝 Зарегистрировать на турнир", callback_data="register_team")
            )
        
        # Кнопка отмены регистрации
        action_buttons.append(
            InlineKeyboardButton("❌ Удалить команду", callback_data="cancel_team")
        )
        
        # Добавляем кнопки действий
        for button in action_buttons:
            keyboard.append([button])
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return PROFILE_MENU

async def format_team_info(team, is_captain=False) -> str:
    """
    Форматирует информацию о команде для отображения.
    
    Args:
        team: Словарь с данными о команде
        is_captain: True, если пользователь является капитаном
        
    Returns:
        Отформатированное сообщение HTML
    """
    # Переводим статус на русский
    status_text = TEAM_STATUS.get(team["status"], "Неизвестно")
    
    # Находим капитана
    captain = None
    for player in team["players"]:
        if player.get("is_captain", False):
            captain = player
            break
    
    # Формируем список всех игроков, начиная с капитана
    all_players = []
    if captain:
        all_players.append(captain)  # Капитан первым
    
    # Добавляем остальных игроков
    for player in team["players"]:
        if not player.get("is_captain", False):
            all_players.append(player)
    
    # Формируем список игроков
    players_list = ""
    for idx, player in enumerate(all_players, 1):
        player_username = f"(@{player['telegram_username']})" if player.get('telegram_username') else ""
        discord_info = f" Discord: {player.get('discord_username', 'Не указан')}" if player.get('discord_username') else ""
        players_list += f"{idx}. {player['nickname']} {player_username}{discord_info}\n"
    
    # Базовое сообщение
    message = (
        "🎮 <b>Информация о команде:</b>\n\n"
        f"🏷️ <b>Название команды:</b> {team['team_name']}\n"
        f"📅 <b>Дата создания:</b> {team['registration_date']}\n"
        f"📊 <b>Статус:</b> {status_text}\n"
    )
    
    # Добавляем информацию о турнире, если есть
    if team.get("tournament_id") and team.get("tournament_name"):
        message += f"🏆 <b>Зарегистрирована на турнир:</b> {team['tournament_name']}\n"
        if team.get("tournament_date"):
            message += f"📆 <b>Дата проведения турнира:</b> {team['tournament_date']}\n"
    
    # Добавляем контактные данные капитана, если они указаны
    if team.get("captain_contact"):
        message += f"📱 <b>Контакт капитана:</b> {team['captain_contact']}\n"
    
    # Добавляем информацию о капитане
    if captain:
        message += f"👨‍✈️ <b>Капитан:</b> {captain['nickname']} (@{captain['telegram_username']})\n"
        if captain.get('discord_username'):
            message += f"🎮 <b>Discord капитана:</b> {captain['discord_username']}\n"
    
    # Добавляем комментарий администратора, если он есть
    if team.get("admin_comment"):
        message += f"\n💬 <b>Комментарий администратора:</b>\n{team['admin_comment']}\n"
    
    # Добавляем список игроков
    message += f"<b>Игроки команды:</b>\n\n{players_list}"
    
    # Дополнительная информация для капитана
    if is_captain:
        if team["status"] == "draft":
            message += (
                "\n📝 <b>Команда в стадии черновика (не зарегистрирована).</b>\n"
                f"Для регистрации на турнир необходимо минимум {MIN_PLAYERS + 1} игроков (включая капитана).\n"
                f"Максимум разрешено {MAX_PLAYERS + 1} игроков (включая капитана).\n\n"
                "Нажмите на игрока, чтобы редактировать его данные или нажмите кнопку \"Добавить игрока\"."
            )
        elif team["status"] == "pending":
            message += (
                "\n⏳ <b>Заявка на участие в турнире подана.</b>\n"
                "Ожидается подтверждение от администраторов турнира."
            )
        elif team["status"] == "approved":
            message += (
                "\n✅ <b>Команда одобрена для участия в турнире!</b>\n"
                "Ожидайте дальнейших инструкций от организаторов."
            )
        elif team["status"] == "rejected":
            message += (
                "\n❌ <b>Заявка отклонена.</b>\n"
                "Вы можете создать новую команду или связаться с администратором."
            )
    
    return message

async def start_create_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс создания новой команды."""
    query = update.callback_query
    await query.answer()
    
    # Проверяем, есть ли у пользователя уже созданные команды
    user_id = query.from_user.id
    db = context.bot_data["db"]
    user_teams = db.get_user_teams(user_id)
    
    # Если у пользователя уже есть команды, блокируем создание новой
    if user_teams:
        # Формируем список команд пользователя
        teams_list = ""
        for idx, team in enumerate(user_teams, 1):
            teams_list += f"{idx}. {team['team_name']} (Статус: {TEAM_STATUS.get(team['status'], 'Неизвестно')})\n"
        
        # Создаем клавиатуру с командами пользователя
        keyboard = []
        for team in user_teams:
            keyboard.append([
                InlineKeyboardButton(f"{team['team_name']}", callback_data=f"view_team_{team['id']}")
            ])
        
        # Добавляем кнопку назад
        keyboard.append([InlineKeyboardButton("◀️ Назад в личный кабинет", callback_data="profile_back")])
        
        await query.message.reply_text(
            "⚠️ <b>Ограничение на создание команды</b>\n\n"
            "Вы не можете создать больше одной команды. Пожалуйста, используйте существующую команду "
            "или удалите её, чтобы создать новую.\n\n"
            f"<b>Ваши команды:</b>\n{teams_list}\n"
            "Выберите команду для управления:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return PROFILE_MENU
    
    # Если нет команд, продолжаем создание
    await query.message.reply_text(
        "🎮 <b>Создание новой команды</b>\n\n"
        "Пожалуйста, введите название вашей команды.\n\n"
        "Требования к названию:\n"
        "- От 3 до 30 символов\n"
        "- Только буквы, цифры, пробелы, дефисы, подчеркивания и точки",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    return TEAM_CREATE_NAME

async def process_team_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод названия команды."""
    team_name = update.message.text.strip()
    
    # Проверка на допустимую длину названия
    if len(team_name) < 2 or len(team_name) > 30:
        await update.message.reply_text(
            "⚠️ Название команды должно содержать от 2 до 30 символов. "
            "Пожалуйста, введите другое название.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_CREATE_NAME
    
    # Проверка на допустимые символы
    if not re.match(r'^[a-zA-Zа-яА-Я0-9\s\-_\.]+$', team_name):
        await update.message.reply_text(
            "⚠️ Название команды содержит недопустимые символы. "
            "Используйте только буквы, цифры, пробелы, дефисы, подчеркивания и точки.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_CREATE_NAME
    
    # Проверка на уникальность названия команды
    db = context.bot_data["db"]
    if db.team_name_exists(team_name):
        await update.message.reply_text(
            "⚠️ Команда с таким названием уже зарегистрирована. "
            "Пожалуйста, выберите другое название.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_CREATE_NAME
    
    # Сохраняем название команды
    context.user_data["new_team_name"] = team_name
    
    await update.message.reply_text(
        f"🎮 Название команды: <b>{team_name}</b>\n\n"
        "Теперь введите свой игровой никнейм. "
        "Вы будете назначены капитаном команды.\n\n"
        "✍🏼 Напишите никнейм в ответном сообщении.",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    return TEAM_CREATE_CAPTAIN

async def process_captain_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод никнейма капитана."""
    captain_nickname = update.message.text.strip()
    
    # Проверка на допустимую длину никнейма
    if len(captain_nickname) < 2 or len(captain_nickname) > 20:
        await update.message.reply_text(
            "⚠️ Никнейм должен содержать от 2 до 20 символов. "
            "Пожалуйста, введите другой никнейм.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_CREATE_CAPTAIN
    
    # Проверяем существование никнейма в PUBG
    nickname_exists, correct_nickname = await check_pubg_nickname(captain_nickname)
    
    if not nickname_exists:
        await update.message.reply_text(
            f"❌ Игрок с никнеймом \"{captain_nickname}\" не найден в PUBG.\n"
            "Пожалуйста, проверьте правильность написания и введите существующий никнейм.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_CREATE_CAPTAIN
    
    # Если никнейм отличается регистром, информируем пользователя
    if captain_nickname != correct_nickname:
        await update.message.reply_text(
            f"ℹ️ Никнейм скорректирован с учетом регистра: \"{correct_nickname}\" (было введено: \"{captain_nickname}\")."
        )
        captain_nickname = correct_nickname
    
    # Сохраняем никнейм в контексте
    context.user_data["captain_nickname"] = captain_nickname
    
    # Запрос Discord username
    await update.message.reply_text(
        f"✅ Никнейм принят: <b>{captain_nickname}</b>\n\n"
        f"Теперь введите ваш Discord username (без #1234).\n"
        f"Это необходимо для участия в турнире и получения уведомлений.",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    return TEAM_CREATE_CAPTAIN_DISCORD

async def process_captain_discord(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод Discord username капитана."""
    discord_username = update.message.text.strip()
    
    # Проверка на допустимую длину Discord username
    if len(discord_username) < 2 or len(discord_username) > 32:
        await update.message.reply_text(
            "⚠️ Discord username должен содержать от 2 до 32 символов. "
            "Пожалуйста, введите корректный Discord username.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_CREATE_CAPTAIN_DISCORD
    
    # Получаем Discord ID и проверяем наличие на сервере
    discord_bot = context.bot_data.get("discord_bot")
    discord_id = await get_discord_id_by_username(discord_username, discord_bot)
    
    if not discord_id:
        await update.message.reply_text(
            f"❌ Пользователь с Discord username \"{discord_username}\" не найден на нашем сервере.\n\n"
            f"Возможные причины:\n"
            f"• Неверно указан Discord username\n"
            f"• Вы не присоединились к нашему Discord серверу\n\n"
            f"Пожалуйста, проверьте правильность написания и убедитесь, что вы присоединились к серверу по ссылке: {DISCORD_INVITE_LINK}",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_CREATE_CAPTAIN_DISCORD
    
    # Проверяем, состоит ли пользователь в нужном Discord сервере
    is_member = await check_discord_membership(discord_id, discord_bot)
    
    if not is_member:
        await update.message.reply_text(
            f"❌ Вы не состоите в нашем Discord сервере.\n\n"
            f"Пожалуйста, присоединитесь к серверу по ссылке: {DISCORD_INVITE_LINK}\n"
            f"После этого повторите ввод Discord username.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_CREATE_CAPTAIN_DISCORD
    
    # Получаем данные о пользователе
    user = update.message.from_user
    team_name = context.user_data["new_team_name"]
    captain_nickname = context.user_data["captain_nickname"]
    
    # Создаем команду в базе данных
    db = context.bot_data["db"]
    
    # Формируем данные о капитане включая Discord
    captain_data = {
        "nickname": captain_nickname, 
        "username": user.username or f"user{user.id}", 
        "telegram_id": user.id,
        "discord_username": discord_username,
        "discord_id": discord_id,
        "is_captain": True
    }
    
    team_id = db.create_team(
        team_name=team_name,
        captain=captain_data
    )
    
    # Сохраняем ID команды в контексте для дальнейших действий
    context.user_data["current_team_id"] = team_id
    
    # Получаем созданную команду
    team = db.get_team_by_id(team_id)
    
    # Формируем сообщение с информацией о команде
    message = await format_team_info(team, is_captain=True)
    
    # Создаем inline клавиатуру
    keyboard = [
        [InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")],
        [InlineKeyboardButton("📝 Зарегистрировать на турнир", callback_data="register_team")],
        [InlineKeyboardButton("◀️ Назад в личный кабинет", callback_data="profile_back")]
    ]
    
    # Отправляем сообщение с inline кнопками
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return PROFILE_MENU

async def add_player_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс добавления игрока."""
    # Могло прийти как через callback, так и через сообщение
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        msg = query.message
    else:
        msg = update.message
    
    team_id = context.user_data.get("current_team_id")
    if not team_id:
        if update.callback_query:
            await query.edit_message_text(
                "⚠️ Ошибка: не удалось определить команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
                reply_markup=get_profile_inline_keyboard()
            )
        else:
            await msg.reply_text(
                "⚠️ Ошибка: не удалось определить команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
                reply_markup=get_profile_inline_keyboard()
            )
        return PROFILE_MENU
    
    # Проверяем количество игроков в команде
    db = context.bot_data["db"]
    team = db.get_team_by_id(team_id)
    
    if len(team["players"]) > MAX_PLAYERS:
        if update.callback_query:
            await query.edit_message_text(
                f"⚠️ В команде уже максимальное количество игроков ({MAX_PLAYERS + 1}, включая капитана).",
                reply_markup=get_back_to_profile_inline_button()
            )
        else:
            await msg.reply_text(
                f"⚠️ В команде уже максимальное количество игроков ({MAX_PLAYERS + 1}, включая капитана).",
                reply_markup=get_back_to_profile_keyboard()
            )
        return PROFILE_MENU
    
    # Если это callback, отправляем новое сообщение, иначе отвечаем на текущее
    if update.callback_query:
        await msg.reply_text(
            "👤 <b>Добавление нового игрока</b>\n\n"
            "Введите Telegram имя пользователя (username) игрока, которого хотите добавить.\n"
            "Формат: @username\n\n"
            "Важно: у пользователя должен быть установлен username в Telegram.",
            reply_markup=get_back_to_profile_keyboard(),
            parse_mode="HTML"
        )
    else:
        await msg.reply_text(
            "👤 <b>Добавление нового игрока</b>\n\n"
            "Введите Telegram имя пользователя (username) игрока, которого хотите добавить.\n"
            "Формат: @username\n\n"
            "Важно: у пользователя должен быть установлен username в Telegram.",
            reply_markup=get_back_to_profile_keyboard(),
            parse_mode="HTML"
        )
    
    return TEAM_ADD_PLAYER_USERNAME

async def process_player_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод Telegram username игрока."""
    username_input = update.message.text.strip()
    
    # Проверяем, соответствует ли ввод формату @username
    username_match = re.match(USERNAME_PATTERN, username_input)
    if not username_match:
        await update.message.reply_text(
            "⚠️ Неверный формат. Введите username в формате @username.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_USERNAME
    
    username = username_match.group(1)
    team_id = context.user_data.get("current_team_id")
    
    if not team_id:
        await update.message.reply_text(
            "⚠️ Ошибка: не удалось определить команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_keyboard()
        )
        return PROFILE_MENU
    
    db = context.bot_data["db"]
    
    # Проверяем, существует ли уже игрок с таким username в команде
    if db.check_username_exists_in_team(team_id, username):
        await update.message.reply_text(
            f"❌ Произошла ошибка при добавлении игрока: Игрок с таким Telegram username уже есть в команде.\n"
            "Пожалуйста, введите другой Telegram username:",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_USERNAME
    
    # Получим Telegram ID пользователя
    userbot = context.bot_data.get("userbot")
    if userbot:
        try:
            telegram_id = await get_tg_id_by_username(username, userbot)
            
            if not telegram_id:
                await update.message.reply_text(
                    f"⚠️ Пользователь с username @{username} не найден в Telegram.\n"
                    "Пожалуйста, проверьте правильность написания и введите существующий username:",
                    reply_markup=get_back_to_profile_keyboard()
                )
                return TEAM_ADD_PLAYER_USERNAME
                
            context.user_data["new_player_telegram_id"] = telegram_id
        except Exception as e:
            logger.warning(f"Не удалось получить Telegram ID для @{username}: {e}")
            
            # Предупреждаем пользователя, но позволяем продолжить
            await update.message.reply_text(
                f"⚠️ Предупреждение: Не удалось проверить существование пользователя @{username}.\n"
                "Убедитесь, что указан корректный username.\n\n"
                "Вы можете продолжить, но учтите, что если username некорректен, "
                "пользователь не сможет получать уведомления."
            )
    
    # Сохраняем username для дальнейшего использования
    context.user_data["new_player_username"] = username
    
    await update.message.reply_text(
        f"Telegram: @{username}\n\n"
        "Теперь введите игровой никнейм этого игрока.",
        reply_markup=get_back_to_profile_keyboard()
    )
    return TEAM_ADD_PLAYER_NICKNAME

async def process_player_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод игрового никнейма игрока."""
    nickname = update.message.text.strip()
    
    # Проверка на допустимую длину никнейма
    if len(nickname) < 2 or len(nickname) > 20:
        await update.message.reply_text(
            "⚠️ Никнейм должен содержать от 2 до 20 символов. "
            "Пожалуйста, введите другой никнейм.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_NICKNAME
    
    # Проверяем существование никнейма в PUBG
    nickname_exists, correct_nickname = await check_pubg_nickname(nickname)
    
    if not nickname_exists:
        await update.message.reply_text(
            f"❌ Игрок с никнеймом \"{nickname}\" не найден в PUBG.\n"
            "Пожалуйста, проверьте правильность написания и введите существующий никнейм.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_NICKNAME
    
    # Если никнейм отличается регистром, информируем пользователя
    if nickname != correct_nickname:
        await update.message.reply_text(
            f"ℹ️ Никнейм скорректирован с учетом регистра: \"{correct_nickname}\" (было введено: \"{nickname}\")."
        )
        nickname = correct_nickname
    
    # Сохраняем никнейм в контексте
    context.user_data["new_player_nickname"] = nickname
    
    # Запрос Discord username
    await update.message.reply_text(
        f"✅ Никнейм принят: <b>{nickname}</b>\n\n"
        f"Теперь введите Discord username игрока (без #1234).\n"
        f"Это необходимо для участия в турнире и получения уведомлений.",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    return TEAM_ADD_PLAYER_DISCORD

async def process_player_discord(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод Discord username игрока."""
    discord_username = update.message.text.strip()
    
    # Проверка на допустимую длину Discord username
    if len(discord_username) < 2 or len(discord_username) > 32:
        await update.message.reply_text(
            "⚠️ Discord username должен содержать от 2 до 32 символов. "
            "Пожалуйста, введите корректный Discord username.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_DISCORD
    
    # Получаем Discord ID и проверяем наличие на сервере
    discord_bot = context.bot_data.get("discord_bot")
    discord_id = await get_discord_id_by_username(discord_username, discord_bot)
    
    if not discord_id:
        await update.message.reply_text(
            f"❌ Пользователь с Discord username \"{discord_username}\" не найден на нашем сервере.\n\n"
            f"Возможные причины:\n"
            f"• Неверно указан Discord username\n"
            f"• Пользователь не присоединился к нашему Discord серверу\n\n"
            f"Пожалуйста, проверьте правильность написания и убедитесь, что пользователь присоединился к серверу по ссылке: {DISCORD_INVITE_LINK}",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_DISCORD
    
    # Проверяем, состоит ли пользователь в нужном Discord сервере
    is_member = await check_discord_membership(discord_id, discord_bot)
    
    if not is_member:
        await update.message.reply_text(
            f"❌ Пользователь не состоит в нашем Discord сервере.\n\n"
            f"Пожалуйста, попросите игрока присоединиться к серверу по ссылке: {DISCORD_INVITE_LINK}\n"
            f"После этого повторите ввод Discord username.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_DISCORD
    
    # Получаем данные об игроке и команде
    username = context.user_data.get("new_player_username")
    telegram_id = context.user_data.get("new_player_telegram_id")
    team_id = context.user_data.get("current_team_id")
    nickname = context.user_data.get("new_player_nickname")
    
    if not team_id or not username or not nickname:
        await update.message.reply_text(
            "⚠️ Ошибка: не удалось определить команду или данные игрока. "
            "Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_keyboard()
        )
        return PROFILE_MENU
    
    db = context.bot_data["db"]
    
    # Проверяем, существует ли уже игрок с таким никнеймом в команде
    if db.check_nickname_exists_in_team(team_id, nickname):
        await update.message.reply_text(
            f"❌ Произошла ошибка при добавлении игрока: Игрок с таким никнеймом уже есть в команде.\n"
            "Пожалуйста, введите другой игровой никнейм:",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_NICKNAME
    
    # Проверяем, существует ли уже игрок с таким Discord username в команде
    if db.check_discord_exists_in_team(team_id, discord_username):
        await update.message.reply_text(
            f"❌ Произошла ошибка при добавлении игрока: Игрок с таким Discord username уже есть в команде.\n"
            "Каждый игрок должен иметь уникальный Discord аккаунт.\n"
            "Пожалуйста, введите другой Discord username:",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_DISCORD
    
    # Формируем данные о новом игроке
    player_data = {
        "nickname": nickname,
        "username": username,
        "telegram_id": telegram_id,
        "discord_username": discord_username,
        "discord_id": discord_id,
        "is_captain": False
    }
    
    try:
        # Получаем предыдущий статус команды
        team_before = db.get_team_by_id(team_id)
        was_pending_approved_or_rejected = team_before["status"] in ["pending", "approved", "rejected"]
        
        # Добавляем игрока в команду
        db.add_player_to_team(team_id, player_data)
        
        # Получаем обновленную команду
        team = db.get_team_by_id(team_id)
        
        # Проверяем, изменился ли статус команды
        status_changed = was_pending_approved_or_rejected and team["status"] == "draft"
        # Сохраняем информацию об изменении статуса
        context.user_data["team_status_changed"] = status_changed
        
        # Формируем сообщение с информацией о команде
        message = await format_team_info(team, is_captain=True)
        
        # Создаем inline клавиатуру
        keyboard = [
            [InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")],
            [InlineKeyboardButton("◀️ Назад в личный кабинет", callback_data="profile_back")]
        ]
        
        # Если это черновик, добавляем кнопку регистрации
        if team["status"] == "draft":
            # Проверяем, достаточно ли игроков для регистрации
            if len(team["players"]) >= 4:  # Минимум 4 игрока (3 + капитан)
                keyboard.insert(1, [InlineKeyboardButton("📝 Зарегистрировать на турнир", callback_data="register_team")])
        
        # Сообщение об изменении статуса, если это произошло
        status_message = ""
        if status_changed:
            status_message = "⚠️ В связи с добавлением игрока, статус команды изменен на 'Черновик'. Для участия в турнире необходимо заново зарегистрировать команду.\n\n"
        
        await update.message.reply_text(
            f"{status_message}✅ Игрок успешно добавлен в команду!\n\n" + message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        # Очищаем данные о новом игроке
        if "new_player_username" in context.user_data:
            del context.user_data["new_player_username"]
        if "new_player_telegram_id" in context.user_data:
            del context.user_data["new_player_telegram_id"]
        if "new_player_nickname" in context.user_data:
            del context.user_data["new_player_nickname"]
        
        return PROFILE_MENU
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении игрока: {e}")
        
        await update.message.reply_text(
            f"❌ Произошла ошибка при добавлении игрока: {str(e)}\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_ADD_PLAYER_USERNAME

async def register_team_for_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс регистрации команды на турнир."""
    query = update.callback_query
    await query.answer()
    
    team_id = context.user_data.get("current_team_id")
    if not team_id:
        await query.edit_message_text(
            "⚠️ Ошибка: не удалось определить команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    db = context.bot_data["db"]
    
    # Получаем все турниры с открытой регистрацией
    active_tournaments = db.get_active_tournaments()
    
    if not active_tournaments:
        await query.edit_message_text(
            "⚠️ На данный момент нет доступных турниров для регистрации.\n\n"
            "Пожалуйста, попробуйте позже или обратитесь к администратору.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    # Проверяем количество игроков в команде
    team = db.get_team_by_id(team_id)
    if len(team["players"]) < 4:  # Минимум 4 игрока (3 + капитан)
        await query.edit_message_text(
            f"⚠️ Для регистрации на турнир необходимо минимум 4 игрока (включая капитана).\n\n"
            f"В вашей команде сейчас {len(team['players'])} игрок(ов).\n\n"
            f"Добавьте больше игроков и попробуйте снова.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    # Проверяем наличие Discord у всех игроков
    players_without_discord = [p for p in team["players"] if not p.get("discord_username")]
    
    if players_without_discord:
        players_list = "\n".join([f"- {p['nickname']} (@{p['telegram_username']})" for p in players_without_discord])
        
        await query.edit_message_text(
            f"⚠️ Для регистрации на турнир все игроки должны иметь указанный Discord username.\n\n"
            f"Следующие игроки не имеют Discord:\n{players_list}\n\n"
            f"Пожалуйста, отредактируйте информацию об этих игроках, добавив их Discord.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    # Создаем клавиатуру с турнирами
    keyboard = []
    for tournament in active_tournaments:
        keyboard.append([
            InlineKeyboardButton(
                f"{tournament['name']} ({tournament['event_date']})",
                callback_data=f"register_for_tournament_{team_id}_{tournament['id']}"
            )
        ])
    
    # Добавляем кнопку "Отмена"
    keyboard.append([
        InlineKeyboardButton("❌ Отмена", callback_data=f"view_team_{team_id}")
    ])
    
    await query.edit_message_text(
        "🏆 <b>Выберите турнир для регистрации</b>\n\n"
        "Доступные турниры:\n",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return PROFILE_MENU

async def confirm_tournament_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтвердить регистрацию команды на выбранный турнир."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID команды и турнира из callback_data
    data_parts = query.data.split("_")
    team_id = int(data_parts[3])
    tournament_id = int(data_parts[4])
    
    db = context.bot_data["db"]
    
    # Получаем информацию о команде и турнире
    team = db.get_team_by_id(team_id)
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not team or not tournament:
        await query.edit_message_text(
            "⚠️ Ошибка: команда или турнир не найдены.",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    # Проверяем, открыта ли регистрация
    if not tournament["registration_open"]:
        await query.edit_message_text(
            f"⚠️ Регистрация на турнир \"{tournament['name']}\" закрыта.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    # Запрашиваем подтверждение
    await query.edit_message_text(
        f"🏆 <b>Подтверждение регистрации на турнир</b>\n\n"
        f"Команда: <b>{team['team_name']}</b>\n"
        f"Турнир: <b>{tournament['name']}</b>\n"
        f"Дата проведения: {tournament['event_date']}\n\n"
        f"Вы уверены, что хотите зарегистрировать команду на этот турнир?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, зарегистрировать", callback_data=f"confirm_register_{team_id}_{tournament_id}"),
                InlineKeyboardButton("❌ Нет, отмена", callback_data=f"view_team_{team_id}")
            ]
        ])
    )
    
    return PROFILE_MENU

async def complete_tournament_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершить процесс регистрации команды на турнир."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID команды и турнира из callback_data
    data_parts = query.data.split("_")
    team_id = int(data_parts[2])
    tournament_id = int(data_parts[3])
    
    db = context.bot_data["db"]
    
    try:
        # Получаем информацию о команде
        team = db.get_team_by_id(team_id)
        
        # Проверяем подписку игроков на канал
        userbot = context.bot_data.get("userbot")
        
        # Список игроков без подписки
        unsubscribed_players = []
        
        logger.info(f"Проверка подписки на канал {CHANNEL_ID} для команды {team['team_name']}")
        
        for player in team["players"]:
            logger.info(f"Проверка игрока {player['nickname']} (@{player.get('telegram_username', 'нет')}) с ID {player.get('telegram_id', 'не указан')}")
            
            # Проверяем подписку только если есть telegram_id
            if player.get("telegram_id"):
                is_subscribed = await check_channel_subscription(userbot, player["telegram_id"], CHANNEL_ID)
                
                # Сохраняем статус подписки в БД
                db.update_player_subscription(player["id"], is_subscribed)
                
                if not is_subscribed:
                    logger.info(f"Игрок {player['nickname']} (@{player.get('telegram_username', 'нет')}) не подписан на канал")
                    unsubscribed_players.append(player)
            else:
                logger.warning(f"У игрока {player['nickname']} (@{player.get('telegram_username', 'нет')}) не указан telegram_id, пропускаем проверку подписки")
        
        # Если есть игроки без подписки, выводим предупреждение
        if unsubscribed_players:
            # Формируем список игроков без подписки
            players_list = ""
            for idx, player in enumerate(unsubscribed_players, 1):
                players_list += f"{idx}. {player['nickname']} (@{player['telegram_username']})\n"
            
            # Создаем клавиатуру с кнопками действий
            keyboard = [
                [InlineKeyboardButton("✅ Продолжить регистрацию", callback_data=f"confirm_register_anyway_{team_id}_{tournament_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data=f"view_team_{team_id}")]
            ]
            
            await query.edit_message_text(
                f"⚠️ <b>Обратите внимание!</b>\n\n"
                f"Следующие игроки не подписаны на канал {CHANNEL_ID}:\n\n"
                f"{players_list}\n"
                f"Для участия в турнире все игроки должны быть подписаны на канал.\n"
                f"Если игроки не подпишутся, команда может лишиться призовых денег.\n\n"
                f"Хотите продолжить регистрацию?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            
            return PROFILE_MENU
        
        # Если все игроки подписаны, продолжаем регистрацию
        # Регистрируем команду на турнир
        db.register_team_for_tournament(team_id, tournament_id)
        
        # Получаем обновленную информацию о команде и турнире
        team = db.get_team_by_id(team_id)
        tournament = db.get_tournament_by_id(tournament_id)
        
        # Формируем сообщение с информацией о команде
        message = await format_team_info(team, is_captain=True)
        
        # Определяем, является ли пользователь капитаном
        user_id = query.from_user.id
        is_captain = any(p.get("is_captain", False) and p.get("telegram_id") == user_id for p in team["players"])
        
        # Создаем клавиатуру действий
        keyboard = []
        
        # Добавляем кнопки для игроков
        player_buttons = []
        for player in team["players"]:
            player_buttons.append(
                InlineKeyboardButton(
                    f"{player['nickname']} (@{player['telegram_username']})",
                    callback_data=f"player_{player['id']}"
                )
            )
        
        # Добавляем каждого игрока отдельной кнопкой
        for button in player_buttons:
            keyboard.append([button])
        
        # Добавляем кнопки действий для капитана
        if is_captain:
            # Пока в "ожидании", можно добавлять игроков и редактировать
            if team["status"] == "pending":
                keyboard.append([InlineKeyboardButton("✏️ Изменить название", callback_data="edit_team_name")])
                keyboard.append([InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")])
            
            # Кнопка отмены регистрации
            keyboard.append([InlineKeyboardButton("❌ Удалить команду", callback_data="cancel_team")])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")])
        
        await query.edit_message_text(
            f"✅ <b>Команда успешно зарегистрирована на турнир!</b>\n\n"
            f"Турнир: <b>{tournament['name']}</b>\n"
            f"Дата проведения: {tournament['event_date']}\n\n"
            f"Ваша заявка ожидает рассмотрения администратором турнира.\n\n"
            + message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        return PROFILE_MENU
        
    except Exception as e:
        logger.error(f"Ошибка при регистрации команды на турнир: {e}")
        
        # Создаем клавиатуру для возврата
        keyboard = [
            [InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")],
            [InlineKeyboardButton("🔄 Показать команду", callback_data=f"view_team_{team_id}")]
        ]
        
        await query.edit_message_text(
            f"❌ <b>Произошла ошибка при регистрации команды на турнир:</b> {str(e)}\n\n"
            f"Пожалуйста, убедитесь, что в команде достаточно игроков и все данные указаны корректно.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return PROFILE_MENU
    
async def complete_registration_anyway(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершить регистрацию команды, несмотря на предупреждение о подписке."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID команды и турнира из callback_data
    data_parts = query.data.split("_")
    team_id = int(data_parts[3])
    tournament_id = int(data_parts[4])
    
    db = context.bot_data["db"]
    
    try:
        # Получаем информацию о команде
        team = db.get_team_by_id(team_id)
        
        # Проверяем подписку игроков на канал еще раз (возможно кто-то успел подписаться)
        userbot = context.bot_data.get("userbot")
        
        for player in team["players"]:
            if player.get("telegram_id"):
                is_subscribed = await check_channel_subscription(userbot, player["telegram_id"], CHANNEL_ID)
                # Сохраняем статус подписки в БД
                db.update_player_subscription(player["id"], is_subscribed)
        
        # Регистрируем команду на турнир
        db.register_team_for_tournament(team_id, tournament_id)
        
        # Получаем обновленную информацию о команде и турнире
        team = db.get_team_by_id(team_id)
        tournament = db.get_tournament_by_id(tournament_id)
        
        # Формируем сообщение с информацией о команде
        message = await format_team_info(team, is_captain=True)
        
        # Определяем, является ли пользователь капитаном
        user_id = query.from_user.id
        is_captain = any(p.get("is_captain", False) and p.get("telegram_id") == user_id for p in team["players"])
        
        # Создаем клавиатуру действий
        keyboard = []
        
        # Добавляем кнопки для игроков
        player_buttons = []
        for player in team["players"]:
            player_buttons.append(
                InlineKeyboardButton(
                    f"{player['nickname']} (@{player['telegram_username']})",
                    callback_data=f"player_{player['id']}"
                )
            )
        
        # Добавляем каждого игрока отдельной кнопкой
        for button in player_buttons:
            keyboard.append([button])
        
        # Добавляем кнопки действий для капитана
        if is_captain:
            # Пока в "ожидании", можно добавлять игроков и редактировать
            if team["status"] == "pending":
                keyboard.append([InlineKeyboardButton("✏️ Изменить название", callback_data="edit_team_name")])
                keyboard.append([InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")])
            
            # Кнопка отмены регистрации
            keyboard.append([InlineKeyboardButton("❌ Удалить команду", callback_data="cancel_team")])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")])
        
        await query.edit_message_text(
            f"✅ <b>Команда успешно зарегистрирована на турнир!</b>\n\n"
            f"Турнир: <b>{tournament['name']}</b>\n"
            f"Дата проведения: {tournament['event_date']}\n\n"
            f"⚠️ <b>Внимание:</b> Некоторые игроки не подписаны на канал. "
            f"Рекомендуем им подписаться, чтобы избежать проблем с получением призовых.\n\n"
            f"Ваша заявка ожидает рассмотрения администратором турнира.\n\n"
            + message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        return PROFILE_MENU
        
    except Exception as e:
        logger.error(f"Ошибка при регистрации команды на турнир: {e}")
        
        # Создаем клавиатуру для возврата
        keyboard = [
            [InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")],
            [InlineKeyboardButton("🔄 Показать команду", callback_data=f"view_team_{team_id}")]
        ]
        
        await query.edit_message_text(
            f"❌ <b>Произошла ошибка при регистрации команды на турнир:</b> {str(e)}\n\n"
            f"Пожалуйста, убедитесь, что в команде достаточно игроков и все данные указаны корректно.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return PROFILE_MENU

async def start_edit_team_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс редактирования названия команды."""
    query = update.callback_query
    await query.answer()
    
    team_id = context.user_data.get("current_team_id")
    if not team_id:
        await query.edit_message_text(
            "⚠️ Ошибка: не удалось определить команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    db = context.bot_data["db"]
    team = db.get_team_by_id(team_id)
    
    await query.message.reply_text(
        f"🎮 <b>Редактирование названия команды</b>\n\n"
        f"Текущее название: <b>{team['team_name']}</b>\n\n"
        f"Введите новое название команды:",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    
    return TEAM_EDIT_NAME

async def process_edit_team_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод нового названия команды."""
    new_name = update.message.text.strip()
    
    # Проверка на допустимую длину названия
    if len(new_name) < 2 or len(new_name) > 30:
        await update.message.reply_text(
            "⚠️ Название команды должно содержать от 2 до 30 символов. "
            "Пожалуйста, введите другое название.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_EDIT_NAME
    
    # Проверка на допустимые символы
    if not re.match(r'^[a-zA-Zа-яА-Я0-9\s\-_\.]+$', new_name):
        await update.message.reply_text(
            "⚠️ Название команды содержит недопустимые символы. "
            "Используйте только буквы, цифры, пробелы, дефисы, подчеркивания и точки.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_EDIT_NAME
    
    team_id = context.user_data.get("current_team_id")
    if not team_id:
        await update.message.reply_text(
            "⚠️ Ошибка: не удалось определить команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    db = context.bot_data["db"]
    
    try:
        # Получаем предыдущий статус команды
        team_before = db.get_team_by_id(team_id)
        old_status = team_before["status"]
        was_pending_approved_or_rejected = old_status in ["pending", "approved", "rejected"]
        
        # Обновляем название команды
        db.update_team_name(team_id, new_name)
        
        # Получаем обновленную команду
        team = db.get_team_by_id(team_id)
        
        # Проверяем, изменился ли статус команды
        status_changed = was_pending_approved_or_rejected and team["status"] == "draft"
        # Сохраняем информацию об изменении статуса
        context.user_data["team_status_changed"] = status_changed
        
        # Если статус изменился с "approved" на "draft", удаляем роли у игроков
        if old_status == "approved" and team["status"] == "draft":
            discord_bot = context.bot_data.get("discord_bot")
            discord_server_id = context.bot_data.get("discord_server_id")
            discord_role_id = context.bot_data.get("discord_role_id")
            discord_captain_role_id = context.bot_data.get("discord_captain_role_id")
            await process_team_roles(db, discord_bot, discord_server_id, discord_role_id, 
                                    discord_captain_role_id, team_id, old_status, team["status"])
        
        # Формируем сообщение с информацией о команде
        message = await format_team_info(team, is_captain=True)
        
        # Определяем, является ли пользователь капитаном
        user_id = update.message.from_user.id
        is_captain = any(p.get("is_captain", False) and p.get("telegram_id") == user_id for p in team["players"])
        
        # Создаем клавиатуру действий
        keyboard = []
        
        # Добавляем кнопки для игроков
        player_buttons = []
        for player in team["players"]:
            player_buttons.append(
                InlineKeyboardButton(
                    f"{player['nickname']} (@{player['telegram_username']})",
                    callback_data=f"player_{player['id']}"
                )
            )
        
        # Добавляем каждого игрока отдельной кнопкой
        for button in player_buttons:
            keyboard.append([button])
        
        # Добавляем кнопки действий для капитана
        if is_captain:
            keyboard.append([InlineKeyboardButton("✏️ Изменить название", callback_data="edit_team_name")])
            keyboard.append([InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")])
            
            # Кнопка регистрации (только для черновиков)
            if team["status"] == "draft":
                keyboard.append([InlineKeyboardButton("📝 Зарегистрировать на турнир", callback_data="register_team")])
            
            # Кнопка отмены
            keyboard.append([InlineKeyboardButton("❌ Удалить команду", callback_data="cancel_team")])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")])
        
        # Сообщение об изменении статуса, если это произошло
        status_message = ""
        if status_changed:
            status_message = "⚠️ В связи с изменением названия команды, статус команды изменен на 'Черновик'. Для участия в турнире необходимо заново зарегистрировать команду.\n\n"
        
        await update.message.reply_text(
            f"{status_message}✅ Название команды успешно изменено!\n\n" + message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        return PROFILE_MENU
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении названия команды: {e}")
        
        await update.message.reply_text(
            f"❌ Произошла ошибка при обновлении названия команды: {str(e)}\n"
            "Пожалуйста, попробуйте еще раз или выберите другое название.",
            reply_markup=get_back_to_profile_keyboard()
        )
        
        return TEAM_EDIT_NAME

async def view_player(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Просмотр информации об игроке и вариантов действий с ним."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID игрока
    player_id = int(query.data.split("_")[1])
    
    # Сохраняем ID игрока в контексте
    context.user_data["current_player_id"] = player_id
    
    # Получаем команду
    team_id = context.user_data.get("current_team_id")
    if not team_id:
        await query.edit_message_text(
            "⚠️ Ошибка: не удалось определить команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    db = context.bot_data["db"]
    team = db.get_team_by_id(team_id)
    
    # Находим игрока по ID
    player = next((p for p in team["players"] if p["id"] == player_id), None)
    if not player:
        await query.edit_message_text(
            "⚠️ Игрок не найден. Возможно, он был удален.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    # Проверяем, является ли пользователь капитаном команды
    user_id = query.from_user.id
    is_captain = any(p.get("is_captain", False) and p.get("telegram_id") == user_id for p in team["players"])
    
    if not is_captain:
        await query.edit_message_text(
            "⚠️ У вас нет прав для редактирования игроков. Только капитан команды может это делать.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    # Формируем сообщение с информацией об игроке
    discord_info = f"\n🎮 <b>Discord:</b> {player['discord_username']}" if player.get('discord_username') else "\n🎮 <b>Discord:</b> Не указан"
    
    message = (
        f"👤 <b>Информация об игроке</b>\n\n"
        f"🎮 <b>Игровой никнейм:</b> {player['nickname']}\n"
        f"📱 <b>Telegram username:</b> @{player['telegram_username']}"
        f"{discord_info}\n"
        f"🔑 <b>Роль:</b> {'Капитан' if player.get('is_captain', False) else 'Игрок'}\n\n"
        f"Выберите действие:"
    )
    
    # Создаем клавиатуру с действиями
    keyboard = []
    
    # Если игрок не капитан, можно редактировать и удалять
    if not player.get("is_captain", False):
        keyboard.append([InlineKeyboardButton("✏️ Изменить никнейм", callback_data=f"edit_player_nickname_{player_id}")])
        keyboard.append([InlineKeyboardButton("📱 Изменить Telegram", callback_data=f"edit_player_username_{player_id}")])
        keyboard.append([InlineKeyboardButton("🎮 Изменить Discord", callback_data=f"edit_player_discord_{player_id}")])
        keyboard.append([InlineKeyboardButton("🗑️ Удалить игрока", callback_data=f"delete_player_{player_id}")])
    else:
        # Для капитана можно редактировать никнейм и Discord
        keyboard.append([InlineKeyboardButton("✏️ Изменить никнейм", callback_data=f"edit_player_nickname_{player_id}")])
        keyboard.append([InlineKeyboardButton("🎮 Изменить Discord", callback_data=f"edit_player_discord_{player_id}")])
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("🔄 Вернуться к команде", callback_data=f"view_team_{team_id}")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return PROFILE_MENU

async def start_edit_player_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс редактирования никнейма игрока."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID игрока из callback_data
    player_id = int(query.data.split("_")[3])
    
    # Сохраняем ID игрока в контексте
    context.user_data["current_player_id"] = player_id
    
    # Получаем информацию о команде и игроке
    team_id = context.user_data.get("current_team_id")
    db = context.bot_data["db"]
    team = db.get_team_by_id(team_id)
    
    # Находим игрока по ID
    player = next((p for p in team["players"] if p["id"] == player_id), None)
    
    if not player:
        await query.edit_message_text(
            "⚠️ Игрок не найден. Возможно, он был удален.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    await query.message.reply_text(
        f"✏️ <b>Редактирование игрового никнейма</b>\n\n"
        f"Игрок: @{player['telegram_username']}\n"
        f"Текущий никнейм: <b>{player['nickname']}</b>\n\n"
        f"Введите новый игровой никнейм:",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    
    return TEAM_EDIT_PLAYER_NICKNAME

async def process_edit_player_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод нового никнейма игрока."""
    new_nickname = update.message.text.strip()
    
    # Проверка на допустимую длину никнейма
    if len(new_nickname) < 2 or len(new_nickname) > 20:
        await update.message.reply_text(
            "⚠️ Никнейм должен содержать от 2 до 20 символов. "
            "Пожалуйста, введите другой никнейм.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_EDIT_PLAYER_NICKNAME
    
    # Проверяем существование никнейма в PUBG
    nickname_exists, correct_nickname = await check_pubg_nickname(new_nickname)
    
    if not nickname_exists:
        await update.message.reply_text(
            f"❌ Игрок с никнеймом \"{new_nickname}\" не найден в PUBG.\n"
            "Пожалуйста, проверьте правильность написания и введите существующий никнейм.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_EDIT_PLAYER_NICKNAME
    
    # Если никнейм отличается регистром, информируем пользователя
    if new_nickname != correct_nickname:
        await update.message.reply_text(
            f"ℹ️ Никнейм скорректирован с учетом регистра: \"{correct_nickname}\" (было введено: \"{new_nickname}\")."
        )
        new_nickname = correct_nickname
    
    player_id = context.user_data.get("current_player_id")
    team_id = context.user_data.get("current_team_id")
    
    if not player_id or not team_id:
        await update.message.reply_text(
            "⚠️ Ошибка: не удалось определить игрока или команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    db = context.bot_data["db"]
    
    try:
        # Получаем предыдущий статус команды
        team_before = db.get_team_by_id(team_id)
        was_pending_approved_or_rejected = team_before["status"] in ["pending", "approved", "rejected"]
        
        # Обновляем никнейм игрока
        db.update_player_nickname(player_id, new_nickname)
        
        # Получаем обновленную команду
        team = db.get_team_by_id(team_id)
        
        # Проверяем, изменился ли статус команды
        status_changed = was_pending_approved_or_rejected and team["status"] == "draft"
        # Сохраняем информацию об изменении статуса
        context.user_data["team_status_changed"] = status_changed
        
        # Формируем сообщение с информацией о команде
        message = await format_team_info(team, is_captain=True)
        
        # Создаем клавиатуру действий
        keyboard = []
        
        # Добавляем кнопки для игроков
        player_buttons = []
        for player in team["players"]:
            player_buttons.append(
                InlineKeyboardButton(
                    f"{player['nickname']} (@{player['telegram_username']})",
                    callback_data=f"player_{player['id']}"
                )
            )
        
        # Добавляем каждого игрока отдельной кнопкой
        for button in player_buttons:
            keyboard.append([button])
        
        # Добавляем кнопки действий для капитана
        keyboard.append([InlineKeyboardButton("✏️ Изменить название", callback_data="edit_team_name")])
        keyboard.append([InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")])
        
        # Кнопка регистрации (только для черновиков)
        if team["status"] == "draft":
            keyboard.append([InlineKeyboardButton("📝 Зарегистрировать на турнир", callback_data="register_team")])
        
        # Кнопка отмены
        keyboard.append([InlineKeyboardButton("❌ Удалить команду", callback_data="cancel_team")])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")])
        
        # Сообщение об изменении статуса, если это произошло
        status_message = ""
        if status_changed:
            status_message = "⚠️ В связи с изменением никнейма игрока, статус команды изменен на 'Черновик'. Для участия в турнире необходимо заново зарегистрировать команду.\n\n"
        
        await update.message.reply_text(
            f"{status_message}✅ Никнейм игрока успешно изменен!\n\n" + message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        return PROFILE_MENU
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении никнейма игрока: {e}")
        
        await update.message.reply_text(
            f"❌ Произошла ошибка при обновлении никнейма игрока: {str(e)}\n"
            "Пожалуйста, попробуйте еще раз или выберите другой никнейм.",
            reply_markup=get_back_to_profile_keyboard()
        )
        
        return TEAM_EDIT_PLAYER_NICKNAME

async def start_edit_player_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс редактирования Telegram username игрока."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID игрока из callback_data
    player_id = int(query.data.split("_")[3])
    
    # Сохраняем ID игрока в контексте
    context.user_data["current_player_id"] = player_id
    
    # Получаем информацию о команде и игроке
    team_id = context.user_data.get("current_team_id")
    db = context.bot_data["db"]
    team = db.get_team_by_id(team_id)
    
    # Находим игрока по ID
    player = next((p for p in team["players"] if p["id"] == player_id), None)
    
    if not player:
        await query.edit_message_text(
            "⚠️ Игрок не найден. Возможно, он был удален.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    await query.message.reply_text(
        f"📱 <b>Редактирование Telegram username</b>\n\n"
        f"Игрок: {player['nickname']}\n"
        f"Текущий username: <b>@{player['telegram_username']}</b>\n\n"
        f"Введите новый Telegram username игрока (формат: @username):",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    
    return TEAM_EDIT_PLAYER_USERNAME

async def process_edit_player_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод нового Telegram username игрока."""
    username_input = update.message.text.strip()
    
    # Проверяем, соответствует ли ввод формату @username
    username_match = re.match(USERNAME_PATTERN, username_input)
    if not username_match:
        await update.message.reply_text(
            "⚠️ Неверный формат. Введите username в формате @username.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_EDIT_PLAYER_USERNAME
    
    username = username_match.group(1)
    
    player_id = context.user_data.get("current_player_id")
    team_id = context.user_data.get("current_team_id")
    
    if not player_id or not team_id:
        await update.message.reply_text(
            "⚠️ Ошибка: не удалось определить игрока или команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    db = context.bot_data["db"]
    
    # Получим Telegram ID пользователя
    userbot = context.bot_data.get("userbot")
    telegram_id = None
    if userbot:
        try:
            telegram_id = await get_tg_id_by_username(username, userbot)
            
            if not telegram_id:
                await update.message.reply_text(
                    f"⚠️ Пользователь с username @{username} не найден в Telegram.\n"
                    "Пожалуйста, проверьте правильность написания и введите существующий username:",
                    reply_markup=get_back_to_profile_keyboard()
                )
                return TEAM_EDIT_PLAYER_USERNAME
        except Exception as e:
            logger.warning(f"Не удалось получить Telegram ID для @{username}: {e}")
            
            # Предупреждаем пользователя, но позволяем продолжить
            await update.message.reply_text(
                f"⚠️ Предупреждение: Не удалось проверить существование пользователя @{username}.\n"
                "Убедитесь, что указан корректный username.\n\n"
                "Вы можете продолжить, но учтите, что если username некорректен, "
                "пользователь не сможет получать уведомления."
            )
    
    try:
        # Получаем предыдущий статус команды
        team_before = db.get_team_by_id(team_id)
        was_pending_approved_or_rejected = team_before["status"] in ["pending", "approved", "rejected"]
        
        # Обновляем Telegram username игрока
        db.update_player_username(player_id, username)
        
        # Получаем обновленную команду
        team = db.get_team_by_id(team_id)
        
        # Проверяем, изменился ли статус команды
        status_changed = was_pending_approved_or_rejected and team["status"] == "draft"
        # Сохраняем информацию об изменении статуса
        context.user_data["team_status_changed"] = status_changed
        
        # Формируем сообщение с информацией о команде
        message = await format_team_info(team, is_captain=True)
        
        # Создаем клавиатуру действий
        keyboard = []
        
        # Добавляем кнопки для игроков
        player_buttons = []
        for player in team["players"]:
            player_buttons.append(
                InlineKeyboardButton(
                    f"{player['nickname']} (@{player['telegram_username']})",
                    callback_data=f"player_{player['id']}"
                )
            )
        
        # Добавляем каждого игрока отдельной кнопкой
        for button in player_buttons:
            keyboard.append([button])
        
        # Добавляем кнопки действий для капитана
        keyboard.append([InlineKeyboardButton("✏️ Изменить название", callback_data="edit_team_name")])
        keyboard.append([InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")])
        
        # Кнопка регистрации (только для черновиков)
        if team["status"] == "draft":
            keyboard.append([InlineKeyboardButton("📝 Зарегистрировать на турнир", callback_data="register_team")])
        
        # Кнопка отмены
        keyboard.append([InlineKeyboardButton("❌ Удалить команду", callback_data="cancel_team")])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")])
        
        # Сообщение об изменении статуса, если это произошло
        status_message = ""
        if status_changed:
            status_message = "⚠️ В связи с изменением Telegram username игрока, статус команды изменен на 'Черновик'. Для участия в турнире необходимо заново зарегистрировать команду.\n\n"
        
        await update.message.reply_text(
            f"{status_message}✅ Telegram username игрока успешно изменен!\n\n" + message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        return PROFILE_MENU
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении Telegram username игрока: {e}")
        
        await update.message.reply_text(
            f"❌ Произошла ошибка при обновлении Telegram username игрока: {str(e)}\n"
            "Пожалуйста, попробуйте еще раз или выберите другой username.",
            reply_markup=get_back_to_profile_keyboard()
        )
        
        return TEAM_EDIT_PLAYER_USERNAME

async def start_edit_player_discord(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс редактирования Discord username игрока."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID игрока из callback_data
    player_id = int(query.data.split("_")[3])
    
    # Сохраняем ID игрока в контексте
    context.user_data["current_player_id"] = player_id
    
    # Получаем информацию о команде и игроке
    team_id = context.user_data.get("current_team_id")
    db = context.bot_data["db"]
    team = db.get_team_by_id(team_id)
    
    # Находим игрока по ID
    player = next((p for p in team["players"] if p["id"] == player_id), None)
    
    if not player:
        await query.edit_message_text(
            "⚠️ Игрок не найден. Возможно, он был удален.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    current_discord = player.get('discord_username', 'Не указан')
    
    await query.message.reply_text(
        f"🎮 <b>Редактирование Discord username</b>\n\n"
        f"Игрок: {player['nickname']} (@{player['telegram_username']})\n"
        f"Текущий Discord: <b>{current_discord}</b>\n\n"
        f"Введите новый Discord username (без #1234):",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    
    return TEAM_EDIT_PLAYER_DISCORD

async def process_edit_player_discord(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод нового Discord username игрока."""
    discord_username = update.message.text.strip()
    
    # Проверка на допустимую длину Discord username
    if len(discord_username) < 2 or len(discord_username) > 32:
        await update.message.reply_text(
            "⚠️ Discord username должен содержать от 2 до 32 символов. "
            "Пожалуйста, введите корректный Discord username.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_EDIT_PLAYER_DISCORD
    
    # Получаем Discord ID и проверяем наличие на сервере
    discord_bot = context.bot_data.get("discord_bot")
    discord_id = await get_discord_id_by_username(discord_username, discord_bot)
    
    if not discord_id:
        await update.message.reply_text(
            f"❌ Пользователь с Discord username \"{discord_username}\" не найден на нашем сервере.\n\n"
            f"Возможные причины:\n"
            f"• Неверно указан Discord username\n"
            f"• Пользователь не присоединился к нашему Discord серверу\n\n"
            f"Пожалуйста, проверьте правильность написания и убедитесь, что пользователь присоединился к серверу по ссылке: {DISCORD_INVITE_LINK}",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_EDIT_PLAYER_DISCORD
    
    # Проверяем, состоит ли пользователь в нужном Discord сервере
    is_member = await check_discord_membership(discord_id, discord_bot)
    
    if not is_member:
        await update.message.reply_text(
            f"❌ Пользователь не состоит в нашем Discord сервере.\n\n"
            f"Пожалуйста, попросите игрока присоединиться к серверу по ссылке: {DISCORD_INVITE_LINK}\n"
            f"После этого повторите ввод Discord username.",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_EDIT_PLAYER_DISCORD
    
    player_id = context.user_data.get("current_player_id")
    team_id = context.user_data.get("current_team_id")
    
    if not player_id or not team_id:
        await update.message.reply_text(
            "⚠️ Ошибка: не удалось определить игрока или команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    db = context.bot_data["db"]
    
    # Проверяем, существует ли уже игрок с таким Discord username в команде (исключая текущего игрока)
    if db.check_discord_exists_in_team(team_id, discord_username, exclude_player_id=player_id):
        await update.message.reply_text(
            f"❌ Произошла ошибка при обновлении: Игрок с таким Discord username уже есть в команде.\n"
            "Каждый игрок должен иметь уникальный Discord аккаунт.\n"
            "Пожалуйста, введите другой Discord username:",
            reply_markup=get_back_to_profile_keyboard()
        )
        return TEAM_EDIT_PLAYER_DISCORD
    
    try:
        # Получаем предыдущий статус команды
        team_before = db.get_team_by_id(team_id)
        was_pending_approved_or_rejected = team_before["status"] in ["pending", "approved", "rejected"]
        
        # Обновляем Discord данные игрока
        db.update_player_discord(player_id, discord_username, discord_id)
        
        # Получаем обновленную команду
        team = db.get_team_by_id(team_id)
        
        # Проверяем, изменился ли статус команды
        status_changed = was_pending_approved_or_rejected and team["status"] == "draft"
        # Сохраняем информацию об изменении статуса
        context.user_data["team_status_changed"] = status_changed
        
        # Формируем сообщение с информацией о команде
        message = await format_team_info(team, is_captain=True)
        
        # Создаем клавиатуру действий
        keyboard = []
        
        # Добавляем кнопки для игроков
        player_buttons = []
        for player in team["players"]:
            player_buttons.append(
                InlineKeyboardButton(
                    f"{player['nickname']} (@{player['telegram_username']})",
                    callback_data=f"player_{player['id']}"
                )
            )
        
        # Добавляем каждого игрока отдельной кнопкой
        for button in player_buttons:
            keyboard.append([button])
        
        # Добавляем кнопки действий для капитана
        keyboard.append([InlineKeyboardButton("✏️ Изменить название", callback_data="edit_team_name")])
        keyboard.append([InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")])
        
        # Кнопка регистрации (только для черновиков)
        if team["status"] == "draft":
            keyboard.append([InlineKeyboardButton("📝 Зарегистрировать на турнир", callback_data="register_team")])
        
        # Кнопка отмены
        keyboard.append([InlineKeyboardButton("❌ Удалить команду", callback_data="cancel_team")])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")])
        
        # Сообщение об изменении статуса, если это произошло
        status_message = ""
        if status_changed:
            status_message = "⚠️ В связи с изменением Discord данных игрока, статус команды изменен на 'Черновик'. Для участия в турнире необходимо заново зарегистрировать команду.\n\n"
        
        await update.message.reply_text(
            f"{status_message}✅ Discord данные игрока успешно изменены!\n\n" + message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        return PROFILE_MENU
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении Discord данных игрока: {e}")
        
        await update.message.reply_text(
            f"❌ Произошла ошибка при обновлении Discord данных игрока: {str(e)}\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=get_back_to_profile_keyboard()
        )
        
        return TEAM_EDIT_PLAYER_DISCORD

async def process_delete_player(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать подтверждение удаления игрока."""
    query = update.callback_query
    await query.answer()
    
    # Получаем решение из callback_data
    parts = query.data.split("_")
    decision = parts[3]
    player_id = int(parts[4])
    
    # Если отмена, возвращаемся к просмотру игрока
    if decision == "no":
        return await view_player(update, context)
    
    # Если подтверждение, удаляем игрока
    team_id = context.user_data.get("current_team_id")
    db = context.bot_data["db"]
    
    try:
        # Получаем предыдущий статус команды
        team_before = db.get_team_by_id(team_id)
        was_pending_approved_or_rejected = team_before["status"] in ["pending", "approved", "rejected"]
        
        # Удаляем игрока
        db.delete_player(player_id)
        
        # Получаем обновленную команду
        team = db.get_team_by_id(team_id)
        
        # Проверяем, изменился ли статус команды
        status_changed = was_pending_approved_or_rejected and team["status"] == "draft"
        # Сохраняем информацию об изменении статуса
        context.user_data["team_status_changed"] = status_changed
        
        # Формируем сообщение с информацией о команде
        message = await format_team_info(team, is_captain=True)
        
        # Создаем клавиатуру действий
        keyboard = []
        
        # Добавляем кнопки для игроков
        player_buttons = []
        for player in team["players"]:
            player_buttons.append(
                InlineKeyboardButton(
                    f"{player['nickname']} (@{player['telegram_username']})",
                    callback_data=f"player_{player['id']}"
                )
            )
        
        # Добавляем каждого игрока отдельной кнопкой
        for button in player_buttons:
            keyboard.append([button])
        
        # Добавляем кнопки действий для капитана
        keyboard.append([InlineKeyboardButton("✏️ Изменить название", callback_data="edit_team_name")])
        keyboard.append([InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")])
        
        # Кнопка регистрации (только для черновиков)
        if team["status"] == "draft":
            keyboard.append([InlineKeyboardButton("📝 Зарегистрировать на турнир", callback_data="register_team")])
        
        # Кнопка отмены
        keyboard.append([InlineKeyboardButton("❌ Удалить команду", callback_data="cancel_team")])
        
        # Добавляем кнопку "Назад"
        keyboard.append([InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")])
        
        # Сообщение об изменении статуса, если это произошло
        status_message = ""
        if status_changed:
            status_message = "⚠️ В связи с удалением игрока, статус команды изменен на 'Черновик'. Для участия в турнире необходимо заново зарегистрировать команду.\n\n"
        
        await query.edit_message_text(
            f"{status_message}✅ Игрок успешно удален из команды!\n\n" + message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        return PROFILE_MENU
        
    except Exception as e:
        logger.error(f"Ошибка при удалении игрока: {e}")
        
        await query.edit_message_text(
            f"❌ Произошла ошибка при удалении игрока: {str(e)}\n",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        
        return PROFILE_MENU

async def confirm_delete_player(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение удаления игрока."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID игрока из callback_data
    player_id = int(query.data.split("_")[2])
    
    # Сохраняем ID игрока в контексте
    context.user_data["current_player_id"] = player_id
    
    # Получаем информацию о команде и игроке
    team_id = context.user_data.get("current_team_id")
    db = context.bot_data["db"]
    team = db.get_team_by_id(team_id)
    
    # Находим игрока по ID
    player = next((p for p in team["players"] if p["id"] == player_id), None)
    
    if not player:
        await query.edit_message_text(
            "⚠️ Игрок не найден. Возможно, он был удален.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Вернуться к команде", callback_data=f"view_team_{team_id}")
            ]])
        )
        return PROFILE_MENU
    
    # Создаем клавиатуру для подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"delete_player_confirm_yes_{player_id}")],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data=f"delete_player_confirm_no_{player_id}")]
    ]
    
    await query.edit_message_text(
        f"⚠️ <b>Вы уверены, что хотите удалить игрока?</b>\n\n"
        f"Игрок: {player['nickname']} (@{player['telegram_username']})\n\n"
        f"Это действие нельзя отменить.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return PROFILE_MENU

async def cancel_team_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменить регистрацию команды."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID команды
    team_id = context.user_data.get("current_team_id")
    if not team_id:
        await query.edit_message_text(
            "⚠️ Ошибка: не удалось определить команду. Пожалуйста, вернитесь в личный кабинет и попробуйте снова.",
            reply_markup=get_profile_inline_keyboard()
        )
        return PROFILE_MENU
    
    # Создаем клавиатуру для подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data="confirm_cancel_yes")],
        [InlineKeyboardButton("❌ Нет, оставить", callback_data="confirm_cancel_no")]
    ]
    
    await query.edit_message_text(
        "⚠️ <b>Вы уверены, что хотите удалить команду?</b>\n\n"
        "Это действие нельзя отменить. Все данные о команде будут удалены.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return PROFILE_MENU

async def confirm_cancel_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение отмены регистрации команды."""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "confirm_cancel_yes":
        team_id = context.user_data.get("current_team_id")
        if not team_id:
            await query.edit_message_text(
                "❌ Произошла ошибка. Не удалось идентифицировать вашу команду.",
                reply_markup=get_profile_inline_keyboard()
            )
            return PROFILE_MENU
        
        # Удаляем команду из базы данных
        db = context.bot_data["db"]
        
        # Получаем информацию о команде перед удалением
        team = db.get_team_by_id(team_id)
        
        if team:
            # Если команда была одобрена, нужно снять Discord роли
            if team['status'] == 'approved':
                discord_bot = context.bot_data.get("discord_bot")
                discord_server_id = context.bot_data.get("discord_server_id")
                discord_role_id = context.bot_data.get("discord_role_id")
                discord_captain_role_id = context.bot_data.get("discord_captain_role_id")
                
                from handlers.utils import process_team_roles
                
                # Пытаемся снять роли
                try:
                    roles_removed = await process_team_roles(
                        db, 
                        discord_bot, 
                        discord_server_id, 
                        discord_role_id, 
                        discord_captain_role_id, 
                        team_id, 
                        'approved', 
                        'draft'
                    )
                    
                    # Если не удалось снять роли, прерываем удаление
                    if not roles_removed:
                        await query.edit_message_text(
                            "❌ Не удалось снять роли в Discord. Удаление команды отменено.",
                            reply_markup=get_profile_inline_keyboard()
                        )
                        return PROFILE_MENU
                
                except Exception as e:
                    logger.error(f"Ошибка при снятии ролей Discord: {e}")
                    await query.edit_message_text(
                        "❌ Произошла ошибка при снятии ролей в Discord. Удаление команды отменено.",
                        reply_markup=get_profile_inline_keyboard()
                    )
                    return PROFILE_MENU
            
            # Удаляем команду только после успешного снятия ролей
            if db.delete_team(team_id):
                await query.edit_message_text(
                    "✅ Команда успешно удалена.\n\n"
                    "Вы можете создать новую команду, выбрав пункт \"Создать команду\" в личном кабинете.",
                    reply_markup=get_profile_inline_keyboard()
                )
                
                # Очищаем данные команды из контекста
                if "current_team_id" in context.user_data:
                    del context.user_data["current_team_id"]
                    
                return PROFILE_MENU
            else:
                await query.edit_message_text(
                    "❌ Произошла ошибка при удалении команды. Пожалуйста, попробуйте позже или обратитесь к администратору.",
                    reply_markup=get_profile_inline_keyboard()
                )
                return PROFILE_MENU
        else:
            await query.edit_message_text(
                "❌ Команда не найдена.",
                reply_markup=get_profile_inline_keyboard()
            )
            return PROFILE_MENU
    else:  # "confirm_cancel_no"
        # Возвращаемся к информации о команде
        team_id = context.user_data.get("current_team_id")
        db = context.bot_data["db"]
        team = db.get_team_by_id(team_id)
        
        is_captain = any(p.get("is_captain", False) and p.get("telegram_id") == query.from_user.id for p in team["players"])
        
        # Форматируем информацию о команде
        message = await format_team_info(team, is_captain=is_captain)
        
        # Создаем клавиатуру действий
        keyboard = []
        
        # Добавляем кнопки для игроков
        player_buttons = []
        for player in team["players"]:
            player_buttons.append(
                InlineKeyboardButton(
                    f"{player['nickname']} (@{player['telegram_username']})",
                    callback_data=f"player_{player['id']}"
                )
            )
        
        # Добавляем каждого игрока отдельной кнопкой
        for button in player_buttons:
            keyboard.append([button])
        
        # Добавляем кнопки действий для капитана
        if is_captain:
            keyboard.append([InlineKeyboardButton("✏️ Изменить название", callback_data="edit_team_name")])
            keyboard.append([InlineKeyboardButton("➕ Добавить игрока", callback_data="add_player")])
            
            if team["status"] == "draft":
                keyboard.append([InlineKeyboardButton("📝 Зарегистрировать на турнир", callback_data="register_team")])
            
            keyboard.append([InlineKeyboardButton("❌ Удалить команду", callback_data="cancel_team")])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад к списку команд", callback_data="profile_teams")])
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        return PROFILE_MENU

async def back_to_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться в личный кабинет."""
    # Может быть вызван как из сообщения, так и из callback_query
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        return await profile_menu(update, context)
    else:
        return await profile_menu(update, context)

async def handle_profile_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для кнопок действий в личном кабинете."""
    query = update.callback_query
    data = query.data
    
    if data == "profile_back":
        return await profile_menu(update, context)
    elif data == "profile_teams":
        return await show_my_teams(update, context)
    elif data == "profile_create_team":
        return await start_create_team(update, context)
    elif data == "profile_check_status":
        # Импортируем функцию проверки статуса
        from handlers.status import check_registration_status
        # Вызовем её с переданным callback_query
        return await check_registration_status(update, context)
    elif data == "profile_main_menu":
        return await back_to_main_menu(update, context)
    elif data == "add_player":
        return await add_player_start(update, context)
    elif data == "edit_team_name":
        return await start_edit_team_name(update, context)
    elif data == "register_team":
        return await register_team_for_tournament(update, context)
    elif data.startswith("register_for_tournament_"):
        return await confirm_tournament_registration(update, context)
    elif data.startswith("confirm_register_anyway_"):
        # Обработка кнопки "Продолжить регистрацию" для команд с неподписанными игроками
        return await complete_registration_anyway(update, context)
    elif data.startswith("confirm_register_"):
        # Обычная регистрация команды
        return await complete_tournament_registration(update, context)
    elif data == "cancel_team":
        return await cancel_team_registration(update, context)
    elif data.startswith("player_"):
        return await view_player(update, context)
    elif data.startswith("edit_player_nickname_"):
        return await start_edit_player_nickname(update, context)
    elif data.startswith("edit_player_username_"):
        return await start_edit_player_username(update, context)
    elif data.startswith("edit_player_discord_"):
        return await start_edit_player_discord(update, context)
    elif data.startswith("delete_player_") and not data.startswith("delete_player_confirm_"):
        return await confirm_delete_player(update, context)
    elif data.startswith("delete_player_confirm_"):
        return await process_delete_player(update, context)
    elif data.startswith("confirm_cancel_"):
        return await confirm_cancel_team(update, context)
    elif data.startswith("view_team_"):
        return await view_team(update, context)
    
    # Добавляем отладочное сообщение для неопознанных callback_data
    await query.answer(f"Неизвестная команда: {data}", show_alert=True)
    logger.warning(f"Неизвестная callback_data: {data}")
    return PROFILE_MENU

# Вспомогательные функции
async def get_tg_id_by_username(username: str, userbot):
    """
    Получает Telegram ID пользователя по его username с помощью Pyrogram.
    
    Args:
        username: Username пользователя (без @)
        userbot: Экземпляр клиента Pyrogram
        
    Returns:
        ID пользователя или None, если пользователь не найден
    """
    if not userbot:
        logger.warning(f"Pyrogram не инициализирован. Невозможно проверить username @{username}")
        return None
    
    try:
        users = await userbot.get_users(username)
        if users:
            if isinstance(users, list):
                if users:
                    return users[0].id
                else:
                    return None
            else:
                return users.id
        else:
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении Telegram ID для @{username}: {e}")
        return None
    
async def check_pubg_nickname(nickname: str) -> tuple[bool, str]:
    """
    Проверяет существование игрового никнейма PUBG через API и возвращает его в правильном регистре.
    
    Args:
        nickname: Игровой никнейм для проверки
        
    Returns:
        Кортеж (существует, правильный_никнейм)
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.pubg.report/search/{nickname}") as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Если найден хотя бы один игрок
                    if data and len(data) > 0:
                        # Берем первый результат и его никнейм в правильном регистре
                        correct_nickname = data[0].get("nickname", nickname)
                        return True, correct_nickname
                
                # Если пустой список или ошибка
                return False, nickname
    except Exception as e:
        logger.error(f"Ошибка при проверке никнейма PUBG: {e}")
        # В случае ошибки запроса считаем никнейм действительным
        return True, nickname
    
async def check_channel_subscription(userbot, telegram_id: int, channel_id: str) -> bool:
    """
    Проверяет, подписан ли пользователь на канал.
    
    Args:
        userbot: Экземпляр клиента Pyrogram
        telegram_id: Telegram ID пользователя
        channel_id: ID канала для проверки
        
    Returns:
        True, если пользователь подписан на канал, иначе False
    """
    if not userbot:
        logger.warning("Pyrogram не инициализирован. Невозможно проверить подписку на канал.")
        return True  # Если Pyrogram не доступен, считаем, что пользователь подписан
    
    # Убираем символ @ из канала, если он есть
    clean_channel_id = channel_id.lstrip('@')
    
    try:
        # Получаем информацию о подписке пользователя на канал
        chat_member = await userbot.get_chat_member(clean_channel_id, telegram_id)
        
        # Если мы дошли до этой точки без исключения, значит пользователь подписан
        logger.info(f"Пользователь {telegram_id} подписан на канал {channel_id}")
        return True
        
    except Exception as e:
        # Только если ошибка именно о неучастии пользователя
        if "USER_NOT_PARTICIPANT" in str(e):
            logger.info(f"Пользователь {telegram_id} не подписан на канал {channel_id}")
            return False
        else:
            # При других ошибках логируем и считаем подписанным
            logger.error(f"Ошибка при проверке подписки на канал для пользователя {telegram_id}: {e}")
            return True

async def get_discord_id_by_username(username: str, discord_bot) -> Optional[str]:
    """
    Получает Discord ID пользователя по его username.
    
    Args:
        username: Discord username пользователя
        discord_bot: Экземпляр бота Discord
        
    Returns:
        Discord ID пользователя или None, если пользователь не найден
    """
    if not discord_bot or not discord_bot.is_ready():
        logger.warning(f"Discord бот не готов. Невозможно проверить username {username}")
        return None
    
    try:
        # Получаем server_id напрямую из глобальной переменной
        from main import DISCORD_SERVER_ID
        
        if not DISCORD_SERVER_ID:
            logger.error("Discord Server ID не найден")
            return None
            
        server_id = int(DISCORD_SERVER_ID)
        guild = discord_bot.get_guild(server_id)
        
        if not guild:
            logger.error(f"Сервер Discord с ID {server_id} не найден")
            return None
        
        # Ищем пользователя по имени в указанном сервере
        for member in guild.members:
            if member.name.lower() == username.lower():
                return str(member.id)
        
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении Discord ID для {username}: {e}")
        return None

async def check_discord_membership(discord_id: str, discord_bot) -> bool:
    """
    Проверяет, является ли пользователь участником Discord сервера.
    
    Args:
        discord_id: Discord ID пользователя
        discord_bot: Экземпляр бота Discord
        
    Returns:
        True, если пользователь состоит в сервере, иначе False
    """
    if not discord_bot or not discord_bot.is_ready():
        logger.warning("Discord бот не готов. Невозможно проверить членство")
        return False
    
    try:
        # Получаем server_id напрямую из глобальной переменной
        from main import DISCORD_SERVER_ID
        
        if not DISCORD_SERVER_ID:
            logger.error("Discord Server ID не найден")
            return False
            
        server_id = int(DISCORD_SERVER_ID)
        guild = discord_bot.get_guild(server_id)
        
        if not guild:
            logger.error(f"Сервер Discord с ID {server_id} не найден")
            return False
        
        member = guild.get_member(int(discord_id))
        return member is not None
    except Exception as e:
        logger.error(f"Ошибка при проверке Discord-членства для ID {discord_id}: {e}")
        return False

def register_profile_handlers(application: Application) -> None:
    """Регистрация всех обработчиков для личного кабинета."""
    # Импортируем функции из модуля status.py
    from handlers.status import check_registration_status, confirm_cancel_registration
    from handlers.status import show_my_team, prompt_team_name, search_team_by_name
    from handlers.status import back_to_status_menu, back_to_main as status_back_to_main
    
    # Обработчик команды для личного кабинета
    profile_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^👤 Личный кабинет$"), profile_menu)],
        states={
            PROFILE_MENU: [
                CallbackQueryHandler(handle_profile_action, pattern="^profile_"),
                CallbackQueryHandler(view_team, pattern="^view_team_"),
                CallbackQueryHandler(handle_profile_action, pattern="^(add_player|edit_team_name|register_team|cancel_team)$"),
                CallbackQueryHandler(handle_profile_action, pattern="^player_"),
                CallbackQueryHandler(handle_profile_action, pattern="^edit_player_"),
                CallbackQueryHandler(handle_profile_action, pattern="^delete_player_"),
                CallbackQueryHandler(handle_profile_action, pattern="^confirm_"),
                CallbackQueryHandler(handle_profile_action, pattern="^register_for_tournament_"),
                CallbackQueryHandler(handle_profile_action, pattern="^player_"),
                MessageHandler(filters.Regex("^👤 Личный кабинет$"), profile_menu),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), profile_menu),
            ],
            TEAM_CREATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_team_name),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            TEAM_CREATE_CAPTAIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_captain_nickname),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            TEAM_CREATE_CAPTAIN_DISCORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_captain_discord),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            TEAM_ADD_PLAYER_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_player_username),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            TEAM_ADD_PLAYER_NICKNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_player_nickname),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            TEAM_ADD_PLAYER_DISCORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_player_discord),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            TEAM_EDIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_edit_team_name),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            TEAM_EDIT_PLAYER_NICKNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_edit_player_nickname),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            TEAM_EDIT_PLAYER_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_edit_player_username),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            TEAM_EDIT_PLAYER_DISCORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^◀️ Назад в личный кабинет$"), process_edit_player_discord),
                MessageHandler(filters.Regex("^◀️ Назад в личный кабинет$"), back_to_profile),
            ],
            # Добавляем обработчики статусов из модуля status.py
            STATUS_INPUT: [
                MessageHandler(filters.Regex("^👤 Моя команда$"), show_my_team),
                MessageHandler(filters.Regex("^🎮 Поиск по названию$"), prompt_team_name),
                MessageHandler(filters.Regex("^◀️ Назад$"), back_to_profile),
            ],
            STATUS_TEAM_ACTION: [
                MessageHandler(filters.Regex("^❌ Отменить регистрацию$|^◀️ Назад$"), status_back_to_main),
            ],
            STATUS_CONFIRM_CANCEL: [
                MessageHandler(filters.Regex("^✅ Да, отменить$|^❌ Нет, оставить$"), confirm_cancel_registration),
            ],
            STATUS_SEARCH_TEAM: [
                MessageHandler(filters.Regex("^◀️ Назад$"), back_to_status_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_team_by_name),
            ],
        },
        fallbacks=[CommandHandler("start", back_to_main_menu)],
    )
    
    application.add_handler(profile_handler)