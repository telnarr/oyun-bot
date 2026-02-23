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
    # Hassas bilgiler yalnızca .env dosyasından okunur
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "7172270461").split(",") if x.strip()]

    # ========== VERİTABANI ==========
    # DATABASE_URL yalnızca .env'den gelir — fallback yok
    DATABASE_URL = os.getenv("DATABASE_URL")

    # ========== DİAMOND SİSTEMİ ==========
    DIAMOND_TO_MANAT = 3.0          # 3 diamond = 1 manat
    MIN_WITHDRAW_DIAMOND = 30.0     # Alt limit: 30 diamond (10 manat)
    MIN_REFERRAL_COUNT = 5          # Para çekmek için minimum referal sayısı

    # Para çekme seçenekleri
    WITHDRAW_OPTIONS = [30.0]

    # ========== REFERAL SİSTEMİ ==========
    REFERAL_REWARD = 1.5            # Referali çağırana verilen diamond
    REFERAL_MIN_GAMES = 5          # Ödül aktive olmak için davet edilen kişinin oynaması gereken oyun sayısı (anti-spam)
    NEW_USER_BONUS = 1.5            # Yeni kullanıcıya verilen başlangıç bonusu

    # ========== İNAKTİVİTE CEZA SİSTEMİ ==========
    INACTIVITY_TIME = 86400         # 24 saat (saniye)
    INACTIVITY_PENALTY = -1.0       # İnaktivite cezası (diamond)

    # ========== GÜNLÜK KAZANÇ LİMİTİ ==========
    DAILY_EARN_CAP = 25.0           # Kullanıcının günde kazanabileceği maksimum diamond (0 = sınırsız)

    # ========== KASA HAVUZU (RTP) KONTROLÜ ==========
    # Toplam dağıtılan / toplam yatırılan > RTP_THRESHOLD ise kazanma ihtimallerini düşür
    RTP_THRESHOLD = 0.90            # %90 RTP eşiği
    RTP_WIN_CHANCE_REDUCTION = 10   # Eşik aşıldığında kazanma ihtimalinden düşülecek yüzde puanı

    # ========== OYUN AYARLARI ==========
    # Sabit kayıp miktarı tüm oyunlar için 0.5 diamond
    FIXED_LOSE_PENALTY = -0.5

    # Almayı Tap Oyunu
    APPLE_BOX_COST = 0.0
    APPLE_BOX_WIN_REWARD = 1.0
    APPLE_BOX_LOSE_PENALTY = -0.5
    APPLE_BOX_WIN_CHANCE = 40       # %40 (RTP havuzuna göre dinamik)

    # Lotereýa (Çeňil) - Kolay Scratch
    SCRATCH_EASY_COST = 0.0
    SCRATCH_EASY_WIN_REWARD = 1.0
    SCRATCH_EASY_LOSE_PENALTY = -0.5
    SCRATCH_EASY_WIN_CHANCE = 60

    # Lotereýa (Kyn) - Zor Scratch
    SCRATCH_HARD_COST = 0.0
    SCRATCH_HARD_WIN_REWARD = 2.0
    SCRATCH_HARD_LOSE_PENALTY = -0.5
    SCRATCH_HARD_WIN_CHANCE = 25

    # Şansly Aýlaw - Çarkıfelek
    WHEEL_COST = 0.0
    WHEEL_REWARDS = [-2, -1, 0, 1, 2, 3, 4, 5, 10]
    WHEEL_WEIGHTS = [28, 32, 15, 12, 6, 3, 2, 1.5, 0.5]

    # ========== ZAR OYUNU ==========
    DICE_WIN_MULTIPLIER = 1.8       # Kazanınca yatırdığının 1.8 katını al (%10 kasa avantajı)
    DICE_LOSE_PENALTY = -0.5        # Kaybedince sabit 0.5 diamond düşer

    # ========== SLOT OYUNU ==========
    SLOT_CHAT_ID = os.getenv("SLOT_CHAT_ID", "-1002550606779")
    SLOT_LOSE_PENALTY = -0.5        # Sabit kayıp 0.5 diamond
    SLOT_WIN_CHANCE = 12            # Temel kazanma şansı (RTP'ye göre dinamik)

    # Slot kombinasyonları: (sembol_listesi, ödül)
    SLOT_COMBINATIONS = [
        (["🍒", "🍒", "🍒"], 1.0),   # Kiraz üçlüsü
        (["🍋", "🍋", "🍋"], 1.5),   # Limon üçlüsü
        (["7️⃣", "7️⃣", "7️⃣"], 5.0), # Jackpot 777
    ]
    SLOT_NEAR_MISS_REWARD = 0.1     # 2 aynı + 1 farklı → teselli ödülü (bakiyeden -0.5 hâlâ düşer)

    # ========== BONUS AYARLARI ==========
    DAILY_BONUS_AMOUNT = 1.0
    DAILY_BONUS_COOLDOWN = 86400    # 24 saat

    # ========== MİNİMUM BAKİYE KONTROLÜ ==========
    MIN_BALANCE_TO_PLAY = 1.0

    # ========== SPONSOR TÜRÜ ==========
    SPONSOR_TYPE_REQUIRED = "required"
    SPONSOR_TYPE_TASK = "task"

# ============================================================================
# VERİTABANI YÖNETİMİ - PostgreSQL
# ============================================================================

class Database:
    """PostgreSQL veritabanı yöneticisi - Asenkron uyumlu ThreadedConnectionPool"""

    def __init__(self):
        self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
            2, 20,
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

            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS daily_stats (
                        user_id BIGINT,
                        stat_date DATE,
                        daily_diamonds_earned NUMERIC(10, 2) DEFAULT 0.0,
                        daily_referrals_count INTEGER DEFAULT 0,
                        daily_withdrawn NUMERIC(10, 2) DEFAULT 0.0,
                        PRIMARY KEY (user_id, stat_date)
                    )
                """)
                conn.commit()
                cursor.close()
                print("✅ daily_stats tablosu oluşturuldu/kontrol edildi")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower():
                    print("ℹ️  daily_stats tablosu zaten var")
                else:
                    print(f"⚠️  daily_stats: {e}")



            # 15. withdrawal_requests.phone_number ekle
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE withdrawal_requests ADD COLUMN phone_number TEXT DEFAULT '';")
                conn.commit()
                cursor.close()
                print("✅ withdrawal_requests.phone_number eklendi")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print("ℹ️  withdrawal_requests.phone_number zaten var")
                else:
                    print(f"⚠️  withdrawal_requests.phone_number: {e}")

            # 16. users.game_count ekle (referral anti-spam için)
            try:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE users ADD COLUMN game_count INTEGER DEFAULT 0;")
                conn.commit()
                cursor.close()
                print("✅ users.game_count eklendi")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print("ℹ️  users.game_count zaten var")
                else:
                    print(f"⚠️  users.game_count: {e}")

            # 17. pending_referral_rewards tablosu (anti-spam referral ödemeleri)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pending_referral_rewards (
                        id SERIAL PRIMARY KEY,
                        referrer_id BIGINT,
                        referred_id BIGINT,
                        reward NUMERIC(10, 2),
                        created_date BIGINT,
                        paid BOOLEAN DEFAULT FALSE,
                        UNIQUE(referrer_id, referred_id)
                    )
                """)
                conn.commit()
                cursor.close()
                print("✅ pending_referral_rewards tablosu oluşturuldu")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower():
                    print("ℹ️  pending_referral_rewards tablosu zaten var")
                else:
                    print(f"⚠️  pending_referral_rewards: {e}")

            # 18. rtp_pool tablosu (kasa havuzu takibi)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rtp_pool (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        total_wagered NUMERIC(14, 4) DEFAULT 0.0,
                        total_paid_out NUMERIC(14, 4) DEFAULT 0.0,
                        CHECK (id = 1)
                    )
                """)
                cursor.execute("""
                    INSERT INTO rtp_pool (id, total_wagered, total_paid_out)
                    VALUES (1, 0, 0)
                    ON CONFLICT (id) DO NOTHING
                """)
                conn.commit()
                cursor.close()
                print("✅ rtp_pool tablosu oluşturuldu/kontrol edildi")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower():
                    print("ℹ️  rtp_pool tablosu zaten var")
                else:
                    print(f"⚠️  rtp_pool: {e}")

            # 19. suspicious_activities tablosu (şüpheli aktivite loglama)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS suspicious_activities (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        activity_type TEXT,
                        details TEXT,
                        detected_at BIGINT
                    )
                """)
                conn.commit()
                cursor.close()
                print("✅ suspicious_activities tablosu oluşturuldu")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower():
                    print("ℹ️  suspicious_activities tablosu zaten var")
                else:
                    print(f"⚠️  suspicious_activities: {e}")

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

        # Kullanıcılar tablosu
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
                last_activity BIGINT DEFAULT 0,
                game_count INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS slot_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                result TEXT,
                reward NUMERIC(10, 2),
                play_date BIGINT
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

        # Para çekme talepleri - diamond NUMERIC + telefon numarası
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                request_id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                diamond_amount NUMERIC(10, 2),
                manat_amount NUMERIC(10, 2),
                request_date BIGINT,
                status TEXT DEFAULT 'pending',
                processed_date BIGINT,
                phone_number TEXT DEFAULT ''
            )
        """)

                # init_db metodunda diğer tabloların altına ekleyin:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                user_id BIGINT,
                stat_date DATE,
                daily_diamonds_earned NUMERIC(10, 2) DEFAULT 0.0,
                daily_referrals_count INTEGER DEFAULT 0,
                daily_withdrawn NUMERIC(10, 2) DEFAULT 0.0,
                PRIMARY KEY (user_id, stat_date)
            )
        """)

        # Bekleyen referral ödülleri (anti-spam)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_referral_rewards (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT,
                referred_id BIGINT,
                reward NUMERIC(10, 2),
                created_date BIGINT,
                paid BOOLEAN DEFAULT FALSE,
                UNIQUE(referrer_id, referred_id)
            )
        """)

        # RTP havuz takibi
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rtp_pool (
                id INTEGER PRIMARY KEY DEFAULT 1,
                total_wagered NUMERIC(14, 4) DEFAULT 0.0,
                total_paid_out NUMERIC(14, 4) DEFAULT 0.0,
                CHECK (id = 1)
            )
        """)
        cursor.execute("""
            INSERT INTO rtp_pool (id, total_wagered, total_paid_out)
            VALUES (1, 0, 0)
            ON CONFLICT (id) DO NOTHING
        """)

        # Şüpheli aktivite kayıtları
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS suspicious_activities (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                activity_type TEXT,
                details TEXT,
                detected_at BIGINT
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
        """Yeni kullanıcı oluştur - Anti-spam referral sistemi"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            current_time = int(time.time())
            cursor.execute("""
                INSERT INTO users (user_id, username, diamond, referred_by, joined_date, last_task_reset, last_activity, game_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, username, Config.NEW_USER_BONUS, referred_by, current_time, current_time, current_time))

            # Eğer referal varsa, ödülü pending olarak kaydet (anti-spam)
            if referred_by:
                cursor.execute("""
                    INSERT INTO pending_referral_rewards (referrer_id, referred_id, reward, created_date, paid)
                    VALUES (%s, %s, %s, %s, FALSE)
                    ON CONFLICT (referrer_id, referred_id) DO NOTHING
                """, (referred_by, user_id, Config.REFERAL_REWARD, current_time))

                # Referal sayısını hemen artır ama diamond'ı henüz verme
                cursor.execute("""
                    UPDATE users
                    SET referral_count = referral_count + 1
                    WHERE user_id = %s
                """, (referred_by,))

                conn.commit()
                cursor.close()
                self.return_connection(conn)
                self.update_daily_referral(referred_by)
                return

            conn.commit()
        except Exception as e:
            conn.rollback()
            logging.error(f"Kullanıcı oluşturma hatası: {e}")
        finally:
            if not conn.closed:
                try:
                    cursor.close()
                    self.return_connection(conn)
                except Exception:
                    pass

    def update_diamond(self, user_id: int, amount: float) -> float:
        """Diamond güncelle - Günlük kazanç limitini uygular. Gerçekte eklenen miktarı döndürür."""
        actual_amount = amount

        # Günlük limit yalnızca pozitif kazançlara uygulanır
        if amount > 0 and Config.DAILY_EARN_CAP > 0:
            from datetime import date
            today = date.today()
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(daily_diamonds_earned, 0) FROM daily_stats
                WHERE user_id = %s AND stat_date = %s
            """, (user_id, today))
            row = cursor.fetchone()
            cursor.close()
            self.return_connection(conn)

            already_earned = float(row[0]) if row else 0.0
            remaining_cap = Config.DAILY_EARN_CAP - already_earned

            if remaining_cap <= 0:
                return 0.0  # Limit doldu, kazanç eklenmez
            actual_amount = min(amount, remaining_cap)

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET diamond = diamond + %s WHERE user_id = %s
        """, (actual_amount, user_id))
        conn.commit()
        cursor.close()
        self.return_connection(conn)

        if actual_amount > 0:
            self.update_daily_diamonds(user_id, actual_amount)

        return actual_amount

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
            req_dict['phone_number'] = req_dict.get('phone_number', '')
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

            # ✅ YENİ: Günlük çekim istatistiğini güncelle
            cursor.close()
            self.return_connection(conn)
            self.update_daily_withdrawn(user_id, float(diamond_amount))
            return

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
            req_dict['phone_number'] = req_dict.get('phone_number', '')
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

    def reset_all_diamonds(self) -> int:
        """Tüm kullanıcıların diamond bakiyelerini 0'la - Returns: etkilenen kullanıcı sayısı"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Önce kaç kullanıcı etkilenecek sayalım
            cursor.execute("SELECT COUNT(*) FROM users WHERE diamond != 0")
            affected_count = cursor.fetchone()[0]

            # Tüm diamond'ları 0'la
            cursor.execute("UPDATE users SET diamond = 0")
            conn.commit()

            cursor.close()
            self.return_connection(conn)
            return affected_count

        except Exception as e:
            conn.rollback()
            logging.error(f"Diamond reset hatası: {e}")
            cursor.close()
            self.return_connection(conn)
            return -1


    def update_daily_diamonds(self, user_id: int, amount: float):
        """Günlük kazanılan diamond'ı güncelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().date()

        cursor.execute("""
            INSERT INTO daily_stats (user_id, stat_date, daily_diamonds_earned)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, stat_date)
            DO UPDATE SET daily_diamonds_earned = daily_stats.daily_diamonds_earned + %s
        """, (user_id, today, amount, amount))

        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def update_daily_referral(self, user_id: int):
        """Günlük referal sayısını güncelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().date()

        cursor.execute("""
            INSERT INTO daily_stats (user_id, stat_date, daily_referrals_count)
            VALUES (%s, %s, 1)
            ON CONFLICT (user_id, stat_date)
            DO UPDATE SET daily_referrals_count = daily_stats.daily_referrals_count + 1
        """, (user_id, today))

        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def update_daily_withdrawn(self, user_id: int, amount: float):
        """Günlük çekilen miktarı güncelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        today = datetime.now().date()

        cursor.execute("""
            INSERT INTO daily_stats (user_id, stat_date, daily_withdrawn)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, stat_date)
            DO UPDATE SET daily_withdrawn = daily_stats.daily_withdrawn + %s
        """, (user_id, today, amount, amount))

        conn.commit()
        cursor.close()
        self.return_connection(conn)

    def get_daily_top_diamonds(self, limit: int = 10) -> List[Dict]:
        """Günlük en çok diamond kazananlar"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        today = datetime.now().date()

        cursor.execute("""
            SELECT u.user_id, u.username, ds.daily_diamonds_earned
            FROM daily_stats ds
            JOIN users u ON ds.user_id = u.user_id
            WHERE ds.stat_date = %s AND u.is_banned = FALSE
            ORDER BY ds.daily_diamonds_earned DESC
            LIMIT %s
        """, (today, limit))

        results = cursor.fetchall()
        cursor.close()
        self.return_connection(conn)

        return [dict(r) for r in results]

    def get_daily_top_referrals(self, limit: int = 10) -> List[Dict]:
        """Günlük en çok referal getiren kullanıcılar"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        today = datetime.now().date()

        cursor.execute("""
            SELECT u.user_id, u.username, ds.daily_referrals_count
            FROM daily_stats ds
            JOIN users u ON ds.user_id = u.user_id
            WHERE ds.stat_date = %s AND u.is_banned = FALSE
            ORDER BY ds.daily_referrals_count DESC
            LIMIT %s
        """, (today, limit))

        results = cursor.fetchall()
        cursor.close()
        self.return_connection(conn)

        return [dict(r) for r in results]

    def get_daily_top_withdrawn(self, limit: int = 10) -> List[Dict]:
        """Günlük en çok para çekenler"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        today = datetime.now().date()

        cursor.execute("""
            SELECT u.user_id, u.username, ds.daily_withdrawn
            FROM daily_stats ds
            JOIN users u ON ds.user_id = u.user_id
            WHERE ds.stat_date = %s AND u.is_banned = FALSE
            ORDER BY ds.daily_withdrawn DESC
            LIMIT %s
        """, (today, limit))

        results = cursor.fetchall()
        cursor.close()
        self.return_connection(conn)

        return [dict(r) for r in results]



    def log_slot_play(self, user_id: int, result: str, reward: float):
        """Slot oyunu kaydını tut (opsiyonel - istatistik için)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO slot_history (user_id, result, reward, play_date)
                VALUES (%s, %s, %s, %s)
            """, (user_id, result, reward, int(time.time())))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logging.error(f"Slot log hatası: {e}")
        finally:
            cursor.close()
            self.return_connection(conn)

    # ========== RTP HAVUZU (KASA) ==========

    def update_rtp_pool(self, wagered: float = 0.0, paid_out: float = 0.0):
        """RTP havuzunu güncelle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE rtp_pool
                SET total_wagered = total_wagered + %s,
                    total_paid_out = total_paid_out + %s
                WHERE id = 1
            """, (wagered, paid_out))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logging.error(f"RTP pool güncelleme hatası: {e}")
        finally:
            cursor.close()
            self.return_connection(conn)

    def get_rtp_ratio(self) -> float:
        """Mevcut RTP oranını döndür (paid_out / wagered). Sıfır bölme durumunda 0.0 döner."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT total_wagered, total_paid_out FROM rtp_pool WHERE id = 1")
            row = cursor.fetchone()
            if not row or row[0] == 0:
                return 0.0
            return float(row[1]) / float(row[0])
        except Exception as e:
            logging.error(f"RTP ratio hatası: {e}")
            return 0.0
        finally:
            cursor.close()
            self.return_connection(conn)

    def get_dynamic_win_chance(self, base_chance: int) -> int:
        """Kasa havuzu oranına göre dinamik kazanma şansı döndür."""
        rtp = self.get_rtp_ratio()
        if rtp > Config.RTP_THRESHOLD:
            adjusted = base_chance - Config.RTP_WIN_CHANCE_REDUCTION
            return max(adjusted, 1)  # En az %1 şans
        return base_chance

    # ========== OYUN SAYACI VE REFERRAL ANTI-SPAM ==========

    def increment_game_count(self, user_id: int):
        """Kullanıcının oyun sayısını artır ve bekleyen referral ödüllerini kontrol et."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE users SET game_count = game_count + 1 WHERE user_id = %s
                RETURNING game_count, referred_by
            """, (user_id,))
            row = cursor.fetchone()
            conn.commit()
            cursor.close()
            self.return_connection(conn)

            if row:
                game_count, referred_by = row
                # 10 oyun eşiğine ulaşıldıysa referrer'a ödülü ver
                if game_count == Config.REFERAL_MIN_GAMES and referred_by:
                    self._pay_pending_referral(user_id, referred_by)
        except Exception as e:
            conn.rollback()
            logging.error(f"Oyun sayacı hatası: {e}")
            try:
                cursor.close()
                self.return_connection(conn)
            except Exception:
                pass

    def _pay_pending_referral(self, referred_id: int, referrer_id: int):
        """Bekleyen referral ödülünü öde."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE pending_referral_rewards
                SET paid = TRUE
                WHERE referrer_id = %s AND referred_id = %s AND paid = FALSE
                RETURNING reward
            """, (referrer_id, referred_id))
            row = cursor.fetchone()
            if row:
                reward = float(row[0])
                conn.commit()
                cursor.close()
                self.return_connection(conn)
                # Referrer'a diamond ekle
                self.update_diamond(referrer_id, reward)
                logging.info(f"Referral ödülü ödendi: referrer={referrer_id}, referred={referred_id}, reward={reward}")
            else:
                conn.rollback()
                cursor.close()
                self.return_connection(conn)
        except Exception as e:
            conn.rollback()
            logging.error(f"Referral ödeme hatası: {e}")
            try:
                cursor.close()
                self.return_connection(conn)
            except Exception:
                pass

    # ========== ŞÜPHELİ AKTİVİTE LOGLAMA ==========

    def log_suspicious_activity(self, user_id: int, activity_type: str, details: str):
        """Şüpheli aktiviteyi kaydet."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO suspicious_activities (user_id, activity_type, details, detected_at)
                VALUES (%s, %s, %s, %s)
            """, (user_id, activity_type, details, int(time.time())))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logging.error(f"Şüpheli aktivite log hatası: {e}")
        finally:
            cursor.close()
            self.return_connection(conn)

    def get_recent_suspicious_activities(self, limit: int = 20):
        """Son şüpheli aktiviteleri getir."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("""
                SELECT sa.*, u.username FROM suspicious_activities sa
                LEFT JOIN users u ON sa.user_id = u.user_id
                ORDER BY sa.detected_at DESC
                LIMIT %s
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Şüpheli aktivite sorgulama hatası: {e}")
            return []
        finally:
            cursor.close()
            self.return_connection(conn)

    # ========== PARA ÇEKME - TELEFON NUMARALI ==========

    def create_withdrawal_request(self, user_id: int, username: str, diamond: float, manat: float, phone_number: str = ""):
        """Para çekme talebi oluştur — telefon numarasıyla birlikte"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO withdrawal_requests
            (user_id, username, diamond_amount, manat_amount, request_date, phone_number)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING request_id
        """, (user_id, username, diamond, manat, int(time.time()), phone_number))
        request_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        self.return_connection(conn)
        return request_id# Global database instance
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
                                f"⚠️ <b>DUÝDYRYŞ!</b>\n\n"
                                f"Bot bu kanalda admin däl:\n"
                                f"📢 {sponsor['channel_name']}\n"
                                f"🆔 <code>{sponsor['channel_id']}</code>\n\n"
                                f"‼️ Sponsor kanalda body admin etmeli"
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
        ],
        # ✅ YENİ: Günlük top kullanıcılar butonu
        [
            InlineKeyboardButton("🏆 Günlük Top Ulanyjylar", callback_data="menu_daily_top")
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
# AKTİVİTE KONTROLÜ - YENİ SİSTEM
# ============================================================================

async def check_and_penalize_inactive_users(application):
    """İnaktif kullanıcıları kontrol et ve cezalandır - BACKGROUND TASK"""
    try:
        logging.info("🔍 İnaktivite kontrolü başladı...")
        inactive_users = db.get_inactive_users()

        penalized_count = 0
        warned_count = 0

        for user in inactive_users:
            user_id = user['user_id']
            balance = user['diamond']

            # Kullanıcının bakiyesi 0 veya eksi mi kontrol et
            if balance <= 0:
                # Sadece uyarı mesajı gönder
                try:
                    await application.bot.send_message(
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
                    warned_count += 1

                except Exception as e:
                    logging.error(f"Uyarı mesajı gönderilemedi {user_id}: {e}")
            else:
                # Bakiye pozitif - ceza uygula
                penalty = Config.INACTIVITY_PENALTY
                db.update_diamond(user_id, penalty)

                try:
                    await application.bot.send_message(
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
                    penalized_count += 1

                except Exception as e:
                    logging.error(f"Ceza mesajı gönderilemedi {user_id}: {e}")

            # Rate limiting için kısa bekleme
            await asyncio.sleep(0.1)

        logging.info(f"✅ İnaktivite kontrolü tamamlandı. {len(inactive_users)} kullanıcı kontrol edildi. "
                    f"Cezalı: {penalized_count}, Uyarılı: {warned_count}")

    except Exception as e:
        logging.error(f"❌ İnaktivite kontrolü hatası: {e}")

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


# start_command fonksiyonundan sonra ekleyin:
async def grupid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grup ID'sini öğren"""
    chat = update.effective_chat
    await update.message.reply_text(
        f"📍 <b>Grup Bilgileri:</b>\n\n"
        f"ID: <code>{chat.id}</code>\n"
        f"Tür: {chat.type}\n"
        f"Başlık: {chat.title}\n"
        f"Username: @{chat.username if chat.username else 'yok'}",
        parse_mode="HTML"
    )

async def reset_all_diamonds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tüm kullanıcıların diamond bakiyelerini sıfırla - ADMIN ONLY"""
    user_id = update.effective_user.id

    if user_id not in Config.ADMIN_IDS:
        await update.message.reply_text("⛔ Siziň admin wezipaňiz ýok!")
        return

    # Onay butonu göster
    keyboard = [
        [
            InlineKeyboardButton("✅ Hawa, ählisini 0 et", callback_data="confirm_reset_diamonds"),
            InlineKeyboardButton("❌ Ýok, ýatyrmak", callback_data="cancel_reset_diamonds")
        ]
    ]

    await update.message.reply_text(
        "⚠️ <b>DİKKAT!</b>\n\n"
        "Bu komut ÄHLÄ° ullanyjylaryň diamond balansyny 0 eder!\n\n"
        "🔴 Bu işlem geri alınmaz!\n"
        "🔴 Tüm diamond'lar silinecek!\n\n"
        "Devam etmek istediğinize emin misiniz?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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



async def handle_combined_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Medya mesajlarını işle - Broadcast veya Mass Post"""
    if not context.user_data:
        return

    # Önce broadcast kontrolü
    if context.user_data.get('waiting_for_broadcast'):
        from bot_admin import handle_broadcast_message
        await handle_broadcast_message(update, context)
        return

    # Sonra mass post kontrolü
    if context.user_data.get('waiting_for_mass_post'):
        from bot_admin import handle_mass_post
        await handle_mass_post(update, context)
        return

async def handle_combined_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text mesajlarını işle - Promo kod, Broadcast, Telefon numarası veya Admin mesajı"""
    if not context.user_data:
        return

    # Admin mesaj gönderme
    if context.user_data.get('waiting_for_admin_msg'):
        from bot_admin import handle_admin_msg_to_user
        await handle_admin_msg_to_user(update, context)
        return

    # Önce broadcast kontrolü
    if context.user_data.get('waiting_for_broadcast'):
        from bot_admin import handle_broadcast_message
        await handle_broadcast_message(update, context)
        return

    # Telefon numarası bekleniyor mu?
    if context.user_data.get('waiting_for_phone'):
        from bot_handlers import handle_phone_number_input
        await handle_phone_number_input(update, context)
        return

    # Sonra promo kod kontrolü
    if context.user_data.get('waiting_for_promo'):
        from bot_handlers import handle_promo_code_input
        await handle_promo_code_input(update, context)
        return

async def debug_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tüm mesajları logla - grup ID'sini bulmak için"""
    if update.message:
        chat_id = update.message.chat_id
        chat_type = update.message.chat.type
        text = update.message.text or "[medya]"
        user = update.message.from_user

        logging.info(f"""
        ========================================
        DEBUG MESAJ:
        Chat ID: {chat_id}
        Chat Type: {chat_type}
        Text: {text}
        User: {user.first_name} (@{user.username})
        Config SLOT_CHAT_ID: {Config.SLOT_CHAT_ID}
        Eşleşme: {str(chat_id) == str(Config.SLOT_CHAT_ID)}
        ========================================
        """)


# ============================================================================
# MAIN
# ============================================================================

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DÜZELTME: SLOT oyunu için handler sıralaması düzeltildi
"""
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
        handle_membership_check,
        play_slot_game
    )
    from bot_admin import admin_command, handle_mass_post, handle_broadcast_message

    application = Application.builder().token(Config.BOT_TOKEN).build()

    # ============ KOMUTLAR ============
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("grupid", grupid_command))

    # Admin komutları
    application.add_handler(CommandHandler("adddia", admin_command))
    application.add_handler(CommandHandler("remdia", admin_command))
    application.add_handler(CommandHandler("userinfo", admin_command))
    application.add_handler(CommandHandler("createpromo", admin_command))
    application.add_handler(CommandHandler("addsponsor", admin_command))
    application.add_handler(CommandHandler("approve", admin_command))
    application.add_handler(CommandHandler("reject", admin_command))
    application.add_handler(CommandHandler("resetdiamonds", reset_all_diamonds_command))

    # Callback handlers
    application.add_handler(CallbackQueryHandler(button_callback))

    # ⚠️ ÖNEMLİ: SLOT HANDLER EN ÖNCE OLMALI!
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex("^🎰 SLOT OÝNA$") & ~filters.COMMAND,
        play_slot_game
    ))

    # Medya handler'lar (broadcast ve mass post için)
    application.add_handler(MessageHandler(
        (filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
        handle_combined_media
    ))

    # Text handler (promo kod ve broadcast için)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_combined_text
    ))

    # ============ İNAKTİVİTE KONTROLÜ ============
    async def inactivity_job_callback(context: ContextTypes.DEFAULT_TYPE):
        """Her 6 saatte bir inaktivite kontrolü yap"""
        await check_and_penalize_inactive_users(context.application)

    # İlk kontrolü 1 dakika sonra başlat, sonra her 6 saatte tekrarla
    application.job_queue.run_repeating(
        inactivity_job_callback,
        interval=21600,  # 6 saat (saniye cinsinden)
        first=60  # İlk çalıştırma 60 saniye sonra
    )


    # ============ KEEP-ALIVE (Railway uyku modunu önle) ============
    KEEP_ALIVE_CHANNEL = "@ononlemlem"

    async def keep_alive_job(context: ContextTypes.DEFAULT_TYPE):
        """Her 4 dakikada bir kanala sessiz mesaj gönder — Railway uyku modunu önler"""
        try:
            now = datetime.now().strftime("%H:%M:%S")
            await context.bot.send_message(
                chat_id=KEEP_ALIVE_CHANNEL,
                text=f"🤖 Bot aktif | {now}",
                disable_notification=True  # Sessiz bildirim — kullanıcıları rahatsız etmez
            )
            logging.info(f"✅ Keep-alive mesajı gönderildi: {now}")
        except Exception as e:
            logging.warning(f"⚠️ Keep-alive hatası: {e}")

    # Her 4 dakikada bir çalıştır (Railway'in uyku süresi genellikle 5 dakikadır)
    application.job_queue.run_repeating(
        keep_alive_job,
        interval=240,   # 4 dakika (saniye cinsinden)
        first=30        # Bot başladıktan 30 saniye sonra ilk mesajı gönder
    )
    print("🔄 Keep-alive görevi aktif! (Her 4 dakikada @ononlemlem kanalına mesaj)")

    # ============ SLOT BUTONU KURULUMU ============
    async def setup_slot_on_startup(application):
        try:
            keyboard = ReplyKeyboardMarkup(
                [[KeyboardButton("🎰 SLOT OÝNA")]],
                resize_keyboard=True,
                one_time_keyboard=False
            )
            await application.bot.send_message(
                chat_id=Config.SLOT_CHAT_ID,
                text=(
                    "🎰 <b>SLOT OÝUNY IŞLEÝÄR!</b>\n\n"
                    "🎯 Aşakdaky düwmä bas we sloty aýla!\n\n"
                    "🏆 <b>Utup bolýan kombinasiýalar:</b>\n"
                    "🍒🍒🍒 = <b>+1.0 💎</b>\n"
                    "🍋🍋🍋 = <b>+1.5 💎</b>\n"
                    "7️⃣7️⃣7️⃣ = <b>+5.0 💎 (JACKPOT!)</b>\n\n"
                    "💡 <b>Golaýlasaňyz:</b> 2 deň + 1 tapawutly = <b>+0.1 💎</b> teselli\n"
                    "😢 <b>Ýitirseň:</b> <b>-0.5 💎</b>\n\n"
                    "🍀 Şanslymykaň?!"
                ),
                parse_mode="HTML",
                reply_markup=keyboard
            )
            logging.info("✅ SLOT butonu gönderildi")
        except Exception as e:
            logging.error(f"Slot button kurulum hatası: {e}")

    application.post_init = setup_slot_on_startup

    # ============ BOTU BAŞLAT ============
    print("🤖 Bot başladı...")
    print("🎰 SLOT oyunu aktif!")
    print(f"📍 SLOT grubu: {Config.SLOT_CHAT_ID}")
    print("⏰ İnaktivite kontrolü 6 saatte bir çalışacak (ilk kontrol 1 dk sonra)")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
