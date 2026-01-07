#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Diamond Bot - Oyun Oynayarak Para Kazan
Türkmen Dili | PostgreSQL | Modüler Yapı
"""

import asyncio
import random
import time
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

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
    """Bot yapılandırması"""
    BOT_TOKEN = os.getenv("BOT_TOKEN", "8133082070:AAE1rRGxQ9_Qqx-LZW54WFuFuGEo9FZhhWc")
    ADMIN_IDS = [7172270461]

    # PostgreSQL - Railway bağlantısı
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Zorunlu kanallar
    REQUIRED_CHANNELS = ["@igro_lab"]

    # Diamond sistemi
    DIAMOND_TO_MANAT = 5  # 5 diamond = 1 manat
    MIN_WITHDRAW_DIAMOND = 25
    MIN_REFERRAL_COUNT = 2

    # Para çekme seçenekleri
    WITHDRAW_OPTIONS = [25, 50, 75, 100]

    # Oyun ayarları
    GAME_SETTINGS = {
        "apple_box": {"cost": 1, "win_reward": 3, "win_chance": 40},
        "scratch_easy": {"cost": 1, "win_reward": 3, "win_chance": 60},
        "scratch_hard": {"cost": 1, "win_reward": 5, "win_chance": 25},
        "wheel": {
            "cost": 2,
            "rewards": [0, 2, 4, 5, 8, 3, -1, -2],
            "weights": [20, 10, 6, 6, 1, 10, 20, 20]
        }
    }

    # Bonus ayarları
    DAILY_BONUS_AMOUNT = 1
    DAILY_BONUS_COOLDOWN = 86400  # 24 saat

# ============================================================================
# VERİTABANI YÖNETİMİ - PostgreSQL
# ============================================================================

class Database:
    """PostgreSQL veritabanı yöneticisi"""

    def __init__(self):
        self.connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,
            Config.DATABASE_URL
        )
        self.init_db()

    def get_connection(self):
        """Bağlantı havuzundan bağlantı al"""
        return self.connection_pool.getconn()

    def return_connection(self, conn):
        """Bağlantıyı havuza geri ver"""
        self.connection_pool.putconn(conn)

    def init_db(self):
        """Veritabanı tablolarını oluştur"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Kullanıcılar tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                diamond INTEGER DEFAULT 0,
                total_withdrawn INTEGER DEFAULT 0,
                referral_count INTEGER DEFAULT 0,
                referred_by BIGINT,
                last_bonus_time BIGINT DEFAULT 0,
                joined_date BIGINT,
                is_banned BOOLEAN DEFAULT FALSE,
                last_task_reset BIGINT DEFAULT 0
            )
        """)

        # Promo kodlar
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                diamond_reward INTEGER,
                max_uses INTEGER,
                current_uses INTEGER DEFAULT 0,
                created_date BIGINT
            )
        """)

        # Kullanıcı promo kod kullanımı
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS used_promo_codes (
                user_id BIGINT,
                code TEXT,
                used_date BIGINT,
                PRIMARY KEY (user_id, code)
            )
        """)

        # Sponsor kanallar/gruplar
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sponsors (
                sponsor_id SERIAL PRIMARY KEY,
                channel_id TEXT UNIQUE,
                channel_name TEXT,
                diamond_reward INTEGER,
                is_active BOOLEAN DEFAULT TRUE,
                created_date BIGINT
            )
        """)

        # Kullanıcı sponsor takip durumu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sponsors (
                user_id BIGINT,
                sponsor_id INTEGER,
                completed_date BIGINT,
                PRIMARY KEY (user_id, sponsor_id)
            )
        """)

        # Para çekme talepleri
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                request_id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                diamond_amount INTEGER,
                manat_amount REAL,
                request_date BIGINT,
                status TEXT DEFAULT 'pending',
                processed_date BIGINT
            )
        """)

        conn.commit()
        cursor.close()
        self.return_connection(conn)

    # ========== KULLANICI İŞLEMLERİ ==========

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Kullanıcı bilgilerini getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        self.return_connection(conn)
        return dict(user) if user else None

    def create_user(self, user_id: int, username: str, referred_by: Optional[int] = None):
        """Yeni kullanıcı oluştur"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (user_id, username, diamond, referred_by, joined_date, last_task_reset)
                VALUES (%s, %s, 5, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, username, referred_by, int(time.time()), int(time.time())))

            if referred_by:
                cursor.execute("""
                    UPDATE users
                    SET diamond = diamond + 1, referral_count = referral_count + 1
                    WHERE user_id = %s
                """, (referred_by,))

            conn.commit()
        except Exception as e:
            conn.rollback()
            logging.error(f"Kullanıcı oluşturma hatası: {e}")
        finally:
            cursor.close()
            self.return_connection(conn)

    def update_diamond(self, user_id: int, amount: int):
        """Diamond güncelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET diamond = diamond + %s WHERE user_id = %s
        """, (amount, user_id))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def set_last_bonus_time(self, user_id: int):
        """Son bonus alma zamanını kaydet"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET last_bonus_time = %s WHERE user_id = %s
        """, (int(time.time()), user_id))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    # ========== PROMO KOD İŞLEMLERİ ==========

    def create_promo_code(self, code: str, diamond_reward: int, max_uses: int):
        """Promo kod oluştur"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO promo_codes (code, diamond_reward, max_uses, created_date)
                VALUES (%s, %s, %s, %s)
            """, (code, diamond_reward, max_uses, int(time.time())))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            return False
        finally:
            cursor.close()
            self.return_connection(conn)

    def use_promo_code(self, code: str, user_id: int) -> Optional[int]:
        """Promo kod kullan"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT * FROM promo_codes WHERE code = %s", (code,))
        promo = cursor.fetchone()

        if not promo:
            cursor.close()
            self.return_connection(conn)
            return None

        if promo['current_uses'] >= promo['max_uses']:
            cursor.close()
            self.return_connection(conn)
            return -1

        cursor.execute("""
            SELECT * FROM used_promo_codes WHERE user_id = %s AND code = %s
        """, (user_id, code))

        if cursor.fetchone():
            cursor.close()
            self.return_connection(conn)
            return -2

        cursor.execute("""
            UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code = %s
        """, (code,))

        cursor.execute("""
            INSERT INTO used_promo_codes (user_id, code, used_date)
            VALUES (%s, %s, %s)
        """, (user_id, code, int(time.time())))

        conn.commit()
        reward = promo['diamond_reward']
        cursor.close()
        self.return_connection(conn)
        return reward

    def get_all_promo_codes(self) -> List[Dict]:
        """Tüm promo kodları getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM promo_codes ORDER BY created_date DESC")
        promos = cursor.fetchall()
        cursor.close()
        self.return_connection(conn)
        return [dict(p) for p in promos]

    def delete_promo_code(self, code: str):
        """Promo kod sil"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM promo_codes WHERE code = %s", (code,))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    # ========== SPONSOR İŞLEMLERİ ==========

    def add_sponsor(self, channel_id: str, channel_name: str, diamond_reward: int):
        """Sponsor kanal/grup ekle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO sponsors (channel_id, channel_name, diamond_reward, created_date)
                VALUES (%s, %s, %s, %s)
            """, (channel_id, channel_name, diamond_reward, int(time.time())))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logging.error(f"Sponsor ekleme hatası: {e}")
            return False
        finally:
            cursor.close()
            self.return_connection(conn)

    def get_active_sponsors(self) -> List[Dict]:
        """Aktif sponsorları getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM sponsors WHERE is_active = TRUE
            ORDER BY created_date ASC
        """)
        sponsors = cursor.fetchall()
        cursor.close()
        self.return_connection(conn)
        return [dict(s) for s in sponsors]

    def get_user_next_sponsor(self, user_id: int) -> Optional[Dict]:
        """Kullanıcının henüz tamamlamadığı bir sonraki sponsoru getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT s.* FROM sponsors s
            WHERE s.is_active = TRUE
            AND s.sponsor_id NOT IN (
                SELECT sponsor_id FROM user_sponsors WHERE user_id = %s
            )
            ORDER BY s.created_date ASC
            LIMIT 1
        """, (user_id,))
        sponsor = cursor.fetchone()
        cursor.close()
        self.return_connection(conn)
        return dict(sponsor) if sponsor else None

    def check_sponsor_completed(self, user_id: int, sponsor_id: int) -> bool:
        """Sponsorun tamamlanıp tamamlanmadığını kontrol et"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM user_sponsors WHERE user_id = %s AND sponsor_id = %s
        """, (user_id, sponsor_id))
        result = cursor.fetchone() is not None
        cursor.close()
        self.return_connection(conn)
        return result

    def complete_sponsor(self, user_id: int, sponsor_id: int):
        """Sponsoru tamamlandı olarak işaretle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO user_sponsors (user_id, sponsor_id, completed_date)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, sponsor_id) DO NOTHING
            """, (user_id, sponsor_id, int(time.time())))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            return False
        finally:
            cursor.close()
            self.return_connection(conn)

    def delete_sponsor(self, sponsor_id: int):
        """Sponsor sil"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sponsors WHERE sponsor_id = %s", (sponsor_id,))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def reset_user_daily_tasks(self, user_id: int):
        """Kullanıcının günlük görevlerini sıfırla"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM user_sponsors WHERE user_id = %s
        """, (user_id,))
        cursor.execute("""
            UPDATE users SET last_task_reset = %s WHERE user_id = %s
        """, (int(time.time()), user_id))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def check_daily_task_reset(self, user_id: int) -> bool:
        """Günlük görevlerin sıfırlanması gerekip gerekmediğini kontrol et"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT last_task_reset FROM users WHERE user_id = %s
        """, (user_id,))
        result = cursor.fetchone()
        cursor.close()
        self.return_connection(conn)

        if not result:
            return False

        last_reset = result[0]
        current_time = int(time.time())

        # 24 saat geçtiyse sıfırla
        if current_time - last_reset >= 86400:
            return True
        return False

    # ========== PARA ÇEKME İŞLEMLERİ ==========

    def create_withdrawal_request(self, user_id: int, username: str, diamond: int, manat: float):
        """Para çekme talebi oluştur"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO withdrawal_requests
            (user_id, username, diamond_amount, manat_amount, request_date)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING request_id
        """, (user_id, username, diamond, manat, int(time.time())))
        request_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        self.return_connection(conn)
        return request_id

    def get_withdrawal_request(self, request_id: int) -> Optional[Dict]:
        """Para çekme talebini getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM withdrawal_requests WHERE request_id = %s
        """, (request_id,))
        request = cursor.fetchone()
        cursor.close()
        self.return_connection(conn)
        return dict(request) if request else None

    def approve_withdrawal(self, request_id: int):
        """Para çekme talebini onayla ve diamond'ı düş"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Talebi getir
        cursor.execute("""
            SELECT user_id, diamond_amount FROM withdrawal_requests
            WHERE request_id = %s
        """, (request_id,))
        result = cursor.fetchone()

        if result:
            user_id, diamond_amount = result

            # Talebi onayla
            cursor.execute("""
                UPDATE withdrawal_requests
                SET status = 'approved', processed_date = %s
                WHERE request_id = %s
            """, (int(time.time()), request_id))

            # Diamond'ı düş
            cursor.execute("""
                UPDATE users
                SET diamond = diamond - %s, total_withdrawn = total_withdrawn + %s
                WHERE user_id = %s
            """, (diamond_amount, diamond_amount, user_id))

            conn.commit()

        cursor.close()
        self.return_connection(conn)

    def reject_withdrawal(self, request_id: int):
        """Para çekme talebini reddet"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE withdrawal_requests
            SET status = 'rejected', processed_date = %s
            WHERE request_id = %s
        """, (int(time.time()), request_id))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def get_pending_withdrawals(self) -> List[Dict]:
        """Bekleyen para çekme taleplerini getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM withdrawal_requests
            WHERE status = 'pending'
            ORDER BY request_date DESC
        """)
        requests = cursor.fetchall()
        cursor.close()
        self.return_connection(conn)
        return [dict(r) for r in requests]

    # ========== DİĞER İŞLEMLER ==========

    def get_all_user_ids(self) -> List[int]:
        """Tüm kullanıcı ID'lerini getir"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE is_banned = FALSE")
        users = [row[0] for row in cursor.fetchall()]
        cursor.close()
        self.return_connection(conn)
        return users

    def get_stats(self) -> Dict:
        """Bot istatistiklerini getir"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(diamond) FROM users")
        total_diamonds = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(total_withdrawn) FROM users")
        total_withdrawn = cursor.fetchone()[0] or 0

        cursor.close()
        self.return_connection(conn)

        return {
            "total_users": total_users,
            "total_diamonds": total_diamonds,
            "total_withdrawn": total_withdrawn
        }

# Global database instance
db = Database()

# ============================================================================
# YARDIMCI FONKSİYONLAR
# ============================================================================

async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Kullanıcının tüm zorunlu kanalları takip edip etmediğini kontrol et"""
    for channel in Config.REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

async def check_sponsor_membership(user_id: int, channel_id: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Kullanıcının sponsor kanalını takip edip etmediğini kontrol et"""
    try:
        member = await context.bot.get_chat_member(channel_id, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except Exception as e:
        logging.error(f"Sponsor kontrol hatası: {e}")
        return False

def get_main_menu_keyboard(is_admin: bool = False):
    """Ana menü klavyesi"""
    keyboard = [
        [
            InlineKeyboardButton("👤 Profil", callback_data="menu_profile"),
            InlineKeyboardButton("💎 Diamond gazan", callback_data="menu_earn")
        ],
        [
            InlineKeyboardButton("💰 Pul çekmek", callback_data="menu_withdraw"),
            InlineKeyboardButton("❓ ÝSS", callback_data="menu_faq")
        ]
    ]

    if is_admin:
        keyboard.append([
            InlineKeyboardButton("👑 Admin Paneli", callback_data="admin_panel")
        ])

    return InlineKeyboardMarkup(keyboard)

def get_earn_menu_keyboard():
    """Diamond kazanma menüsü"""
    keyboard = [
        [InlineKeyboardButton("🎮 Oýunlar", callback_data="earn_games")],
        [InlineKeyboardButton("🎁 Günlük bonus", callback_data="earn_daily_bonus")],
        [InlineKeyboardButton("📋 Günlük zadanýa", callback_data="earn_tasks")],
        [InlineKeyboardButton("🎟 Promo kod", callback_data="earn_promo")],
        [InlineKeyboardButton("🔙 Yza gaýt", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_games_keyboard():
    """Oyunlar menüsü"""
    keyboard = [
        [InlineKeyboardButton("🎯 Almany Tap", callback_data="game_apple")],
        [InlineKeyboardButton("🎰 Lotereýa (Ýeňil)", callback_data="game_scratch_easy")],
        [InlineKeyboardButton("🎰 Lotereýa (Kyn)", callback_data="game_scratch_hard")],
        [InlineKeyboardButton("🎡 Şansly Aýlaw", callback_data="game_wheel")],
        [InlineKeyboardButton("🔙 Yza gaýt", callback_data="menu_earn")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ============================================================================
# BOT KOMUTLARI
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start komutu"""
    user = update.effective_user

    # Davet linki kontrolü
    referred_by = None
    if context.args:
        try:
            referred_by = int(context.args[0])
        except:
            pass

    # Kanal takibi kontrolü
    is_member = await check_channel_membership(user.id, context)

    if not is_member:
        channels_text = "\n".join([f"📢 {ch}" for ch in Config.REQUIRED_CHANNELS])
        keyboard = [[InlineKeyboardButton("✅ Agza boldum", callback_data=f"check_membership_{referred_by if referred_by else 0}")]]

        await update.message.reply_text(
            f"🎮 <b>Hoş geldiňiz!</b>\n\n"
            f"🎉 Boty ulanmak üçin aşakdaky kanallara agza boluň:\n\n"
            f"{channels_text}\n\n"
            f"✅ Ählisine agza bolduňmy? Aşakdaky düwmä bas!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Kullanıcıyı kaydet
    existing_user = db.get_user(user.id)

    if not existing_user:
        db.create_user(user.id, user.username or "noname", referred_by)

        welcome_msg = (
            f"🎊 <b>Gutlaýarys {user.first_name}!</b>\n\n"
            f"💎 Başlangyç bonusy: <b>3 diamond</b>\n"
        )

        if referred_by:
            welcome_msg += f"🎁 Sizi çagyran adama hem bonus berildi!\n"

            try:
                referrer_data = db.get_user(referred_by)
                if referrer_data:
                    await context.bot.send_message(
                        chat_id=referred_by,
                        text=(
                            f"🎉 <b>Täze Referal!</b>\n\n"
                            f"👤 @{user.username or user.first_name} siziň referalyňyz bilen bota goşuldy!\n"
                            f"💎 Bonus: <b>+1 diamond</b>\n\n"
                            f"👥 Jemi referalyňyz: <b>{referrer_data['referral_count'] + 1}</b>"
                        ),
                        parse_mode="HTML"
                    )
            except Exception as e:
                logging.error(f"Duýduryş ugradylmady: {e}")

        await update.message.reply_text(welcome_msg, parse_mode="HTML")

    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ana menüyü göster"""
    user = update.effective_user
    user_data = db.get_user(user.id)

    # Eğer kullanıcı yoksa, oluştur
    if not user_data:
        db.create_user(user.id, user.username or "noname")
        user_data = db.get_user(user.id)

    text = (
        f"🎮 <b>Diamond Labs - Oýun oýnap pul gazanyň!</b>\n\n"
        f"💎 Siziň balansynyz: <b>{user_data['diamond']} diamond</b>\n\n"
        f"🎯 Oýunlar oýnaň, bonus gazanyň we hakyky pul alyň!\n"
        f"💰 5 diamond = 1 manat\n\n"
        f"📊 Näme etjek bolýaňyz?"
    )

    is_admin = user.id in Config.ADMIN_IDS
    keyboard = get_main_menu_keyboard(is_admin)

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
# MAIN
# ============================================================================

def main():
    """Bot'u başlat"""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    # Import handlers
    from bot_handlers import (
        button_callback, 
        handle_promo_code_input,
        handle_membership_check
    )
    from bot_admin import admin_command

    application = Application.builder().token(Config.BOT_TOKEN).build()

    # Komutlar
    application.add_handler(CommandHandler("start", start_command))
    
    # Admin komutları
    application.add_handler(CommandHandler("adddia", admin_command))
    application.add_handler(CommandHandler("remdia", admin_command))
    application.add_handler(CommandHandler("userinfo", admin_command))
    application.add_handler(CommandHandler("createpromo", admin_command))
    application.add_handler(CommandHandler("addsponsor", admin_command))
    application.add_handler(CommandHandler("broadcast", admin_command))
    application.add_handler(CommandHandler("approve", admin_command))
    application.add_handler(CommandHandler("reject", admin_command))

    # Callback handlers
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Message handlers (promo kod girişi için)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_promo_code_input
    ))

    print("🤖 Bot başlady...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
