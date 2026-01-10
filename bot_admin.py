#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Admin Panel Modülü - Gelişmiş Yönetim Sistemi
Güncellenmiş Versiyon - Yeni Sponsor Sistemi ve Toplu Post
"""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from psycopg2.extras import RealDictCursor

# Import from bot_main
from bot_main import db, Config

# ============================================================================
# ADMİN PANELİ
# ============================================================================

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panelini göster - Güncellenmiş"""
    query = update.callback_query

    keyboard = [
        [InlineKeyboardButton("👥 Ulanyjylar", callback_data="admin_users")],
        [InlineKeyboardButton("💰 Pul çekme talaplary", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("🏆 Top Ulanyjylar", callback_data="admin_top_users")],
        [InlineKeyboardButton("🎟 Promo kod döret", callback_data="admin_promo_create")],
        [InlineKeyboardButton("🗑 Promo kod poz", callback_data="admin_promo_delete")],
        [InlineKeyboardButton("📢 Sponsor Dolandyryş", callback_data="admin_sponsor_menu")],
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📣 Hemmä habar", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📮 Toplu Post", callback_data="admin_mass_post")],
        [InlineKeyboardButton("🔙 Yza gaýt", callback_data="back_main")]
    ]

    await query.edit_message_text(
        "👑 <b>Admin Paneli</b>\n\nNäme etjek bolýaňyz?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================================================================
# KULLANICI YÖNETİMİ
# ============================================================================

async def admin_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcı yönetimi menüsü"""
    query = update.callback_query

    text = (
        "👥 <b>Ulanyjy dolandyryş</b>\n\n"
        "Ulanyjy ID ýazyň:\n"
        "• Diamond goşmak üçin: /adddia 123456789 10\n"
        "• Diamond aýyrmak üçin: /remdia 123456789 5\n"
        "• Ulanyjy maglumatyny görmek: /userinfo 123456789\n"
        "• Ulanyjyny ban etmek: /banuser 123456789\n"
        "• Ban aýyrmak: /unbanuser 123456789\n\n"
        "💡 <b>Belllik:</b> Ondalykly sayy ulanyp bilersiňiz (mysal: 1.5)"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")
        ]])
    )

# ============================================================================
# TOP KULLANICILAR
# ============================================================================

async def admin_top_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top kullanıcılar menüsü"""
    query = update.callback_query

    keyboard = [
        [InlineKeyboardButton("💎 Iň köp Diamond", callback_data="admin_top_diamonds")],
        [InlineKeyboardButton("👥 Iň köp Referal", callback_data="admin_top_referrals")],
        [InlineKeyboardButton("💸 Iň köp Çekilen", callback_data="admin_top_withdrawn")],
        [InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")]
    ]

    await query.edit_message_text(
        "🏆 <b>Top Ulanyjylar</b>\n\nHaýsy statistikany görmek isleýärsiňiz?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_top_diamonds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """En çok diamond'a sahip kullanıcılar"""
    callback_query = update.callback_query

    try:
        # PostgreSQL query
        conn = db.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT user_id, username, diamond
            FROM users
            WHERE is_banned = FALSE
            ORDER BY diamond DESC
            LIMIT 10
        """)
        top_users = cursor.fetchall()
        cursor.close()
        db.return_connection(conn)

        # Convert to list of dicts
        top_users = [dict(user) for user in top_users]
    except Exception as e:
        logging.error(f"Top diamonds query error: {e}")
        await callback_query.edit_message_text(
            "🏆 <b>Iň köp Diamond</b>\n\n❌ Database hatasy ýüze çykdy.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_top_users")
            ]])
        )
        return

    if not top_users:
        await callback_query.edit_message_text(
            "🏆 <b>Iň köp Diamond</b>\n\n❌ Häzir hiç hili ulanyjy ýok.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_top_users")
            ]])
        )
        return

    text = "🏆 <b>Iň köp Diamond - TOP 10</b>\n\n"

    medals = ["🥇", "🥈", "🥉"]
    for idx, user in enumerate(top_users, 1):
        medal = medals[idx-1] if idx <= 3 else f"{idx}."

        username = f"@{user['username']}" if user['username'] else "—"
        telegram_id = user['user_id']

        text += (
            f"{medal} {username}\n"
            f"   🆔 <code>{telegram_id}</code>\n"
            f"   💎 <b>{float(user['diamond']):.1f}</b> diamond\n\n"
        )

    await callback_query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_top_users")
        ]])
    )

async def admin_top_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """En çok referral'a sahip kullanıcılar"""
    query = update.callback_query

    try:
        conn = db.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT user_id, username, referral_count
            FROM users
            WHERE is_banned = FALSE
            ORDER BY referral_count DESC
            LIMIT 10
        """)
        top_users = cursor.fetchall()
        cursor.close()
        db.return_connection(conn)

        top_users = [dict(user) for user in top_users]
    except Exception as e:
        logging.error(f"Top referrals query error: {e}")
        await query.edit_message_text(
            "🏆 <b>Iň köp Referal</b>\n\n❌ Database hatasy ýüze çykdy.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_top_users")
            ]])
        )
        return

    if not top_users:
        await query.edit_message_text(
            "🏆 <b>Iň köp Referal</b>\n\n❌ Häzir hiç hili ulanyjy ýok.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_top_users")
            ]])
        )
        return

    text = "🏆 <b>Iň köp Referal - TOP 10</b>\n\n"

    medals = ["🥇", "🥈", "🥉"]
    for idx, user in enumerate(top_users, 1):
        medal = medals[idx-1] if idx <= 3 else f"{idx}."
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{medal} {username}\n   👥 <b>{user['referral_count']}</b> referal\n\n"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_top_users")
        ]])
    )

async def admin_top_withdrawn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """En çok para çeken kullanıcılar"""
    query = update.callback_query

    try:
        conn = db.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT user_id, username, total_withdrawn
            FROM users
            WHERE is_banned = FALSE
            ORDER BY total_withdrawn DESC
            LIMIT 10
        """)
        top_users = cursor.fetchall()
        cursor.close()
        db.return_connection(conn)

        top_users = [dict(user) for user in top_users]
    except Exception as e:
        logging.error(f"Top withdrawn query error: {e}")
        await query.edit_message_text(
            "🏆 <b>Iň köp Çekilen</b>\n\n❌ Database hatasy ýüze çykdy.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_top_users")
            ]])
        )
        return

    if not top_users:
        await query.edit_message_text(
            "🏆 <b>Iň köp Çekilen</b>\n\n❌ Häzir hiç hili ulanyjy ýok.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_top_users")
            ]])
        )
        return

    text = "🏆 <b>Iň köp Çekilen - TOP 10</b>\n\n"

    medals = ["🥇", "🥈", "🥉"]
    for idx, user in enumerate(top_users, 1):
        medal = medals[idx-1] if idx <= 3 else f"{idx}."
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        withdrawn = float(user['total_withdrawn'])
        manat = withdrawn / Config.DIAMOND_TO_MANAT
        text += f"{medal} {username}\n   💸 <b>{withdrawn:.1f}</b> diamond ({manat:.2f} TMT)\n\n"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_top_users")
        ]])
    )

# ============================================================================
# PARA ÇEKME YÖNETİMİ
# ============================================================================

async def admin_withdrawals_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Para çekme talepleri menüsü"""
    query = update.callback_query

    pending_requests = db.get_pending_withdrawals()

    if not pending_requests:
        await query.edit_message_text(
            "💰 <b>Pul Çekme Talaplary</b>\n\n"
            "✅ Häzir hiç hili talap ýok.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")
            ]])
        )
        return

    text = "💰 <b>Garaşýan Talaplar:</b>\n\n"

    keyboard = []
    for req in pending_requests:
        text += (
            f"📋 №{req['request_id']}\n"
            f"👤 @{req['username']} (ID: {req['user_id']})\n"
            f"💎 {req['diamond_amount']:.1f} diamond ({req['manat_amount']:.2f} TMT)\n\n"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"✅ №{req['request_id']} Tassykla",
                callback_data=f"admin_approve_{req['request_id']}"
            ),
            InlineKeyboardButton(
                f"❌ №{req['request_id']} Ret et",
                callback_data=f"admin_reject_{req['request_id']}"
            )
        ])

    keyboard.append([InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_approve_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Para çekme talebini onayla"""
    query = update.callback_query
    request_id = int(query.data.split("_")[2])

    request = db.get_withdrawal_request(request_id)

    if not request or request['status'] != 'pending':
        await query.answer("❌ Talap tapylmady ýa-da eýýäm işlenildi!", show_alert=True)
        return

    # Onayla ve diamond'ı düş
    db.approve_withdrawal(request_id)

    # Kullanıcıya bildirim
    try:
        await context.bot.send_message(
            chat_id=request['user_id'],
            text=(
                f"✅ <b>TALAP TASSYKLANDY!</b>\n\n"
                f"📋 Talap №: {request_id}\n"
                f"💎 Mukdar: {request['diamond_amount']:.1f} diamond\n"
                f"💵 Manat: {request['manat_amount']:.2f} TMT\n\n"
                f"💰 Diamond hasabyňyzdan düşürildi.\n"
                f"📞 Admin siz bilen ýakynda habarlaşar."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Kullanıcıya bildirim gönderilemedi: {e}")

    # KANALA BİLDİRİM GÖNDER
    try:
        announcement_text = (
            f"✅ <b>Talap Tassyklandy!</b>\n\n"
            f"📋 Talap №: {request_id}\n"
            f"👤 Ulanyjy: @{request['username']}\n"
            f"💎 Mukdar: {request['diamond_amount']:.1f} diamond\n"
            f"💵 Manat: {request['manat_amount']:.2f} TMT\n\n"
            f"🎉 Gutlaýarys!"
        )

        await context.bot.send_message(
            chat_id="@diamond_labs",
            text=announcement_text,
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Kanala bildirim gönderilemedi: {e}")

    await query.answer("✅ Talap tassyklandy!", show_alert=True)
    await admin_withdrawals_menu(update, context)

async def admin_reject_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Para çekme talebini reddet"""
    query = update.callback_query
    request_id = int(query.data.split("_")[2])

    request = db.get_withdrawal_request(request_id)

    if not request or request['status'] != 'pending':
        await query.answer("❌ Talap tapylmady ýa-da eýýäm işlenildi!", show_alert=True)
        return

    # Reddet
    db.reject_withdrawal(request_id)

    # Kullanıcıya bildirim
    try:
        await context.bot.send_message(
            chat_id=request['user_id'],
            text=(
                f"❌ <b>TALAP RET EDILDI</b>\n\n"
                f"📋 Talap №: {request_id}\n"
                f"💎 Mukdar: {request['diamond_amount']:.1f} diamond\n\n"
                f"🔄 Diamond hasabyňyzda galýar.\n"
                f"📞 Soraglar üçin admin bilen habarlaşyň: @dekanaska"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Kullanıcıya bildirim gönderilemedi: {e}")

    await query.answer("❌ Talap ret edildi!", show_alert=True)
    await admin_withdrawals_menu(update, context)

# ============================================================================
# PROMO KOD YÖNETİMİ
# ============================================================================

async def admin_promo_create_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo kod oluşturma menüsü"""
    query = update.callback_query

    text = (
        "🎟 <b>Promo Kod Döretmek</b>\n\n"
        "Täze promo kod döretmek üçin:\n"
        "/createpromo KOD_ADY 10 100\n\n"
        "Mysal: /createpromo BONUS2026 15.5 50\n"
        "(15.5 diamond berýär, 50 gezek ulanyp bolýar)\n\n"
        "💡 Ondalykly sayy ulanyp bilersiňiz!"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")
        ]])
    )

async def admin_promo_delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo kod silme menüsü"""
    query = update.callback_query

    promo_codes = db.get_all_promo_codes()

    if not promo_codes:
        await query.edit_message_text(
            "🎟 <b>Promo Kodlar</b>\n\n"
            "❌ Häzir hiç hili promo kod ýok.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")
            ]])
        )
        return

    text = "🎟 <b>Promo Kodlar - Pozmak üçin saýlaň:</b>\n\n"

    keyboard = []
    for promo in promo_codes:
        text += (
            f"🔹 <code>{promo['code']}</code>\n"
            f"   💎 {promo['diamond_reward']:.1f} diamond\n"
            f"   📊 {promo['current_uses']}/{promo['max_uses']} ulanylyş\n\n"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"🗑 {promo['code']} - Pozmak",
                callback_data=f"admin_delpromo_{promo['code']}"
            )
        ])

    keyboard.append([InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_delete_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo kod sil"""
    query = update.callback_query
    code = query.data.split("_", 2)[2]

    db.delete_promo_code(code)

    await query.answer(f"✅ {code} promo kody pozuldy!", show_alert=True)
    await admin_promo_delete_menu(update, context)

# ============================================================================
# SPONSOR YÖNETİMİ - YENİ GELİŞTİRİLMİŞ SİSTEM
# ============================================================================

async def admin_sponsor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sponsor yönetim menüsü - Ana menü"""
    query = update.callback_query

    keyboard = [
        [InlineKeyboardButton("➕ /start için kanal goş", callback_data="admin_sponsor_add_required")],
        [InlineKeyboardButton("➕ Zadanýa için sponsor goş", callback_data="admin_sponsor_add_task")],
        [InlineKeyboardButton("📋 /start kanallaryny gör", callback_data="admin_sponsor_list_required")],
        [InlineKeyboardButton("📋 Zadanýa sponsorlaryny gör", callback_data="admin_sponsor_list_task")],
        [InlineKeyboardButton("🗑 Sponsor poz", callback_data="admin_sponsor_delete")],
        [InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")]
    ]

    await query.edit_message_text(
        "📢 <b>Sponsor Dolandyryş</b>\n\n"
        "Näme etmek isleýärsiňiz?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_sponsor_add_required_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zorunlu kanal ekleme menüsü"""
    query = update.callback_query

    text = (
        "➕ <b>/start için Kanal Goşmak</b>\n\n"
        "Täze zorunlu kanal goşmak üçin:\n"
        "/addsponsor @kanal_ady Kanal ady 0 required\n\n"
        "Mysal:\n"
        "/addsponsor @my_channel Meniň kanalym 0 required\n\n"
        "⚠️ <b>Belllikler:</b>\n"
        "• /start kanallar üçin diamond 0 bolmaly\n"
        "• 'required' sözüni ýazmaly\n"
        "• Boty kanalda admin ediň!"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_sponsor_menu")
        ]])
    )

async def admin_sponsor_add_task_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Görev sponsoru ekleme menüsü"""
    query = update.callback_query

    text = (
        "➕ <b>Zadanýa için Sponsor Goşmak</b>\n\n"
        "Täze zadanýa sponsory goşmak üçin:\n"
        "/addsponsor @kanal_ady Kanal ady 5 task\n\n"
        "Mysal:\n"
        "/addsponsor @my_channel Meniň kanalym 3.5 task\n"
        "(3.5 diamond berýär)\n\n"
        "⚠️ <b>Belllikler:</b>\n"
        "• Zadanýa sponsorlar üçin diamond mukdary belläň\n"
        "• 'task' sözüni ýazmaly\n"
        "• Ondalykly sayy ulanyp bilersiňiz\n"
        "• Boty kanalda admin ediň!"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_sponsor_menu")
        ]])
    )

async def admin_sponsor_list_required(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zorunlu kanalları listele"""
    query = update.callback_query

    sponsors = db.get_required_channels()

    if not sponsors:
        await query.edit_message_text(
            "📋 <b>/start Kanallar</b>\n\n"
            "❌ Häzir hiç hili zorunlu kanal ýok.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_sponsor_menu")
            ]])
        )
        return

    text = "📋 <b>/start için Zorunly Kanallar:</b>\n\n"

    for sponsor in sponsors:
        admin_status = "✅" if sponsor.get('bot_is_admin', True) else "❌"
        text += (
            f"{admin_status} <b>{sponsor['channel_name']}</b>\n"
            f"   📢 {sponsor['channel_id']}\n"
            f"   🆔 ID: {sponsor['sponsor_id']}\n\n"
        )

    text += "\n✅ = Bot admin\n❌ = Bot admin däl (boty admin ediň!)"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_sponsor_menu")
        ]])
    )

async def admin_sponsor_list_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Görev sponsorlarını listele"""
    query = update.callback_query

    sponsors = db.get_task_sponsors()

    if not sponsors:
        await query.edit_message_text(
            "📋 <b>Zadanýa Sponsorlar</b>\n\n"
            "❌ Häzir hiç hili zadanýa sponsory ýok.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_sponsor_menu")
            ]])
        )
        return

    text = "📋 <b>Zadanýa Sponsorlar:</b>\n\n"

    for sponsor in sponsors:
        admin_status = "✅" if sponsor.get('bot_is_admin', True) else "❌"
        text += (
            f"{admin_status} <b>{sponsor['channel_name']}</b>\n"
            f"   📢 {sponsor['channel_id']}\n"
            f"   💎 {sponsor['diamond_reward']:.1f} diamond\n"
            f"   🆔 ID: {sponsor['sponsor_id']}\n\n"
        )

    text += "\n✅ = Bot admin\n❌ = Bot admin däl (boty admin ediň!)"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_sponsor_menu")
        ]])
    )

async def admin_sponsor_delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sponsor silme menüsü"""
    query = update.callback_query

    sponsors = db.get_active_sponsors()

    if not sponsors:
        await query.edit_message_text(
            "📢 <b>Sponsorlar</b>\n\n"
            "❌ Häzir hiç hili sponsor ýok.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_sponsor_menu")
            ]])
        )
        return

    text = "📢 <b>Sponsorlar - Pozmak üçin saýlaň:</b>\n\n"

    keyboard = []
    for sponsor in sponsors:
        sponsor_type_text = "🔴 /start" if sponsor['sponsor_type'] == Config.SPONSOR_TYPE_REQUIRED else "🟢 Zadanýa"
        text += (
            f"🔹 <b>{sponsor['channel_name']}</b> ({sponsor_type_text})\n"
            f"   📢 {sponsor['channel_id']}\n"
            f"   💎 {sponsor['diamond_reward']:.1f} diamond\n\n"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"🗑 {sponsor['channel_name']} - Pozmak",
                callback_data=f"admin_delsponsor_{sponsor['sponsor_id']}"
            )
        ])

    keyboard.append([InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_sponsor_menu")])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_delete_sponsor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sponsor sil"""
    query = update.callback_query
    sponsor_id = int(query.data.split("_")[2])

    db.delete_sponsor(sponsor_id)

    await query.answer("✅ Sponsor pozuldy!", show_alert=True)
    await admin_sponsor_delete_menu(update, context)

# ============================================================================
# İSTATİSTİKLER
# ============================================================================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """İstatistikler"""
    query = update.callback_query

    stats = db.get_stats()

    text = (
        f"📊 <b>Bot Statistikasy</b>\n\n"
        f"👥 Jemi ulanyjylar: <b>{stats['total_users']}</b>\n"
        f"💎 Jemi diamond: <b>{stats['total_diamonds']:.1f}</b>\n"
        f"💸 Jemi çekilen: <b>{stats['total_withdrawn']:.1f}</b> diamond\n"
        f"💰 Manat görnüşinde: <b>{stats['total_withdrawn'] / Config.DIAMOND_TO_MANAT:.2f}</b> TMT"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")
        ]])
    )

# ============================================================================
# BROADCAST - KULLANICILARA TOPLU MESAJ
# ============================================================================

async def admin_broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast menüsü"""
    query = update.callback_query

    text = (
        "📣 <b>Hemmeler Habar Ugratmak</b>\n\n"
        "Ähli ulanyjylara habar ugratmak üçin:\n"
        "/broadcast Siziň habaryňyz\n\n"
        "⚠️ Bu ähli ulanyjylara iberiler!\n\n"
        "💡 <b>Giňişleýin format:</b>\n"
        "Mesaj içinde satır atlamalary we boşluklar korunur.\n"
        "HTML formatı desteklenir:\n"
        "<b>bold</b>, <i>italic</i>, <code>code</code>"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")
        ]])
    )

# ============================================================================
# TOPLU POST - YENİ ÖZELLİK
# ============================================================================

async def admin_mass_post_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toplu post menüsü - Yeni Özellik"""
    query = update.callback_query

    text = (
        "📮 <b>Toplu Post Göndermek</b>\n\n"
        "Botun admin olduğu tüm sponsor kanallarına post göndermek için:\n\n"
        "1️⃣ Bu menüden sonra görselli veya yazılı postunuzu gönderin\n"
        "2️⃣ Bot otomatik olarak tüm kanallara yayınlayacak\n\n"
        "⚠️ <b>Önemli:</b>\n"
        "• Sadece bir mesaj gönderin (resim + yazı veya sadece yazı)\n"
        "• Bot sadece admin olduğu kanallara post gönderebilir\n"
        "• İptal etmek için /cancel yazın\n\n"
        "✅ Hazır olduğunuzda postunuzu gönderin!"
    )

    # Kullanıcıyı bekleme moduna al
    context.user_data['waiting_for_mass_post'] = True

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 İptal", callback_data="admin_panel")
        ]])
    )

async def handle_mass_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toplu post işle - Yeni Özellik"""
    # Güvenli kontrol - context.user_data None olabilir
    if not context.user_data:
        return

    if not context.user_data.get('waiting_for_mass_post'):
        return

    user_id = update.effective_user.id

    # Admin kontrolü
    if user_id not in Config.ADMIN_IDS:
        return

    # Bekleme modunu kapat
    context.user_data['waiting_for_mass_post'] = False

    # Tüm aktif sponsorları al (bot admin olduğu)
    all_sponsors = db.get_active_sponsors()

    success_count = 0
    failed_count = 0
    failed_channels = []

    status_msg = await update.message.reply_text(
        "📮 <b>Post gönderiliyor...</b>\n\n"
        "⏳ Lütfen bekleyin...",
        parse_mode="HTML"
    )

    for sponsor in all_sponsors:
        try:
            # Botun admin olup olmadığını kontrol et
            try:
                bot_member = await context.bot.get_chat_member(sponsor['channel_id'], context.bot.id)
                is_admin = bot_member.status in ["administrator", "creator"]

                if not is_admin:
                    failed_count += 1
                    failed_channels.append(f"{sponsor['channel_name']} (admin değil)")
                    # Durumu güncelle
                    db.update_sponsor_bot_admin_status(sponsor['sponsor_id'], False)
                    continue
            except Exception as e:
                logging.error(f"Admin kontrol hatası {sponsor['channel_id']}: {e}")
                failed_count += 1
                failed_channels.append(f"{sponsor['channel_name']} (erişim hatası)")
                continue

            # Mesajı kanala gönder
            if update.message.photo:
                # Fotoğraflı mesaj
                photo = update.message.photo[-1]  # En yüksek kalite
                caption = update.message.caption or ""
                await context.bot.send_photo(
                    chat_id=sponsor['channel_id'],
                    photo=photo.file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif update.message.video:
                # Videolu mesaj
                video = update.message.video
                caption = update.message.caption or ""
                await context.bot.send_video(
                    chat_id=sponsor['channel_id'],
                    video=video.file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif update.message.document:
                # Dosya
                document = update.message.document
                caption = update.message.caption or ""
                await context.bot.send_document(
                    chat_id=sponsor['channel_id'],
                    document=document.file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            else:
                # Sadece yazı
                await context.bot.send_message(
                    chat_id=sponsor['channel_id'],
                    text=update.message.text,
                    parse_mode="HTML"
                )

            success_count += 1
            await asyncio.sleep(0.5)  # Rate limit için bekleme

        except Exception as e:
            failed_count += 1
            failed_channels.append(f"{sponsor['channel_name']} ({str(e)[:30]})")
            logging.error(f"Post gönderme hatası {sponsor['channel_id']}: {e}")

    # Sonuç mesajı
    result_text = (
        f"📮 <b>Toplu Post Tamamlandı!</b>\n\n"
        f"✅ Başarılı: <b>{success_count}</b> kanal\n"
        f"❌ Başarısız: <b>{failed_count}</b> kanal\n\n"
    )

    if failed_channels:
        result_text += "❌ <b>Başarısız Kanallar:</b>\n"
        for channel in failed_channels[:10]:  # İlk 10'unu göster
            result_text += f"• {channel}\n"
        if len(failed_channels) > 10:
            result_text += f"• ... ve {len(failed_channels) - 10} kanal daha\n"

    await status_msg.edit_text(result_text, parse_mode="HTML")

    
# ============================================================================
# ADMİN KOMUTLARI
# ============================================================================

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
            amount = float(context.args[1])

            db.update_diamond(target_user, amount)

            await update.message.reply_text(
                f"✅ {target_user} ID-li ulanyjynyň hasabyna {amount:.1f} 💎 goşuldy!"
            )
        except:
            await update.message.reply_text("❌ Nädogry format! /adddia 123456789 10.5")

    # Diamond çıkarma
    elif command == "remdia":
        try:
            target_user = int(context.args[0])
            amount = float(context.args[1])

            db.update_diamond(target_user, -amount)

            await update.message.reply_text(
                f"✅ {target_user} ID-li ulanyjynyň hasabyndan {amount:.1f} 💎 aýyryldy!"
            )
        except:
            await update.message.reply_text("❌ Nädogry format! /remdia 123456789 5.5")

    # Kullanıcı bilgisi
    elif command == "userinfo":
        try:
            target_user = int(context.args[0])
            user_data = db.get_user(target_user)

            if user_data:
                text = (
                    f"👤 <b>Ulanyjy Maglumaty</b>\n\n"
                    f"🆔 ID: {user_data['user_id']}\n"
                    f"👤 Ulanyjy: @{user_data['username']}\n"
                    f"💎 Diamond: {user_data['diamond']:.1f}\n"
                    f"👥 Referal: {user_data['referral_count']}\n"
                    f"💸 Çekilen: {user_data['total_withdrawn']:.1f}\n"
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
            diamond = float(context.args[1])
            max_uses = int(context.args[2])

            success = db.create_promo_code(code, diamond, max_uses)

            if success:
                await update.message.reply_text(
                    f"✅ Promo kod döredildi!\n\n"
                    f"🎟 Kod: <code>{code}</code>\n"
                    f"💎 Mukdar: {diamond:.1f}\n"
                    f"📢 Ulanyş sany: {max_uses}",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text("❌ Bu kod eýýäm bar!")
        except:
            await update.message.reply_text("❌ Nädogry format! /createpromo KOD 10.5 100")

    # Sponsor ekleme - GELİŞTİRİLMİŞ
    elif command == "addsponsor":
        try:
            channel_id = context.args[0]
            diamond = float(context.args[-2])
            sponsor_type = context.args[-1]  # 'required' veya 'task'
            channel_name = " ".join(context.args[1:-2])

            # Tip kontrolü
            if sponsor_type not in [Config.SPONSOR_TYPE_REQUIRED, Config.SPONSOR_TYPE_TASK]:
                await update.message.reply_text(
                    "❌ Sponsor tipi 'required' veya 'task' bolmaly!"
                )
                return

            success = db.add_sponsor(channel_id, channel_name, diamond, sponsor_type)

            if success:
                type_text = "/start kanaly" if sponsor_type == Config.SPONSOR_TYPE_REQUIRED else "Zadanýa sponsory"
                await update.message.reply_text(
                    f"✅ {type_text} goşuldy!\n\n"
                    f"📢 Kanal: {channel_name}\n"
                    f"🆔 ID: <code>{channel_id}</code>\n"
                    f"💎 Mukdar: {diamond:.1f}\n"
                    f"📋 Tip: {sponsor_type}\n\n"
                    f"⚠️ Boty kanalda admin ediň!",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text("❌ Çalşyşlyk ýüze çykdy!")
        except Exception as e:
            await update.message.reply_text(
                f"❌ Nädogry format!\n\n"
                f"<b>/start kanaly üçin:</b>\n"
                f"/addsponsor @kanal_ady Kanal ady 0 required\n\n"
                f"<b>Zadanýa üçin:</b>\n"
                f"/addsponsor @kanal_ady Kanal ady 5.5 task\n\n"
                f"Hata: {e}",
                parse_mode="HTML"
            )

    # Broadcast
    elif command == "broadcast":
        try:
            # Mesajın tamamını al (komut hariç)
            message_parts = update.message.text.split(maxsplit=1)
            if len(message_parts) < 2:
                await update.message.reply_text("❌ Habar ýazyň!")
                return

            message = message_parts[1]

            users = db.get_all_user_ids()

            success = 0
            failed = 0

            status_msg = await update.message.reply_text("📣 Habar iberilýär...")

            for user_id in users:
                try:
                    # Mesajı olduğu gibi gönder
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"📢 <b>Habar:</b>\n\n{message}",
                        parse_mode="HTML"
                    )
                    success += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    failed += 1
                    logging.error(f"Broadcast hatası user {user_id}: {e}")

            await status_msg.edit_text(
                f"✅ Habar ugradyldy!\n\n"
                f"✔ Üstünlikli: {success}\n"
                f"✗ Başartmady: {failed}"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Çalşyşlyk: {e}")

    # Para çekme onaylama
    elif command == "approve":
        try:
            request_id = int(context.args[0])
            request = db.get_withdrawal_request(request_id)

            if not request:
                await update.message.reply_text("❌ Talap tapylmady!")
                return

            if request['status'] != 'pending':
                await update.message.reply_text("❌ Bu talap eýýäm işlenildi!")
                return

            db.approve_withdrawal(request_id)

            # Kullanıcıya bildirim
            try:
                await context.bot.send_message(
                    chat_id=request['user_id'],
                    text=(
                        f"✅ <b>TALAP TASSYKLANDY!</b>\n\n"
                        f"📋 Talap №: {request_id}\n"
                        f"💎 Mukdar: {request['diamond_amount']:.1f} diamond\n"
                        f"💵 Manat: {request['manat_amount']:.2f} TMT\n\n"
                        f"💰 Diamond hasabyňyzdan düşürildi.\n"
                        f"📞 Admin siz bilen ýakynda habarlaşar."
                    ),
                    parse_mode="HTML"
                )
            except:
                pass

            # KANALA BİLDİRİM GÖNDER
            try:
                announcement_text = (
                    f"✅ <b>Talap Tassyklandy!</b>\n\n"
                    f"📋 Talap №: {request_id}\n"
                    f"👤 Ulanyjy: @{request['username']}\n"
                    f"💎 Mukdar: {request['diamond_amount']:.1f} diamond\n"
                    f"💵 Manat: {request['manat_amount']:.2f} TMT\n\n"
                    f"🎉 Gutlaýarys!"
                )

                await context.bot.send_message(
                    chat_id="@diamond_labs",
                    text=announcement_text,
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Kanala bildirim gönderilemedi: {e}")

            await update.message.reply_text(
                f"✅ Talap №{request_id} tassyklandy!\n"
                f"Ulanyjy: @{request['username']}\n"
                f"Mukdar: {request['diamond_amount']:.1f} 💎 ({request['manat_amount']:.2f} TMT)"
            )
        except:
            await update.message.reply_text("❌ Nädogry format! /approve 123")

    # Para çekme reddetme
    elif command == "reject":
        try:
            request_id = int(context.args[0])
            request = db.get_withdrawal_request(request_id)

            if not request:
                await update.message.reply_text("❌ Talap tapylmady!")
                return

            if request['status'] != 'pending':
                await update.message.reply_text("❌ Bu talap eýýäm işlenildi!")
                return

            db.reject_withdrawal(request_id)

            # Kullanıcıya bildirim
            try:
                await context.bot.send_message(
                    chat_id=request['user_id'],
                    text=(
                        f"❌ <b>TALAP RET EDILDI</b>\n\n"
                        f"📋 Talap №: {request_id}\n"
                        f"💎 Mukdar: {request['diamond_amount']:.1f} diamond\n\n"
                        f"🔄 Diamond hasabyňyzda galýar.\n"
                        f"📞 Soraglar üçin admin bilen habarlaşyň: @dekanaska"
                    ),
                    parse_mode="HTML"
                )
            except:
                pass

            await update.message.reply_text(
                f"❌ Talap №{request_id} ret edildi!\n"
                f"Ulanyjy: @{request['username']}"
            )
        except:
            await update.message.reply_text("❌ Nädogry format! /reject 123")

# ============================================================================
# CALLBACK ROUTER
# ============================================================================

async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin callback'lerini yönlendir"""
    query = update.callback_query
    data = query.data

    # Admin panel callbacks
    if data == "admin_panel":
        await show_admin_panel(update, context)
    elif data == "admin_users":
        await admin_users_menu(update, context)
    elif data == "admin_withdrawals":
        await admin_withdrawals_menu(update, context)

    # Top Users callbacks
    elif data == "admin_top_users":
        await admin_top_users_menu(update, context)
    elif data == "admin_top_diamonds":
        await admin_top_diamonds(update, context)
    elif data == "admin_top_referrals":
        await admin_top_referrals(update, context)
    elif data == "admin_top_withdrawn":
        await admin_top_withdrawn(update, context)

    # Promo callbacks
    elif data == "admin_promo_create":
        await admin_promo_create_menu(update, context)
    elif data == "admin_promo_delete":
        await admin_promo_delete_menu(update, context)

    # Sponsor callbacks - YENİ
    elif data == "admin_sponsor_menu":
        await admin_sponsor_menu(update, context)
    elif data == "admin_sponsor_add_required":
        await admin_sponsor_add_required_menu(update, context)
    elif data == "admin_sponsor_add_task":
        await admin_sponsor_add_task_menu(update, context)
    elif data == "admin_sponsor_list_required":
        await admin_sponsor_list_required(update, context)
    elif data == "admin_sponsor_list_task":
        await admin_sponsor_list_task(update, context)
    elif data == "admin_sponsor_delete":
        await admin_sponsor_delete_menu(update, context)

    # Other callbacks
    elif data == "admin_stats":
        await admin_stats(update, context)
    elif data == "admin_broadcast":
        await admin_broadcast_menu(update, context)
    elif data == "admin_mass_post":
        await admin_mass_post_menu(update, context)

    # Action callbacks
    elif data.startswith("admin_approve_"):
        await admin_approve_withdrawal(update, context)
    elif data.startswith("admin_reject_"):
        await admin_reject_withdrawal(update, context)
    elif data.startswith("admin_delpromo_"):
        await admin_delete_promo(update, context)
    elif data.startswith("admin_delsponsor_"):
        await admin_delete_sponsor(update, context)
