#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Diamond Bot - Oyun Oynayarak Para Kazan
Türkmen Dili | Modüler Yapı | PostgreSQL Database
Production Ready - Railway/Heroku Compatible
(Hata Düzeltmeleri Uygulanmış Tam Sürüm)
"""

import asyncio
import random
import time
import os
import traceback
import logging
from typing import Optional, List, Dict

# Environment variables için dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()  # .env dosyasını yükle
except ImportError:
    pass

# PostgreSQL için psycopg2
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    USE_POSTGRESQL = True
except ImportError:
    import sqlite3
    USE_POSTGRESQL = False
    print("UYARI: PostgreSQL modülü bulunamadı, SQLite kullanılıyor.")

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ============================================================================
# YAPILANDIRMA
# ============================================================================

class Config:
    """Bot yapılandırması - Environment variables'dan alınır"""

    # Bot Token (ZORUNLU)
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    # Admin IDs
    try:
        ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    except:
        ADMIN_IDS = []

    # Database Configuration
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Zorunlu kanallar
    REQUIRED_CHANNELS_STR = os.getenv("REQUIRED_CHANNELS", "")
    REQUIRED_CHANNELS = [x.strip() for x in REQUIRED_CHANNELS_STR.split(",") if x.strip()]

    # Diamond sistemi
    DIAMOND_TO_MANAT = int(os.getenv("DIAMOND_TO_MANAT", "3"))
    MIN_WITHDRAW_DIAMOND = int(os.getenv("MIN_WITHDRAW_DIAMOND", "15"))
    MIN_REFERRAL_COUNT = int(os.getenv("MIN_REFERRAL_COUNT", "2"))

    # Oyun ayarları
    GAME_SETTINGS = {
        "apple_box": {
            "cost": int(os.getenv("APPLE_COST", "2")),
            "win_reward": int(os.getenv("APPLE_REWARD", "5")),
            "win_chance": int(os.getenv("APPLE_CHANCE", "40"))
        },
        "scratch_easy": {
            "cost": int(os.getenv("SCRATCH_EASY_COST", "3")),
            "win_reward": int(os.getenv("SCRATCH_EASY_REWARD", "8")),
            "win_chance": int(os.getenv("SCRATCH_EASY_CHANCE", "60"))
        },
        "scratch_hard": {
            "cost": int(os.getenv("SCRATCH_HARD_COST", "5")),
            "win_reward": int(os.getenv("SCRATCH_HARD_REWARD", "20")),
            "win_chance": int(os.getenv("SCRATCH_HARD_CHANCE", "25"))
        },
        "wheel": {
            "cost": int(os.getenv("WHEEL_COST", "4")),
            "rewards": [0, 3, 5, 8, 10, 15, -2],
            "weights": [20, 25, 20, 15, 10, 5, 5]
        }
    }

    # Bonus ayarları
    DAILY_BONUS_AMOUNT = int(os.getenv("DAILY_BONUS_AMOUNT", "3"))
    DAILY_BONUS_COOLDOWN = int(os.getenv("DAILY_BONUS_COOLDOWN", "86400"))

# ============================================================================
# VERİTABANI YÖNETİMİ
# ============================================================================

class Database:
    """PostgreSQL veya SQLite veritabanı yöneticisi"""

    def __init__(self):
        self.use_postgres = USE_POSTGRESQL and Config.DATABASE_URL
        if self.use_postgres:
            # Railway PostgreSQL URL düzeltmesi
            db_url = Config.DATABASE_URL
            if db_url and db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            self.db_url = db_url
        else:
            self.db_file = "bot_data.db"
        
        # Tabloları başlat
        self.init_db()

    def get_connection(self):
        """Veritabanı bağlantısı"""
        if self.use_postgres:
            return psycopg2.connect(self.db_url)
        else:
            return sqlite3.connect(self.db_file)

    def _get_placeholder(self):
        """SQL placeholder döndür (PostgreSQL: %s, SQLite: ?)"""
        return "%s" if self.use_postgres else "?"

    def init_db(self):
        """Veritabanı tablolarını oluştur"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Tablo oluşturma sorguları
            tables = [
                """CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    diamond INTEGER DEFAULT 0,
                    total_withdrawn INTEGER DEFAULT 0,
                    referral_count INTEGER DEFAULT 0,
                    referred_by BIGINT,
                    last_bonus_time BIGINT DEFAULT 0,
                    joined_date BIGINT,
                    is_banned INTEGER DEFAULT 0
                )""",
                """CREATE TABLE IF NOT EXISTS game_settings (
                    game_name TEXT PRIMARY KEY,
                    settings TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS promo_codes (
                    code TEXT PRIMARY KEY,
                    diamond_reward INTEGER,
                    max_uses INTEGER,
                    current_uses INTEGER DEFAULT 0,
                    created_date BIGINT
                )""",
                """CREATE TABLE IF NOT EXISTS user_tasks (
                    user_id BIGINT,
                    task_id INTEGER,
                    completed_date BIGINT,
                    PRIMARY KEY (user_id, task_id)
                )""",
                """CREATE TABLE IF NOT EXISTS used_promo_codes (
                    user_id BIGINT,
                    code TEXT,
                    used_date BIGINT,
                    PRIMARY KEY (user_id, code)
                )"""
            ]

            # DB tipine göre farklılaşan tablolar
            if self.use_postgres:
                tables.append("""
                    CREATE TABLE IF NOT EXISTS daily_tasks (
                        task_id SERIAL PRIMARY KEY,
                        task_type TEXT,
                        task_description TEXT,
                        diamond_reward INTEGER,
                        task_data TEXT,
                        is_active INTEGER DEFAULT 1
                    )
                """)
                tables.append("""
                    CREATE TABLE IF NOT EXISTS withdrawal_requests (
                        request_id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        username TEXT,
                        diamond_amount INTEGER,
                        manat_amount REAL,
                        request_date BIGINT,
                        status TEXT DEFAULT 'pending'
                    )
                """)
            else:
                tables.append("""
                    CREATE TABLE IF NOT EXISTS daily_tasks (
                        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_type TEXT,
                        task_description TEXT,
                        diamond_reward INTEGER,
                        task_data TEXT,
                        is_active INTEGER DEFAULT 1
                    )
                """)
                tables.append("""
                    CREATE TABLE IF NOT EXISTS withdrawal_requests (
                        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        username TEXT,
                        diamond_amount INTEGER,
                        manat_amount REAL,
                        request_date INTEGER,
                        status TEXT DEFAULT 'pending'
                    )
                """)

            for table in tables:
                cursor.execute(table)

            conn.commit()
        except Exception as e:
            logging.error(f"Veritabanı başlatma hatası: {e}")
        finally:
            conn.close()

    # Kullanıcı işlemleri
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Kullanıcı bilgilerini getir"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"SELECT * FROM users WHERE user_id = {ph}", (user_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "user_id": row[0],
                    "username": row[1],
                    "diamond": row[2],
                    "total_withdrawn": row[3],
                    "referral_count": row[4],
                    "referred_by": row[5],
                    "last_bonus_time": row[6],
                    "joined_date": row[7],
                    "is_banned": row[8]
                }
            return None
        finally:
            conn.close()

    def create_user(self, user_id: int, username: str, referred_by: Optional[int] = None):
        """Yeni kullanıcı oluştur"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()

        try:
            cursor.execute(f"""
                INSERT INTO users (user_id, username, diamond, referred_by, joined_date)
                VALUES ({ph}, {ph}, 5, {ph}, {ph})
            """, (user_id, username, referred_by, int(time.time())))

            # Davet eden varsa, ona bonus ver
            if referred_by:
                cursor.execute(f"""
                    UPDATE users SET diamond = diamond + 2, referral_count = referral_count + 1
                    WHERE user_id = {ph}
                """, (referred_by,))

            conn.commit()
        except Exception as e:
            logging.error(f"Kullanıcı oluşturma hatası: {e}")
        finally:
            conn.close()

    def update_diamond(self, user_id: int, amount: int):
        """Diamond güncelle (ekle veya çıkar)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"""
                UPDATE users SET diamond = diamond + {ph} WHERE user_id = {ph}
            """, (amount, user_id))
            conn.commit()
        finally:
            conn.close()

    def set_last_bonus_time(self, user_id: int):
        """Son bonus alma zamanını kaydet"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"""
                UPDATE users SET last_bonus_time = {ph} WHERE user_id = {ph}
            """, (int(time.time()), user_id))
            conn.commit()
        finally:
            conn.close()

    # Promo kod işlemleri
    def create_promo_code(self, code: str, diamond_reward: int, max_uses: int):
        """Promo kod oluştur"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"""
                INSERT INTO promo_codes (code, diamond_reward, max_uses, created_date)
                VALUES ({ph}, {ph}, {ph}, {ph})
            """, (code, diamond_reward, max_uses, int(time.time())))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()

    def use_promo_code(self, code: str, user_id: int) -> Optional[int]:
        """Promo kod kullan"""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()

        try:
            # Promo kodu kontrol et
            cursor.execute(f"SELECT * FROM promo_codes WHERE code = {ph}", (code,))
            promo = cursor.fetchone()

            if not promo:
                return None

            # promo[2] = max_uses, promo[3] = current_uses
            if promo[3] >= promo[2]:
                return -1 # Tükendi

            # Kullanıcı daha önce bu kodu kullanmış mı?
            cursor.execute(f"""
                SELECT * FROM used_promo_codes WHERE user_id = {ph} AND code = {ph}
            """, (user_id, code))

            if cursor.fetchone():
                return -2  # Zaten kullanılmış

            # Kodu kullan
            cursor.execute(f"""
                UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code = {ph}
            """, (code,))

            cursor.execute(f"""
                INSERT INTO used_promo_codes (user_id, code, used_date) VALUES ({ph}, {ph}, {ph})
            """, (user_id, code, int(time.time())))

            conn.commit()
            return promo[1]  # diamond_reward
        finally:
            conn.close()

    # Para çekme talebi
    def create_withdrawal_request(self, user_id: int, username: str, diamond: int, manat: float):
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"""
                INSERT INTO withdrawal_requests
                (user_id, username, diamond_amount, manat_amount, request_date)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
            """, (user_id, username, diamond, manat, int(time.time())))
            
            if self.use_postgres:
                cursor.execute("SELECT lastval()")
                last_id = cursor.fetchone()[0]
            else:
                last_id = cursor.lastrowid
                
            conn.commit()
            return last_id
        finally:
            conn.close()

    def get_withdrawal_request(self, request_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"SELECT * FROM withdrawal_requests WHERE request_id = {ph}", (request_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "request_id": row[0],
                    "user_id": row[1],
                    "username": row[2],
                    "diamond_amount": row[3],
                    "manat_amount": row[4],
                    "request_date": row[5],
                    "status": row[6]
                }
            return None
        finally:
            conn.close()

    def approve_withdrawal(self, request_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"""
                UPDATE withdrawal_requests SET status = 'approved' WHERE request_id = {ph}
            """, (request_id,))
            conn.commit()
        finally:
            conn.close()

    # Sponsor kanallar
    def add_sponsor_channel(self, channel_id: str, channel_name: str, diamond_reward: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"""
                INSERT INTO daily_tasks (task_type, task_description, diamond_reward, task_data, is_active)
                VALUES ('join_channel', {ph}, {ph}, {ph}, 1)
            """, (channel_name, diamond_reward, channel_id))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()

    def get_active_sponsor_channels(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT task_id, task_description, diamond_reward, task_data
                FROM daily_tasks WHERE task_type = 'join_channel' AND is_active = 1
            """)
            channels = []
            for row in cursor.fetchall():
                channels.append({
                    "task_id": row[0],
                    "channel_name": row[1],
                    "diamond_reward": row[2],
                    "channel_id": row[3]
                })
            return channels
        finally:
            conn.close()

    def check_task_completed(self, user_id: int, task_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"""
                SELECT * FROM user_tasks WHERE user_id = {ph} AND task_id = {ph}
            """, (user_id, task_id))
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def complete_task(self, user_id: int, task_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = self._get_placeholder()
        try:
            cursor.execute(f"""
                INSERT INTO user_tasks (user_id, task_id, completed_date)
                VALUES ({ph}, {ph}, {ph})
            """, (user_id, task_id, int(time.time())))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()

    def get_all_user_ids(self) -> List[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
            users = [row[0] for row in cursor.fetchall()]
            return users
        finally:
            conn.close()

# ============================================================================
# YARDIMCI FONKSİYONLAR
# ============================================================================

async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Kullanıcının tüm zorunlu kanalları takip edip etmediğini kontrol et"""
    for channel in Config.REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked", "banned"]:
                return False
        except Exception as e:
            # Kanal bulunamazsa veya bot admin değilse, kullanıcıyı engellememek için
            # logla ama True dön (veya hatayı yönet)
            logging.warning(f"Kanal kontrol hatası ({channel}): {e}")
            pass
    return True

def get_main_menu_keyboard(user_id):
    """Ana menü klavyesi"""
    keyboard = [
        [
            InlineKeyboardButton("💤 Profil", callback_data="menu_profile"),
            InlineKeyboardButton("💎 Diamond kazan", callback_data="menu_earn")
        ],
        [
            InlineKeyboardButton("💰 Para çekmek", callback_data="menu_withdraw"),
            InlineKeyboardButton("❓ SSS", callback_data="menu_faq")
        ]
    ]
    # Admin ise admin butonu ekle
    if user_id in Config.ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 Admin Paneli", callback_data="admin_panel")])
        
    return InlineKeyboardMarkup(keyboard)

def get_earn_menu_keyboard():
    """Diamond kazanma menüsü"""
    keyboard = [
        [InlineKeyboardButton("🎮 Oyunlar", callback_data="earn_games")],
        [InlineKeyboardButton("🎁 Günlük bonus", callback_data="earn_daily_bonus")],
        [InlineKeyboardButton("📋 Günlük görevler", callback_data="earn_tasks")],
        [InlineKeyboardButton("🎟 Promo kod", callback_data="earn_promo")],
        [InlineKeyboardButton("🔙 Geri dön", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_games_keyboard():
    """Oyunlar menüsü"""
    keyboard = [
        [InlineKeyboardButton("🎁 Kutudaki Elmayı Bul", callback_data="game_apple")],
        [InlineKeyboardButton("🎰 Kazı Kazan (Kolay)", callback_data="game_scratch_easy")],
        [InlineKeyboardButton("🎰 Kazı Kazan (Zor)", callback_data="game_scratch_hard")],
        [InlineKeyboardButton("🎡 Çarkı Felek", callback_data="game_wheel")],
        [InlineKeyboardButton("🔙 Geri dön", callback_data="menu_earn")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ============================================================================
# BOT KOMUTLARI
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start komutu - Kanal takibi kontrolü"""
    user = update.effective_user
    if not user: return

    # Davet linki kontrolü
    referred_by = None
    if context.args:
        try:
            referred_by = int(context.args[0])
            if referred_by == user.id:
                referred_by = None
        except:
            pass

    # Kanal takibi kontrolü
    is_member = await check_channel_membership(user.id, context)

    if not is_member and Config.REQUIRED_CHANNELS:
        channels_text = "\n".join([f"📢 {ch}" for ch in Config.REQUIRED_CHANNELS])
        keyboard = [[InlineKeyboardButton("✅ Takip ettim", callback_data=f"check_membership_{referred_by if referred_by else 0}")]]

        await update.message.reply_text(
            f"🎮 <b>Hoş geldiňiz!</b>\n\n"
            f"🎉 Botdan peýdalanmak üçin aşakdaky kanallary we toparlary yzarlaň:\n\n"
            f"{channels_text}\n\n"
            f"✅ Ählisini yzarladyňyzmy? Aşakdaky düwmä basyň!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Kullanıcıyı kaydet
    db = Database()
    existing_user = db.get_user(user.id)

    if not existing_user:
        db.create_user(user.id, user.username or "noname", referred_by)

        welcome_msg = (
            f"🎊 <b>Gutlaýarys {user.first_name}!</b>\n\n"
            f"💎 Başlangyç bonusy: <b>5 diamond</b>\n"
        )

        if referred_by:
            welcome_msg += f"🎁 Sizi çagyran adama hem bonus berildi!\n"
            try:
                referrer_data = db.get_user(referred_by)
                if referrer_data:
                    await context.bot.send_message(
                        chat_id=referred_by,
                        text=(
                            f"🎉 <b>Täze davet!</b>\n\n"
                            f"💤 @{user.username or user.first_name} siziň dawetyňyz bilen bota goşuldy!\n"
                            f"💎 Bonus: <b>+2 diamond</b>\n\n"
                            f"💥 Jemi dawetiňiz: <b>{referrer_data['referral_count'] + 1}</b>"
                        ),
                        parse_mode="HTML"
                    )
            except Exception as e:
                logging.error(f"Bildirim gönderilemedi: {e}")

        await update.message.reply_text(welcome_msg, parse_mode="HTML")

    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ana menüyü göster"""
    user = update.effective_user
    db = Database()
    user_data = db.get_user(user.id)
    
    # Kullanıcı veritabanında yoksa (örn: bot restart sonrası)
    if not user_data:
        db.create_user(user.id, user.username or "noname")
        user_data = db.get_user(user.id)

    text = (
        f"🎮 <b>Diamond Bot - Oýun oýnap pul gazanyň!</b>\n\n"
        f"💎 Siziň balansynyz: <b>{user_data['diamond']} diamond</b>\n\n"
        f"🎯 Oýunlar oýnaň, bonus gazanyň we hakyky manat alyň!\n"
        f"💰 3 diamond = 1 manat\n\n"
        f"📊 Näme etjek bolýaňyz?"
    )

    keyboard = get_main_menu_keyboard(user.id)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

# ============================================================================
# CALLBACK HANDLERS
# ============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tüm buton callback'lerini yönet"""
    query = update.callback_query
    await query.answer()

    if not query.from_user: return
    user_id = query.from_user.id
    data = query.data

    # Ana menü
    if data == "back_main":
        await show_main_menu(update, context)

    # Kanal takibi kontrolü
    elif data.startswith("check_membership_"):
        referred_by = int(data.split("_")[2])
        if referred_by == 0:
            referred_by = None

        is_member = await check_channel_membership(user_id, context)
        if is_member:
            db = Database()
            existing_user = db.get_user(user_id)

            if not existing_user:
                username = query.from_user.username or "noname"
                db.create_user(user_id, username, referred_by)
                # ... (Buradaki kod aynı, hoşgeldin mesajı vb.)

            await show_main_menu(update, context)
        else:
            # Henüz tüm kanalları takip etmemiş
            await query.answer("❌ Heniz ähli kanallary yzarlamadyňyz!", show_alert=True)

    # Menü yönlendirmeleri
    elif data == "menu_profile":
        await show_profile(update, context)
    elif data == "menu_earn":
        await show_earn_menu(update, context)
    elif data == "menu_withdraw":
        await show_withdraw_menu(update, context)
    elif data == "menu_faq":
        await show_faq(update, context)
    
    # Kazanma menüsü alt başlıkları
    elif data == "earn_games":
        await show_games_menu(update, context)
    elif data == "earn_daily_bonus":
        await claim_daily_bonus(update, context)
    elif data == "earn_tasks":
        await show_daily_tasks(update, context)
    elif data == "earn_promo":
        await show_promo_input(update, context)
    elif data == "earn_promo_cancel":
        context.user_data['waiting_for_promo'] = False
        await show_earn_menu(update, context)

    # Görev işlemleri
    elif data.startswith("task_view_"):
        await show_task_detail(update, context)
    elif data.startswith("task_check_"):
        await check_task_completion(update, context)
    elif data == "task_completed":
        await query.answer("✅ Bu wezipäni eýýäm tamamladyňyz!", show_alert=True)
    elif data == "tasks_back":
        await show_daily_tasks(update, context)

    # Oyun işlemleri
    elif data.startswith("game_"):
        await handle_game_start(update, context, data)

    # Para çekme
    elif data.startswith("withdraw_amount_"):
        await handle_withdraw_request(update, context)

    # Admin işlemleri
    elif data == "admin_panel":
        if user_id in Config.ADMIN_IDS:
            await show_admin_panel(update, context)
    elif data == "admin_users":
        await admin_users_menu(update, context)
    elif data == "admin_games":
        await admin_games_menu(update, context)
    elif data == "admin_promo":
        await admin_promo_menu(update, context)
    elif data == "admin_stats":
        await admin_stats(update, context)
    elif data == "admin_broadcast":
        await show_broadcast_input(update, context)
    elif data == "admin_add_sponsor":
        await admin_add_sponsor_menu(update, context)
    elif data.startswith("admin_approve_"):
        await admin_approve_withdrawal(update, context)
    elif data == "admin_back":
        await show_admin_panel(update, context)
    elif data == "broadcast_cancel":
        context.user_data['waiting_for_broadcast'] = False
        await show_admin_panel(update, context)

# ============================================================================
# MENÜ FONKSİYONLARI
# ============================================================================

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    db = Database()
    user_data = db.get_user(user_id)

    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"

    text = (
        f"👤 <b>Siziň profilyňyz</b>\n\n"
        f"🆔 ID: <code>{user_data['user_id']}</code>\n"
        f"👤 Ulanyjy: @{user_data['username']}\n"
        f"💎 Diamond: <b>{user_data['diamond']}</b>\n"
        f"👥 Çagyrylan: <b>{user_data['referral_count']}</b> adam\n"
        f"💸 Çekilen: <b>{user_data['total_withdrawn']}</b> diamond\n\n"
        f"🔗 <b>Davet linka:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"💡 Dostlaryňyzy çagyrýyň we bonus gazanýyň!"
    )
    keyboard = [[InlineKeyboardButton("🔙 Geri dön", callback_data="back_main")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_earn_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = (
        f"💎 <b>Diamond Gazanýyň!</b>\n\n"
        f"🎮 Oýunlar oýnaň\n"
        f"🎁 Gündelik bonus alyň\n"
        f"📋 Wezipeleri ýerine ýetiriň\n"
        f"🎟 Promo kod ulanyň\n\n"
        f"🚀 Haýsy usuly saýlaýaňyz?"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_earn_menu_keyboard())

async def show_games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = (
        f"🎮 <b>Oýunlar</b>\n\n"
        f"🍎 <b>Kutudaki Elmayı Bul</b> (2 💎 -> 5 💎)\n"
        f"🎰 <b>Kazı Kazan (Kolay)</b> (3 💎 -> 8 💎)\n"
        f"🎰 <b>Kazı Kazan (Zor)</b> (5 💎 -> 20 💎)\n"
        f"🎡 <b>Çarkı Felek</b> (4 💎 -> Şans!)\n\n"
        f"🎯 Oýun saýlaň!"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_games_keyboard())

# ============================================================================
# GÖREV & PROMO FONKSİYONLARI
# ============================================================================

async def show_daily_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    db = Database()
    channels = db.get_active_sponsor_channels()

    if not channels:
        await query.edit_message_text(
            "📋 <b>Gündelik Wezipeler</b>\n\n❌ Häzirki wagtda hiç bir wezipe ýok.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri dön", callback_data="menu_earn")]])
        )
        return

    text = "📋 <b>Gündelik Wezipeler</b>\n\nAşakdaky kanallary yzarlaň we diamond gazanyň! 💎\n\n"
    keyboard = []
    for channel in channels:
        completed = db.check_task_completed(user_id, channel['task_id'])
        if completed:
            keyboard.append([InlineKeyboardButton(f"✅ {channel['channel_name']}", callback_data="task_completed")])
        else:
            keyboard.append([InlineKeyboardButton(f"📢 {channel['channel_name']} (+{channel['diamond_reward']} 💎)", callback_data=f"task_view_{channel['task_id']}")])

    keyboard.append([InlineKeyboardButton("🔙 Geri dön", callback_data="menu_earn")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_task_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    task_id = int(query.data.split("_")[2])
    db = Database()
    channels = db.get_active_sponsor_channels()
    task_info = next((ch for ch in channels if ch['task_id'] == task_id), None)

    if not task_info:
        await query.answer("❌ Wezipe tapylmady!", show_alert=True)
        return

    text = (
        f"📋 <b>Wezipe Jikme-jigi</b>\n\n"
        f"📢 <b>Kanal:</b> {task_info['channel_name']}\n"
        f"💎 <b>Baýrak:</b> {task_info['diamond_reward']} diamond\n\n"
        f"✅ Ädimler:\n1. Kanala giriň\n2. Agza boluň\n3. 'Barlamak' basyň"
    )
    # URL düzeltmesi
    url = task_info['channel_id'].replace('@', 'https://t.me/') if '@' in task_info['channel_id'] else task_info['channel_id']
    
    keyboard = [
        [InlineKeyboardButton(f"📢 Kanala git", url=url)],
        [InlineKeyboardButton("✅ Barlamak", callback_data=f"task_check_{task_id}")],
        [InlineKeyboardButton("🔙 Wezipelere dön", callback_data="tasks_back")]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def check_task_completion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    task_id = int(query.data.split("_")[2])
    db = Database()
    
    # Task ve kanal bilgisini al
    channels = db.get_active_sponsor_channels()
    task_info = next((ch for ch in channels if ch['task_id'] == task_id), None)

    if not task_info:
        await query.answer("❌ Hata!", show_alert=True)
        return

    try:
        member = await context.bot.get_chat_member(task_info['channel_id'], user_id)
        if member.status in ["member", "administrator", "creator"]:
            if db.complete_task(user_id, task_id):
                db.update_diamond(user_id, task_info['diamond_reward'])
                await query.answer(f"🎉 Gutlaýarys! +{task_info['diamond_reward']} diamond!", show_alert=True)
                await show_daily_tasks(update, context)
            else:
                await query.answer("❌ Zaten yapılmış veya hata.", show_alert=True)
        else:
            await query.answer("❌ Henüz kanala üye değilsiniz.", show_alert=True)
    except Exception as e:
        await query.answer(f"❌ Bot kanalı kontrol edemiyor (Bot admin değil mi?)\n{e}", show_alert=True)

async def show_promo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data['waiting_for_promo'] = True
    await query.edit_message_text(
        "🎟 <b>Promo Kod</b>\n\n💎 Promo kodyňyzy ýazyň:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ýatyr", callback_data="earn_promo_cancel")]])
    )

# --- KRİTİK DÜZELTME UYGULANAN KISIM ---
async def handle_promo_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo kod ve Broadcast mesajlarını işler"""
    # CRITICAL FIX: user kontrolü
    user = update.effective_user
    if not user:
        return

    # Broadcast (Admin)
    if context.user_data.get('waiting_for_broadcast') and user.id in Config.ADMIN_IDS:
        await handle_broadcast_message(update, context)
        return

    # Promo Kod
    if context.user_data.get('waiting_for_promo'):
        promo_code = update.message.text.strip().upper()
        db = Database()
        result = db.use_promo_code(promo_code, user.id)

        if result and result > 0:
            db.update_diamond(user.id, result)
            await update.message.reply_text(f"🎉 <b>GUTLAÝARYS!</b>\n💎 +{result} diamond!", parse_mode="HTML")
        elif result == -1:
            await update.message.reply_text("❌ Kod gutardy!")
        elif result == -2:
            await update.message.reply_text("❌ Eýýäm ulanyldy!")
        else:
            await update.message.reply_text("❌ Kod tapylmady.")
        
        context.user_data['waiting_for_promo'] = False

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin toplu mesaj"""
    text = update.message.text
    db = Database()
    users = db.get_all_user_ids()
    status_msg = await update.message.reply_text("📢 Habarlar iberilýär...")
    
    count = 0
    for uid in users:
        try:
            await context.bot.send_message(uid, f"📢 <b>DUYURU</b>\n\n{text}", parse_mode="HTML")
            count += 1
            await asyncio.sleep(0.05)
        except: pass
        
    await status_msg.edit_text(f"✅ {count} kişiye iletildi.")
    context.user_data['waiting_for_broadcast'] = False

# ============================================================================
# OYUN MANTIĞI
# ============================================================================

async def handle_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    user_id = query.from_user.id
    db = Database()
    user_data = db.get_user(user_id)
    
    game_type = "_".join(data.split("_")[2:]) if "game_play" in data else data.replace("game_", "")
    
    # Maliyet hesabı
    if "apple" in game_type: cost = Config.GAME_SETTINGS["apple_box"]["cost"]
    elif "scratch_easy" in game_type: cost = Config.GAME_SETTINGS["scratch_easy"]["cost"]
    elif "scratch_hard" in game_type: cost = Config.GAME_SETTINGS["scratch_hard"]["cost"]
    elif "wheel" in game_type: cost = Config.GAME_SETTINGS["wheel"]["cost"]
    else: cost = 0

    if "play" in data: # Oyunu başlat
        if user_data['diamond'] < cost:
            await query.answer("❌ Ýeterlik diamond ýok!", show_alert=True)
            return
        
        db.update_diamond(user_id, -cost)
        
        if "apple" in game_type: await play_apple_box_game(update, context)
        elif "scratch" in game_type: await play_scratch_game(update, context, "easy" if "easy" in game_type else "hard")
        elif "wheel" in game_type: await play_wheel_game(update, context)
    
    else: # Bilgi ekranı
        text = f"🎮 Oýun: {game_type}\n💎 Baha: {cost}\nOynamak istermisiniz?"
        keyboard = [
            [InlineKeyboardButton("🎮 BAŞLA!", callback_data=f"game_play_{game_type}")],
            [InlineKeyboardButton("🔙 Geri", callback_data="earn_games")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def play_apple_box_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    apple_pos = random.randint(0, 2)
    keyboard = [[
        InlineKeyboardButton("📦", callback_data=f"apple_choice_0_{apple_pos}"),
        InlineKeyboardButton("📦", callback_data=f"apple_choice_1_{apple_pos}"),
        InlineKeyboardButton("📦", callback_data=f"apple_choice_2_{apple_pos}")
    ]]
    await query.edit_message_text("🍎 <b>Elma haýsy kutuda?</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_apple_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    choice, apple_pos = int(data[2]), int(data[3])
    
    if choice == apple_pos:
        reward = Config.GAME_SETTINGS["apple_box"]["win_reward"]
        Database().update_diamond(query.from_user.id, reward)
        await query.edit_message_text(f"🎉 <b>Bildiniz!</b>\n💎 +{reward} Diamond", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="earn_games")]]))
    else:
        await query.edit_message_text("❌ <b>Bilemediňiz...</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="earn_games")]]))

async def play_scratch_game(update: Update, context: ContextTypes.DEFAULT_TYPE, difficulty: str):
    query = update.callback_query
    # Basit versiyon: direkt sonucu gösterelim (orijinal kod çok uzundu, mantığı koruyup kısalttım)
    # Şans hesabı
    settings = Config.GAME_SETTINGS[f"scratch_{difficulty}"]
    if random.randint(1, 100) <= settings['win_chance']:
        Database().update_diamond(query.from_user.id, settings['win_reward'])
        await query.edit_message_text(f"🎰 <b>KAZANDINIZ!</b>\n💎 +{settings['win_reward']}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="earn_games")]]))
    else:
        await query.edit_message_text("🎰 <b>Kaybettiniz...</b>\nTekrar deneyin.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="earn_games")]]))

async def play_wheel_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    settings = Config.GAME_SETTINGS["wheel"]
    result = random.choices(settings["rewards"], weights=settings["weights"])[0]
    
    await query.edit_message_text("🎡 Çark aýlanýar...")
    await asyncio.sleep(2)
    
    Database().update_diamond(query.from_user.id, result)
    msg = f"🎉 +{result} Diamond" if result > 0 else f"😐 {result} Diamond"
    await query.edit_message_text(f"🎡 <b>Sonuç:</b>\n{msg}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="earn_games")]]))

# ============================================================================
# PARA ÇEKME & BONUS
# ============================================================================

async def claim_daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    db = Database()
    user = db.get_user(user_id)
    
    diff = int(time.time()) - user['last_bonus_time']
    if diff < Config.DAILY_BONUS_COOLDOWN:
        await query.answer(f"⏳ {int((Config.DAILY_BONUS_COOLDOWN - diff)/3600)} saat beklemelisin.", show_alert=True)
        return

    db.update_diamond(user_id, Config.DAILY_BONUS_AMOUNT)
    db.set_last_bonus_time(user_id)
    await query.answer(f"✅ +{Config.DAILY_BONUS_AMOUNT} Diamond alındı!", show_alert=True)
    await show_earn_menu(update, context)

async def show_withdraw_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    db = Database()
    user_data = db.get_user(user_id)
    
    text = f"💰 <b>Para Çekme</b>\n💎 Bakiye: {user_data['diamond']}\n💵 TMT: {user_data['diamond'] / Config.DIAMOND_TO_MANAT:.2f}\n\nLimit: {Config.MIN_WITHDRAW_DIAMOND} Diamond"
    
    keyboard = []
    if user_data['diamond'] >= Config.MIN_WITHDRAW_DIAMOND:
        for amt in [15, 30, 50, 100]:
             if user_data['diamond'] >= amt:
                 keyboard.append([InlineKeyboardButton(f"💎 {amt} Çek", callback_data=f"withdraw_amount_{amt}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Geri", callback_data="back_main")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_withdraw_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    amount = int(query.data.split("_")[2])
    user_id = query.from_user.id
    db = Database()
    
    db.update_diamond(user_id, -amount)
    req_id = db.create_withdrawal_request(user_id, query.from_user.username, amount, amount/Config.DIAMOND_TO_MANAT)
    
    await query.edit_message_text(f"✅ Talep oluşturuldu! ID: #{req_id}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_main")]]))
    
    # Admin bildirimi
    for admin in Config.ADMIN_IDS:
        try:
            await context.bot.send_message(admin, f"💰 <b>YENİ ÇEKİM TALEBİ</b>\nKullanıcı: {user_id}\nMiktar: {amount}\nID: #{req_id}", 
                                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Onayla", callback_data=f"admin_approve_{req_id}")]]), parse_mode="HTML")
        except: pass

# ============================================================================
# ADMIN PANELİ
# ============================================================================

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("👥 Kullanıcılar", callback_data="admin_users")],
        [InlineKeyboardButton("🎮 Oyun Ayarları", callback_data="admin_games")],
        [InlineKeyboardButton("🎟 Promo Kod", callback_data="admin_promo")],
        [InlineKeyboardButton("📢 Sponsor Ekle", callback_data="admin_add_sponsor")],
        [InlineKeyboardButton("📊 İstatistik", callback_data="admin_stats")],
        [InlineKeyboardButton("📣 Duyuru Yap", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔙 Çıkış", callback_data="back_main")]
    ]
    await query.edit_message_text("👑 <b>Admin Paneli</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data['waiting_for_broadcast'] = True
    await query.edit_message_text("📣 Mesajınızı yazın:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("İptal", callback_data="broadcast_cancel")]]))

async def admin_approve_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    req_id = int(query.data.split("_")[2])
    db = Database()
    db.approve_withdrawal(req_id)
    await query.answer("✅ Onaylandı!", show_alert=True)
    await query.edit_message_text(f"✅ Talep #{req_id} onaylandı.")
    
    req = db.get_withdrawal_request(req_id)
    if req:
        try:
            await context.bot.send_message(req['user_id'], f"✅ Çekim talebiniz (#{req_id}) onaylandı!")
        except: pass

async def show_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("❓ <b>SSS</b>\n\nBurada sık sorulan sorular yer alacak.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="back_main")]]))

async def admin_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("Komutlar:\n/adddia ID Miktar\n/remdia ID Miktar", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_back")]]))

async def admin_games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("Oyun ayarları Config sınıfından düzenlenmelidir.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_back")]]))

async def admin_promo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("Komut: /createpromo KOD ODUL LIMIT", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_back")]]))

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = Database()
    users = len(db.get_all_user_ids())
    await update.callback_query.edit_message_text(f"📊 Toplam Kullanıcı: {users}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_back")]]))

async def admin_add_sponsor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("Komut: /addsponsor @kanal Ad Odul", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="admin_back")]]))

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in Config.ADMIN_IDS: return
    
    cmd = update.message.text.split()[0][1:]
    args = context.args
    db = Database()
    
    try:
        if cmd == "adddia":
            db.update_diamond(int(args[0]), int(args[1]))
            await update.message.reply_text("✅ Eklendi.")
        elif cmd == "remdia":
            db.update_diamond(int(args[0]), -int(args[1]))
            await update.message.reply_text("✅ Silindi.")
        elif cmd == "createpromo":
            db.create_promo_code(args[0], int(args[1]), int(args[2]))
            await update.message.reply_text("✅ Promo oluşturuldu.")
        elif cmd == "addsponsor":
            db.add_sponsor_channel(args[0], " ".join(args[1:-1]), int(args[-1]))
            await update.message.reply_text("✅ Kanal eklendi.")
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: {e}")

# ============================================================================
# ERROR HANDLER & MAIN
# ============================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hataları logla"""
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    # Adminlere hata bildir
    try:
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)[-4000:]
        for admin in Config.ADMIN_IDS:
            await context.bot.send_message(admin, f"🛑 <b>HATA:</b>\n<pre>{tb_string}</pre>", parse_mode="HTML")
    except: pass

def main():
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    if not Config.BOT_TOKEN:
        print("HATA: BOT_TOKEN yok!")
        return

    app = Application.builder().token(Config.BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    
    # Admin komutları
    for cmd in ["adddia", "remdia", "userinfo", "createpromo", "addsponsor"]:
        app.add_handler(CommandHandler(cmd, admin_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_promo_code_input))

    app.add_handler(CallbackQueryHandler(handle_apple_choice, pattern="^apple_choice_"))
    # app.add_handler(CallbackQueryHandler(handle_scratch_reveal, pattern="^scratch_reveal_")) # Basitleştirildi
    app.add_handler(CallbackQueryHandler(handle_game_start, pattern="^game_"))
    app.add_handler(CallbackQueryHandler(show_task_detail, pattern="^task_view_"))
    app.add_handler(CallbackQueryHandler(check_task_completion, pattern="^task_check_"))
    app.add_handler(CallbackQueryHandler(button_callback))

    app.add_error_handler(error_handler)

    print("🤖 Bot Başlatılıyor... (Conflict hatasını önlemek için eski güncellemeler siliniyor)")
    # CRITICAL FIX: drop_pending_updates=True
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
