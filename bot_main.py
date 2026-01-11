#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Diamond Bot - Oyun Oynayarak Para Kazan
Türkmen Dili | PostgreSQL | Modüler Yapı
Güncellenmiş Versiyon - İnaktivite Ceza Sistemi Eklendi
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
# YAPILANDIRMA - KOLAYCA DEĞİŞTİRİLEBİLİR AYARLAR
# ============================================================================

class Config:
    """Bot yapılandırması - Tüm ayarlar buradan yönetilir"""

    # ========== BOT AYARLARI ==========
    BOT_TOKEN = os.getenv("BOT_TOKEN", "8133082070:AAE1rRGxQ9_Qqx-LZW54WFuFuGEo9FZhhWc")
    ADMIN_IDS = [7172270461]  # Admin kullanıcı ID'leri

    # ========== VERİTABANI ==========
    DATABASE_URL = os.getenv("DATABASE_URL")

    # ========== DİAMOND SİSTEMİ ==========
    DIAMOND_TO_MANAT = 5.0  # 5 diamond = 1 manat
    MIN_WITHDRAW_DIAMOND = 50.0  # Minimum çekilebilir diamond
    MIN_REFERRAL_COUNT = 5  # Para çekmek için minimum referal sayısı

    # Para çekme seçenekleri
    WITHDRAW_OPTIONS = [50.0, 75.0, 100.0]

    # ========== REFERAL SİSTEMİ ==========
    REFERAL_REWARD = 0.5  # Referal çağıran kişiye verilecek diamond
    NEW_USER_BONUS = 3.0  # Yeni kullanıcıya verilecek başlangıç diamond

    # ========== İNAKTİVİTE CEZA SİSTEMİ - YENİ ==========
    INACTIVITY_TIME = 86400  # 24 saat (saniye cinsinden) - kullanıcı bu süre boyunca aktif değilse ceza alır
    INACTIVITY_PENALTY = -1.0  # İnaktivite cezası (diamond olarak)

    # ========== OYUN AYARLARI ==========
    # Not: cost = 0 ise oyun bedava, kazanırsa +win_reward, kaybederse -lose_penalty

    # Almayı Tap Oyunu
    APPLE_BOX_COST = 0.0  # Giriş ücreti (0 = bedava)
    APPLE_BOX_WIN_REWARD = 1.0  # Kazanınca alınan diamond
    APPLE_BOX_LOSE_PENALTY = -1.0  # Kaybedince düşen diamond
    APPLE_BOX_WIN_CHANCE = 40  # Kazanma şansı (%)

    # Lotereýa (Çeňil) - Kolay Scratch
    SCRATCH_EASY_COST = 0.0
    SCRATCH_EASY_WIN_REWARD = 1.0
    SCRATCH_EASY_LOSE_PENALTY = -1.0
    SCRATCH_EASY_WIN_CHANCE = 60  # %60 kazanma şansı

    # Lotereýa (Kyn) - Zor Scratch
    SCRATCH_HARD_COST = 0.0
    SCRATCH_HARD_WIN_REWARD = 3.0
    SCRATCH_HARD_LOSE_PENALTY = -1.0
    SCRATCH_HARD_WIN_CHANCE = 25  # %25 kazanma şansı

    # Şansly Aýlaw - Çarkıfelek
    WHEEL_COST = 0.0  # Her zaman bedava
    # Çarkıfelek ödülleri ve olasılıkları
    WHEEL_REWARDS = [0, 2, 4, 5, 6, 3, -2, -3]  # Olası sonuçlar
    WHEEL_WEIGHTS = [25, 10, 5, 4, 1, 8, 25, 25]  # Her sonucun çıkma olasılığı (ağırlık)

    # ========== BONUS AYARLARI ==========
    DAILY_BONUS_AMOUNT = 1.0  # Günlük bonus miktarı
    DAILY_BONUS_COOLDOWN = 86400  # 24 saat (saniye cinsinden)

    # ========== MİNİMUM BAKİYE KONTROLÜ ==========
    MIN_BALANCE_TO_PLAY = 0.0  # Oyun oynamak için minimum bakiye
    # Not: Oyunlar bedava olsa bile kullanıcının bakiyesi ekside olamaz

    # ========== SPONSOR TÜRÜ ==========
    SPONSOR_TYPE_REQUIRED = "required"  # /start için zorunlu kanallar
    SPONSOR_TYPE_TASK = "task"  # Günlük görev kanalları

# ============================================================================
# VERİTABANI YÖNETİMİ - PostgreSQL
# ============================================================================

class Database:
    """PostgreSQL veritabanı yöneticisi - Geliştirilmiş Versiyon"""

    def __init__(self):
        self.connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,
            Config.DATABASE_URL
        )
        self.init_db()
        self.migrate_database()

    def migrate_database(self):
        """Veritabanını yeni yapıya güncelle - Migration (Transaction Güvenli)"""
        conn = self.get_connection()

        try:
            print("🔄 Veritabanı güncelleniyor...")

            # Her işlem için ayrı cursor ve commit

            # 1. users.last_task_reset ekle
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE users ADD COLUMN last_task_reset BIGINT DEFAULT 0;")
                conn.commit()
                cursor.close()
                print("✅ users.last_task_reset eklendi")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print("ℹ️  users.last_task_reset zaten var")
                else:
                    print(f"⚠️  users.last_task_reset: {e}")

            # 2. users.last_activity ekle - YENİ
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE users ADD COLUMN last_activity BIGINT DEFAULT 0;")
                conn.commit()
                cursor.close()
                print("✅ users.last_activity eklendi")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print("ℹ️  users.last_activity zaten var")
                else:
                    print(f"⚠️  users.last_activity: {e}")

            # 3. sponsors.sponsor_type ekle
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE sponsors ADD COLUMN sponsor_type TEXT DEFAULT 'task';")
                conn.commit()
                cursor.close()
                print("✅ sponsors.sponsor_type eklendi")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print("ℹ️  sponsors.sponsor_type zaten var")
                else:
                    print(f"⚠️  sponsors.sponsor_type: {e}")

            # 4. sponsors.bot_is_admin ekle
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE sponsors ADD COLUMN bot_is_admin BOOLEAN DEFAULT TRUE;")
                conn.commit()
                cursor.close()
                print("✅ sponsors.bot_is_admin eklendi")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print("ℹ️  sponsors.bot_is_admin zaten var")
                else:
                    print(f"⚠️  sponsors.bot_is_admin: {e}")

            # 5. users diamond NUMERIC
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE users ALTER COLUMN diamond TYPE NUMERIC(10, 2);")
                conn.commit()
                cursor.close()
                print("✅ users.diamond NUMERIC yapıldı")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  users.diamond NUMERIC: zaten doğru tipte")

            # 6. users total_withdrawn NUMERIC
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE users ALTER COLUMN total_withdrawn TYPE NUMERIC(10, 2);")
                conn.commit()
                cursor.close()
                print("✅ users.total_withdrawn NUMERIC yapıldı")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  users.total_withdrawn NUMERIC: zaten doğru tipte")

            # 7. sponsors diamond_reward NUMERIC
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE sponsors ALTER COLUMN diamond_reward TYPE NUMERIC(10, 2);")
                conn.commit()
                cursor.close()
                print("✅ sponsors.diamond_reward NUMERIC yapıldı")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  sponsors.diamond_reward NUMERIC: zaten doğru tipte")

            # 8. promo_codes diamond_reward NUMERIC
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE promo_codes ALTER COLUMN diamond_reward TYPE NUMERIC(10, 2);")
                conn.commit()
                cursor.close()
                print("✅ promo_codes.diamond_reward NUMERIC yapıldı")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  promo_codes.diamond_reward NUMERIC: zaten doğru tipte")

            # 9. withdrawal_requests diamond_amount NUMERIC
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE withdrawal_requests ALTER COLUMN diamond_amount TYPE NUMERIC(10, 2);")
                conn.commit()
                cursor.close()
                print("✅ withdrawal_requests.diamond_amount NUMERIC yapıldı")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  withdrawal_requests.diamond_amount NUMERIC: zaten doğru tipte")

            # 10. withdrawal_requests manat_amount NUMERIC
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE withdrawal_requests ALTER COLUMN manat_amount TYPE NUMERIC(10, 2);")
                conn.commit()
                cursor.close()
                print("✅ withdrawal_requests.manat_amount NUMERIC yapıldı")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  withdrawal_requests.manat_amount NUMERIC: zaten doğru tipte")

            # 11. NULL değerleri güncelle - users.last_task_reset
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users
                    SET last_task_reset = EXTRACT(EPOCH FROM NOW())::BIGINT
                    WHERE last_task_reset IS NULL OR last_task_reset = 0;
                """)
                conn.commit()
                cursor.close()
                print("✅ users.last_task_reset NULL değerleri güncellendi")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  users.last_task_reset güncelleme: {e}")

            # 12. NULL değerleri güncelle - users.last_activity - YENİ
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users
                    SET last_activity = EXTRACT(EPOCH FROM NOW())::BIGINT
                    WHERE last_activity IS NULL OR last_activity = 0;
                """)
                conn.commit()
                cursor.close()
                print("✅ users.last_activity NULL değerleri güncellendi")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  users.last_activity güncelleme: {e}")

            # 13. NULL değerleri güncelle - sponsors.sponsor_type
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sponsors
                    SET sponsor_type = 'task'
                    WHERE sponsor_type IS NULL;
                """)
                conn.commit()
                cursor.close()
                print("✅ sponsors.sponsor_type NULL değerleri güncellendi")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  sponsors.sponsor_type güncelleme: {e}")

            # 14. NULL değerleri güncelle - sponsors.bot_is_admin
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sponsors
                    SET bot_is_admin = TRUE
                    WHERE bot_is_admin IS NULL;
                """)
                conn.commit()
                cursor.close()
                print("✅ sponsors.bot_is_admin NULL değerleri güncellendi")
            except Exception as e:
                conn.rollback()
                print(f"ℹ️  sponsors.bot_is_admin güncelleme: {e}")

            print("✅ Veritabanı migration tamamlandı!")

        except Exception as e:
            print(f"❌ Genel migration hatası: {e}")
            logging.error(f"Migration error: {e}")
        finally:
            self.return_connection(conn)


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

        # Kullanıcılar tablosu - diamond artık NUMERIC (ondalıklı)
        # YENİ: last_activity eklendi
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                diamond NUMERIC(10, 2) DEFAULT 0.0,
                total_withdrawn NUMERIC(10, 2) DEFAULT 0.0,
                referral_count INTEGER DEFAULT 0,
                referred_by BIGINT,
                last_bonus_time BIGINT DEFAULT 0,
                joined_date BIGINT,
                is_banned BOOLEAN DEFAULT FALSE,
                last_task_reset BIGINT DEFAULT 0,
                last_activity BIGINT DEFAULT 0
            )
        """)

        # Promo kodlar - reward artık NUMERIC
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                diamond_reward NUMERIC(10, 2),
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

        # Sponsor kanallar/gruplar - YENİ: sponsor_type eklendi
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sponsors (
                sponsor_id SERIAL PRIMARY KEY,
                channel_id TEXT UNIQUE,
                channel_name TEXT,
                diamond_reward NUMERIC(10, 2),
                sponsor_type TEXT DEFAULT 'task',
                is_active BOOLEAN DEFAULT TRUE,
                created_date BIGINT,
                bot_is_admin BOOLEAN DEFAULT TRUE
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

        # Para çekme talepleri - diamond NUMERIC
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                request_id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                diamond_amount NUMERIC(10, 2),
                manat_amount NUMERIC(10, 2),
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
        if user:
            user_dict = dict(user)
            # NUMERIC değerleri float'a çevir
            user_dict['diamond'] = float(user_dict['diamond'])
            user_dict['total_withdrawn'] = float(user_dict['total_withdrawn'])
            return user_dict
        return None

    def create_user(self, user_id: int, username: str, referred_by: Optional[int] = None):
        """Yeni kullanıcı oluştur - Geliştirilmiş referal sistemi"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            current_time = int(time.time())
            # Yeni kullanıcıya başlangıç bonusu ver
            # YENİ: last_activity eklendi
            cursor.execute("""
                INSERT INTO users (user_id, username, diamond, referred_by, joined_date, last_task_reset, last_activity)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, username, Config.NEW_USER_BONUS, referred_by, current_time, current_time, current_time))

            # Eğer referal varsa, referansı çağıran kişiye bonus ver
            if referred_by:
                cursor.execute("""
                    UPDATE users
                    SET diamond = diamond + %s, referral_count = referral_count + 1
                    WHERE user_id = %s
                """, (Config.REFERAL_REWARD, referred_by))

            conn.commit()
        except Exception as e:
            conn.rollback()
            logging.error(f"Kullanıcı oluşturma hatası: {e}")
        finally:
            cursor.close()
            self.return_connection(conn)

    def update_diamond(self, user_id: int, amount: float):
        """Diamond güncelle - Artık ondalıklı sayıları destekler"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET diamond = diamond + %s WHERE user_id = %s
        """, (amount, user_id))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def get_user_balance(self, user_id: int) -> float:
        """Kullanıcının mevcut bakiyesini getir"""
        user = self.get_user(user_id)
        return user['diamond'] if user else 0.0

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

    # ========== AKTİVİTE SİSTEMİ - YENİ ==========

    def update_last_activity(self, user_id: int):
        """Kullanıcının son aktivite zamanını güncelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET last_activity = %s WHERE user_id = %s
        """, (int(time.time()), user_id))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def get_inactive_users(self) -> List[Dict]:
        """İnaktif kullanıcıları getir (INACTIVITY_TIME süresi boyunca aktif olmayanlar)"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        current_time = int(time.time())
        threshold_time = current_time - Config.INACTIVITY_TIME

        cursor.execute("""
            SELECT * FROM users
            WHERE is_banned = FALSE
            AND last_activity < %s
            AND last_activity > 0
        """, (threshold_time,))

        users = cursor.fetchall()
        cursor.close()
        self.return_connection(conn)

        result = []
        for u in users:
            user_dict = dict(u)
            user_dict['diamond'] = float(user_dict['diamond'])
            user_dict['total_withdrawn'] = float(user_dict['total_withdrawn'])
            result.append(user_dict)
        return result

    # ========== PROMO KOD İŞLEMLERİ ==========

    def create_promo_code(self, code: str, diamond_reward: float, max_uses: int):
        """Promo kod oluştur - Artık ondalıklı ödül destekler"""
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
            logging.error(f"Promo kod oluşturma hatası: {e}")
            return False
        finally:
            cursor.close()
            self.return_connection(conn)

    def use_promo_code(self, code: str, user_id: int) -> Optional[float]:
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
        reward = float(promo['diamond_reward'])
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
        result = []
        for p in promos:
            promo_dict = dict(p)
            promo_dict['diamond_reward'] = float(promo_dict['diamond_reward'])
            result.append(promo_dict)
        return result

    def delete_promo_code(self, code: str):
        """Promo kod sil"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM promo_codes WHERE code = %s", (code,))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    # ========== SPONSOR İŞLEMLERİ - YENİ GELİŞTİRİLMİŞ ==========

    def add_sponsor(self, channel_id: str, channel_name: str, diamond_reward: float, sponsor_type: str = "task"):
        """Sponsor kanal/grup ekle - YENİ: sponsor_type parametresi eklendi"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO sponsors (channel_id, channel_name, diamond_reward, sponsor_type, created_date)
                VALUES (%s, %s, %s, %s, %s)
            """, (channel_id, channel_name, diamond_reward, sponsor_type, int(time.time())))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logging.error(f"Sponsor ekleme hatası: {e}")
            return False
        finally:
            cursor.close()
            self.return_connection(conn)

    def get_sponsors_by_type(self, sponsor_type: str) -> List[Dict]:
        """Belirli türdeki sponsorları getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM sponsors
            WHERE is_active = TRUE AND sponsor_type = %s
            ORDER BY created_date ASC
        """, (sponsor_type,))
        sponsors = cursor.fetchall()
        cursor.close()
        self.return_connection(conn)
        result = []
        for s in sponsors:
            sponsor_dict = dict(s)
            sponsor_dict['diamond_reward'] = float(sponsor_dict['diamond_reward'])
            result.append(sponsor_dict)
        return result

    def get_required_channels(self) -> List[Dict]:
        """Zorunlu takip edilmesi gereken kanalları getir"""
        return self.get_sponsors_by_type(Config.SPONSOR_TYPE_REQUIRED)

    def get_task_sponsors(self) -> List[Dict]:
        """Günlük görev sponsorlarını getir"""
        return self.get_sponsors_by_type(Config.SPONSOR_TYPE_TASK)

    def get_active_sponsors(self) -> List[Dict]:
        """Tüm aktif sponsorları getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT * FROM sponsors WHERE is_active = TRUE
            ORDER BY created_date ASC
        """)
        sponsors = cursor.fetchall()
        cursor.close()
        self.return_connection(conn)
        result = []
        for s in sponsors:
            sponsor_dict = dict(s)
            sponsor_dict['diamond_reward'] = float(sponsor_dict['diamond_reward'])
            result.append(sponsor_dict)
        return result

    def get_user_next_sponsor(self, user_id: int) -> Optional[Dict]:
        """Kullanıcının henüz tamamlamadığı bir sonraki task sponsorunu getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT s.* FROM sponsors s
            WHERE s.is_active = TRUE
            AND s.sponsor_type = %s
            AND s.sponsor_id NOT IN (
                SELECT sponsor_id FROM user_sponsors WHERE user_id = %s
            )
            ORDER BY s.created_date ASC
            LIMIT 1
        """, (Config.SPONSOR_TYPE_TASK, user_id))
        sponsor = cursor.fetchone()
        cursor.close()
        self.return_connection(conn)
        if sponsor:
            sponsor_dict = dict(sponsor)
            sponsor_dict['diamond_reward'] = float(sponsor_dict['diamond_reward'])
            return sponsor_dict
        return None

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

    def update_sponsor_bot_admin_status(self, sponsor_id: int, is_admin: bool):
        """Sponsorda botun admin durumunu güncelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE sponsors SET bot_is_admin = %s WHERE sponsor_id = %s
        """, (is_admin, sponsor_id))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def get_sponsor_by_id(self, sponsor_id: int) -> Optional[Dict]:
        """ID'ye göre sponsor getir"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM sponsors WHERE sponsor_id = %s", (sponsor_id,))
        sponsor = cursor.fetchone()
        cursor.close()
        self.return_connection(conn)
        if sponsor:
            sponsor_dict = dict(sponsor)
            sponsor_dict['diamond_reward'] = float(sponsor_dict['diamond_reward'])
            return sponsor_dict
        return None

    def reset_user_daily_tasks(self, user_id: int):
        """Kullanıcının günlük görevlerini sıfırla"""
        conn = self.get_connection()
        cursor = conn.cursor()
        # Sadece task tipindeki sponsorları sıfırla
        cursor.execute("""
            DELETE FROM user_sponsors
            WHERE user_id = %s
            AND sponsor_id IN (
                SELECT sponsor_id FROM sponsors WHERE sponsor_type = %s
            )
        """, (user_id, Config.SPONSOR_TYPE_TASK))
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

    def create_withdrawal_request(self, user_id: int, username: str, diamond: float, manat: float):
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
        if request:
            req_dict = dict(request)
            req_dict['diamond_amount'] = float(req_dict['diamond_amount'])
            req_dict['manat_amount'] = float(req_dict['manat_amount'])
            return req_dict
        return None

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
        result = []
        for r in requests:
            req_dict = dict(r)
            req_dict['diamond_amount'] = float(req_dict['diamond_amount'])
            req_dict['manat_amount'] = float(req_dict['manat_amount'])
            result.append(req_dict)
        return result

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
            "total_diamonds": float(total_diamonds),
            "total_withdrawn": float(total_withdrawn)
        }

# Global database instance
db = Database()

# ============================================================================
# YARDIMCI FONKSIYONLAR
# ============================================================================

async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, List[str]]:
    """
    Kullanıcının tüm zorunlu kanalları takip edip etmediğini kontrol et
    Returns: (is_member, not_joined_channels)
    """
    required_channels = db.get_required_channels()
    not_joined = []

    for sponsor in required_channels:
        try:
            member = await context.bot.get_chat_member(sponsor['channel_id'], user_id)
            if member.status in ["left", "kicked"]:
                not_joined.append(sponsor['channel_name'])
        except Exception as e:
            logging.error(f"Kanal kontrolü hatası {sponsor['channel_id']}: {e}")
            not_joined.append(sponsor['channel_name'])

    return (len(not_joined) == 0, not_joined)

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

async def check_bot_admin_in_sponsor(sponsor_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Botun sponsor kanalında admin olup olmadığını kontrol et"""
    sponsor = db.get_sponsor_by_id(sponsor_id)
    if not sponsor:
        return False

    try:
        bot_member = await context.bot.get_chat_member(sponsor['channel_id'], context.bot.id)
        is_admin = bot_member.status in ["administrator", "creator"]

        # Durumu veritabanında güncelle
        if sponsor['bot_is_admin'] != is_admin:
            db.update_sponsor_bot_admin_status(sponsor_id, is_admin)

            # Eğer bot admin değilse, admin'e bildirim gönder
            if not is_admin:
                for admin_id in Config.ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=(
                                f"⚠️ <b>DİKKAT!</b>\n\n"
                                f"Bot artık bu kanalda admin değil:\n"
                                f"📢 {sponsor['channel_name']}\n"
                                f"🆔 <code>{sponsor['channel_id']}</code>\n\n"
                                f"‼️ Sponsor sisteminin düzgün çalışması için botu admin yapın!"
                            ),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logging.error(f"Admin bildirim hatası: {e}")

        return is_admin
    except Exception as e:
        logging.error(f"Bot admin kontrolü hatası: {e}")
        db.update_sponsor_bot_admin_status(sponsor_id, False)
        return False

def can_play_game(user_balance: float) -> bool:
    """Kullanıcının oyun oynayıp oynayamayacağını kontrol et"""
    # Oyunlar bedava ama bakiye 0'ın altına inemez
    return user_balance >= Config.MIN_BALANCE_TO_PLAY

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
        [InlineKeyboardButton("🎰 Lotereýa (Çeňil)", callback_data="game_scratch_easy")],
        [InlineKeyboardButton("🎰 Lotereýa (Kyn)", callback_data="game_scratch_hard")],
        [InlineKeyboardButton("🎡 Şansly Aýlaw", callback_data="game_wheel")],
        [InlineKeyboardButton("🔙 Yza gaýt", callback_data="menu_earn")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ============================================================================
# AKTİVİTE KONTROLÜ - YENİ SİSTEM
# ============================================================================

async def check_and_penalize_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    """İnaktif kullanıcıları kontrol et ve cezalandır - BACKGROUND TASK"""
    try:
        inactive_users = db.get_inactive_users()

        for user in inactive_users:
            user_id = user['user_id']
            balance = user['diamond']

            # Kullanıcının bakiyesi 0 veya eksi mi kontrol et
            if balance <= 0:
                # Sadece uyarı mesajı gönder
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⚠️ <b>Aktiwlik ýok!</b>\n\n"
                            f"Siz 24 sagat bäri boty ulanmadyňyz!\n\n"
                            f"💎 Balansyňyz: <b>{balance:.1f} diamond</b>\n\n"
                            f"📌 <b>Belllik:</b> Bakiýeňiz 0-dan az bolansoň, "
                            f"aktiwlik bolmasa diňe duýduryş alýarsyňyz.\n\n"
                            f"🎮 Bot bilen işjeň boluň:\n"
                            f"• Oýun oýnaň\n"
                            f"• Zadanýalary ýerine ýetiriň\n"
                            f"• Bonus alyň\n\n"
                            f"Eger işjeň bolmasaňyz, indiki gezek jeza alyp bilersiňiz!"
                        ),
                        parse_mode="HTML"
                    )

                    # Aktivite zamanını güncelle (bir sonraki kontrol için)
                    db.update_last_activity(user_id)

                except Exception as e:
                    logging.error(f"Uyarı mesajı gönderilemedi {user_id}: {e}")
            else:
                # Bakiye pozitif - ceza uygula
                penalty = Config.INACTIVITY_PENALTY
                db.update_diamond(user_id, penalty)

                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⚠️ <b>Aktiwlik ýok - JEZA!</b>\n\n"
                            f"Siz 24 sagat bäri boty ulanmadyňyz!\n\n"
                            f"💎 Jeza: <b>{penalty} diamond</b>\n"
                            f"💰 Täze balansyňyz: <b>{balance + penalty:.1f} diamond</b>\n\n"
                            f"🎮 <b>Jeza almazlyk üçin:</b>\n"
                            f"• Her gün boty açyň\n"
                            f"• Oýunlary oýnaň\n"
                            f"• Zadanýalary ýerine ýetiriň\n"
                            f"• Bonus alyň\n\n"
                            f"📊 Işjeň boluň we diamond gazanyň!"
                        ),
                        parse_mode="HTML"
                    )

                    # Aktivite zamanını güncelle
                    db.update_last_activity(user_id)

                except Exception as e:
                    logging.error(f"Ceza mesajı gönderilemedi {user_id}: {e}")

        logging.info(f"İnaktivite kontrolü tamamlandı. {len(inactive_users)} kullanıcı işlendi.")

    except Exception as e:
        logging.error(f"İnaktivite kontrolü hatası: {e}")

# ============================================================================
# BOT KOMUTLARI
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start komutu - Geliştirilmiş sponsor kontrolü"""
    user = update.effective_user

    # Aktivite güncelle - YENİ
    db.update_last_activity(user.id)

    # Davet linki kontrolü
    referred_by = None
    if context.args:
        try:
            referred_by = int(context.args[0])
        except:
            pass

    # Zorunlu kanal takibi kontrolü
    is_member, not_joined = await check_channel_membership(user.id, context)

    if not is_member:
        # Takip edilmesi gereken kanalları göster
        required_channels = db.get_required_channels()

        keyboard = []
        for sponsor in required_channels:
            keyboard.append([
                InlineKeyboardButton(
                    f"📢 {sponsor['channel_name']}",
                    url=f"https://t.me/{sponsor['channel_id'].replace('@', '')}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "✅ Ählisinä Agza Boldum",
                callback_data=f"check_membership_{referred_by if referred_by else 0}"
            )
        ])

        await update.message.reply_text(
            f"🎮 <b>Hoş geldiňiz!</b>\n\n"
            f"🎉 Boty ulanmak üçin aşakdaky kanallara agza boluň:\n\n"
            f"⚠️ Her birini açyň we agza boluň, soňra 'Ählisinä Agza Boldum' düwmesine basyň!",
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
            f"💎 Başlangyç bonusy: <b>{Config.NEW_USER_BONUS} diamond</b>\n"
        )

        if referred_by:
            welcome_msg += f"🎁 Sizi çagyran adama hem <b>{Config.REFERAL_REWARD} diamond</b> berildi!\n"

            try:
                referrer_data = db.get_user(referred_by)
                if referrer_data:
                    await context.bot.send_message(
                        chat_id=referred_by,
                        text=(
                            f"🎉 <b>Täze Referal!</b>\n\n"
                            f"👤 @{user.username or user.first_name} siziň referalyňyz bilen bota goşuldy!\n"
                            f"💎 Bonus: <b>+{Config.REFERAL_REWARD} diamond</b>\n\n"
                            f"👥 Jemi referalyňyz: <b>{referrer_data['referral_count'] + 1}</b>"
                        ),
                        parse_mode="HTML"
                    )
            except Exception as e:
                logging.error(f"Duýdyryş ugradylmady: {e}")

        await update.message.reply_text(welcome_msg, parse_mode="HTML")

    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ana menüyü göster"""
    user = update.effective_user

    # Aktivite güncelle - YENİ
    db.update_last_activity(user.id)

    user_data = db.get_user(user.id)

    # Eğer kullanıcı yoksa, oluştur
    if not user_data:
        db.create_user(user.id, user.username or "noname")
        user_data = db.get_user(user.id)

    text = (
        f"🎮 <b>Diamond Labs - Oýun oýnap pul gazanyň!</b>\n\n"
        f"💎 Siziň balansynyz: <b>{user_data['diamond']:.1f} diamond</b>\n\n"
        f"🎯 Oýunlar oýnaň, bonus gazanyň we hakyky pul alyň!\n"
        f"💰 {Config.DIAMOND_TO_MANAT} diamond = 1 manat\n\n"
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
    from bot_admin import admin_command, handle_mass_post

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

    # TOPLU POST HANDLER (ÖNCE)
    application.add_handler(MessageHandler(
        (filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
        handle_mass_post
    ))

    # Message handlers (promo kod girişi ve toplu post için)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_promo_code_input
    ))

    # Admin için toplu post handler'ı ekle
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        handle_mass_post
    ))

    # İNAKTİVİTE KONTROL JOB - YENİ
    # Her 6 saatte bir inaktif kullanıcıları kontrol et
    job_queue = application.job_queue
    job_queue.run_repeating(
        check_and_penalize_inactive_users,
        interval=21600,  # 6 saat (6 * 60 * 60)
        first=60  # İlk çalıştırma 60 saniye sonra
    )

    print("🤖 Bot başlady...")
    print(f"⏰ İnaktivite kontrolü aktif: {Config.INACTIVITY_TIME} saniye ({Config.INACTIVITY_TIME/3600:.1f} saat)")
    print(f"💎 İnaktivite cezası: {Config.INACTIVITY_PENALTY} diamond")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
