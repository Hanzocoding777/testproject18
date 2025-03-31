import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from constants import MAX_PLAYERS

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_file: str = "tournament.db"):
        self.db_file = db_file
        self.init_db()

    def init_db(self) -> None:
        """Инициализация базы данных и создание необходимых таблиц."""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            
            # Таблица турниров
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tournaments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    event_date TEXT NOT NULL,
                    registration_open BOOLEAN DEFAULT 1,
                    created_date TIMESTAMP NOT NULL
                )
            ''')
            
            # Таблица команд (добавлено поле tournament_id)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_name TEXT NOT NULL UNIQUE,
                    captain_contact TEXT NOT NULL,
                    registration_date TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'pending',
                    admin_comment TEXT,
                    tournament_id INTEGER,
                    FOREIGN KEY (tournament_id) REFERENCES tournaments (id)
                )
            ''')
            
            # Таблица игроков (добавлены поля discord_username и discord_id)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id INTEGER,
                    nickname TEXT NOT NULL,
                    telegram_username TEXT NOT NULL,
                    telegram_id INTEGER,
                    discord_username TEXT,
                    discord_id TEXT,
                    is_captain BOOLEAN DEFAULT 0,
                    FOREIGN KEY (team_id) REFERENCES teams (id) ON DELETE CASCADE
                )
            ''')
            
            # Проверяем наличие столбца sub в таблице players
            cursor.execute("PRAGMA table_info(players)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if "sub" not in columns:
                logger.info("Добавление столбца 'sub' в таблицу players")
                cursor.execute("ALTER TABLE players ADD COLUMN sub TEXT DEFAULT NULL")
            
            # Проверяем наличие столбцов discord_username и discord_id в таблице players
            if "discord_username" not in columns:
                logger.info("Добавление столбца 'discord_username' в таблицу players")
                cursor.execute("ALTER TABLE players ADD COLUMN discord_username TEXT DEFAULT NULL")
            
            if "discord_id" not in columns:
                logger.info("Добавление столбца 'discord_id' в таблицу players")
                cursor.execute("ALTER TABLE players ADD COLUMN discord_id TEXT DEFAULT NULL")
            
            # Таблица администраторов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    added_date TIMESTAMP NOT NULL
                )
            ''')
            
            # Таблица статистики
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TIMESTAMP NOT NULL,
                    registrations_count INTEGER DEFAULT 0,
                    approved_count INTEGER DEFAULT 0,
                    rejected_count INTEGER DEFAULT 0
                )
            ''')
            
            # Добавляем дефолтного админа, если таблица пуста
            cursor.execute('SELECT COUNT(*) FROM admins')
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    'INSERT INTO admins (telegram_id, username, added_date) VALUES (?, ?, ?)',
                    (123456789, 'admin', datetime.now())  # Замените на реальный ID администратора
                )
            
            conn.commit()

    # ----- Методы для работы с турнирами -----
    
    def create_tournament(self, name: str, description: str, event_date: str) -> int:
        """
        Создать новый турнир.
        
        Args:
            name: Название турнира
            description: Описание турнира
            event_date: Дата проведения турнира
            
        Returns:
            ID созданного турнира
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO tournaments (name, description, event_date, registration_open, created_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (name, description, event_date, True, datetime.now()))
                
                tournament_id = cursor.lastrowid
                conn.commit()
                return tournament_id
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: tournaments.name" in str(e):
                raise ValueError("Турнир с таким названием уже существует")
            raise e
    
    def get_all_tournaments(self) -> List[Dict[str, Any]]:
        """
        Получить список всех турниров.
        
        Returns:
            Список словарей с данными турниров
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, name, description, event_date, registration_open, created_date
                FROM tournaments
                ORDER BY created_date DESC
            ''')
            
            tournaments = []
            for tournament in cursor.fetchall():
                tournament_dict = dict(tournament)
                
                # Добавляем количество команд для каждого турнира
                cursor.execute('''
                    SELECT COUNT(*) FROM teams WHERE tournament_id = ?
                ''', (tournament['id'],))
                
                team_count = cursor.fetchone()[0]
                tournament_dict['team_count'] = team_count
                
                tournaments.append(tournament_dict)
                
            return tournaments
    
    def get_tournament_by_id(self, tournament_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о турнире по ID.
        
        Args:
            tournament_id: ID турнира
            
        Returns:
            Словарь с данными турнира или None, если турнир не найден
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, name, description, event_date, registration_open, created_date
                FROM tournaments
                WHERE id = ?
            ''', (tournament_id,))
            
            tournament = cursor.fetchone()
            if not tournament:
                return None
                
            return dict(tournament)
    
    def update_tournament(self, tournament_id: int, name: str = None, description: str = None, 
                         event_date: str = None, registration_open: bool = None) -> bool:
        """
        Обновить информацию о турнире.
        
        Args:
            tournament_id: ID турнира
            name: Новое название турнира (опционально)
            description: Новое описание турнира (опционально)
            event_date: Новая дата проведения турнира (опционально)
            registration_open: Статус открытия регистрации (опционально)
            
        Returns:
            True, если обновление успешно, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Формируем запрос и параметры в зависимости от переданных данных
                update_parts = []
                params = []
                
                if name is not None:
                    update_parts.append("name = ?")
                    params.append(name)
                
                if description is not None:
                    update_parts.append("description = ?")
                    params.append(description)
                
                if event_date is not None:
                    update_parts.append("event_date = ?")
                    params.append(event_date)
                
                if registration_open is not None:
                    update_parts.append("registration_open = ?")
                    params.append(registration_open)
                
                # Если нет данных для обновления
                if not update_parts:
                    return False
                
                # Формируем SQL-запрос
                sql = f"UPDATE tournaments SET {', '.join(update_parts)} WHERE id = ?"
                params.append(tournament_id)
                
                cursor.execute(sql, params)
                conn.commit()
                
                return cursor.rowcount > 0
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: tournaments.name" in str(e):
                raise ValueError("Турнир с таким названием уже существует")
            raise e
    
    def close_tournament_registration(self, tournament_id: int) -> bool:
        """
        Закрыть регистрацию на турнир.
        
        Args:
            tournament_id: ID турнира
            
        Returns:
            True, если обновление успешно, иначе False
        """
        return self.update_tournament(tournament_id, registration_open=False)
    
    def get_active_tournaments(self) -> List[Dict[str, Any]]:
        """
        Получить список всех турниров с открытой регистрацией.
        
        Returns:
            Список словарей с данными турниров
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, name, description, event_date, registration_open, created_date
                FROM tournaments
                WHERE registration_open = 1
                ORDER BY created_date DESC
            ''')
            
            tournaments = [dict(t) for t in cursor.fetchall()]
            return tournaments
    
    def delete_tournament(self, tournament_id: int) -> bool:
        """
        Удалить турнир и связанные с ним команды.
        
        Args:
            tournament_id: ID турнира
            
        Returns:
            True, если удаление успешно, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Получаем список команд, зарегистрированных на турнир
                cursor.execute('SELECT id FROM teams WHERE tournament_id = ?', (tournament_id,))
                team_ids = [row[0] for row in cursor.fetchall()]
                
                # Удаляем игроков из команд
                for team_id in team_ids:
                    cursor.execute('DELETE FROM players WHERE team_id = ?', (team_id,))
                
                # Удаляем команды
                cursor.execute('DELETE FROM teams WHERE tournament_id = ?', (tournament_id,))
                
                # Удаляем турнир
                cursor.execute('DELETE FROM tournaments WHERE id = ?', (tournament_id,))
                
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при удалении турнира: {e}")
            return False

    def register_team(self, team_name: str, players: List[Dict[str, Any]], captain_contact: str, tournament_id: Optional[int] = None) -> int:
        """
        Регистрация новой команды в базе данных.
        
        Args:
            team_name: Название команды
            players: Список игроков с их данными
            captain_contact: Контактные данные капитана
            tournament_id: ID турнира (опционально)
            
        Returns:
            ID созданной команды
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Добавляем команду
                if tournament_id:
                    cursor.execute('''
                        INSERT INTO teams (team_name, captain_contact, registration_date, tournament_id)
                        VALUES (?, ?, ?, ?)
                    ''', (team_name, captain_contact, datetime.now(), tournament_id))
                else:
                    cursor.execute('''
                        INSERT INTO teams (team_name, captain_contact, registration_date)
                        VALUES (?, ?, ?)
                    ''', (team_name, captain_contact, datetime.now()))
                
                team_id = cursor.lastrowid
                
                # Добавляем игроков
                for player in players:
                    cursor.execute('''
                        INSERT INTO players (team_id, nickname, telegram_username, telegram_id, discord_username, discord_id, is_captain)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        team_id, 
                        player['nickname'], 
                        player['username'], 
                        player.get('telegram_id'), 
                        player.get('discord_username'),
                        player.get('discord_id'),
                        player.get('is_captain', False)
                    ))
                
                # Обновляем статистику
                today = datetime.now().date()
                cursor.execute(
                    'SELECT id FROM stats WHERE date(date) = date(?)', 
                    (today.isoformat(),)
                )
                
                stat_id = cursor.fetchone()
                if stat_id:
                    cursor.execute(
                        'UPDATE stats SET registrations_count = registrations_count + 1 WHERE id = ?',
                        (stat_id[0],)
                    )
                else:
                    cursor.execute(
                        'INSERT INTO stats (date, registrations_count) VALUES (?, 1)',
                        (datetime.now(),)
                    )
                
                conn.commit()
                return team_id
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: teams.team_name" in str(e):
                raise ValueError("Команда с таким названием уже существует")
            raise e
        
    def get_user_teams(self, telegram_id: int) -> List[Dict[str, Any]]:
        """
        Получить список всех команд, в которых участвует пользователь.
        
        Args:
            telegram_id: Telegram ID пользователя
            
        Returns:
            Список словарей с данными команд
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Получаем список команд, где пользователь является игроком
            cursor.execute('''
                SELECT DISTINCT t.id, t.team_name, t.status, t.registration_date, 
                    t.captain_contact, t.admin_comment, t.tournament_id
                FROM teams t
                JOIN players p ON t.id = p.team_id
                WHERE p.telegram_id = ?
                ORDER BY t.registration_date DESC
            ''', (telegram_id,))
            
            teams = []
            
            for team in cursor.fetchall():
                team_dict = dict(team)
                
                # Получаем игроков для каждой команды
                cursor.execute('''
                    SELECT id, nickname, telegram_username, telegram_id, discord_username, discord_id, is_captain
                    FROM players
                    WHERE team_id = ?
                ''', (team['id'],))
                
                players = [dict(p) for p in cursor.fetchall()]
                team_dict['players'] = players
                
                # Если у команды есть привязка к турниру, получаем информацию о турнире
                if team_dict['tournament_id']:
                    cursor.execute('''
                        SELECT name, event_date
                        FROM tournaments
                        WHERE id = ?
                    ''', (team_dict['tournament_id'],))
                    
                    tournament = cursor.fetchone()
                    if tournament:
                        team_dict['tournament_name'] = tournament['name']
                        team_dict['tournament_date'] = tournament['event_date']
                
                teams.append(team_dict)
            
            return teams

    def get_team_by_id(self, team_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить данные о команде по ее ID.
        
        Args:
            team_id: ID команды
            
        Returns:
            Словарь с данными команды или None, если команда не найдена
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Получаем информацию о команде (включая tournament_id)
            cursor.execute('''
                SELECT id, team_name, status, registration_date, admin_comment, captain_contact, tournament_id
                FROM teams
                WHERE id = ?
            ''', (team_id,))
            
            team = cursor.fetchone()
            if not team:
                return None
            
            # Получаем список игроков
            cursor.execute('''
                SELECT id, nickname, telegram_username, telegram_id, discord_username, discord_id, is_captain
                FROM players
                WHERE team_id = ?
            ''', (team_id,))
            
            players = cursor.fetchall()
            
            team_dict = dict(team)
            
            # Если у команды есть турнир, получаем информацию о нём
            if team_dict['tournament_id']:
                cursor.execute('''
                    SELECT name, event_date
                    FROM tournaments
                    WHERE id = ?
                ''', (team_dict['tournament_id'],))
                
                tournament = cursor.fetchone()
                if tournament:
                    team_dict['tournament_name'] = tournament['name']
                    team_dict['tournament_date'] = tournament['event_date']
            
            # Форматируем результат
            team_dict['players'] = [dict(p) for p in players]
            return team_dict

    def get_team_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить данные о команде по Telegram ID игрока.
        
        Args:
            telegram_id: Telegram ID игрока
            
        Returns:
            Словарь с данными команды или None, если команда не найдена
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row  # Для получения словарей вместо кортежей
            cursor = conn.cursor()
            
            # Находим team_id по telegram_id игрока
            cursor.execute('''
                SELECT team_id FROM players WHERE telegram_id = ?
            ''', (telegram_id,))
            
            player = cursor.fetchone()
            if not player:
                return None
            
            team_id = player['team_id']
            
            # Получаем информацию о команде
            cursor.execute('''
                SELECT id, team_name, status, registration_date, admin_comment, captain_contact, tournament_id
                FROM teams
                WHERE id = ?
            ''', (team_id,))
            
            team = cursor.fetchone()
            if not team:
                return None
            
            # Получаем список игроков
            cursor.execute('''
                SELECT id, nickname, telegram_username, telegram_id, discord_username, discord_id, is_captain
                FROM players
                WHERE team_id = ?
            ''', (team_id,))
            
            players = cursor.fetchall()
            
            team_dict = dict(team)
            
            # Если у команды есть турнир, получаем информацию о нём
            if team_dict['tournament_id']:
                cursor.execute('''
                    SELECT name, event_date
                    FROM tournaments
                    WHERE id = ?
                ''', (team_dict['tournament_id'],))
                
                tournament = cursor.fetchone()
                if tournament:
                    team_dict['tournament_name'] = tournament['name']
                    team_dict['tournament_date'] = tournament['event_date']
            
            # Форматируем результат
            team_dict['players'] = [dict(p) for p in players]
            return team_dict

    def get_team_by_name(self, team_name: str) -> Optional[Dict[str, Any]]:
        """
        Получить данные о команде по ее названию.
        
        Args:
            team_name: Название команды
            
        Returns:
            Словарь с данными команды или None, если команда не найдена
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Ищем команду по названию (без учета регистра)
            cursor.execute('''
                SELECT id, team_name, status, registration_date, admin_comment, captain_contact, tournament_id
                FROM teams
                WHERE LOWER(team_name) = LOWER(?)
            ''', (team_name,))
            
            team = cursor.fetchone()
            if not team:
                return None
            
            # Получаем список игроков
            cursor.execute('''
                SELECT id, nickname, telegram_username, telegram_id, discord_username, discord_id, is_captain
                FROM players
                WHERE team_id = ?
            ''', (team['id'],))
            
            players = cursor.fetchall()
            
            team_dict = dict(team)
            
            # Если у команды есть турнир, получаем информацию о нём
            if team_dict['tournament_id']:
                cursor.execute('''
                    SELECT name, event_date
                    FROM tournaments
                    WHERE id = ?
                ''', (team_dict['tournament_id'],))
                
                tournament = cursor.fetchone()
                if tournament:
                    team_dict['tournament_name'] = tournament['name']
                    team_dict['tournament_date'] = tournament['event_date']
            
            # Форматируем результат
            team_dict['players'] = [dict(p) for p in players]
            return team_dict

    def register_team_for_tournament(self, team_id: int, tournament_id: int) -> bool:
        """
        Зарегистрировать команду на турнир.
        
        Args:
            team_id: ID команды
            tournament_id: ID турнира
            
        Returns:
            True в случае успеха, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Проверяем, существует ли команда
                cursor.execute('SELECT status FROM teams WHERE id = ?', (team_id,))
                team = cursor.fetchone()
                
                if not team:
                    raise ValueError("Команда не найдена")
                
                if team[0] != 'draft':
                    raise ValueError("Команда уже зарегистрирована или имеет неподходящий статус")
                
                # Проверяем, существует ли турнир и открыта ли регистрация
                cursor.execute('SELECT registration_open FROM tournaments WHERE id = ?', (tournament_id,))
                tournament = cursor.fetchone()
                
                if not tournament:
                    raise ValueError("Турнир не найден")
                
                if not tournament[0]:
                    raise ValueError("Регистрация на турнир закрыта")
                
                # Проверяем количество игроков
                cursor.execute('SELECT COUNT(*) FROM players WHERE team_id = ?', (team_id,))
                player_count = cursor.fetchone()[0]
                
                if player_count < 4:  # Минимум 4 игрока (3 + капитан)
                    raise ValueError(f"Для регистрации необходимо минимум 4 игрока (включая капитана)")
                
                # Обновляем статус команды и привязываем к турниру
                cursor.execute('''
                    UPDATE teams 
                    SET status = ?, tournament_id = ? 
                    WHERE id = ?
                ''', ('pending', tournament_id, team_id))
                
                # Обновляем статистику
                today = datetime.now().date()
                cursor.execute(
                    'SELECT id FROM stats WHERE date(date) = date(?)', 
                    (today.isoformat(),)
                )
                
                stat_id = cursor.fetchone()
                if stat_id:
                    cursor.execute(
                        'UPDATE stats SET registrations_count = registrations_count + 1 WHERE id = ?',
                        (stat_id[0],)
                    )
                else:
                    cursor.execute(
                        'INSERT INTO stats (date, registrations_count) VALUES (?, 1)',
                        (datetime.now(),)
                    )
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при регистрации команды на турнир: {e}")
            raise ValueError(str(e))

    def create_team(self, team_name: str, captain: Dict[str, Any]) -> int:
        """
        Создать новую команду с капитаном.
        
        Args:
            team_name: Название команды
            captain: Словарь с данными капитана
            
        Returns:
            ID созданной команды
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Проверяем уникальность названия команды
                cursor.execute('SELECT 1 FROM teams WHERE LOWER(team_name) = LOWER(?)', (team_name,))
                if cursor.fetchone():
                    raise ValueError("Команда с таким названием уже существует")
                
                # Добавляем команду со статусом "draft"
                cursor.execute('''
                    INSERT INTO teams (team_name, captain_contact, registration_date, status)
                    VALUES (?, ?, ?, ?)
                ''', (team_name, f"@{captain['username']}", datetime.now(), "draft"))
                
                team_id = cursor.lastrowid
                
                # Добавляем капитана в список игроков
                cursor.execute('''
                    INSERT INTO players (team_id, nickname, telegram_username, telegram_id, discord_username, discord_id, is_captain)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    team_id, 
                    captain['nickname'], 
                    captain['username'], 
                    captain['telegram_id'], 
                    captain.get('discord_username'),
                    captain.get('discord_id'),
                    True
                ))
                
                conn.commit()
                return team_id
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Ошибка при создании команды: {str(e)}")

    def add_player_to_team(self, team_id: int, player: Dict[str, Any]) -> bool:
        """
        Добавить игрока в команду.
        
        Args:
            team_id: ID команды
            player: Словарь с данными игрока
            
        Returns:
            True в случае успеха, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Проверяем, существует ли команда
                cursor.execute('SELECT status FROM teams WHERE id = ?', (team_id,))
                team = cursor.fetchone()
                
                if not team:
                    raise ValueError("Команда не найдена")
                
                team_status = team[0]
                
                # Проверяем количество игроков
                cursor.execute('SELECT COUNT(*) FROM players WHERE team_id = ?', (team_id,))
                player_count = cursor.fetchone()[0]
                
                if player_count > MAX_PLAYERS:
                    raise ValueError(f"Превышено максимальное количество игроков ({MAX_PLAYERS + 1}, включая капитана)")
                
                # Проверяем, не зарегистрирован ли игрок с таким же ником или username
                cursor.execute('''
                    SELECT 1 FROM players 
                    WHERE team_id = ? AND (LOWER(nickname) = LOWER(?) OR LOWER(telegram_username) = LOWER(?))
                ''', (team_id, player['nickname'], player['username']))
                
                if cursor.fetchone():
                    raise ValueError("Игрок с таким никнеймом или Telegram username уже есть в команде")
                
                # Проверяем, не зарегистрирован ли игрок с таким Telegram ID в другой команде
                if player.get('telegram_id'):
                    cursor.execute('''
                        SELECT t.team_name FROM players p
                        JOIN teams t ON p.team_id = t.id
                        WHERE p.telegram_id = ? AND p.team_id != ?
                    ''', (player['telegram_id'], team_id))
                    
                    other_team = cursor.fetchone()
                    if other_team:
                        raise ValueError(f"Этот игрок уже зарегистрирован в команде '{other_team[0]}'")
                
                # Добавляем игрока
                cursor.execute('''
                    INSERT INTO players (team_id, nickname, telegram_username, telegram_id, discord_username, discord_id, is_captain)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    team_id, 
                    player['nickname'], 
                    player['username'], 
                    player.get('telegram_id'), 
                    player.get('discord_username'),
                    player.get('discord_id'),
                    player.get('is_captain', False)
                ))
                
                # Изменяем статус команды на "draft", если она была "approved" или "rejected"
                if team_status in ["pending", "approved", "rejected"]:
                    cursor.execute('UPDATE teams SET status = ? WHERE id = ?', ("draft", team_id))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении игрока: {e}")
            raise ValueError(str(e))
        
    def check_username_exists_in_team(self, team_id: int, username: str) -> bool:
        """
        Проверить, существует ли игрок с таким username в указанной команде.
        
        Args:
            team_id: ID команды
            username: Telegram username игрока (без @)
            
        Returns:
            True, если игрок с таким username уже есть в команде, иначе False
        """
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 1 FROM players 
                WHERE team_id = ? AND LOWER(telegram_username) = LOWER(?)
            ''', (team_id, username))
            return cursor.fetchone() is not None
        
    def check_discord_exists_in_team(self, team_id: int, discord_username: str, exclude_player_id: Optional[int] = None) -> bool:
        """
        Проверить, существует ли игрок с таким Discord username в указанной команде.
        
        Args:
            team_id: ID команды
            discord_username: Discord username игрока
            exclude_player_id: ID игрока, которого нужно исключить из проверки (для редактирования)
            
        Returns:
            True, если игрок с таким Discord username уже есть в команде, иначе False
        """
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            
            if exclude_player_id:
                cursor.execute('''
                    SELECT 1 FROM players 
                    WHERE team_id = ? AND LOWER(discord_username) = LOWER(?) AND id != ?
                ''', (team_id, discord_username, exclude_player_id))
            else:
                cursor.execute('''
                    SELECT 1 FROM players 
                    WHERE team_id = ? AND LOWER(discord_username) = LOWER(?)
                ''', (team_id, discord_username))
                
            return cursor.fetchone() is not None
        
    def check_nickname_exists_in_team(self, team_id: int, nickname: str) -> bool:
        """
        Проверить, существует ли игрок с таким никнеймом в указанной команде.
        
        Args:
            team_id: ID команды
            nickname: Игровой никнейм
            
        Returns:
            True, если игрок с таким никнеймом уже есть в команде, иначе False
        """
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 1 FROM players 
                WHERE team_id = ? AND LOWER(nickname) = LOWER(?)
            ''', (team_id, nickname))
            return cursor.fetchone() is not None
        
    def update_team_name(self, team_id: int, new_name: str) -> bool:
        """
        Обновить название команды.
        
        Args:
            team_id: ID команды
            new_name: Новое название команды
            
        Returns:
            True в случае успеха, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Проверяем, существует ли команда
                cursor.execute('SELECT status FROM teams WHERE id = ?', (team_id,))
                team = cursor.fetchone()
                
                if not team:
                    raise ValueError("Команда не найдена")
                
                team_status = team[0]
                
                # Проверяем уникальность нового названия
                cursor.execute('SELECT 1 FROM teams WHERE LOWER(team_name) = LOWER(?) AND id != ?', (new_name, team_id))
                if cursor.fetchone():
                    raise ValueError("Команда с таким названием уже существует")
                
                # Обновляем название команды
                cursor.execute('UPDATE teams SET team_name = ? WHERE id = ?', (new_name, team_id))
                
                # Изменяем статус команды на "draft", если она была "pending", "approved" или "rejected"
                if team_status in ["pending", "approved", "rejected"]:
                    cursor.execute('UPDATE teams SET status = ? WHERE id = ?', ("draft", team_id))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении названия команды: {e}")
            raise ValueError(str(e))

    def update_player_nickname(self, player_id: int, new_nickname: str) -> bool:
        """
        Обновить никнейм игрока.
        
        Args:
            player_id: ID игрока
            new_nickname: Новый никнейм
            
        Returns:
            True в случае успеха, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Получаем информацию о команде игрока
                cursor.execute('''
                    SELECT t.id, t.status, p.team_id 
                    FROM players p
                    JOIN teams t ON p.team_id = t.id
                    WHERE p.id = ?
                ''', (player_id,))
                
                player_info = cursor.fetchone()
                if not player_info:
                    raise ValueError("Игрок не найден")
                
                team_id = player_info[2]
                team_status = player_info[1]
                
                # Проверяем, не занят ли никнейм другим игроком в этой команде
                cursor.execute('''
                    SELECT 1 FROM players
                    WHERE team_id = ? AND LOWER(nickname) = LOWER(?) AND id != ?
                ''', (team_id, new_nickname, player_id))
                
                if cursor.fetchone():
                    raise ValueError("Игрок с таким никнеймом уже есть в команде")
                
                # Обновляем никнейм игрока
                cursor.execute('UPDATE players SET nickname = ? WHERE id = ?', (new_nickname, player_id))
                
                # Изменяем статус команды на "draft", если она была "approved" или "rejected"
                if team_status in ["pending", "approved", "rejected"]:
                    cursor.execute('UPDATE teams SET status = ? WHERE id = ?', ("draft", team_id))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении никнейма игрока: {e}")
            raise ValueError(str(e))

    def update_player_username(self, player_id: int, new_username: str) -> bool:
        """
        Обновить Telegram username игрока.
        
        Args:
            player_id: ID игрока
            new_username: Новый Telegram username (без @)
            
        Returns:
            True в случае успеха, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Получаем информацию о команде игрока
                cursor.execute('''
                    SELECT t.id, t.status, p.team_id 
                    FROM players p
                    JOIN teams t ON p.team_id = t.id
                    WHERE p.id = ?
                ''', (player_id,))
                
                player_info = cursor.fetchone()
                if not player_info:
                    raise ValueError("Игрок не найден")
                
                team_id = player_info[2]
                team_status = player_info[1]
                
                # Проверяем, не занят ли username другим игроком в этой команде
                cursor.execute('''
                    SELECT 1 FROM players
                    WHERE team_id = ? AND LOWER(telegram_username) = LOWER(?) AND id != ?
                ''', (team_id, new_username, player_id))
                
                if cursor.fetchone():
                    raise ValueError("Игрок с таким Telegram username уже есть в команде")
                
                # Обновляем username игрока
                cursor.execute('UPDATE players SET telegram_username = ? WHERE id = ?', (new_username, player_id))
                
                # Изменяем статус команды на "draft", если она была "approved" или "rejected"
                if team_status in ["pending", "approved", "rejected"]:
                    cursor.execute('UPDATE teams SET status = ? WHERE id = ?', ("draft", team_id))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении Telegram username игрока: {e}")
            raise ValueError(str(e))

    def update_player_discord(self, player_id: int, discord_username: str, discord_id: str) -> bool:
        """
        Обновить Discord данные игрока.
        
        Args:
            player_id: ID игрока
            discord_username: Discord username игрока
            discord_id: Discord ID игрока
            
        Returns:
            True в случае успеха, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Получаем информацию о команде игрока
                cursor.execute('''
                    SELECT t.id, t.status, p.team_id 
                    FROM players p
                    JOIN teams t ON p.team_id = t.id
                    WHERE p.id = ?
                ''', (player_id,))
                
                player_info = cursor.fetchone()
                if not player_info:
                    raise ValueError("Игрок не найден")
                
                team_id = player_info[2]
                team_status = player_info[1]
                
                # Обновляем Discord данные игрока
                cursor.execute('''
                    UPDATE players 
                    SET discord_username = ?, discord_id = ? 
                    WHERE id = ?
                ''', (discord_username, discord_id, player_id))
                
                # Изменяем статус команды на "draft", если она была "approved" или "rejected"
                if team_status in ["pending", "approved", "rejected"]:
                    cursor.execute('UPDATE teams SET status = ? WHERE id = ?', ("draft", team_id))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении Discord данных игрока: {e}")
            raise ValueError(str(e))
        
    def update_player_subscription(self, player_id: int, is_subscribed: bool) -> bool:
        """
        Обновить статус подписки игрока на канал.
        
        Args:
            player_id: ID игрока
            is_subscribed: True, если подписан, False если нет
            
        Returns:
            True в случае успеха, иначе False
        """
        try:
            sub_status = "+" if is_subscribed else "-"
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE players SET sub = ? WHERE id = ?', (sub_status, player_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса подписки игрока: {e}")
            return False

    def delete_player(self, player_id: int) -> bool:
        """
        Удалить игрока из команды.
        
        Args:
            player_id: ID игрока
            
        Returns:
            True в случае успеха, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Получаем информацию о команде игрока
                cursor.execute('''
                    SELECT t.id, t.status, p.team_id, p.is_captain
                    FROM players p
                    JOIN teams t ON p.team_id = t.id
                    WHERE p.id = ?
                ''', (player_id,))
                
                player_info = cursor.fetchone()
                if not player_info:
                    raise ValueError("Игрок не найден")
                
                team_id = player_info[2]
                team_status = player_info[1]
                is_captain = player_info[3]
                
                # Проверяем только, является ли игрок капитаном
                if is_captain:
                    raise ValueError("Нельзя удалить капитана команды")
                
                # Удаляем игрока
                cursor.execute('DELETE FROM players WHERE id = ?', (player_id,))
                
                # Изменяем статус команды на "draft", если она была "approved" или "rejected"
                if team_status in ["pending", "approved", "rejected"]:
                    cursor.execute('UPDATE teams SET status = ? WHERE id = ?', ("draft", team_id))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка при удалении игрока: {e}")
            raise ValueError(str(e))

    def team_name_exists(self, team_name: str) -> bool:
        """
        Проверить, существует ли команда с указанным названием.
        
        Args:
            team_name: Название команды
            
        Returns:
            True, если команда существует, иначе False
        """
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 1 FROM teams WHERE LOWER(team_name) = LOWER(?)
            ''', (team_name,))
            return cursor.fetchone() is not None

    def update_team_status(self, team_id: int, status: str, comment: Optional[str] = None) -> bool:
        """
        Обновить статус команды и/или добавить комментарий.
        
        Args:
            team_id: ID команды
            status: Новый статус ('pending', 'approved', 'rejected')
            comment: Комментарий администратора (опционально)
            
        Returns:
            True, если обновление успешно, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Получаем текущий статус, чтобы обновить статистику
                cursor.execute('SELECT status FROM teams WHERE id = ?', (team_id,))
                current_status = cursor.fetchone()
                
                if current_status:
                    # Обновляем статус и комментарий
                    if comment is not None:
                        cursor.execute('''
                            UPDATE teams 
                            SET status = ?, admin_comment = ?
                            WHERE id = ?
                        ''', (status, comment, team_id))
                    else:
                        cursor.execute('''
                            UPDATE teams 
                            SET status = ?
                            WHERE id = ?
                        ''', (status, team_id))
                    
                    # Обновляем статистику только если статус изменился
                    if current_status[0] != status:
                        today = datetime.now().date()
                        cursor.execute(
                            'SELECT id FROM stats WHERE date(date) = date(?)', 
                            (today.isoformat(),)
                        )
                        
                        stat_id = cursor.fetchone()
                        if stat_id:
                            if status == 'approved':
                                cursor.execute(
                                    'UPDATE stats SET approved_count = approved_count + 1 WHERE id = ?',
                                    (stat_id[0],)
                                )
                            elif status == 'rejected':
                                cursor.execute(
                                    'UPDATE stats SET rejected_count = rejected_count + 1 WHERE id = ?',
                                    (stat_id[0],)
                                )
                        else:
                            # Создаем новую запись в статистике
                            approved_count = 1 if status == 'approved' else 0
                            rejected_count = 1 if status == 'rejected' else 0
                            
                            cursor.execute('''
                                INSERT INTO stats (date, approved_count, rejected_count)
                                VALUES (?, ?, ?)
                            ''', (datetime.now(), approved_count, rejected_count))
                    
                    conn.commit()
                    return True
                
                return False
        except Exception as e:
            print(f"Ошибка при обновлении статуса команды: {e}")
            return False

    def get_all_teams(self, status: Optional[str] = None, tournament_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Получить список всех команд с опциональной фильтрацией по статусу и турниру.
        
        Args:
            status: Фильтр по статусу (опционально)
            tournament_id: Фильтр по ID турнира (опционально)
            
        Returns:
            Список словарей с данными команд
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = '''
                SELECT t.id, t.team_name, t.status, t.registration_date, 
                    t.captain_contact, t.admin_comment, t.tournament_id
                FROM teams t
                WHERE 1=1
            '''
            
            params = []
            if status:
                query += ' AND t.status = ?'
                params.append(status)
            
            if tournament_id:
                query += ' AND t.tournament_id = ?'
                params.append(tournament_id)
            
            query += ' ORDER BY t.registration_date DESC'
            
            cursor.execute(query, params)
            teams = []
            
            for team in cursor.fetchall():
                team_dict = dict(team)
                
                # Получаем игроков для каждой команды
                cursor.execute('''
                    SELECT id, nickname, telegram_username, telegram_id, discord_username, discord_id, is_captain
                    FROM players
                    WHERE team_id = ?
                ''', (team['id'],))
                
                players = [dict(p) for p in cursor.fetchall()]
                team_dict['players'] = players
                
                # Если у команды есть турнир, получаем информацию о нём
                if team_dict['tournament_id']:
                    cursor.execute('''
                        SELECT name, event_date
                        FROM tournaments
                        WHERE id = ?
                    ''', (team_dict['tournament_id'],))
                    
                    tournament = cursor.fetchone()
                    if tournament:
                        team_dict['tournament_name'] = tournament['name']
                        team_dict['tournament_date'] = tournament['event_date']
                
                teams.append(team_dict)
            
            return teams

    def is_admin(self, telegram_id: int) -> bool:
        """
        Проверить, является ли пользователь администратором.
        
        Args:
            telegram_id: Telegram ID пользователя
            
        Returns:
            True, если пользователь администратор, иначе False
        """
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM admins WHERE telegram_id = ?', (telegram_id,))
            return cursor.fetchone() is not None

    def add_admin(self, telegram_id: int, username: str) -> bool:
        """
        Добавить нового администратора.
        
        Args:
            telegram_id: Telegram ID нового администратора
            username: Имя пользователя
            
        Returns:
            True, если добавление успешно, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO admins (telegram_id, username, added_date)
                    VALUES (?, ?, ?)
                ''', (telegram_id, username, datetime.now()))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def remove_admin(self, telegram_id: int) -> bool:
        """
        Удалить администратора.
        
        Args:
            telegram_id: Telegram ID администратора для удаления
            
        Returns:
            True, если удаление успешно, иначе False
        """
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM admins WHERE telegram_id = ?', (telegram_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_all_admins(self) -> List[Dict[str, Any]]:
        """
        Получить список всех администраторов.
        
        Returns:
            Список словарей с данными администраторов
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT telegram_id, username, added_date FROM admins')
            return [dict(admin) for admin in cursor.fetchall()]

    def get_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Получить статистику регистраций за указанное количество дней.
        
        Args:
            days: Количество дней для выборки
            
        Returns:
            Список словарей со статистикой по дням
        """
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT date(date) as day, 
                       SUM(registrations_count) as registrations,
                       SUM(approved_count) as approved,
                       SUM(rejected_count) as rejected
                FROM stats
                WHERE date(date) >= date('now', ?)
                GROUP BY day
                ORDER BY day DESC
            ''', (f'-{days} days',))
            
            return [dict(day) for day in cursor.fetchall()]

    def delete_team(self, team_id: int) -> bool:
        """
        Удалить команду из базы данных.
        
        Args:
            team_id: ID команды для удаления
            
        Returns:
            True, если удаление успешно, иначе False
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # Сначала удаляем игроков
                cursor.execute('DELETE FROM players WHERE team_id = ?', (team_id,))
                
                # Затем удаляем команду
                cursor.execute('DELETE FROM teams WHERE id = ?', (team_id,))
                
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Ошибка при удалении команды: {e}")
            return False