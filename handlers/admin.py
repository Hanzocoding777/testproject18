import re
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, 
    ConversationHandler, MessageHandler, filters, Application
)

from handlers.utils import process_team_roles
from constants import *

logger = logging.getLogger(__name__)

# Новые состояния для управления турнирами
(
    ADMIN_TOURNAMENT_MENU,
    ADMIN_CREATE_TOURNAMENT_NAME,
    ADMIN_CREATE_TOURNAMENT_DESCRIPTION,
    ADMIN_CREATE_TOURNAMENT_DATE,
    ADMIN_EDIT_TOURNAMENT,
    ADMIN_EDIT_TOURNAMENT_NAME,
    ADMIN_EDIT_TOURNAMENT_DESCRIPTION,
    ADMIN_EDIT_TOURNAMENT_DATE,
) = range(ADMIN_TEAM_FILTER + 1, ADMIN_TEAM_FILTER + 9)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать админ-панель."""
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("У вас нет доступа к админ-панели.")
        return ConversationHandler.END

    # Получаем статистику по командам
    all_teams = db.get_all_teams()
    pending_count = len([t for t in all_teams if t["status"] == "pending"])
    approved_count = len([t for t in all_teams if t["status"] == "approved"])
    rejected_count = len([t for t in all_teams if t["status"] == "rejected"])
    total_count = len(all_teams)

    keyboard = [
        [InlineKeyboardButton(f"📋 Список команд ({total_count})", callback_data="admin_teams_list")],
        [
            InlineKeyboardButton(f"✅ Одобренные ({approved_count})", callback_data="admin_teams_approved"),
            InlineKeyboardButton(f"❌ Отклоненные ({rejected_count})", callback_data="admin_teams_rejected")
        ],
        [InlineKeyboardButton(f"⏳ Ожидающие ({pending_count})", callback_data="admin_teams_pending")],
        [InlineKeyboardButton("🏆 Управление турнирами", callback_data="admin_tournaments")],
        [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add_admin")],
        [InlineKeyboardButton("👥 Список админов", callback_data="admin_admins_list")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔐 Админ-панель\n\nВыберите действие:",
        reply_markup=reply_markup
    )
    return ADMIN_MENU

async def admin_teams_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать список турниров для просмотра команд с определенным статусом."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return

    command_parts = query.data.split("_")
    filter_status = None
    
    # Обработка случая, когда выбрана конкретная команда
    if len(command_parts) > 3 and command_parts[2] == "team":
        team_id = int(command_parts[3])
        return await show_team_info(update, context, team_id)
    
    # Если выбран фильтр по статусу
    if len(command_parts) > 2:
        status_map = {"approved": "approved", "rejected": "rejected", "pending": "pending"}
        filter_status = status_map.get(command_parts[2])
    
    # Если фильтр не выбран, показываем все команды без группировки по турнирам
    if not filter_status:
        teams = db.get_all_teams()
        
        if not teams:
            back_button = InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
            ]])
            
            await query.edit_message_text(
                "Зарегистрированных команд пока нет.",
                reply_markup=back_button
            )
            return

        # Формируем список всех команд с кнопками
        keyboard = []
        message = "<b>📋 Все команды</b>\n\n"
        message += f"Найдено команд: {len(teams)}\n\n"
        message += "Выберите команду для просмотра подробной информации:\n"
        
        for team in teams:
            status_emoji = "⏳" if team["status"] == "pending" else "✅" if team["status"] == "approved" else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_emoji} {team['team_name']}",
                    callback_data=f"admin_teams_team_{team['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return
    
    # Если выбран фильтр по статусу, показываем список турниров
    tournaments = db.get_all_tournaments()
    
    if not tournaments:
        back_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
        ]])
        
        await query.edit_message_text(
            "В системе нет созданных турниров.",
            reply_markup=back_button
        )
        return
    
    # Выбираем правильный emoji и текст для статуса
    status_emoji = "⏳" if filter_status == "pending" else "✅" if filter_status == "approved" else "❌"
    status_text = "ожидающие" if filter_status == "pending" else "одобренные" if filter_status == "approved" else "отклоненные"
    
    # Формируем список турниров с количеством команд с выбранным статусом
    keyboard = []
    
    for tournament in tournaments:
        # Получаем количество команд для этого турнира с указанным статусом
        tournament_teams = db.get_all_teams(status=filter_status, tournament_id=tournament['id'])
        teams_count = len(tournament_teams)
        
        keyboard.append([
            InlineKeyboardButton(
                f"{tournament['name']} ({teams_count} команд)",
                callback_data=f"admin_tournament_teams_status_{tournament['id']}_{filter_status}"
            )
        ])
    
    # Добавляем опцию "Все турниры"
    all_teams = db.get_all_teams(status=filter_status)
    all_teams_count = len(all_teams)
    
    keyboard.append([
        InlineKeyboardButton(
            f"Все турниры ({all_teams_count} команд)",
            callback_data=f"admin_tournament_teams_status_all_{filter_status}"
        )
    ])
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])
    
    await query.edit_message_text(
        f"{status_emoji} <b>{status_text.capitalize()} команды</b>\n\n"
        f"Выберите турнир для просмотра команд:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
async def admin_tournament_status_teams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать список команд определенного турнира с определенным статусом."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Разбираем данные callback
    parts = query.data.split("_")
    tournament_id = parts[4]
    status = parts[5]
    
    # Если выбрано "Все турниры"
    if tournament_id == "all":
        tournament_id = None
        tournament_name = "Все турниры"
    else:
        tournament_id = int(tournament_id)
        tournament = db.get_tournament_by_id(tournament_id)
        tournament_name = tournament['name'] if tournament else "Неизвестный турнир"
    
    # Получаем команды с указанным статусом для выбранного турнира
    teams = db.get_all_teams(status=status, tournament_id=tournament_id)
    
    if not teams:
        await query.edit_message_text(
            f"В турнире \"{tournament_name}\" нет {TEAM_STATUS.get(status, 'зарегистрированных')} команд.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data=f"admin_teams_{status}")
            ]])
        )
        return
    
    # Выбираем правильный emoji и текст для статуса
    status_emoji = "⏳" if status == "pending" else "✅" if status == "approved" else "❌"
    status_text = "ожидающие" if status == "pending" else "одобренные" if status == "approved" else "отклоненные"
    
    # Формируем список команд с кнопками
    keyboard = []
    
    message = f"{status_emoji} <b>{status_text.capitalize()} команды</b> - {tournament_name}\n\n"
    message += f"Найдено команд: {len(teams)}\n\n"
    message += "Выберите команду для просмотра подробной информации:\n"
    
    # Добавляем кнопки для каждой команды
    for team in teams:
        keyboard.append([
            InlineKeyboardButton(
                f"{team['team_name']}",
                callback_data=f"admin_teams_team_{team['id']}"
            )
        ])
    
    # Добавляем кнопку экспорта
    export_text = f"📝 Экспортировать {status_emoji} {status_text} команды в файл"
    
    keyboard.append([
        InlineKeyboardButton(
            export_text,
            callback_data=f"admin_export_teams_{status}_{tournament_id if tournament_id else 'all'}"
        )
    ])
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"admin_teams_{status}")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])
    
    await query.edit_message_text(
        f"{status_emoji} <b>{status_text.capitalize()} команды</b>\n\n"
        f"Выберите турнир для просмотра команд:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def show_team_info(update: Update, context: ContextTypes.DEFAULT_TYPE, team_id: int) -> None:
    """Показать информацию о конкретной команде."""
    query = update.callback_query
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Получаем информацию о команде
    teams = db.get_all_teams()
    team = next((t for t in teams if t["id"] == team_id), None)
    
    if not team:
        await query.edit_message_text(
            "❌ Команда не найдена.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_teams_list")
            ]])
        )
        return
    
    # Определяем кнопки в зависимости от статуса команды
    keyboard = []
    
    if team["status"] == "pending":
        keyboard.append([
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_team_{team_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_team_{team_id}")
        ])
    elif team["status"] == "approved":
        keyboard.append([
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_team_{team_id}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_team_{team_id}")
        ])
    elif team["status"] == "rejected":
        keyboard.append([
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_team_{team_id}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_team_{team_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("💬 Комментарий", callback_data=f"comment_team_{team_id}")])
    
    # Добавляем кнопку "Назад к списку"
    if team["status"] == "pending":
        back_data = "admin_teams_pending"
    elif team["status"] == "approved":
        back_data = "admin_teams_approved"
    elif team["status"] == "rejected":
        back_data = "admin_teams_rejected"
    else:
        back_data = "admin_teams_list"
    
    keyboard.append([InlineKeyboardButton("◀️ Назад к списку", callback_data=back_data)])
    
    # Формируем список игроков со ссылками на статистику
    players_list = ""
    captain = None
    
    for player in team["players"]:
        stat_url = f"https://pubg.op.gg/user/{player['nickname']}"
        stat_button = f"<a href='{stat_url}'>📊</a>"
        discord_info = f" [Discord: {player.get('discord_username', 'Не указан')}]" if player.get('discord_username') else ""
        
        if player.get("is_captain", False) or (isinstance(player, tuple) and len(player) > 2 and player[2]):
            if isinstance(player, dict):
                captain = f"• {player['nickname']} – @{player['telegram_username']} (Капитан) {discord_info} {stat_button}"
            else:
                captain = f"• {player[0]} – @{player[1]} (Капитан) {discord_info} {stat_button}"
        else:
            if isinstance(player, dict):
                player_info = f"• {player['nickname']} – @{player['telegram_username']} {discord_info} {stat_button}"
            else:
                player_info = f"• {player[0]} – @{player[1]} {discord_info} {stat_button}"
            players_list += f"{player_info}\n"
    
    # Добавляем капитана в начало списка
    if captain:
        players_list = f"{captain}\n\n{players_list}"
    
    # Строим сообщение с информацией о команде
    message = (
        f"🎮 <b>Команда:</b> {team['team_name']}\n"
        f"📅 <b>Дата регистрации:</b> {team['registration_date']}\n"
        f"📱 <b>Контакт капитана:</b> {team['captain_contact']}\n"
        f"📊 <b>Статус:</b> {TEAM_STATUS.get(team['status'], 'Неизвестно')}\n"
        f"💭 <b>Комментарий:</b> {team['admin_comment'] or 'Нет'}\n\n"
        f"👥 <b>Игроки:</b>\n{players_list}"
    )
    
    # Отправляем сообщение с информацией о команде
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
        disable_web_page_preview=True  # Отключаем предпросмотр ссылок
    )

async def handle_team_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка действий с командами."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    discord_bot = context.bot_data.get("discord_bot")
    discord_server_id = context.bot_data.get("discord_server_id")
    discord_role_id = context.bot_data.get("discord_role_id")
    discord_captain_role_id = context.bot_data.get("discord_captain_role_id")
    
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return

    action, entity_type, entity_id = query.data.split("_")
    entity_id = int(entity_id)
    
    if entity_type == "team":
        if action == "approve":
            # Получаем текущий статус команды
            team = db.get_team_by_id(entity_id)
            old_status = team["status"] if team else None
            
            if db.update_team_status(entity_id, "approved"):
                # После успешного обновления статуса, выдаем роли игрокам
                await process_team_roles(db, discord_bot, discord_server_id, discord_role_id, 
                                         discord_captain_role_id, entity_id, old_status, "approved")
                
                # Возвращаемся к информации о команде
                await query.answer("✅ Команда одобрена!")
                await show_team_info(update, context, entity_id)
            else:
                await query.answer("❌ Ошибка при обновлении статуса команды.")
        
        elif action == "reject":
            # Получаем текущий статус команды
            team = db.get_team_by_id(entity_id)
            old_status = team["status"] if team else None
            
            if db.update_team_status(entity_id, "rejected"):
                # После успешного обновления статуса, удаляем роли у игроков, если они были одобрены ранее
                await process_team_roles(db, discord_bot, discord_server_id, discord_role_id, 
                                         discord_captain_role_id, entity_id, old_status, "rejected")
                
                # Возвращаемся к информации о команде
                await query.answer("❌ Команда отклонена!")
                await show_team_info(update, context, entity_id)
            else:
                await query.answer("❌ Ошибка при обновлении статуса команды.")
        
        elif action == "comment":
            context.user_data["commenting_team"] = entity_id
            await query.message.reply_text(
                "💬 Введите комментарий для команды:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Отмена", callback_data="cancel_comment")
                ]])
            )
            return ADMIN_COMMENTING
            
        elif action == "delete":
            # Запрашиваем подтверждение перед удалением
            await query.edit_message_text(
                "⚠️ Вы уверены, что хотите удалить эту команду? Это действие нельзя отменить.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{entity_id}"),
                        InlineKeyboardButton("❌ Нет, отмена", callback_data=f"admin_teams_team_{entity_id}")
                    ]
                ])
            )

async def confirm_delete_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подтверждение удаления команды."""
    query = update.callback_query
    await query.answer()
    
    if "cancel_delete" in query.data:
        # Отмена удаления - возвращаемся к списку команд
        await admin_teams_list(update, context)
        return
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Получаем ID команды из callback_data
    team_id = int(query.data.split("_")[2])
    
    # Узнаем статус команды перед удалением для возврата к правильному списку
    teams = db.get_all_teams()
    team = next((t for t in teams if t["id"] == team_id), None)
    
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
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("◀️ Назад", callback_data="admin_teams_list")
                        ]])
                    )
                    return
            
            except Exception as e:
                logger.error(f"Ошибка при снятии ролей Discord: {e}")
                await query.edit_message_text(
                    "❌ Произошла ошибка при снятии ролей в Discord. Удаление команды отменено.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("◀️ Назад", callback_data="admin_teams_list")
                    ]])
                )
                return
        
        # Удаляем команду только после успешного снятия ролей
        if db.delete_team(team_id):
            # Определяем, к какому списку вернуться
            if team["status"] == "pending":
                callback_data = "admin_teams_pending"
            elif team["status"] == "approved":
                callback_data = "admin_teams_approved"
            elif team["status"] == "rejected":
                callback_data = "admin_teams_rejected"
            else:
                callback_data = "admin_teams_list"
            
            # Сообщаем об успешном удалении и предлагаем вернуться
            await query.edit_message_text(
                "✅ Команда успешно удалена.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад к списку", callback_data=callback_data)
                ]])
            )
        else:
            # В случае ошибки предлагаем вернуться к общему списку
            await query.edit_message_text(
                "❌ Ошибка при удалении команды.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="admin_teams_list")
                ]])
            )
    else:
        await query.edit_message_text(
            "❌ Команда не найдена.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_teams_list")
            ]])
        )

async def handle_admin_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка комментария администратора."""
    db = context.bot_data["db"]
    
    # Проверяем, был ли это callback для отмены
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        if query.data == "cancel_comment":
            await query.message.edit_text("Добавление комментария отменено.")
            return ConversationHandler.END
    
    # Получаем ID команды из user_data
    team_id = context.user_data.get("commenting_team")
    if not team_id:
        await update.message.reply_text("Произошла ошибка. Попробуйте снова.")
        return ConversationHandler.END
    
    comment = update.message.text
    
    # Обновляем комментарий в базе данных
    if db.update_team_status(team_id, status=None, comment=comment):
        await update.message.reply_text("💬 Комментарий успешно добавлен!")
        
        # Показываем обновленную информацию о команде
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("👁️ Посмотреть команду", callback_data=f"admin_teams_team_{team_id}")
        ]])
        await update.message.reply_text(
            "Нажмите на кнопку, чтобы увидеть обновленную информацию о команде:",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text("❌ Ошибка при добавлении комментария.")
    
    # Очищаем user_data
    if "commenting_team" in context.user_data:
        del context.user_data["commenting_team"]
    
    return ConversationHandler.END

async def admin_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для добавления нового администратора."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return ConversationHandler.END
    
    await query.message.reply_text(
        "👤 Введите Telegram ID или @username нового администратора:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Отмена", callback_data="admin_back")
        ]])
    )
    return ADMIN_ADDING

async def process_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ID или username нового администратора."""
    db = context.bot_data["db"]
    
    admin_input = update.message.text.strip()
    
    # Проверяем формат ввода (ID или @username)
    if admin_input.isdigit():
        # Это числовой ID
        admin_id = int(admin_input)
        admin_username = None
        
        try:
            # Пытаемся получить информацию о пользователе по ID
            user = await context.bot.get_chat(admin_id)
            admin_username = user.username or user.first_name
        except Exception as e:
            await update.message.reply_text(
                f"❌ Не удалось найти пользователя с ID {admin_id}. Ошибка: {str(e)}"
            )
            return ConversationHandler.END
    
    else:
        # Проверяем, является ли ввод username-ом
        username_match = re.match(USERNAME_PATTERN, admin_input)
        if username_match:
            username = username_match.group(1)
            
            try:
                # Пытаемся получить информацию о пользователе по username
                user = await context.bot.get_chat(f"@{username}")
                admin_id = user.id
                admin_username = user.username or user.first_name
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Не удалось найти пользователя с username @{username}. Ошибка: {str(e)}"
                )
                return ConversationHandler.END
        else:
            await update.message.reply_text(
                "❌ Неверный формат. Введите числовой ID или @username пользователя."
            )
            return ADMIN_ADDING
    
    # Проверяем, является ли пользователь уже администратором
    if db.is_admin(admin_id):
        await update.message.reply_text(
            f"❌ Пользователь {admin_username} (ID: {admin_id}) уже является администратором."
        )
    else:
        # Добавляем нового администратора
        if db.add_admin(admin_id, admin_username):
            await update.message.reply_text(
                f"✅ Пользователь {admin_username} (ID: {admin_id}) успешно добавлен как администратор!"
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка при добавлении администратора. Возможно, такой ID уже существует."
            )
    
    # Предлагаем вернуться в админ-панель
    admin_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔐 Вернуться в админ-панель", callback_data="admin_back")
    ]])
    await update.message.reply_text(
        "Что делать дальше?",
        reply_markup=admin_keyboard
    )
    
    return ConversationHandler.END

async def admin_admins_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать список всех администраторов."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Получаем список всех администраторов
    admins = db.get_all_admins()
    
    if not admins:
        await query.edit_message_text(
            "⚠️ В системе нет зарегистрированных администраторов.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
            ]])
        )
        return
    
    # Формируем сообщение со списком администраторов
    message = "👥 <b>Список администраторов:</b>\n\n"
    
    for idx, admin in enumerate(admins, 1):
        admin_name = admin["username"] or "Без имени"
        admin_date = admin["added_date"]
        message += f"{idx}. {admin_name} (ID: {admin['telegram_id']})\n   📅 Добавлен: {admin_date}\n\n"
    
    # Добавляем кнопку "Назад"
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
        ]]),
        parse_mode="HTML"
    )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать статистику регистраций."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Получаем статистику за последние 7 дней
    stats = db.get_stats(7)
    
    # Получаем общую статистику по командам
    all_teams = db.get_all_teams()
    pending_count = len([t for t in all_teams if t["status"] == "pending"])
    approved_count = len([t for t in all_teams if t["status"] == "approved"])
    rejected_count = len([t for t in all_teams if t["status"] == "rejected"])
    total_count = len(all_teams)
    
    # Формируем сообщение со статистикой
    message = "📊 <b>Статистика турнира</b>\n\n"
    
    # Общая статистика
    message += "📈 <b>Общая статистика:</b>\n"
    message += f"• Всего команд: {total_count}\n"
    message += f"• Ожидают рассмотрения: {pending_count}\n"
    message += f"• Одобрено: {approved_count}\n"
    message += f"• Отклонено: {rejected_count}\n\n"
    
    # Статистика по дням
    if stats:
        message += "📅 <b>Статистика за последние 7 дней:</b>\n\n"
        
        for day in stats:
            message += f"<b>{day['day']}</b>\n"
            message += f"• Новых регистраций: {day['registrations'] or 0}\n"
            message += f"• Одобрено: {day['approved'] or 0}\n"
            message += f"• Отклонено: {day['rejected'] or 0}\n\n"
    else:
        message += "За последние 7 дней нет данных о регистрациях."
    
    # Добавляем кнопку "Назад"
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
        ]]),
        parse_mode="HTML"
    )

async def admin_select_tournament_for_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор турнира для экспорта команд."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Получаем статус команд из callback_data
    command_parts = query.data.split("_")
    status = command_parts[3] if len(command_parts) > 3 else None
    
    # Получаем список турниров
    tournaments = db.get_all_tournaments()
    
    if not tournaments:
        await query.edit_message_text(
            "⚠️ В системе нет созданных турниров.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
            ]])
        )
        return
    
    # Формируем клавиатуру с турнирами
    keyboard = []
    
    for tournament in tournaments:
        teams_count = len(db.get_all_teams(status=status, tournament_id=tournament['id']))
        keyboard.append([
            InlineKeyboardButton(
                f"{tournament['name']} ({teams_count} команд)",
                callback_data=f"admin_export_teams_{status}_{tournament['id']}"
            )
        ])
    
    # Кнопка экспорта всех команд
    all_teams_count = len(db.get_all_teams(status=status))
    keyboard.append([
        InlineKeyboardButton(
            f"Все турниры ({all_teams_count} команд)",
            callback_data=f"admin_export_teams_{status}_all"
        )
    ])
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])
    
    status_text = "все"
    if status == "pending":
        status_text = "ожидающие"
    elif status == "approved":
        status_text = "одобренные"
    elif status == "rejected":
        status_text = "отклоненные"
    
    await query.edit_message_text(
        f"📥 <b>Экспорт команд в файл</b>\n\n"
        f"Выберите турнир, для которого хотите экспортировать {status_text} команды:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def admin_export_teams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Экспорт команд в текстовый файл."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Получаем параметры из callback_data
    command_parts = query.data.split("_")
    status = command_parts[3] if len(command_parts) > 3 else None
    tournament_id = command_parts[4] if len(command_parts) > 4 and command_parts[4] != "all" else None
    
    if tournament_id:
        tournament_id = int(tournament_id)
        tournament = db.get_tournament_by_id(tournament_id)
        tournament_name = tournament['name'] if tournament else "Неизвестный турнир"
    else:
        tournament_name = "Все турниры"
    
    # Получаем команды
    teams = db.get_all_teams(status=status, tournament_id=tournament_id)
    
    if not teams:
        await query.answer("⚠️ Нет команд для экспорта.")
        # Возвращаемся к списку турниров
        return await query.edit_message_text(
            f"В турнире \"{tournament_name}\" нет {TEAM_STATUS.get(status, 'зарегистрированных')} команд для экспорта.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data=f"admin_teams_{status}")
            ]])
        )
    
    # Формируем имя файла
    status_text = "Все"
    if status == "pending":
        status_text = "Ожидающие"
    elif status == "approved":
        status_text = "Одобренные"
    elif status == "rejected":
        status_text = "Отклоненные"
    
    filename = f"{status_text}_команды_{tournament_name}.txt"
    
    # Формируем содержимое файла
    file_content = ""
    
    for team in teams:
        # Добавляем название команды
        file_content += f"{team['team_name']}\n"
        
        # Сортируем игроков: сначала капитан, потом остальные
        captain = None
        other_players = []
        
        for player in team["players"]:
            if player.get("is_captain", False):
                captain = player
            else:
                other_players.append(player)
        
        # Добавляем игроков в список
        player_index = 1
        
        if captain:
            # Добавляем информацию о Discord капитана
            discord_info = f" Discord: {captain.get('discord_username', 'Не указан')}" if captain.get('discord_username') else ""
            file_content += f"{player_index}) {captain['nickname']}{discord_info}\n"
            player_index += 1
        
        for player in other_players:
            # Добавляем информацию о Discord игрока
            discord_info = f" Discord: {player.get('discord_username', 'Не указан')}" if player.get('discord_username') else ""
            file_content += f"{player_index}) {player['nickname']}{discord_info}\n"
            player_index += 1
        
        file_content += "\n"  # Пустая строка между командами
    
    # Создаем и отправляем файл
    with open(filename, "w", encoding="utf-8") as f:
        f.write(file_content)
    
    # Отправляем файл пользователю
    await query.message.reply_document(
        document=open(filename, 'rb'),
        filename=filename,
        caption=f"Экспортированы {status_text.lower()} команды для турнира {tournament_name}"
    )
    
    # Удаляем временный файл
    import os
    os.remove(filename)
    
    # Возвращаемся к списку команд турнира
    await query.edit_message_text(
        f"✅ Файл с {status_text.lower()} командами успешно экспортирован!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Вернуться к списку команд", 
                                 callback_data=f"admin_tournament_teams_status_{tournament_id if tournament_id else 'all'}_{status}")
        ]])
    )

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться в админ-меню."""
    query = update.callback_query
    await query.answer()
    
    # Получаем статистику по командам
    db = context.bot_data["db"]
    all_teams = db.get_all_teams()
    pending_count = len([t for t in all_teams if t["status"] == "pending"])
    approved_count = len([t for t in all_teams if t["status"] == "approved"])
    rejected_count = len([t for t in all_teams if t["status"] == "rejected"])
    total_count = len(all_teams)
    
    keyboard = [
        [InlineKeyboardButton(f"📋 Список команд ({total_count})", callback_data="admin_teams_list")],
        [
            InlineKeyboardButton(f"✅ Одобренные ({approved_count})", callback_data="admin_teams_approved"),
            InlineKeyboardButton(f"❌ Отклоненные ({rejected_count})", callback_data="admin_teams_rejected")
        ],
        [InlineKeyboardButton(f"⏳ Ожидающие ({pending_count})", callback_data="admin_teams_pending")],
        [InlineKeyboardButton("🏆 Управление турнирами", callback_data="admin_tournaments")],
        [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add_admin")],
        [InlineKeyboardButton("👥 Список админов", callback_data="admin_admins_list")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔐 Админ-панель\n\nВыберите действие:",
        reply_markup=reply_markup
    )
    return ADMIN_MENU

# Обработчики для управления турнирами

async def admin_tournaments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню управления турнирами."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return ADMIN_MENU
    
    # Получаем список турниров
    tournaments = db.get_all_tournaments()
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать новый турнир", callback_data="admin_create_tournament")]
    ]
    
    # Добавляем кнопки для каждого турнира
    for tournament in tournaments:
        registration_status = "🔓" if tournament["registration_open"] else "🔒"
        team_count = tournament.get("team_count", 0)
        keyboard.append([
            InlineKeyboardButton(
                f"{registration_status} {tournament['name']} ({team_count} команд)", 
                callback_data=f"admin_tournament_{tournament['id']}"
            )
        ])
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])
    
    message = "<b>🏆 Управление турнирами</b>\n\n"
    
    if tournaments:
        message += "Список доступных турниров:\n\n"
        for idx, tournament in enumerate(tournaments, 1):
            status = "🔓 Регистрация открыта" if tournament["registration_open"] else "🔒 Регистрация закрыта"
            team_count = tournament.get("team_count", 0)
            message += f"{idx}. <b>{tournament['name']}</b>\n"
            message += f"   Дата: {tournament['event_date']}\n"
            message += f"   Статус: {status}\n"
            message += f"   Команд: {team_count}\n\n"
    else:
        message += "На данный момент нет созданных турниров. Создайте первый турнир!"
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return ADMIN_TOURNAMENT_MENU

async def admin_create_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс создания нового турнира."""
    print("Вызвана функция admin_create_tournament")  # Отладочное сообщение
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return ADMIN_MENU
    
    # Отправляем сообщение с запросом названия турнира
    await query.message.reply_text(
        "🏆 <b>Создание нового турнира</b>\n\n"
        "Пожалуйста, введите название турнира:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Отмена", callback_data="admin_tournaments")
        ]])
    )
    
    print(f"Устанавливаем состояние {ADMIN_CREATE_TOURNAMENT_NAME}")  # Отладочное сообщение
    return ADMIN_CREATE_TOURNAMENT_NAME

async def admin_process_tournament_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод названия турнира."""
    print(f"Вызвана функция admin_process_tournament_name с текстом: {update.message.text}")  # Отладочное сообщение
    tournament_name = update.message.text.strip()
    
    # Проверка на допустимую длину названия
    if len(tournament_name) < 2 or len(tournament_name) > 100:
        await update.message.reply_text(
            "⚠️ Название турнира должно содержать от 2 до 100 символов. "
            "Пожалуйста, введите другое название.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Отмена", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_CREATE_TOURNAMENT_NAME
    
    # Сохраняем название в контексте
    print(f"Сохраняем название турнира: {tournament_name}")  # Отладочное сообщение
    context.user_data["new_tournament_name"] = tournament_name
    
    # Запрашиваем описание
    await update.message.reply_text(
        f"🏆 Название турнира: <b>{tournament_name}</b>\n\n"
        "Теперь введите описание турнира:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Отмена", callback_data="admin_tournaments")
        ]])
    )
    
    print(f"Переходим к состоянию {ADMIN_CREATE_TOURNAMENT_DESCRIPTION}")  # Отладочное сообщение
    return ADMIN_CREATE_TOURNAMENT_DESCRIPTION

async def admin_process_tournament_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод описания турнира."""
    tournament_description = update.message.text.strip()
    
    # Проверка на допустимую длину описания
    if len(tournament_description) < 10:
        await update.message.reply_text(
            "⚠️ Описание турнира должно содержать минимум 10 символов. "
            "Пожалуйста, введите более подробное описание.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Отмена", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_CREATE_TOURNAMENT_DESCRIPTION
    
    # Сохраняем описание в контексте
    context.user_data["new_tournament_description"] = tournament_description
    
    # Запрашиваем дату проведения
    await update.message.reply_text(
        f"🏆 <b>Название турнира:</b> {context.user_data['new_tournament_name']}\n"
        f"<b>Описание:</b> {tournament_description[:100]}...\n\n"
        "Теперь введите дату проведения турнира в формате ДД.ММ.ГГГГ:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Отмена", callback_data="admin_tournaments")
        ]])
    )
    
    return ADMIN_CREATE_TOURNAMENT_DATE

async def admin_process_tournament_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод даты проведения турнира и создать турнир."""
    tournament_date = update.message.text.strip()
    
    # Проверка формата даты
    date_pattern = r"^\d{2}\.\d{2}\.\d{4}$"
    if not re.match(date_pattern, tournament_date):
        await update.message.reply_text(
            "⚠️ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Отмена", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_CREATE_TOURNAMENT_DATE
    
    # Сохраняем дату в контексте
    context.user_data["new_tournament_date"] = tournament_date
    
    # Получаем все данные из контекста
    tournament_name = context.user_data["new_tournament_name"]
    tournament_description = context.user_data["new_tournament_description"]
    
    # Создаем турнир в базе данных
    db = context.bot_data["db"]
    try:
        tournament_id = db.create_tournament(
            name=tournament_name,
            description=tournament_description,
            event_date=tournament_date
        )
        
        # Информируем пользователя об успешном создании
        await update.message.reply_text(
            f"✅ <b>Турнир успешно создан!</b>\n\n"
            f"<b>Название:</b> {tournament_name}\n"
            f"<b>Дата проведения:</b> {tournament_date}\n"
            f"<b>Статус регистрации:</b> Открыта\n\n"
            f"Теперь команды могут регистрироваться на этот турнир.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К списку турниров", callback_data="admin_tournaments")
            ]])
        )
        
        # Очищаем данные о новом турнире из контекста
        if "new_tournament_name" in context.user_data:
            del context.user_data["new_tournament_name"]
        if "new_tournament_description" in context.user_data:
            del context.user_data["new_tournament_description"]
        if "new_tournament_date" in context.user_data:
            del context.user_data["new_tournament_date"]
            
        return ADMIN_TOURNAMENT_MENU
        
    except ValueError as e:
        # В случае ошибки (например, турнир с таким названием уже существует)
        await update.message.reply_text(
            f"❌ <b>Ошибка при создании турнира:</b> {str(e)}\n\n"
            f"Пожалуйста, попробуйте еще раз или выберите другое название.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Попробовать снова", callback_data="admin_create_tournament"),
                InlineKeyboardButton("◀️ Назад", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU

async def admin_show_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать информацию о турнире."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return ADMIN_MENU
    
    # Получаем ID турнира из callback_data
    tournament_id = int(query.data.split("_")[2])
    context.user_data["current_tournament_id"] = tournament_id
    
    # Получаем информацию о турнире
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not tournament:
        await query.edit_message_text(
            "❌ Турнир не найден.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU
    
    # Получаем список команд, зарегистрированных на этот турнир
    teams = db.get_all_teams()
    tournament_teams = [t for t in teams if t.get("tournament_id") == tournament_id]
    
    # Формируем сообщение с информацией о турнире
    message = (
        f"🏆 <b>{tournament['name']}</b>\n\n"
        f"📝 <b>Описание:</b>\n{tournament['description']}\n\n"
        f"📅 <b>Дата проведения:</b> {tournament['event_date']}\n"
        f"🔐 <b>Статус регистрации:</b> {'Открыта' if tournament['registration_open'] else 'Закрыта'}\n"
        f"📊 <b>Команд зарегистрировано:</b> {len(tournament_teams)}\n\n"
    )
    
    # Формируем кнопки действий
    keyboard = []
    
    # Кнопки редактирования
    keyboard.append([
        InlineKeyboardButton("✏️ Редактировать название", callback_data=f"admin_edit_tournament_name_{tournament_id}"),
        InlineKeyboardButton("📝 Редактировать описание", callback_data=f"admin_edit_tournament_desc_{tournament_id}")
    ])
    
    keyboard.append([
        InlineKeyboardButton("📅 Изменить дату", callback_data=f"admin_edit_tournament_date_{tournament_id}")
    ])
    
    # Кнопка открытия/закрытия регистрации
    if tournament['registration_open']:
        keyboard.append([InlineKeyboardButton("🔒 Закрыть регистрацию", callback_data=f"admin_close_tournament_{tournament_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🔓 Открыть регистрацию", callback_data=f"admin_open_tournament_{tournament_id}")])
    
    # Кнопка удаления турнира
    keyboard.append([InlineKeyboardButton("🗑️ Удалить турнир", callback_data=f"admin_delete_tournament_{tournament_id}")])
    
    # Кнопка показа команд
    keyboard.append([InlineKeyboardButton(f"👥 Команды ({len(tournament_teams)})", callback_data=f"admin_tournament_teams_{tournament_id}")])
    
    # Кнопка назад
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_tournaments")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return ADMIN_TOURNAMENT_MENU

async def admin_close_tournament_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Закрыть регистрацию на турнир."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return ADMIN_MENU
    
    # Получаем ID турнира из callback_data
    tournament_id = int(query.data.split("_")[3])
    
    # Закрываем регистрацию
    success = db.close_tournament_registration(tournament_id)
    
    if success:
        await query.answer("✅ Регистрация на турнир закрыта!")
        # Возвращаемся к просмотру турнира
        return await admin_show_tournament(update, context)
    else:
        await query.answer("❌ Ошибка при закрытии регистрации.")
        return ADMIN_TOURNAMENT_MENU

async def admin_open_tournament_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Открыть регистрацию на турнир."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return ADMIN_MENU
    
    # Получаем ID турнира из callback_data
    tournament_id = int(query.data.split("_")[3])
    
    # Открываем регистрацию
    success = db.update_tournament(tournament_id, registration_open=True)
    
    if success:
        await query.answer("✅ Регистрация на турнир открыта!")
        # Возвращаемся к просмотру турнира
        return await admin_show_tournament(update, context)
    else:
        await query.answer("❌ Ошибка при открытии регистрации.")
        return ADMIN_TOURNAMENT_MENU

async def admin_edit_tournament_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс редактирования названия турнира."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID турнира из callback_data
    tournament_id = int(query.data.split("_")[4])
    context.user_data["editing_tournament_id"] = tournament_id
    
    # Получаем информацию о турнире
    db = context.bot_data["db"]
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not tournament:
        await query.edit_message_text(
            "❌ Турнир не найден.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU
    
    # Отправляем сообщение с запросом нового названия
    await query.message.reply_text(
        f"✏️ <b>Редактирование названия турнира</b>\n\n"
        f"Текущее название: <b>{tournament['name']}</b>\n\n"
        f"Пожалуйста, введите новое название турнира:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Отмена", callback_data=f"admin_tournament_{tournament_id}")
        ]])
    )
    
    return ADMIN_EDIT_TOURNAMENT_NAME

async def admin_process_edit_tournament_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод нового названия турнира."""
    new_name = update.message.text.strip()
    
    # Проверка на допустимую длину названия
    if len(new_name) < 2 or len(new_name) > 100:
        await update.message.reply_text(
            "⚠️ Название турнира должно содержать от 2 до 100 символов. "
            "Пожалуйста, введите другое название.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Отмена", callback_data=f"admin_tournament_{context.user_data['editing_tournament_id']}")
            ]])
        )
        return ADMIN_EDIT_TOURNAMENT_NAME
    
    tournament_id = context.user_data.get("editing_tournament_id")
    db = context.bot_data["db"]
    
    try:
        # Обновляем название турнира
        success = db.update_tournament(tournament_id, name=new_name)
        
        if success:
            # Создаем кнопку для возврата к просмотру турнира
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К турниру", callback_data=f"admin_tournament_{tournament_id}")
            ]])
            
            await update.message.reply_text(
                f"✅ Название турнира успешно изменено на <b>{new_name}</b>!",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            # Очищаем ID редактируемого турнира из контекста
            if "editing_tournament_id" in context.user_data:
                del context.user_data["editing_tournament_id"]
            
            return ADMIN_TOURNAMENT_MENU
        else:
            await update.message.reply_text(
                "❌ Ошибка при обновлении названия турнира.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 К турниру", callback_data=f"admin_tournament_{tournament_id}")
                ]])
            )
            return ADMIN_TOURNAMENT_MENU
            
    except ValueError as e:
        # В случае ошибки (например, турнир с таким названием уже существует)
        await update.message.reply_text(
            f"❌ <b>Ошибка при обновлении названия турнира:</b> {str(e)}\n\n"
            f"Пожалуйста, попробуйте еще раз или выберите другое название.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К турниру", callback_data=f"admin_tournament_{tournament_id}")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU

async def admin_edit_tournament_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс редактирования описания турнира."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID турнира из callback_data
    tournament_id = int(query.data.split("_")[4])
    context.user_data["editing_tournament_id"] = tournament_id
    
    # Получаем информацию о турнире
    db = context.bot_data["db"]
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not tournament:
        await query.edit_message_text(
            "❌ Турнир не найден.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU
    
    # Отправляем сообщение с запросом нового описания
    await query.message.reply_text(
        f"📝 <b>Редактирование описания турнира</b>\n\n"
        f"Текущее описание:\n{tournament['description']}\n\n"
        f"Пожалуйста, введите новое описание турнира:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Отмена", callback_data=f"admin_tournament_{tournament_id}")
        ]])
    )
    
    return ADMIN_EDIT_TOURNAMENT_DESCRIPTION

async def admin_process_edit_tournament_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод нового описания турнира."""
    new_description = update.message.text.strip()
    
    # Проверка на допустимую длину описания
    if len(new_description) < 10:
        await update.message.reply_text(
            "⚠️ Описание турнира должно содержать минимум 10 символов. "
            "Пожалуйста, введите более подробное описание.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Отмена", callback_data=f"admin_tournament_{context.user_data['editing_tournament_id']}")
            ]])
        )
        return ADMIN_EDIT_TOURNAMENT_DESCRIPTION
    
    tournament_id = context.user_data.get("editing_tournament_id")
    db = context.bot_data["db"]
    
    try:
        # Обновляем описание турнира
        success = db.update_tournament(tournament_id, description=new_description)
        
        if success:
            # Создаем кнопку для возврата к просмотру турнира
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К турниру", callback_data=f"admin_tournament_{tournament_id}")
            ]])
            
            await update.message.reply_text(
                f"✅ Описание турнира успешно обновлено!",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            # Очищаем ID редактируемого турнира из контекста
            if "editing_tournament_id" in context.user_data:
                del context.user_data["editing_tournament_id"]
            
            return ADMIN_TOURNAMENT_MENU
        else:
            await update.message.reply_text(
                "❌ Ошибка при обновлении описания турнира.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 К турниру", callback_data=f"admin_tournament_{tournament_id}")
                ]])
            )
            return ADMIN_TOURNAMENT_MENU
            
    except Exception as e:
        # В случае ошибки
        await update.message.reply_text(
            f"❌ <b>Ошибка при обновлении описания турнира:</b> {str(e)}\n\n"
            f"Пожалуйста, попробуйте еще раз.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К турниру", callback_data=f"admin_tournament_{tournament_id}")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU

async def admin_edit_tournament_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать процесс редактирования даты проведения турнира."""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID турнира из callback_data
    tournament_id = int(query.data.split("_")[4])
    context.user_data["editing_tournament_id"] = tournament_id
    
    # Получаем информацию о турнире
    db = context.bot_data["db"]
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not tournament:
        await query.edit_message_text(
            "❌ Турнир не найден.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU
    
    # Отправляем сообщение с запросом новой даты
    await query.message.reply_text(
        f"📅 <b>Редактирование даты проведения турнира</b>\n\n"
        f"Текущая дата: <b>{tournament['event_date']}</b>\n\n"
        f"Пожалуйста, введите новую дату проведения турнира в формате ДД.ММ.ГГГГ:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Отмена", callback_data=f"admin_tournament_{tournament_id}")
        ]])
    )
    
    return ADMIN_EDIT_TOURNAMENT_DATE

async def admin_process_edit_tournament_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ввод новой даты проведения турнира."""
    new_date = update.message.text.strip()
    
    # Проверка формата даты
    date_pattern = r"^\d{2}\.\d{2}\.\d{4}$"
    if not re.match(date_pattern, new_date):
        await update.message.reply_text(
            "⚠️ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Отмена", callback_data=f"admin_tournament_{context.user_data['editing_tournament_id']}")
            ]])
        )
        return ADMIN_EDIT_TOURNAMENT_DATE
    
    tournament_id = context.user_data.get("editing_tournament_id")
    db = context.bot_data["db"]
    
    try:
        # Обновляем дату проведения турнира
        success = db.update_tournament(tournament_id, event_date=new_date)
        
        if success:
            # Создаем кнопку для возврата к просмотру турнира
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К турниру", callback_data=f"admin_tournament_{tournament_id}")
            ]])
            
            await update.message.reply_text(
                f"✅ Дата проведения турнира успешно изменена на <b>{new_date}</b>!",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            # Очищаем ID редактируемого турнира из контекста
            if "editing_tournament_id" in context.user_data:
                del context.user_data["editing_tournament_id"]
            
            return ADMIN_TOURNAMENT_MENU
        else:
            await update.message.reply_text(
                "❌ Ошибка при обновлении даты проведения турнира.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 К турниру", callback_data=f"admin_tournament_{tournament_id}")
                ]])
            )
            return ADMIN_TOURNAMENT_MENU
            
    except Exception as e:
        # В случае ошибки
        await update.message.reply_text(
            f"❌ <b>Ошибка при обновлении даты проведения турнира:</b> {str(e)}\n\n"
            f"Пожалуйста, попробуйте еще раз.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К турниру", callback_data=f"admin_tournament_{tournament_id}")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU

async def admin_delete_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос подтверждения удаления турнира."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return ADMIN_MENU
    
    # Получаем ID турнира из callback_data
    tournament_id = int(query.data.split("_")[3])
    
    # Получаем информацию о турнире
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not tournament:
        await query.edit_message_text(
            "❌ Турнир не найден.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU
    
    # Запрашиваем подтверждение
    await query.edit_message_text(
        f"⚠️ <b>Вы уверены, что хотите удалить турнир?</b>\n\n"
        f"Название: <b>{tournament['name']}</b>\n"
        f"Дата: {tournament['event_date']}\n\n"
        f"❗️ <b>Важно:</b> При удалении турнира также будут удалены все команды, зарегистрированные на него!\n\n"
        f"Это действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"admin_confirm_delete_tournament_{tournament_id}"),
                InlineKeyboardButton("❌ Нет, отмена", callback_data=f"admin_tournament_{tournament_id}")
            ]
        ])
    )
    
    return ADMIN_TOURNAMENT_MENU

async def admin_confirm_delete_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение удаления турнира."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return ADMIN_MENU
    
    # Получаем ID турнира из callback_data
    tournament_id = int(query.data.split("_")[4])
    
    # Удаляем турнир
    success = db.delete_tournament(tournament_id)
    
    if success:
        await query.edit_message_text(
            "✅ Турнир успешно удален вместе со всеми зарегистрированными на него командами.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ К списку турниров", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU
    else:
        await query.edit_message_text(
            "❌ Ошибка при удалении турнира.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ К списку турниров", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU

async def admin_tournament_teams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список команд, зарегистрированных на турнир."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    if not db.is_admin(query.from_user.id):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return ADMIN_MENU
    
    # Получаем ID турнира из callback_data
    tournament_id = int(query.data.split("_")[3])
    
    # Получаем информацию о турнире
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not tournament:
        await query.edit_message_text(
            "❌ Турнир не найден.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_tournaments")
            ]])
        )
        return ADMIN_TOURNAMENT_MENU
    
    # Получаем список команд, зарегистрированных на турнир
    teams = db.get_all_teams()
    tournament_teams = [t for t in teams if t.get("tournament_id") == tournament_id]
    
    # Формируем сообщение со списком команд
    message = f"👥 <b>Команды, зарегистрированные на турнир:</b> {tournament['name']}\n\n"
    
    if tournament_teams:
        for idx, team in enumerate(tournament_teams, 1):
            status_emoji = "⏳" if team["status"] == "pending" else "✅" if team["status"] == "approved" else "❌"
            message += f"{idx}. {status_emoji} <b>{team['team_name']}</b>\n"
            message += f"   Статус: {TEAM_STATUS.get(team['status'], 'Неизвестно')}\n"
            
            # Добавляем информацию о капитане
            captain = next((p for p in team["players"] if p.get("is_captain", False)), None)
            if captain:
                discord_info = f" Discord: {captain.get('discord_username', 'Не указан')}" if captain.get('discord_username') else ""
                message += f"   Капитан: {captain['nickname']} (@{captain['telegram_username']}){discord_info}\n"
            
            message += f"   Дата регистрации: {team['registration_date']}\n\n"
    else:
        message += "На этот турнир пока не зарегистрировано ни одной команды."
    
    # Формируем кнопки
    keyboard = []
    
    # Добавляем кнопки для каждой команды
    for team in tournament_teams:
        status_emoji = "⏳" if team["status"] == "pending" else "✅" if team["status"] == "approved" else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_emoji} {team['team_name']}",
                callback_data=f"admin_teams_team_{team['id']}"
            )
        ])
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("◀️ Назад к турниру", callback_data=f"admin_tournament_{tournament_id}")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return ADMIN_TOURNAMENT_MENU

def register_admin_handlers(application: Application) -> None:
    """Регистрация всех обработчиков для админ-панели."""
    
    # Обработчик команды /admin
    application.add_handler(CommandHandler("admin", admin_command))
    
    # Обработчики для callback-запросов
    application.add_handler(CallbackQueryHandler(admin_teams_list, pattern="^admin_teams_"))
    application.add_handler(CallbackQueryHandler(admin_tournament_status_teams, pattern="^admin_tournament_teams_status_"))
    application.add_handler(CallbackQueryHandler(admin_export_teams, pattern="^admin_export_teams_"))
    application.add_handler(CallbackQueryHandler(admin_add_admin, pattern="^admin_add_admin$"))
    application.add_handler(CallbackQueryHandler(admin_admins_list, pattern="^admin_admins_list$"))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_back, pattern="^admin_back$"))
    application.add_handler(CallbackQueryHandler(handle_team_action, pattern="^(approve|reject|comment|delete)_team_"))
    application.add_handler(CallbackQueryHandler(confirm_delete_team, pattern="^confirm_delete_"))
    
    # Новые обработчики для управления турнирами
    application.add_handler(CallbackQueryHandler(admin_tournaments, pattern="^admin_tournaments$"))
    application.add_handler(CallbackQueryHandler(admin_show_tournament, pattern="^admin_tournament_\\d+$"))
    application.add_handler(CallbackQueryHandler(admin_tournament_teams, pattern="^admin_tournament_teams_\\d+$"))
    application.add_handler(CallbackQueryHandler(admin_close_tournament_registration, pattern="^admin_close_tournament_\\d+$"))
    application.add_handler(CallbackQueryHandler(admin_open_tournament_registration, pattern="^admin_open_tournament_\\d+$"))
    application.add_handler(CallbackQueryHandler(admin_delete_tournament, pattern="^admin_delete_tournament_\\d+$"))
    application.add_handler(CallbackQueryHandler(admin_confirm_delete_tournament, pattern="^admin_confirm_delete_tournament_\\d+$"))

    # ConversationHandler для создания турнира
    create_tournament_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_create_tournament, pattern="^admin_create_tournament$")],
        states={
            ADMIN_CREATE_TOURNAMENT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_tournament_name)
            ],
            ADMIN_CREATE_TOURNAMENT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_tournament_description)
            ],
            ADMIN_CREATE_TOURNAMENT_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_tournament_date)
            ],
        },
        fallbacks=[CallbackQueryHandler(admin_tournaments, pattern="^admin_tournaments$")],
        map_to_parent={
            ADMIN_TOURNAMENT_MENU: ADMIN_TOURNAMENT_MENU
        }
    )
    application.add_handler(create_tournament_handler)

    # ConversationHandler для редактирования турнира (объединяем всё в один)
    edit_tournament_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_edit_tournament_name, pattern="^admin_edit_tournament_name_\\d+$"),
            CallbackQueryHandler(admin_edit_tournament_description, pattern="^admin_edit_tournament_desc_\\d+$"),
            CallbackQueryHandler(admin_edit_tournament_date, pattern="^admin_edit_tournament_date_\\d+$")
        ],
        states={
            ADMIN_EDIT_TOURNAMENT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_edit_tournament_name)
            ],
            ADMIN_EDIT_TOURNAMENT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_edit_tournament_description)
            ],
            ADMIN_EDIT_TOURNAMENT_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_edit_tournament_date)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(admin_show_tournament, pattern="^admin_tournament_\\d+$")
        ],
        map_to_parent={
            ADMIN_TOURNAMENT_MENU: ADMIN_TOURNAMENT_MENU
        }
    )
    application.add_handler(edit_tournament_handler)
    
    # Обработчики для комментирования команд
    comment_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_team_action, pattern="^comment_team_")],
        states={
            ADMIN_COMMENTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_comment),
                CallbackQueryHandler(handle_admin_comment, pattern="^cancel_comment$")
            ],
        },
        fallbacks=[CommandHandler("admin", admin_command)],
        per_message=True
    )
    application.add_handler(comment_handler)
    
    # Обработчики для добавления админов
    add_admin_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_admin, pattern="^admin_add_admin$")],
        states={
            ADMIN_ADDING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_add_admin),
                CallbackQueryHandler(admin_back, pattern="^admin_back$")
            ],
        },
        fallbacks=[CommandHandler("admin", admin_command)],
        per_message=True
    )
    application.add_handler(add_admin_handler)