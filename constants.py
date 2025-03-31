# Константы для состояний разговора
(
    # Главные состояния
    START, 
    REGISTRATION, 
    TOURNAMENT_INFO, 
    FAQ,
    
    # Состояния регистрации
    CHECKING_SUBSCRIPTION,
    TEAM_NAME,
    CAPTAIN_NICKNAME,
    PLAYERS_LIST,
    SUBSCRIPTION_CHECK_RESULT,
    CAPTAIN_CONTACTS,
    CONFIRMATION,
    
    # Админские состояния
    ADMIN_MENU,
    ADMIN_ADDING,
    ADMIN_COMMENTING,
    ADMIN_TEAM_FILTER,
    
    # Новые админские состояния для управления турнирами
    ADMIN_TOURNAMENT_MENU,
    ADMIN_CREATE_TOURNAMENT_NAME,
    ADMIN_CREATE_TOURNAMENT_DESCRIPTION,
    ADMIN_CREATE_TOURNAMENT_DATE,
    ADMIN_EDIT_TOURNAMENT,
    ADMIN_EDIT_TOURNAMENT_NAME,
    ADMIN_EDIT_TOURNAMENT_DESCRIPTION,
    ADMIN_EDIT_TOURNAMENT_DATE,
    
    # Состояния просмотра статуса
    STATUS_INPUT,
    STATUS_TEAM_ACTION,
    STATUS_CONFIRM_CANCEL,
    STATUS_SEARCH_TEAM,
    
    # Состояния личного кабинета
    PROFILE_MENU,
    TEAM_CREATE_NAME,
    TEAM_CREATE_CAPTAIN,
    TEAM_VIEW,
    TEAM_ADD_PLAYER_USERNAME,
    TEAM_ADD_PLAYER_NICKNAME,
    
    # Состояния редактирования команды и игроков
    TEAM_EDIT_NAME,
    TEAM_EDIT_PLAYER_MENU,
    TEAM_EDIT_PLAYER_NICKNAME,
    TEAM_EDIT_PLAYER_USERNAME,
    TEAM_CONFIRM_DELETE_PLAYER,
    
    # Новые состояния для Discord
    TEAM_CREATE_CAPTAIN_DISCORD,
    TEAM_ADD_PLAYER_DISCORD,
    TEAM_EDIT_PLAYER_DISCORD,
    
) = range(41)  # Обновлено общее количество состояний

# ID канала для проверки подписки
CHANNEL_ID = "@pubgruprime"

# Ссылка на Discord сервер
DISCORD_INVITE_LINK = "https://discord.gg/rupubg"

# Минимальное и максимальное количество игроков
MIN_PLAYERS = 3  # Не включая капитана
MAX_PLAYERS = 5  # Не включая капитана

# Статусы команд
TEAM_STATUS = {
    "draft": "📝 Черновик (не зарегистрирована)",
    "pending": "⏳ Ожидает подтверждения",
    "approved": "✅ Одобрено",
    "rejected": "❌ Отклонено"
}

# Шаблоны для регулярных выражений
PLAYER_PATTERN = r"(.+?)\s*[-–]\s*@([a-zA-Z0-9_]+)"
USERNAME_PATTERN = r"^@([a-zA-Z0-9_]+)$"