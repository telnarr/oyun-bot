#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Diamond Bot - Oyun Oynayarak Para Kazan
Türkmen Dili | Modüler Yapı | PostgreSQL Database
Production Ready Version
"""

import asyncio
import random
import os
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging

# PostgreSQL için gerekli
import psycopg2
from psycopg2.extras import RealDictCursor

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
    BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    
    # PostgreSQL bağlantısı (Railway otomatik sağlar)
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # Admin ID'leri (virgülle ayrılmış)
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",")]

    # Zorunlu kanallar (virgülle ayrılmış)
    REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS", "@igro_lab").split(",")

    # Diamond sistemi
    DIAMOND_TO_MANAT = int(os.getenv("DIAMOND_TO_MANAT", "3"))
    MIN_WITHDRAW_DIAMOND = int(os.getenv("MIN_WITHDRAW_DIAMOND", "15"))
    MIN_REFERRAL_COUNT = int(os.getenv("MIN_REFERRAL_COUNT", "2"))

    # Oyun ayarları (varsayılan)
    GAME_SETTINGS = {
        "apple_box": {
            "cost": 2,
            "win_reward": 5,
            "win_chance": 40
        },
        "scratch_easy": {
            "cost": 3,
            "win_reward": 8,
            "win_chance": 60
        },
        "scratch_hard": {
            "cost": 5,
            "win_reward": 20,
            "win_chance": 25
        },
        "wheel": {
            "cost": 4,
            "rewards": [0, 3, 5, 8, 10, 15, -2],
            "weights": [20, 25, 20, 15, 10, 5, 5]
        }
    }

    # Bonus ayarları
    DAILY_BONUS_AMOUNT = int(os.getenv("DAILY_BONUS_AMOUNT", "3"))
    DAILY_BONUS_COOLDOWN = 86400  # 24 saat

# ============================================================================
# VERİTABANI YÖNETİMİ
# ============================================================================

class Database:
    """PostgreSQL veritabanı yöneticisi"""

    def __init__(self):
        self.init_db()

    def get_connection(self):
        """Veritabanı bağlantısı"""
        return psycopg2.connect(Config.DATABASE_URL, cursor_factory=RealDictCursor)

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
                is_banned INTEGER DEFAULT 0
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

        # Kullanılmış promo kodlar
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS used_promo_codes (
                user_id BIGINT,
                code TEXT,
                used_date BIGINT,
                PRIMARY KEY (user_id, code)
            )
        """)

        # Günlük görevler
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_tasks (
                task_id SERIAL PRIMARY KEY,
                task_type TEXT,
                task_description TEXT,
                diamond_reward INTEGER,
                task_data TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)

        # Kullanıcı görev tamamlama
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_tasks (
                user_id BIGINT,
                task_id INTEGER,
                completed_date BIGINT,
                PRIMARY KEY (user_id, task_id)
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
                status TEXT DEFAULT 'pending'
            )
        """)

        conn.commit()
        conn.close()

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Kullanıcı bilgilerini getir"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_user(self, user_id: int, username: str, referred_by: Optional[int] = None):
        """Yeni kullanıcı oluştur"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (user_id, username, diamond, referred_by, joined_date)
                VALUES (%s, %s, 5, %s, %s)
            """, (user_id, username, referred_by, int(time.time())))

            if referred_by:
                cursor.execute("""
                    UPDATE users SET diamond = diamond + 2, referral_count = referral_count + 1
                    WHERE user_id = %s
                """, (referred_by,))

            conn.commit()
        except psycopg2.IntegrityError:
            pass
        finally:
            conn.close()

    def update_diamond(self, user_id: int, amount: int):
        """Diamond güncelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET diamond = diamond + %s WHERE user_id = %s
        """, (amount, user_id))
        conn.commit()
        conn.close()

    def set_last_bonus_time(self, user_id: int):
        """Son bonus alma zamanını kaydet"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET last_bonus_time = %s WHERE user_id = %s
        """, (int(time.time()), user_id))
        conn.commit()
        conn.close()

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
        except psycopg2.IntegrityError:
            return False
        finally:
            conn.close()

    def use_promo_code(self, code: str, user_id: int) -> Optional[int]:
        """Promo kod kullan"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM promo_codes WHERE code = %s", (code,))
        promo = cursor.fetchone()

        if not promo:
            conn.close()
            return None

        if promo['current_uses'] >= promo['max_uses']:
            conn.close()
            return -1

        cursor.execute("""
            SELECT * FROM used_promo_codes WHERE user_id = %s AND code = %s
        """, (user_id, code))

        if cursor.fetchone():
            conn.close()
            return -2

        cursor.execute("""
            UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code = %s
        """, (code,))

        cursor.execute("""
            INSERT INTO used_promo_codes (user_id, code, used_date) VALUES (%s, %s, %s)
        """, (user_id, code, int(time.time())))

        conn.commit()
        conn.close()

        return promo['diamond_reward']

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
        last_id = cursor.fetchone()['request_id']
        conn.commit()
        conn.close()
        return last_id

    def get_withdrawal_request(self, request_id: int):
        """Para çekme talebini getir"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM withdrawal_requests WHERE request_id = %s", (request_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def approve_withdrawal(self, request_id: int):
        """Para çekme talebini onayla"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE withdrawal_requests SET status = 'approved' WHERE request_id = %s
        """, (request_id,))
        conn.commit()
        conn.close()

    def add_sponsor_channel(self, channel_id: str, channel_name: str, diamond_reward: int):
        """Sponsor kanal ekle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO daily_tasks (task_type, task_description, diamond_reward, task_data, is_active)
                VALUES ('join_channel', %s, %s, %s, 1)
            """, (channel_name, diamond_reward, channel_id))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()

    def get_active_sponsor_channels(self):
        """Aktif sponsor kanalları getir"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT task_id, task_description, diamond_reward, task_data
            FROM daily_tasks WHERE task_type = 'join_channel' AND is_active = 1
        """)
        channels = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return channels

    def check_task_completed(self, user_id: int, task_id: int) -> bool:
        """Görevin tamamlanıp tamamlanmadığını kontrol et"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM user_tasks WHERE user_id = %s AND task_id = %s
        """, (user_id, task_id))
        result = cursor.fetchone() is not None
        conn.close()
        return result

    def complete_task(self, user_id: int, task_id: int):
        """Görevi tamamlandı olarak işaretle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO user_tasks (user_id, task_id, completed_date)
                VALUES (%s, %s, %s)
            """, (user_id, task_id, int(time.time())))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()

    def get_all_user_ids(self) -> List[int]:
        """Tüm kullanıcı ID'lerini getir"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
        users = [row['user_id'] for row in cursor.fetchall()]
        conn.close()
        return users

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

def get_main_menu_keyboard(is_admin=False):
    """Ana menü klavyesi"""
    keyboard = [
        [
            InlineKeyboardButton("👤 Profil", callback_data="menu_profile"),
            InlineKeyboardButton("💎 Diamond kazan", callback_data="menu_earn")
        ],
        [
            InlineKeyboardButton("💰 Para çekmek", callback_data="menu_withdraw"),
            InlineKeyboardButton("❓ SSS", callback_data="menu_faq")
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
        [InlineKeyboardButton("🍎 Kutudaki Elmayı Bul", callback_data="game_apple")],
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

    referred_by = None
    if context.args:
        try:
            referred_by = int(context.args[0])
        except:
            pass

    is_member = await check_channel_membership(user.id, context)

    if not is_member:
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
                            f"👤 @{user.username or user.first_name} siziň dawetyňyz bilen bota goşuldy!\n"
                            f"💎 Bonus: <b>+2 diamond</b>\n\n"
                            f"👥 Jemi dawetiňiz: <b>{referrer_data['referral_count'] + 1}</b>"
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

    text = (
        f"🎮 <b>Diamond Bot - Oýun oýnap pul gazanyň!</b>\n\n"
        f"💎 Siziň balansyňyz: <b>{user_data['diamond']} diamond</b>\n\n"
        f"🎯 Oýunlar oýnaň, bonus gazanyň we hakyky manat alyň!\n"
        f"💰 3 diamond = 1 manat\n\n"
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
# CALLBACK HANDLERS
# ============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tüm buton callback'lerini yönet"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "back_main":
        await show_main_menu(update, context)

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

                welcome_text = "✅ <b>Ajaýyp!</b>\n\n"
                welcome_text += f"💎 Başlangyç bonusy: <b>5 diamond</b>\n"

                if referred_by:
                    welcome_text += f"🎁 Sizi çagyran adama hem bonus berildi!\n"

                    try:
                        referrer_data = db.get_user(referred_by)
                        if referrer_data:
                            await context.bot.send_message(
                                chat_id=referred_by,
                                text=(
                                    f"🎉 <b>Täze davet!</b>\n\n"
                                    f"👤 @{username} siziň dawetyňyz bilen bota goşuldy!\n"
                                    f"💎 Bonus: <b>+2 diamond</b>\n\n"
                                    f"👥 Jemi dawetiňiz: <b>{referrer_data['referral_count'] + 1}</b>"
                                ),
                                parse_mode="HTML"
                            )
                    except Exception as e:
                        logging.error(f"Bildirim gönderilemedi: {e}")

                await query.edit_message_text(
                    welcome_text + "\nIndi bot ulanyp bilersiňiz! 🎉",
                    parse_mode="HTML"
                )
            else:
                await query.edit_message_text(
                    "✅ <b>Ajaýyp!</b>\n\nIndi bot ulanyp bilersiňiz! 🎉",
                    parse_mode="HTML"
                )

            await show_main_menu(update, context)
        else:
            await query.answer("❌ Heniz ähli kanallary yzarlamadyňyz!", show_alert=True)

    elif data == "menu_profile":
        await show_profile(update, context)

    elif data == "menu_earn":
        await show_earn_menu(update, context)

    elif data == "earn_promo_cancel":
        context.user_data['waiting_for_promo'] = False
        await show_earn_menu(update, context)

    elif data == "task_completed":
        await query.answer("✅ Bu wezipäni eýýäm tamamladyňyz!", show_alert=True)
        
    elif data == "earn_games":
        await show_games_menu(update, context)

    elif data == "menu_withdraw":
        await show_withdraw_menu(update, context)

    elif data.startswith("withdraw_amount_"):
        await handle_withdraw_request(update, context)

    elif data == "menu_faq":
        await show_faq(update, context)

    elif data == "earn_daily_bonus":
        await claim_daily_bonus(update, context)

    elif data == "earn_tasks":
        await show_daily_tasks(update, context)

    elif data.startswith("task_join_"):
        await handle_task_join(update, context)
    
    elif data.startswith("task_check_"):
        await handle_task_check(update, context)

    elif data == "earn_promo":
        await show_promo_input(update, context)

    elif data.startswith("game_"):
        await handle_game_start(update, context, data)

    elif data == "admin_panel":
        if user_id in Config.ADMIN_IDS:
            await show_admin_panel(update, context)
        else:
            await query.answer("❌ Siziň admin hukugyňyz ýok!", show_alert=True)

    elif data == "admin_users":
        await admin_users_menu(update, context)

    elif data == "admin_games":
        await admin_games_menu(update, context)

    elif data == "admin_promo":
        await admin_promo_menu(update, context)

    elif data == "admin_stats":
        await admin_stats(update, context)

    elif data == "admin_broadcast":
        await admin_broadcast_menu(update, context)

    elif data == "admin_add_sponsor":
        await admin_add_sponsor_menu(update, context)

    elif data.startswith("admin_approve_"):
        await admin_approve_withdrawal(update, context)

    elif data == "admin_back":
        await show_admin_panel(update, context)

# ============================================================================
# MENÜ FONKSİYONLARI
# ============================================================================

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Profil göster"""
    query = update.callback_query
    user_id = query.from_user.id

    db = Database()
    user_data = db.get_user(user_id)

    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"

    text = (
        f"👤 <b>Siziň profil</b>\n\n"
        f"🆔 ID: <code>{user_data['user_id']}</code>\n"
        f"👤 Ulanyjy: @{user_data['username']}\n"
        f"💎 Diamond: <b>{user_data['diamond']}</b>\n"
        f"👥 Çagrylan: <b>{user_data['referral_count']}</b> adam\n"
        f"💸 Çekilen: <b>{user_data['total_withdrawn']}</b> diamond\n\n"
        f"🔗 <b>Davet linka:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"💡 Dostlaryňyzy çagryň we bonus gazanyň!"
    )

    keyboard = [[InlineKeyboardButton("🔙 Geri dön", callback_data="back_main")]]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_earn_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Diamond kazanma menüsü"""
    query = update.callback_query

    text = (
        f"💎 <b>Diamond Gazanyň!</b>\n\n"
        f"🎮 Oýunlar oýnaň\n"
        f"🎁 Gündelik bonus alyň\n"
        f"📋 Wezipeleri ýerine ýetiriň\n"
        f"🎟 Promo kod ulanyň\n\n"
        f"🚀 Haýsy usuly saýlaýaňyz?"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=get_earn_menu_keyboard()
    )

async def show_games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oyunlar menüsü"""
    query = update.callback_query

    text = (
        f"🎮 <b>Oýunlar</b>\n\n"
        f"🍎 <b>Kutudaki Elmayı Bul</b>\n"
        f"   • Bahasy: 2 💎\n"
        f"   • Gazanç: 5 💎\n\n"
        f"🎰 <b>Kazı Kazan (Kolay)</b>\n"
        f"   • Bahasy: 3 💎\n"
        f"   • Gazanç: 8 💎\n\n"
        f"🎰 <b>Kazı Kazan (Zor)</b>\n"
        f"   • Bahasy: 5 💎\n"
        f"   • Gazanç: 20 💎\n\n"
        f"🎡 <b>Çarkı Felek</b>\n"
        f"   • Bahasy: 4 💎\n"
        f"   • Gazanç: 0-15 💎\n\n"
        f"🎯 Oýun saýlaň!"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=get_games_keyboard()
    )

async def show_daily_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Günlük görevler menüsü - Tek tek gösterim"""
    query = update.callback_query
    user_id = query.from_user.id

    db = Database()
    channels = db.get_active_sponsor_channels()

    if not channels:
        await query.edit_message_text(
            "📋 <b>Gündelik Wezipeler</b>\n\n"
            "❌ Häzirki wagtda hiç bir wezipe ýok.\n"
            "Soňra gaýtadan baryp görüň!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Geri dön", callback_data="menu_earn")
            ]])
        )
        return

    # İlk tamamlanmamış görevi bul
    current_task = None
    for channel in channels:
        if not db.check_task_completed(user_id, channel['task_id']):
            current_task = channel
            break

    if not current_task:
        # Tüm görevler tamamlanmış
        await query.edit_message_text(
            "🎉 <b>Gutlaýarys!</b>\n\n"
            "✅ Ähli wezipeleri tamamladyňyz!\n"
            "💎 Täze wezipeler goşulýança garaşyň.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Geri dön", callback_data="menu_earn")
            ]])
        )
        return

    # Tek görevi göster
    text = (
        f"📋 <b>Gündelik Wezipe</b>\n\n"
        f"📢 <b>{current_task['task_description']}</b>\n\n"
        f"💎 Baýrak: <b>+{current_task['diamond_reward']} diamond</b>\n\n"
        f"📍 Kanal: {current_task['task_data']}\n\n"
        f"1️⃣ Kanala giriň\n"
        f"2️⃣ 'Takip ettim' düwmä basyň"
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Kanala git", url=f"https://t.me/{current_task['task_data'].replace('@', '')}")],
        [InlineKeyboardButton("✅ Takip ettim", callback_data=f"task_check_{current_task['task_id']}")],
        [InlineKeyboardButton("🔙 Geri dön", callback_data="menu_earn")]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_task_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Görev tamamlama - kanal takibi kontrol"""
    query = update.callback_query
    user_id = query.from_user.id

    task_id = int(query.data.split("_")[2])

    db = Database()
    channels = db.get_active_sponsor_channels()

    task_info = None
    for ch in channels:
        if ch['task_id'] == task_id:
            task_info = ch
            break

    if not task_info:
        await query.answer("❌ Wezipe tapylmady!", show_alert=True)
        return

    # Kanal takibini kontrol et (Bot kanalda admin olmalı)
    try:
        member = await context.bot.get_chat_member(task_info['task_data'], user_id)
        if member.status in ["member", "administrator", "creator"]:
            # Görevi tamamla
            if db.complete_task(user_id, task_id):
                db.update_diamond(user_id, task_info['diamond_reward'])

                await query.answer(
                    f"✅ +{task_info['diamond_reward']} 💎 aldyňyz!",
                    show_alert=True
                )

                # Bir sonraki göreve geç
                await show_daily_tasks(update, context)
            else:
                await query.answer("❌ Bu wezipäni eýýäm tamamladyňyz!", show_alert=True)
        else:
            await query.answer(
                f"❌ Ilki bilen {task_info['task_data']} kanalyny yzarlaň!",
                show_alert=True
            )
    except Exception as e:
        logging.error(f"Kanal kontrolü hatası: {e}")
        await query.answer(
            f"❌ Kanaly barlaýanda ýalňyşlyk ýüze çykdy!\n"
            f"Bot bu kanalda admin bolmalydyr.",
            show_alert=True
        )

async def handle_task_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eski fonksiyon - artık kullanılmıyor"""
    pass

async def show_promo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo kod girişi"""
    query = update.callback_query

    context.user_data['waiting_for_promo'] = True

    await query.edit_message_text(
        "🎟 <b>Promo Kod</b>\n\n"
        "💎 Promo kodyňyzy ýazyň:\n\n"
        "Mysaly: <code>BONUS2024</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Ýatyr", callback_data="earn_promo_cancel")
        ]])
    )

async def handle_promo_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo kod mesajını işle"""
    if not context.user_data.get('waiting_for_promo'):
        return

    user_id = update.effective_user.id
    promo_code = update.message.text.strip().upper()

    db = Database()
    result = db.use_promo_code(promo_code, user_id)

    if result is None:
        await update.message.reply_text(
            "❌ <b>Ýalňyş kod!</b>\n\n"
            "Bu promo kod tapylmady.",
            parse_mode="HTML"
        )
    elif result == -1:
        await update.message.reply_text(
            "❌ <b>Kod gutardy!</b>\n\n"
            "Bu promo kodyň ulanyş möhleti gutardy.",
            parse_mode="HTML"
        )
    elif result == -2:
        await update.message.reply_text(
            "❌ <b>Eýýäm ulanyldy!</b>\n\n"
            "Siz bu promo kody öň ulandyňyz.",
            parse_mode="HTML"
        )
    else:
        db.update_diamond(user_id, result)
        await update.message.reply_text(
            f"🎉 <b>GUTLAÝARYS!</b>\n\n"
            f"💎 Siz <b>{result} diamond</b> aldyňyz!\n"
            f"🎟 Kod: <code>{promo_code}</code>",
            parse_mode="HTML"
        )

    context.user_data['waiting_for_promo'] = False

async def show_withdraw_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Para çekme menüsü - DÜZELTİLDİ"""
    query = update.callback_query
    user_id = query.from_user.id

    db = Database()
    user_data = db.get_user(user_id)

    can_withdraw = (
        user_data['diamond'] >= Config.MIN_WITHDRAW_DIAMOND and
        user_data['referral_count'] >= Config.MIN_REFERRAL_COUNT
    )

    text = (
        f"💰 <b>Pul Çekmek</b>\n\n"
        f"💎 Siziň balansynyz: <b>{user_data['diamond']} diamond</b>\n"
        f"💵 Manat görnüşinde: <b>{user_data['diamond'] / Config.DIAMOND_TO_MANAT:.2f} TMT</b>\n\n"
        f"📋 <b>Şertler:</b>\n"
        f"   • Minimum: {Config.MIN_WITHDRAW_DIAMOND} 💎 ({Config.MIN_WITHDRAW_DIAMOND / Config.DIAMOND_TO_MANAT:.0f} TMT)\n"
        f"   • Azyndan {Config.MIN_REFERRAL_COUNT} adam çagymaly\n"
        f"   • 3 diamond = 1 manat\n\n"
    )

    if can_withdraw:
        text += f"✅ Siz pul çekip bilersiňiz!\n\n"
        text += f"💎 Näçe diamond çekmek isleýärsiňiz?"
        
        # Çekebileceği miktarları hesapla
        amounts = []
        if user_data['diamond'] >= 15:
            amounts.append(15)
        if user_data['diamond'] >= 30:
            amounts.append(30)
        if user_data['diamond'] >= 60:
            amounts.append(60)
        
        keyboard = []
        for amount in amounts:
            manat = amount / Config.DIAMOND_TO_MANAT
            keyboard.append([InlineKeyboardButton(
                f"💎 {amount} diamond ({manat:.0f} TMT)", 
                callback_data=f"withdraw_amount_{amount}"
            )])
    else:
        reasons = []
        if user_data['diamond'] < Config.MIN_WITHDRAW_DIAMOND:
            reasons.append(f"❌ Ýeterlik diamond ýok ({Config.MIN_WITHDRAW_DIAMOND} gerek)")
        if user_data['referral_count'] < Config.MIN_REFERRAL_COUNT:
            reasons.append(f"❌ Azyndan {Config.MIN_REFERRAL_COUNT} adam çagyrmalysynyz")

        text += "\n".join(reasons)
        keyboard = []

    keyboard.append([InlineKeyboardButton("🔙 Geri dön", callback_data="back_main")])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_withdraw_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Para çekme talebi işle - DÜZELTİLDİ"""
    query = update.callback_query
    user_id = query.from_user.id

    amount = int(query.data.split("_")[2])

    db = Database()
    user_data = db.get_user(user_id)

    if user_data['diamond'] < amount:
        await query.answer("❌ Ýeterlik diamond ýok!", show_alert=True)
        return

    # Manat hesapla
    manat = amount / Config.DIAMOND_TO_MANAT

    # Talep oluştur
    request_id = db.create_withdrawal_request(
        user_id, 
        user_data['username'], 
        amount, 
        manat
    )

    # Kullanıcıya bildir
    await query.edit_message_text(
        f"✅ <b>Talap döredildi!</b>\n\n"
        f"🆔 Talap belgisi: <code>{request_id}</code>\n"
        f"💎 Mukdar: {amount} diamond\n"
        f"💵 Manat: {manat:.1f} TMT\n\n"
        f"⏳ Admin tarapyndan serediler.\n"
        f"📞 Admin size ýakyn wagtda habarlaşar!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Ana menä", callback_data="back_main")
        ]])
    )

    # Adminlere bildir
    for admin_id in Config.ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🔔 <b>TÄZE PUL ÇEKME TALABY!</b>\n\n"
                    f"🆔 Talap: <code>{request_id}</code>\n"
                    f"👤 Ulanyjy: @{user_data['username']} (ID: {user_id})\n"
                    f"💎 Mukdar: {amount} diamond\n"
                    f"💵 Manat: {manat:.1f} TMT\n\n"
                    f"Tassyklamak üçin:\n"
                    f"/approve {request_id}"
                ),
                parse_mode="HTML"
            )
        except:
            pass

async def show_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SSS göster"""
    query = update.callback_query

    text = (
        f"❓ <b>Ýygy-ýygydan soralýan soraglar</b>\n\n"
        f"<b>🎮 Nädip oýnamaly?</b>\n"
        f"Oýunlary saýlap, diamond bilen bahalaň. Her oýnunda gazanmak mümkinçiligi bar!\n\n"
        f"<b>💎 Diamond nädip gazanmaly?</b>\n"
        f"• Oýunlar oýnaň\n"
        f"• Gündelik bonus alyň\n"
        f"• Wezipeleri ýerine ýetiriň\n"
        f"• Dostlaryňyzy çagryň\n"
        f"• Promo kodlary ulanyň\n\n"
        f"<b>💰 Pul nädip çekmeli?</b>\n"
        f"• Azyndan {Config.MIN_WITHDRAW_DIAMOND} diamond toplamaly\n"
        f"• {Config.MIN_REFERRAL_COUNT} adam çagymaly\n"
        f"• 'Para çekmek' bölüminden talap döretmeli\n"
        f"• Admin size manat iberýär\n\n"
        f"<b>🔒 Howpsuzlyk</b>\n"
        f"Siziň maglumatlaryňyz goragly saklanýar. Hiç bir üçünji tarapa berilmeýär.\n\n"
        f"<b>📞 Goldaw</b>\n"
        f"Sograglaryňyz bar bolsa: @admin_username"
    )

    keyboard = [[InlineKeyboardButton("🔙 Geri dön", callback_data="back_main")]]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def claim_daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Günlük bonus al"""
    query = update.callback_query
    user_id = query.from_user.id

    db = Database()
    user_data = db.get_user(user_id)

    current_time = int(time.time())
    time_since_last = current_time - user_data['last_bonus_time']

    if time_since_last < Config.DAILY_BONUS_COOLDOWN:
        remaining = Config.DAILY_BONUS_COOLDOWN - time_since_last
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60

        await query.answer(
            f"⏰ Indiki bonusa {hours} sagat {minutes} minut galanda!",
            show_alert=True
        )

        await query.edit_message_text(
            f"⏰ <b>Garaşyň!</b>\n\n"
            f"🎁 Gündelik bonusynyzy eýýäm aldyňyz!\n\n"
            f"⏳ Indiki bonus: <b>{hours} sagat {minutes} minut</b> soň\n"
            f"💎 Bonus mukdary: <b>{Config.DAILY_BONUS_AMOUNT} diamond</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Geri dön", callback_data="menu_earn")
            ]])
        )
        return

    # Bonus ver
    db.update_diamond(user_id, Config.DAILY_BONUS_AMOUNT)
    db.set_last_bonus_time(user_id)

    await query.edit_message_text(
        f"🎁 <b>Gutlaýarys!</b>\n\n"
        f"💎 Siz <b>{Config.DAILY_BONUS_AMOUNT} diamond</b> aldyňyz!\n\n"
        f"⏰ Indiki bonus 24 sagatdan soň gelip biler.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Geri dön", callback_data="menu_earn")
        ]])
    )

# ============================================================================
# OYUNLAR
# ============================================================================

async def handle_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str):
    """Oyun başlatma - Önce bilgi göster"""
    query = update.callback_query
    user_id = query.from_user.id

    db = Database()
    user_data = db.get_user(user_id)

    game_costs = {
        "game_apple": Config.GAME_SETTINGS["apple_box"]["cost"],
        "game_scratch_easy": Config.GAME_SETTINGS["scratch_easy"]["cost"],
        "game_scratch_hard": Config.GAME_SETTINGS["scratch_hard"]["cost"],
        "game_wheel": Config.GAME_SETTINGS["wheel"]["cost"]
    }

    if game_type == "game_apple":
        settings = Config.GAME_SETTINGS["apple_box"]
        text = (
            f"🍎 <b>Kutudaki Elmayı Bul</b>\n\n"
            f"🎯 <b>Nädip oýnamaly?</b>\n"
            f"3 sany kutu görkeziler. Birinde elma bar!\n"
            f"Dogry kutuny saýlasaňyz gazanýaňyz! 🎉\n\n"
            f"💎 <b>Bahasy:</b> {settings['cost']} diamond\n"
            f"🎁 <b>Gazanç:</b> {settings['win_reward']} diamond\n"
            f"📊 <b>Şans:</b> %{settings['win_chance']}\n\n"
            f"💰 Siziň balansynyz: <b>{user_data['diamond']} 💎</b>"
        )

    elif game_type == "game_scratch_easy":
        settings = Config.GAME_SETTINGS["scratch_easy"]
        text = (
            f"🎰 <b>Kazı Kazan (Kolay)</b>\n\n"
            f"🎯 <b>Nädip oýnamaly?</b>\n"
            f"9 sany kart bar. 4 gezek açyp bilersiňiz!\n"
            f"3 sany birmeňzeş miw tapyň we gazanyň! 🍎🍊🍇\n\n"
            f"💎 <b>Bahasy:</b> {settings['cost']} diamond\n"
            f"🎁 <b>Gazanç:</b> {settings['win_reward']} diamond\n"
            f"📊 <b>Şans:</b> %{settings['win_chance']} (Kolay)\n\n"
            f"💰 Siziň balansynyz: <b>{user_data['diamond']} 💎</b>"
        )

    elif game_type == "game_scratch_hard":
        settings = Config.GAME_SETTINGS["scratch_hard"]
        text = (
            f"🎰 <b>Kazı Kazan (Zor)</b>\n\n"
            f"🎯 <b>Nädip oýnamaly?</b>\n"
            f"9 sany kart bar. 4 gezek açyp bilersiňiz!\n"
            f"3 sany birmeňzeş miwäni tapyň we gazanyň! 🍎🍊🍇🍋🍓🍉\n"
            f"⚠️ Köp dürli miweler bar - has kyn!\n\n"
            f"💎 <b>Bahasy:</b> {settings['cost']} diamond\n"
            f"🎁 <b>Gazanç:</b> {settings['win_reward']} diamond\n"
            f"📊 <b>Şans:</b> %{settings['win_chance']} (Zor)\n\n"
            f"💰 Siziň balansynyz: <b>{user_data['diamond']} 💎</b>"
        )

    elif game_type == "game_wheel":
        settings = Config.GAME_SETTINGS["wheel"]
        text = (
            f"🎡 <b>Çarkı Felek</b>\n\n"
            f"🎯 <b>Nädip oýnamaly?</b>\n"
            f"Çark aýlanar we bir netije gelýär!\n"
            f"Bagtly bolsaňyz uly gazanç alyp bilersiňiz! 💰\n\n"
            f"💎 <b>Bahasy:</b> {settings['cost']} diamond\n"
            f"🎁 <b>Mümkin bolan netijeler:</b>\n"
            f"   • 0 💎 (boş)\n"
            f"   • +3 💎\n"
            f"   • +5 💎\n"
            f"   • +8 💎\n"
            f"   • +10 💎\n"
            f"   • +15 💎 (JACKPOT!)\n"
            f"   • -2 💎 (jeza)\n\n"
            f"💰 Siziň balansynyz: <b>{user_data['diamond']} 💎</b>"
        )
    else:
        text = "❌ Oýun tapylmady!"

    cost = game_costs.get(game_type, 0)

    if user_data['diamond'] < cost:
        keyboard = [[InlineKeyboardButton("🔙 Geri dön", callback_data="earn_games")]]
        text += f"\n\n❌ <b>Ýeterlik diamond ýok!</b>"
    else:
        keyboard = [
            [InlineKeyboardButton("🎮 BAŞLA!", callback_data=f"game_play_{game_type}")],
            [InlineKeyboardButton("🔙 Geri dön", callback_data="earn_games")]
        ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def start_game_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oyunu gerçekten başlat"""
    query = update.callback_query
    user_id = query.from_user.id

    game_type = "_".join(query.data.split("_")[2:])

    db = Database()
    user_data = db.get_user(user_id)

    game_costs = {
        "game_apple": Config.GAME_SETTINGS["apple_box"]["cost"],
        "game_scratch_easy": Config.GAME_SETTINGS["scratch_easy"]["cost"],
        "game_scratch_hard": Config.GAME_SETTINGS["scratch_hard"]["cost"],
        "game_wheel": Config.GAME_SETTINGS["wheel"]["cost"]
    }

    cost = game_costs.get(game_type, 0)

    if user_data['diamond'] < cost:
        await query.answer(
            f"❌ Ýeterlik diamond ýok! {cost} 💎 gerek.",
            show_alert=True
        )
        return

    # Diamond düş
    db.update_diamond(user_id, -cost)

    # Oyunu başlat
    if game_type == "game_apple":
        await play_apple_box_game(update, context)
    elif game_type == "game_scratch_easy":
        await play_scratch_game(update, context, "easy")
    elif game_type == "game_scratch_hard":
        await play_scratch_game(update, context, "hard")
    elif game_type == "game_wheel":
        await play_wheel_game(update, context)

async def play_apple_box_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kutudaki Elmayı Bul oyunu"""
    query = update.callback_query
    user_id = query.from_user.id

    await query.edit_message_text("🍎 Oýun başlaýar...")
    await asyncio.sleep(1)

    await query.edit_message_text("📦 Kutular taýýarlanýar...")
    await asyncio.sleep(1)

    await query.edit_message_text("🔄 Kutular garyşýar...")
    await asyncio.sleep(1.5)

    apple_pos = random.randint(0, 2)

    keyboard = [[
        InlineKeyboardButton("📦 1", callback_data=f"apple_choice_0_{apple_pos}"),
        InlineKeyboardButton("📦 2", callback_data=f"apple_choice_1_{apple_pos}"),
        InlineKeyboardButton("📦 3", callback_data=f"apple_choice_2_{apple_pos}")
    ]]

    await query.edit_message_text(
        "🎮 <b>Kutudaki Elmayı Bul</b>\n\n"
        "🍎 Elma haýsy kutuda? Saýlaň!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_apple_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kutu seçimi"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data.split("_")
    choice = int(data[2])
    apple_pos = int(data[3])

    db = Database()

    await query.edit_message_text("📦 Kutu açylýar...")
    await asyncio.sleep(1.5)

    if choice == apple_pos:
        reward = Config.GAME_SETTINGS["apple_box"]["win_reward"]
        db.update_diamond(user_id, reward)

        await query.edit_message_text(
            f"🎉 <b>GUTLAÝARYS!</b>\n\n"
            f"🍎 Elma bu kutudady!\n"
            f"💎 Gazanç: <b>{reward} diamond</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎮 Täzeden oýnamak", callback_data="game_apple"),
                InlineKeyboardButton("🔙 Oýunlar", callback_data="earn_games")
            ]])
        )
    else:
        result_list = ["❌", "❌", "❌"]
        result_list[apple_pos] = "🍎"
        result_text = " ".join(result_list)

        await query.edit_message_text(
            f"😢 <b>Gynandyryjy...</b>\n\n"
            f"{result_text}\n\n"
            f"🍎 Elma beýleki kutudady!\n"
            f"💪 Täzeden synanyşyň!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎮 Täzeden oýnamak", callback_data="game_apple"),
                InlineKeyboardButton("🔙 Oýunlar", callback_data="earn_games")
            ]])
        )

async def play_scratch_game(update: Update, context: ContextTypes.DEFAULT_TYPE, difficulty: str):
    """Kazı Kazan oyunu"""
    query = update.callback_query

    await query.edit_message_text("🎰 Kazı Kazan taýýarlanýar...")
    await asyncio.sleep(1)

    if difficulty == "easy":
        fruits = ["🍎", "🍊", "🍇"]
        distribution = [4, 3, 2]
    else:
        fruits = ["🍎", "🍊", "🍇", "🍋", "🍓", "🍉"]
        distribution = [3, 1, 1, 1, 1, 2]

    cards = []
    for fruit, count in zip(fruits, distribution):
        cards.extend([fruit] * count)
    random.shuffle(cards)

    context.user_data['scratch_cards'] = cards
    context.user_data['scratch_revealed'] = [False] * 9
    context.user_data['scratch_attempts'] = 4
    context.user_data['scratch_difficulty'] = difficulty

    await show_scratch_board(update, context)

async def show_scratch_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kazı Kazan tahtasını göster"""
    query = update.callback_query

    revealed = context.user_data.get('scratch_revealed', [])
    cards = context.user_data.get('scratch_cards', [])
    attempts = context.user_data.get('scratch_attempts', 4)

    keyboard = []
    for i in range(3):
        row = []
        for j in range(3):
            idx = i * 3 + j
            if revealed[idx]:
                row.append(InlineKeyboardButton(cards[idx], callback_data=f"scratch_x_{idx}"))
            else:
                row.append(InlineKeyboardButton("❓", callback_data=f"scratch_reveal_{idx}"))
        keyboard.append(row)

    text = (
        f"🎰 <b>Kazı Kazan</b>\n\n"
        f"🎯 3 sany birmeňzeş miwäni tapyň!\n"
        f"🎫 Galan synanyşyk: <b>{attempts}</b>"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_scratch_reveal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kazı Kazan kartını aç"""
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split("_")[2])

    revealed = context.user_data.get('scratch_revealed', [])

    if revealed[idx]:
        return

    revealed[idx] = True
    context.user_data['scratch_revealed'] = revealed
    context.user_data['scratch_attempts'] -= 1

    attempts = context.user_data['scratch_attempts']
    cards = context.user_data['scratch_cards']

    await show_scratch_board(update, context)

    revealed_cards = [cards[i] for i, r in enumerate(revealed) if r]

    from collections import Counter
    counts = Counter(revealed_cards)

    won = False
    winning_fruit = None
    for fruit, count in counts.items():
        if count >= 3:
            won = True
            winning_fruit = fruit
            break

    if won or attempts == 0:
        await asyncio.sleep(1)

        user_id = query.from_user.id
        db = Database()

        if won:
            difficulty = context.user_data['scratch_difficulty']
            reward = Config.GAME_SETTINGS[f"scratch_{difficulty}"]["win_reward"]
            db.update_diamond(user_id, reward)

            context.user_data['scratch_revealed'] = [True] * 9
            await show_scratch_board(update, context)

            await asyncio.sleep(0.5)

            # Mesajları temizle ve oyunlar menüsüne dön - DÜZELTİLDİ
            await query.message.delete()
            
            # Yeni mesaj gönder
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    f"🎉 <b>GUTLAÝARYS!</b>\n\n"
                    f"🎰 3 sany {winning_fruit} tapdyňyz!\n"
                    f"💎 Gazanç: <b>{reward} diamond</b>"
                ),
                parse_mode="HTML"
            )
            
            await asyncio.sleep(2)
            await show_games_menu_message(context, query.message.chat_id)
            
        else:
            context.user_data['scratch_revealed'] = [True] * 9
            await show_scratch_board(update, context)

            await asyncio.sleep(0.5)

            # Mesajları temizle - DÜZELTİLDİ
            await query.message.delete()
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    f"😢 <b>Gynandyryjy...</b>\n\n"
                    f"🎫 Synanyşyklaryňyz gutardy!\n"
                    f"💪 Täzeden synanyşyň!"
                ),
                parse_mode="HTML"
            )
            
            await asyncio.sleep(2)
            await show_games_menu_message(context, query.message.chat_id)

async def show_games_menu_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Oyunlar menüsünü mesaj olarak göster"""
    text = (
        f"🎮 <b>Oýunlar</b>\n\n"
        f"🍎 <b>Kutudaki Elmayı Bul</b>\n"
        f"   • Bahasy: 2 💎\n"
        f"   • Gazanç: 5 💎\n\n"
        f"🎰 <b>Kazı Kazan (Kolay)</b>\n"
        f"   • Bahasy: 3 💎\n"
        f"   • Gazanç: 8 💎\n\n"
        f"🎰 <b>Kazı Kazan (Zor)</b>\n"
        f"   • Bahasy: 5 💎\n"
        f"   • Gazanç: 20 💎\n\n"
        f"🎡 <b>Çarkı Felek</b>\n"
        f"   • Bahasy: 4 💎\n"
        f"   • Gazanç: 0-15 💎\n\n"
        f"🎯 Oýun saýlaň!"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=get_games_keyboard()
    )

async def play_wheel_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Çarkı Felek oyunu - Geliştirilmiş animasyon"""
    query = update.callback_query
    user_id = query.from_user.id

    rewards = Config.GAME_SETTINGS["wheel"]["rewards"]
    weights = Config.GAME_SETTINGS["wheel"]["weights"]

    # Sonucu önceden seç
    result = random.choices(rewards, weights=weights)[0]

    await query.edit_message_text("🎡 <b>Çark taýýarlanýar...</b>", parse_mode="HTML")
    await asyncio.sleep(1)

    # Ödülleri göster
    rewards_text = "🎡 <b>Çarkdaky baýraklar:</b>\n\n"
    for reward in sorted(set(rewards), reverse=True):
        if reward > 0:
            rewards_text += f"💎 +{reward} diamond\n"
        elif reward == 0:
            rewards_text += f"❌ 0 diamond (boş)\n"
        else:
            rewards_text += f"⚠️ {reward} diamond (jeza)\n"

    await query.edit_message_text(rewards_text, parse_mode="HTML")
    await asyncio.sleep(2)

    # Çark dönüyor - Her ödül teker teker gösterilecek
    await query.edit_message_text("🎡 <b>Çark aýlanýar...</b>", parse_mode="HTML")
    await asyncio.sleep(0.5)

    # Animasyon - Ödüller teker teker geçiyor
    animation_rewards = [15, 10, 8, 5, 3, 0, -2, 15, 10, 8, 5, 3, 0]
    
    # Sonucu animasyonun sonuna ekle
    if result not in animation_rewards[-3:]:
        animation_rewards.append(result)
    
    for i, reward in enumerate(animation_rewards):
        if reward > 0:
            emoji = "💎"
            text = f"+{reward}"
        elif reward == 0:
            emoji = "❌"
            text = "0"
        else:
            emoji = "⚠️"
            text = f"{reward}"
        
        # Son 3 animasyonda yavaşla
        if i >= len(animation_rewards) - 3:
            sleep_time = 0.8
        elif i >= len(animation_rewards) - 6:
            sleep_time = 0.5
        else:
            sleep_time = 0.3
        
        await query.edit_message_text(
            f"🎡 <b>Çark aýlanýar...</b>\n\n"
            f"{'🔄 ' * (i % 3 + 1)}\n\n"
            f"<b>{emoji} {text}</b>",
            parse_mode="HTML"
        )
        await asyncio.sleep(sleep_time)

    # Çark duruyor
    await query.edit_message_text("🎡 <b>Çark haýallaýar...</b>", parse_mode="HTML")
    await asyncio.sleep(1)

    await query.edit_message_text("🎡 <b>Çark durýar...</b>", parse_mode="HTML")
    await asyncio.sleep(1)

    # Sonuç
    db = Database()

    if result > 0:
        db.update_diamond(user_id, result)
        emoji = "🎉"
        message = f"GUTLAÝARYS! +{result} diamond gazandyňyz!"
    elif result == 0:
        emoji = "😕"
        message = "Bu gezek zadyňyz çykmady!"
    else:
        db.update_diamond(user_id, result)
        emoji = "😢"
        message = f"Gynandyryjy! {result} diamond jeza aldyňyz!"

    await query.edit_message_text(
        f"{emoji} <b>{message}</b>\n\n"
        f"💎 Netije: <b>{'+' if result > 0 else ''}{result}</b> diamond",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎡 Täzeden oýnamak", callback_data="game_wheel"),
            InlineKeyboardButton("🔙 Oýunlar", callback_data="earn_games")
        ]])
    )

# ============================================================================
# ADMIN PANELİ
# ============================================================================

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panelini göster"""
    query = update.callback_query

    keyboard = [
        [InlineKeyboardButton("👥 Ulanyjylar", callback_data="admin_users")],
        [InlineKeyboardButton("🎮 Oýun sazlamalary", callback_data="admin_games")],
        [InlineKeyboardButton("🎟 Promo kod döret", callback_data="admin_promo")],
        [InlineKeyboardButton("📢 Sponsor kanal goş", callback_data="admin_add_sponsor")],
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📣 Ähline habar", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔙 Ana menä dön", callback_data="back_main")]
    ]

    await query.edit_message_text(
        "👑 <b>Admin Paneli</b>\n\nNäme etjek bolýaňyz?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcı yönetimi menüsü"""
    query = update.callback_query
    await query.answer()

    text = (
        "👥 <b>Ulanyjy dolandyryşy</b>\n\n"
        "Ulanyjy ID ýazyň:\n"
        "• Diamond goşmak üçin: /adddia 123456789 10\n"
        "• Diamond aýyrmak üçin: /remdia 123456789 5\n"
        "• Ulanyjy maglumatyny görmek: /userinfo 123456789"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Geri", callback_data="admin_back")
        ]])
    )

async def admin_games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oyun ayarları menüsü"""
    query = update.callback_query
    await query.answer()

    settings = Config.GAME_SETTINGS

    text = (
        "🎮 <b>Oýun Sazlamalary</b>\n\n"
        "<b>🍎 Kutudaki Elmayı Bul:</b>\n"
        f"   • Bahasy: {settings['apple_box']['cost']} 💎\n"
        f"   • Gazanç: {settings['apple_box']['win_reward']} 💎\n"
        f"   • Şans: {settings['apple_box']['win_chance']}%\n\n"
        "<b>🎰 Kazı Kazan (Kolay):</b>\n"
        f"   • Bahasy: {settings['scratch_easy']['cost']} 💎\n"
        f"   • Gazanç: {settings['scratch_easy']['win_reward']} 💎\n"
        f"   • Şans: {settings['scratch_easy']['win_chance']}%\n\n"
        "<b>🎰 Kazı Kazan (Zor):</b>\n"
        f"   • Bahasy: {settings['scratch_hard']['cost']} 💎\n"
        f"   • Gazanç: {settings['scratch_hard']['win_reward']} 💎\n"
        f"   • Şans: {settings['scratch_hard']['win_chance']}%\n\n"
        "<b>🎡 Çarkı Felek:</b>\n"
        f"   • Bahasy: {settings['wheel']['cost']} 💎\n\n"
        "Üýtgetmek üçin kod faýlyndaky Config.GAME_SETTINGS üýtgediň."
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Geri", callback_data="admin_back")
        ]])
    )

async def admin_promo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo kod oluşturma menüsü"""
    query = update.callback_query
    await query.answer()

    text = (
        "🎟 <b>Promo Kod Döretmek</b>\n\n"
        "Täze promo kod döretmek üçin:\n"
        "/createpromo KOD_ADY 10 100\n\n"
        "Mysaly: /createpromo BONUS2024 15 50\n"
        "(15 diamond berýär, 50 gezek ulanyp bolýar)"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Geri", callback_data="admin_back")
        ]])
    )

async def admin_add_sponsor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sponsor kanal ekleme"""
    query = update.callback_query
    await query.answer()

    text = (
        "📢 <b>Sponsor Kanal Goşmak</b>\n\n"
        "Täze sponsor kanal goşmak üçin:\n"
        "/addsponsor @kanal_ady Kanal ady 5\n\n"
        "Mysaly:\n"
        "/addsponsor @my_channel Meniň kanalym 3\n"
        "(3 diamond berýär)\n\n"
        "⚠️ Bot bu kanallarda admin bolmalydyr!"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Geri", callback_data="admin_back")
        ]])
    )

async def admin_broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toplu mesaj gönderme"""
    query = update.callback_query
    await query.answer()

    text = (
        "📢 <b>Ähline Habar Ýaýratmak</b>\n\n"
        "Ähli ulanyjylara habar ýaýratmak üçin:\n"
        "/broadcast Siziň habaryňyz\n\n"
        "⚠️ Bu ähli ulanyjylara iberiler!"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Geri", callback_data="admin_back")
        ]])
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin komutları"""
    user_id = update.effective_user.id

    if user_id not in Config.ADMIN_IDS:
        return

    command = update.message.text.split()[0][1:]

    # Diamond ekleme
    if command == "adddia":
        try:
            target_user = int(context.args[0])
            amount = int(context.args[1])

            db = Database()
            db.update_diamond(target_user, amount)

            await update.message.reply_text(
                f"✅ {target_user} ID-li ulanyjynyň hasabyna {amount} 💎 goşuldy!"
            )
        except:
            await update.message.reply_text("❌ Nädogry format! /adddia 123456789 10")

    # Diamond çıkarma
    elif command == "remdia":
        try:
            target_user = int(context.args[0])
            amount = int(context.args[1])

            db = Database()
            db.update_diamond(target_user, -amount)

            await update.message.reply_text(
                f"✅ {target_user} ID-li ulanyjynyň hasabyndan {amount} 💎 aýryldy!"
            )
        except:
            await update.message.reply_text("❌ Nädogry format! /remdia 123456789 5")

    # Kullanıcı bilgisi
    elif command == "userinfo":
        try:
            target_user = int(context.args[0])

            db = Database()
            user_data = db.get_user(target_user)

            if user_data:
                text = (
                    f"👤 <b>Ulanyjy Maglumat</b>\n\n"
                    f"🆔 ID: {user_data['user_id']}\n"
                    f"👤 Ulanyjy: @{user_data['username']}\n"
                    f"💎 Diamond: {user_data['diamond']}\n"
                    f"👥 Davetler: {user_data['referral_count']}\n"
                    f"💸 Çekilen: {user_data['total_withdrawn']}\n"
                    f"🚫 Ban: {'Hawa' if user_data['is_banned'] else 'Ýok'}"
                )
                await update.message.reply_text(text, parse_mode="HTML")
            else:
                await update.message.reply_text("❌ Ulanyjy tapylmady!")
        except:
            await update.message.reply_text("❌ Nädogry format! /userinfo 123456789")

    # Promo kod oluşturma
    elif command == "createpromo":
        try:
            code = context.args[0].upper()
            diamond = int(context.args[1])
            max_uses = int(context.args[2])

            db = Database()
            success = db.create_promo_code(code, diamond, max_uses)

            if success:
                await update.message.reply_text(
                    f"✅ Promo kod döredildi!\n\n"
                    f"🎟 Kod: <code>{code}</code>\n"
                    f"💎 Mukdar: {diamond}\n"
                    f"📢 Ulanyş sany: {max_uses}",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text("❌ Bu kod eýýäm bar!")
        except:
            await update.message.reply_text("❌ Nädogry format! /createpromo KOD 10 100")

    # Toplu mesaj
    elif command == "broadcast":
        try:
            message = " ".join(context.args)

            db = Database()
            users = db.get_all_user_ids()

            success = 0
            failed = 0

            status_msg = await update.message.reply_text("📢 Habarlar iberilýär...")

            for user_id in users:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"📢 <b>Habar:</b>\n\n{message}",
                        parse_mode="HTML"
                    )
                    success += 1
                    await asyncio.sleep(0.05)
                except:
                    failed += 1

            await status_msg.edit_text(
                f"✅ Habar ýaýradyldy!\n\n"
                f"✔ Üstünlikli: {success}\n"
                f"✗ Başartmady: {failed}"
            )
        except:
            await update.message.reply_text("❌ Nädogry format! /broadcast Siziň habaryňyz")

    # Sponsor kanal ekleme
    elif command == "addsponsor":
        try:
            channel_id = context.args[0]
            diamond = int(context.args[-1])
            channel_name = " ".join(context.args[1:-1])

            db = Database()
            success = db.add_sponsor_channel(channel_id, channel_name, diamond)

            if success:
                await update.message.reply_text(
                    f"✅ Sponsor kanal goşuldy!\n\n"
                    f"📢 Kanal: {channel_name}\n"
                    f"🆔 ID: <code>{channel_id}</code>\n"
                    f"💎 Mukdar: {diamond}\n\n"
                    f"⚠️ Bot bu kanalda admin bolmalydyr!",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text("❌ Ýalňyşlyk ýüze çykdy!")
        except:
            await update.message.reply_text(
                "❌ Nädogry format!\n"
                "/addsponsor @kanal_ady Kanal ady 5"
            )

    # Para çekme onaylama - DÜZELTİLDİ
    elif command == "approve":
        try:
            request_id = int(context.args[0])

            db = Database()
            request = db.get_withdrawal_request(request_id)

            if not request:
                await update.message.reply_text("❌ Talap tapylmady!")
                return

            if request['status'] == 'approved':
                await update.message.reply_text("❌ Bu talap eýýäm tassyklandy!")
                return

            # Kullanıcının elmaslarını çıkar
            db.update_diamond(request['user_id'], -request['diamond_amount'])
            
            # Toplam çekilen miktarı güncelle
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET total_withdrawn = total_withdrawn + %s
                WHERE user_id = %s
            """, (request['diamond_amount'], request['user_id']))
            conn.commit()
            conn.close()

            # Talebi onayla
            db.approve_withdrawal(request_id)

            await update.message.reply_text(
                f"✅ Talap tassyklandy!\n\n"
                f"🆔 Talap: {request_id}\n"
                f"👤 Ulanyjy: @{request['username']}\n"
                f"💎 Mukdar: {request['diamond_amount']}\n"
                f"💵 Manat: {request['manat_amount']:.1f} TMT\n\n"
                f"💰 Ulanyjynyň hasabyndan elmaslar aýryldy."
            )

            # Kullanıcıya bildir
            try:
                await context.bot.send_message(
                    chat_id=request['user_id'],
                    text=(
                        f"✅ <b>Para çekme tassyklandy!</b>\n\n"
                        f"🆔 Talap: <code>{request_id}</code>\n"
                        f"💎 Mukdar: {request['diamond_amount']} diamond\n"
                        f"💵 Manat: {request['manat_amount']:.1f} TMT\n\n"
                        f"💰 Pul ýakyn wagtda siziň hasabyňyza iberiler.\n"
                        f"📞 Admin size habarlaşar!"
                    ),
                    parse_mode="HTML"
                )
            except:
                pass

        except:
            await update.message.reply_text("❌ Nädogry format! /approve 1")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """İstatistikler"""
    query = update.callback_query
    await query.answer()

    db = Database()
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']

    cursor.execute("SELECT SUM(diamond) as total FROM users")
    total_diamonds = cursor.fetchone()['total'] or 0

    cursor.execute("SELECT SUM(total_withdrawn) as total FROM users")
    total_withdrawn = cursor.fetchone()['total'] or 0

    conn.close()

    text = (
        f"📊 <b>Bot Statistikasy</b>\n\n"
        f"👥 Jemi ulanyjylar: <b>{total_users}</b>\n"
        f"💎 Jemi diamond: <b>{total_diamonds}</b>\n"
        f"💸 Jemi çekilen: <b>{total_withdrawn}</b> diamond\n"
        f"💰 Manat görnüşinde: <b>{total_withdrawn / Config.DIAMOND_TO_MANAT:.2f}</b> TMT"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Geri", callback_data="admin_back")
        ]])
    )

async def admin_approve_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback ile para çekme onaylama - şu an kullanılmıyor"""
    pass

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Bot'u başlat"""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    application = Application.builder().token(Config.BOT_TOKEN).build()

    # Komutlar
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("adddia", admin_command))
    application.add_handler(CommandHandler("remdia", admin_command))
    application.add_handler(CommandHandler("userinfo", admin_command))
    application.add_handler(CommandHandler("createpromo", admin_command))
    application.add_handler(CommandHandler("broadcast", admin_command))
    application.add_handler(CommandHandler("addsponsor", admin_command))
    application.add_handler(CommandHandler("approve", admin_command))

    # Mesaj handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_promo_code_input))

    # Callback handlers
    application.add_handler(CallbackQueryHandler(handle_apple_choice, pattern="^apple_choice_"))
    application.add_handler(CallbackQueryHandler(handle_scratch_reveal, pattern="^scratch_reveal_"))
    application.add_handler(CallbackQueryHandler(start_game_play, pattern="^game_play_"))
    application.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Bot başladý...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
