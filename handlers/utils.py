import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def assign_discord_role_to_player(discord_bot, server_id, role_id, player_discord_id):
    """Выдает роль пользователю в Discord."""
    if not discord_bot or not discord_bot.is_ready():
        logger.warning("Discord бот не готов. Невозможно выдать роль")
        return False
    
    try:
        # Получаем сервер
        guild = discord_bot.get_guild(int(server_id))
        if not guild:
            logger.error(f"Сервер Discord с ID {server_id} не найден")
            return False
        
        # Получаем роль
        role = guild.get_role(int(role_id))
        if not role:
            logger.error(f"Роль Discord с ID {role_id} не найдена")
            return False
        
        # Получаем пользователя
        member = guild.get_member(int(player_discord_id))
        if not member:
            logger.error(f"Пользователь Discord с ID {player_discord_id} не найден на сервере")
            return False
        
        # Выдаем роль
        await member.add_roles(role, reason="Команда одобрена для участия в турнире")
        logger.info(f"Роль {role.name} выдана пользователю {member.name}")
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при выдаче роли Discord: {e}")
        return False

async def remove_discord_role_from_player(discord_bot, server_id, role_id, player_discord_id):
    """Удаляет роль у пользователя в Discord."""
    if not discord_bot or not discord_bot.is_ready():
        logger.warning("Discord бот не готов. Невозможно удалить роль")
        return False
    
    try:
        # Получаем сервер
        guild = discord_bot.get_guild(int(server_id))
        if not guild:
            logger.error(f"Сервер Discord с ID {server_id} не найден")
            return False
        
        # Получаем роль
        role = guild.get_role(int(role_id))
        if not role:
            logger.error(f"Роль Discord с ID {role_id} не найдена")
            return False
        
        # Получаем пользователя
        member = guild.get_member(int(player_discord_id))
        if not member:
            logger.error(f"Пользователь Discord с ID {player_discord_id} не найден на сервере")
            return False
        
        # Удаляем роль
        await member.remove_roles(role, reason="Статус команды изменен")
        logger.info(f"Роль {role.name} удалена у пользователя {member.name}")
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при удалении роли Discord: {e}")
        return False

async def process_team_roles(db, discord_bot, discord_server_id, discord_role_id, discord_captain_role_id, team_id, old_status, new_status):
    """Обрабатывает изменение ролей для всех игроков команды при изменении статуса."""
    # Если роль не указана, пропускаем обработку
    if not discord_role_id:
        logger.warning("ID роли Discord не указан. Пропускаем обработку ролей")
        return True
    
    # Получаем информацию о команде
    team = db.get_team_by_id(team_id)
    if not team:
        logger.error(f"Команда с ID {team_id} не найдена")
        return False
    
    # Обрабатываем выдачу ролей при одобрении команды
    if old_status != "approved" and new_status == "approved":
        logger.info(f"Выдаем роли команде {team['team_name']} (ID: {team_id})")
        for player in team["players"]:
            # Проверяем наличие Discord ID
            if player.get("discord_id"):
                try:
                    # Выдаем роль игрока
                    await assign_discord_role_to_player(
                        discord_bot, 
                        discord_server_id, 
                        discord_role_id, 
                        player["discord_id"]
                    )
                    
                    # Если игрок капитан, выдаем дополнительную роль капитана
                    if player.get("is_captain") and discord_captain_role_id:
                        await assign_discord_role_to_player(
                            discord_bot, 
                            discord_server_id, 
                            discord_captain_role_id, 
                            player["discord_id"]
                        )
                except Exception as e:
                    logger.error(f"Ошибка при выдаче роли игроку {player['nickname']}: {e}")
                    return False
        return True
    
    # Обрабатываем удаление ролей при изменении статуса с approved на draft/rejected
    elif old_status == "approved" and (new_status == "draft" or new_status == "rejected"):
        logger.info(f"Удаляем роли у команды {team['team_name']} (ID: {team_id})")
        
        # Флаг для отслеживания успешности снятия ролей
        all_roles_removed = True
        
        for player in team["players"]:
            # Проверяем наличие Discord ID
            if player.get("discord_id"):
                try:
                    # Удаляем роль игрока
                    result_player = await remove_discord_role_from_player(
                        discord_bot, 
                        discord_server_id, 
                        discord_role_id, 
                        player["discord_id"]
                    )
                    
                    # Если игрок капитан, удаляем дополнительную роль капитана
                    if player.get("is_captain") and discord_captain_role_id:
                        result_captain = await remove_discord_role_from_player(
                            discord_bot, 
                            discord_server_id, 
                            discord_captain_role_id, 
                            player["discord_id"]
                        )
                        
                        # Если не удалось снять роль капитана
                        if not result_captain:
                            logger.warning(f"Не удалось снять роль капитана у игрока {player['nickname']}")
                            all_roles_removed = False
                    
                    # Если не удалось снять роль игрока
                    if not result_player:
                        logger.warning(f"Не удалось снять роль у игрока {player['nickname']}")
                        all_roles_removed = False
                
                except Exception as e:
                    logger.error(f"Ошибка при снятии роли с игрока {player['nickname']}: {e}")
                    all_roles_removed = False
        
        return all_roles_removed

    # Если не попали ни в один сценарий
    return False