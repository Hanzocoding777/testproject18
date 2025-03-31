import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, Application
)

from constants import *

logger = logging.getLogger(__name__)

async def check_registration_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверка статуса регистрации команды по Telegram ID пользователя."""
    # Определяем, откуда брать user_id (из сообщения или из callback_query)
    if update.callback_query:
        user_id = update.callback_query.from_user.id
    else:
        user_id = update.message.from_user.id
    
    db = context.bot_data["db"]
    
    # Создаем клавиатуру для выбора метода проверки
    check_keyboard = [
        [KeyboardButton("👤 Моя команда")],
        [KeyboardButton("🎮 Поиск по названию")],
        [KeyboardButton("◀️ Назад")]
    ]
    check_markup = ReplyKeyboardMarkup(check_keyboard, resize_keyboard=True)
    
    # Если это callback_query, отправляем новое сообщение
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            "🔍 <b>Проверка статуса регистрации</b>\n\n"
            "Выберите способ проверки:\n"
            "• <b>Моя команда</b> - узнать статус своей команды\n"
            "• <b>Поиск по названию</b> - найти команду по названию",
            reply_markup=check_markup,
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "🔍 <b>Проверка статуса регистрации</b>\n\n"
            "Выберите способ проверки:\n"
            "• <b>Моя команда</b> - узнать статус своей команды\n"
            "• <b>Поиск по названию</b> - найти команду по названию",
            reply_markup=check_markup,
            parse_mode="HTML"
        )
    
    return STATUS_INPUT

async def show_my_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать информацию о команде пользователя."""
    # Определяем откуда брать user_id и как отправлять сообщение
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        reply_func = update.callback_query.message.reply_text
        await update.callback_query.answer()
    else:
        user_id = update.message.from_user.id
        reply_func = update.message.reply_text
    
    db = context.bot_data["db"]
    
    # Пытаемся найти команду пользователя по его Telegram ID
    team = db.get_team_by_telegram_id(user_id)
    
    if team:
        # Формируем сообщение с информацией о команде
        message = await format_team_info(team, is_my_team=True)
        
        # Создаем клавиатуру в зависимости от статуса команды и роли пользователя
        keyboard = []
        
        # Проверяем, является ли пользователь капитаном
        is_captain = any(p.get("is_captain", False) and p.get("telegram_id") == user_id for p in team["players"])
        
        if is_captain and team["status"] == "pending":
            # Если пользователь капитан и заявка в ожидании, предлагаем отменить заявку
            keyboard.append([KeyboardButton("❌ Отменить регистрацию")])
        
        keyboard.append([KeyboardButton("◀️ Назад")])
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await reply_func(message, reply_markup=reply_markup, parse_mode="HTML")
        
        # Сохраняем ID команды в контексте для возможных дальнейших действий
        context.user_data["current_team_id"] = team["id"]
        
        return STATUS_TEAM_ACTION
    else:
        # Если команда не найдена
        message = (
            "⚠️ <b>Команда не найдена</b>\n\n"
            "Вы еще не зарегистрировали свою команду или не являетесь участником какой-либо команды.\n\n"
            "Чтобы зарегистрировать команду, воспользуйтесь личным кабинетом."
        )
        
        back_keyboard = ReplyKeyboardMarkup([[KeyboardButton("◀️ Назад")]], resize_keyboard=True)
        
        await reply_func(message, reply_markup=back_keyboard, parse_mode="HTML")
        return STATUS_INPUT

async def prompt_team_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запросить название команды для поиска."""
    await update.message.reply_text(
        "🔍 Введите название команды для поиска:",
        reply_markup=get_back_keyboard()
    )
    return STATUS_SEARCH_TEAM

async def search_team_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Найти команду по названию."""
    team_name = update.message.text.strip()
    db = context.bot_data["db"]
    
    # Проверка на минимальную длину названия
    if len(team_name) < 3:
        await update.message.reply_text(
            "⚠️ Слишком короткое название для поиска. Введите минимум 3 символа.",
            reply_markup=get_back_keyboard()
        )
        return STATUS_SEARCH_TEAM
    
    # Ищем команду по названию
    team = db.get_team_by_name(team_name)
    
    if team:
        # Формируем сообщение с информацией о команде (публичная версия)
        message = await format_team_info(team, is_my_team=False)
        
        back_keyboard = ReplyKeyboardMarkup([[KeyboardButton("◀️ Назад")]], resize_keyboard=True)
        
        await update.message.reply_text(message, reply_markup=back_keyboard, parse_mode="HTML")
        return STATUS_INPUT
    else:
        # Если команда не найдена
        await update.message.reply_text(
            f"❌ Команда с названием \"{team_name}\" не найдена.\n\n"
            "Проверьте правильность ввода названия или попробуйте другое название.",
            reply_markup=get_back_keyboard()
        )
        return STATUS_SEARCH_TEAM

async def format_team_info(team, is_my_team=False) -> str:
    """
    Форматирует информацию о команде для отображения.
    
    Args:
        team: Словарь с данными о команде
        is_my_team: True, если это команда текущего пользователя
        
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
        players_list += f"{idx}. {player['nickname']} (@{player['telegram_username']})"
        if player.get('discord_username'):
            players_list += f" Discord: {player['discord_username']}"
        players_list += "\n"
    
    # Базовое сообщение
    message = (
        "🔍 <b>Информация о команде:</b>\n\n"
        f"🎮 <b>Название команды:</b> {team['team_name']}\n"
        f"📅 <b>Дата регистрации:</b> {team['registration_date']}\n"
        f"📊 <b>Общий статус:</b> {status_text}\n"
    )
    
    # Добавляем информацию о турнирах
    if team.get("tournaments"):
        message += "\n🏆 <b>Участие в турнирах:</b>\n"
        for tournament in team["tournaments"]:
            # Определяем эмодзи статуса
            status_emoji = "⏳" if tournament["registration_status"] == "pending" else "✅" if tournament["registration_status"] == "approved" else "❌"
            tournament_status = TEAM_STATUS.get(tournament["registration_status"], "Неизвестно")
            
            message += (
                f"\n• {status_emoji} <b>{tournament['name']}</b>\n"
                f"  📅 Дата проведения: {tournament['event_date']}\n"
                f"  📊 Статус заявки: {tournament_status}\n"
            )
    elif team["status"] == "draft":
        message += "\n📝 <i>Команда пока не зарегистрирована ни на один турнир</i>\n"
    
    # Дополнительная информация для своей команды
    if is_my_team:
        message += f"\n📱 <b>Контакт капитана:</b> {team['captain_contact']}\n"
    
    # Добавляем информацию о капитане
    if captain:
        message += f"👨‍✈️ <b>Капитан:</b> {captain['nickname']} (@{captain['telegram_username']})\n"
        if captain.get('discord_username'):
            message += f"🎮 <b>Discord капитана:</b> {captain['discord_username']}\n"
    
    # Добавляем комментарий администратора, если он есть
    if team.get("admin_comment"):
        message += f"\n💬 <b>Комментарий администратора:</b>\n{team['admin_comment']}\n"
    
    # Добавляем список игроков
    message += f"\n<b>Игроки:</b>\n{players_list}"
    
    # Дополнительная информация по статусам турниров
    if is_my_team:
        if all(t["registration_status"] == "approved" for t in team.get("tournaments", [])):
            message += (
                "\n✅ <b>Все заявки на турниры одобрены!</b>\n"
                "Ожидайте дальнейших инструкций от организаторов."
            )
        elif any(t["registration_status"] == "pending" for t in team.get("tournaments", [])):
            message += (
                "\n⏳ <b>Есть заявки на рассмотрении.</b>\n"
                "Мы уведомим вас, когда статус изменится."
            )
        elif team["status"] == "draft":
            message += (
                "\n📝 <b>Команда в стадии формирования.</b>\n"
                "Для участия в турнирах необходимо зарегистрировать команду."
            )
    
    return message

async def handle_team_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка действий с командой пользователя."""
    action = update.message.text.strip()
    
    if action == "❌ Отменить регистрацию":
        # Создаем клавиатуру для подтверждения
        confirm_keyboard = [
            [KeyboardButton("✅ Да, отменить")],
            [KeyboardButton("❌ Нет, оставить")]
        ]
        confirm_markup = ReplyKeyboardMarkup(confirm_keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "⚠️ <b>Вы уверены, что хотите отменить регистрацию вашей команды?</b>\n\n"
            "Это действие нельзя отменить. Все данные о команде будут удалены.",
            reply_markup=confirm_markup,
            parse_mode="HTML"
        )
        return STATUS_CONFIRM_CANCEL
    elif action == "◀️ Назад":
        return await check_registration_status(update, context)
    else:
        return await check_registration_status(update, context)

async def confirm_cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение отмены регистрации команды."""
    choice = update.message.text.strip()
    
    if choice == "✅ Да, отменить":
        team_id = context.user_data.get("current_team_id")
        if not team_id:
            # Если ID команды не найден в контексте
            await update.message.reply_text(
                "❌ Произошла ошибка. Не удалось идентифицировать вашу команду.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
        
        # Удаляем команду из базы данных
        db = context.bot_data["db"]
        if db.delete_team(team_id):
            await update.message.reply_text(
                "✅ Регистрация вашей команды успешно отменена.\n\n"
                "Вы можете создать новую команду в личном кабинете.",
                reply_markup=get_main_keyboard()
            )
            
            # Очищаем данные команды из контекста
            if "current_team_id" in context.user_data:
                del context.user_data["current_team_id"]
                
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при отмене регистрации. Пожалуйста, попробуйте позже или обратитесь к администратору.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
    else:
        # Возвращаемся к информации о команде
        return await show_my_team(update, context)

async def back_to_status_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться в меню проверки статуса."""
    return await check_registration_status(update, context)

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться в главное меню."""
    await update.message.reply_text(
        "Вы вернулись в главное меню. Выберите нужное действие:",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

def get_back_keyboard():
    """Простая клавиатура только с кнопкой Назад."""
    keyboard = [
        [KeyboardButton("◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_main_keyboard():
    """Главная клавиатура с основными функциями."""
    keyboard = [
        [KeyboardButton("👤 Личный кабинет")],
        [KeyboardButton("ℹ️ Информация о турнире")],
        [KeyboardButton("❓ FAQ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def back_to_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться в профиль."""
    from handlers.profile import profile_menu
    return await profile_menu(update, context)

def register_status_handlers(application: Application) -> None:
    """Регистрация всех обработчиков для проверки статуса."""
    
    status_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Проверить статус регистрации$"), check_registration_status)],
        states={
            STATUS_INPUT: [
                MessageHandler(filters.Regex("^👤 Моя команда$"), show_my_team),
                MessageHandler(filters.Regex("^🎮 Поиск по названию$"), prompt_team_name),
                MessageHandler(filters.Regex("^◀️ Назад$"), back_to_main),
            ],
            STATUS_TEAM_ACTION: [
                MessageHandler(filters.Regex("^❌ Отменить регистрацию$|^◀️ Назад$"), handle_team_action),
            ],
            STATUS_CONFIRM_CANCEL: [
                MessageHandler(filters.Regex("^✅ Да, отменить$|^❌ Нет, оставить$"), confirm_cancel_registration),
            ],
            STATUS_SEARCH_TEAM: [
                MessageHandler(filters.Regex("^◀️ Назад$"), back_to_status_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_team_by_name),
            ],
        },
        fallbacks=[CommandHandler("start", back_to_main)],
    )
    
    application.add_handler(status_handler)
