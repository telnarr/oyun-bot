#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Admin Panel Modülü - Gelişmiş Yönetim Sistemi
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
    """Admin panelini göster"""
    query = update.callback_query

    keyboard = [
        [InlineKeyboardButton("👥 Ulanyjylar", callback_data="admin_users")],
        [InlineKeyboardButton("💰 Pul çekme talaplary", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("🏆 Top Ulanyjylar", callback_data="admin_top_users")],
        [InlineKeyboardButton("🎟 Promo kod döret", callback_data="admin_promo_create")],
        [InlineKeyboardButton("🗑 Promo kod poz", callback_data="admin_promo_delete")],
        [InlineKeyboardButton("📢 Sponsor goş", callback_data="admin_sponsor_add")],
        [InlineKeyboardButton("🗑 Sponsor poz", callback_data="admin_sponsor_delete")],
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📣 Hemmä habar", callback_data="admin_broadcast")],
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
        "👥 <b>Ulanyjy dolandyryşy</b>\n\n"
        "Ulanyjy ID ýazyň:\n"
        "• Diamond goşmak üçin: /adddia 123456789 10\n"
        "• Diamond aýyrmak üçin: /remdia 123456789 5\n"
        "• Ulanyjy maglumatyny görmek: /userinfo 123456789\n"
        "• Ulanyjyny ban etmek: /banuser 123456789\n"
        "• Ban aýyrmak: /unbanuser 123456789"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")
        ]])
    )

# ============================================================================
# TOP KULLANICILAR - YENİ ÖZELLİK
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
        username = f"@{user['username']}" if user.get('username') else f"ID: {user['user_id']}"
        text += f"{medal} {username}\n   💎 <b>{user['diamond']}</b> diamond\n\n"

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
        # Database'den en çok referral'a sahip kullanıcıları çek
        top_users = db.get_top_users_by_referral(limit=10)
    except AttributeError:
        # Eğer fonksiyon yoksa manuel query
        try:
            query_sql = """
                SELECT user_id, username, referral_count 
                FROM users 
                WHERE is_banned = 0
                ORDER BY referral_count DESC 
                LIMIT 10
            """
            top_users = db.execute_query(query_sql)
        except:
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
        # Database'den en çok para çeken kullanıcıları çek
        top_users = db.get_top_users_by_withdrawn(limit=10)
    except AttributeError:
        # Eğer fonksiyon yoksa manuel query
        try:
            query_sql = """
                SELECT user_id, username, total_withdrawn 
                FROM users 
                WHERE is_banned = 0
                ORDER BY total_withdrawn DESC 
                LIMIT 10
            """
            top_users = db.execute_query(query_sql)
        except:
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
        manat = user['total_withdrawn'] / Config.DIAMOND_TO_MANAT
        text += f"{medal} {username}\n   💸 <b>{user['total_withdrawn']}</b> diamond ({manat:.2f} TMT)\n\n"

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
            f"💎 {req['diamond_amount']} diamond ({req['manat_amount']:.2f} TMT)\n\n"
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
                f"💎 Mukdar: {request['diamond_amount']} diamond\n"
                f"💵 Manat: {request['manat_amount']:.2f} TMT\n\n"
                f"💰 Diamond hasabyňyzdan düşürildi.\n"
                f"📞 Admin siz bilen ýakynda habarlaşar."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Kullanıcıya bildirim gönderilemedi: {e}")

    # KANALA BİLDİRİM GÖNDER - YENİ ÖZELLİK
    try:
        announcement_text = (
            f"✅ <b>Talap Tassyklandy!</b>\n\n"
            f"📋 Talap №: {request_id}\n"
            f"👤 Ulanyjy: @{request['username']}\n"
            f"💎 Mukdar: {request['diamond_amount']} diamond\n"
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
                f"💎 Mukdar: {request['diamond_amount']} diamond\n\n"
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
        "Mysal: /createpromo BONUS2026 15 50\n"
        "(15 diamond berýär, 50 gezek ulanyp bolýar)"
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

    text = "🎟 <b>Promo Kodlar - Pozmak üçin saýlañ:</b>\n\n"

    keyboard = []
    for promo in promo_codes:
        text += (
            f"🔹 <code>{promo['code']}</code>\n"
            f"   💎 {promo['diamond_reward']} diamond\n"
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
# SPONSOR YÖNETİMİ
# ============================================================================

async def admin_sponsor_add_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sponsor ekleme menüsü"""
    query = update.callback_query

    text = (
        "📢 <b>Sponsor Goşmak</b>\n\n"
        "Täze sponsor goşmak üçin:\n"
        "/addsponsor @kanal_ady Kanal ady 5\n\n"
        "Mysal:\n"
        "/addsponsor @my_channel Meniň kanalym 3\n"
        "(3 diamond berýär)"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")
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
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")
            ]])
        )
        return

    text = "📢 <b>Sponsorlar - Pozmak üçin saýlañ:</b>\n\n"

    keyboard = []
    for sponsor in sponsors:
        text += (
            f"🔹 <b>{sponsor['channel_name']}</b>\n"
            f"   📢 {sponsor['channel_id']}\n"
            f"   💎 {sponsor['diamond_reward']} diamond\n\n"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"🗑 {sponsor['channel_name']} - Pozmak",
                callback_data=f"admin_delsponsor_{sponsor['sponsor_id']}"
            )
        ])

    keyboard.append([InlineKeyboardButton("🔙 Yza gaýt", callback_data="admin_panel")])

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
        f"💎 Jemi diamond: <b>{stats['total_diamonds']}</b>\n"
        f"💸 Jemi çekilen: <b>{stats['total_withdrawn']}</b> diamond\n"
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
# BROADCAST
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
        "Mesaj içinde satır atlamaları ve boşluklar korunur.\n"
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
            amount = int(context.args[1])

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

            db.update_diamond(target_user, -amount)

            await update.message.reply_text(
                f"✅ {target_user} ID-li ulanyjynyň hasabyndan {amount} 💎 aýyryldy!"
            )
        except:
            await update.message.reply_text("❌ Nädogry format! /remdia 123456789 5")

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
                    f"💎 Diamond: {user_data['diamond']}\n"
                    f"👥 Referal: {user_data['referral_count']}\n"
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

            success = db.create_promo_code(code, diamond, max_uses)

            if success:
                await update.message.reply_text(
                    f"✅ Promo kod döredildi!\n\n"
                    f"🎟 Kod: <code>{code}</code>\n"
                    f"💎 Mukdar: {diamond}\n"
                    f"🔢 Ulanyş sany: {max_uses}",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text("❌ Bu kod eýýäm bar!")
        except:
            await update.message.reply_text("❌ Nädogry format! /createpromo KOD 10 100")

    # Sponsor ekleme
    elif command == "addsponsor":
        try:
            channel_id = context.args[0]
            diamond = int(context.args[-1])
            channel_name = " ".join(context.args[1:-1])

            success = db.add_sponsor(channel_id, channel_name, diamond)

            if success:
                await update.message.reply_text(
                    f"✅ Sponsor goşuldy!\n\n"
                    f"📢 Kanal: {channel_name}\n"
                    f"🆔 ID: <code>{channel_id}</code>\n"
                    f"💎 Mukdar: {diamond}",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text("❌ Çalşyşlyk ýüze çykdy!")
        except:
            await update.message.reply_text(
                "❌ Nädogry format!\n"
                "/addsponsor @kanal_ady Kanal ady 5"
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
                        f"💎 Mukdar: {request['diamond_amount']} diamond\n"
                        f"💵 Manat: {request['manat_amount']:.2f} TMT\n\n"
                        f"💰 Diamond hasabyňyzdan düşürildi.\n"
                        f"📞 Admin siz bilen ýakynda habarlaşar."
                    ),
                    parse_mode="HTML"
                )
            except:
                pass

            # KANALA BİLDİRİM GÖNDER - YENİ ÖZELLİK
            try:
                announcement_text = (
                    f"✅ <b>Talap Tassyklandy!</b>\n\n"
                    f"📋 Talap №: {request_id}\n"
                    f"👤 Ulanyjy: @{request['username']}\n"
                    f"💎 Mukdar: {request['diamond_amount']} diamond\n"
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
                f"Mukdar: {request['diamond_amount']} 💎 ({request['manat_amount']:.2f} TMT)"
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
                        f"💎 Mukdar: {request['diamond_amount']} diamond\n\n"
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
    
    # Top Users callbacks - YENİ
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
    
    # Sponsor callbacks
    elif data == "admin_sponsor_add":
        await admin_sponsor_add_menu(update, context)
    elif data == "admin_sponsor_delete":
        await admin_sponsor_delete_menu(update, context)
    
    # Other callbacks
    elif data == "admin_stats":
        await admin_stats(update, context)
    elif data == "admin_broadcast":
        await admin_broadcast_menu(update, context)
    
    # Action callbacks
    elif data.startswith("admin_approve_"):
        await admin_approve_withdrawal(update, context)
    elif data.startswith("admin_reject_"):
        await admin_reject_withdrawal(update, context)
    elif data.startswith("admin_delpromo_"):
        await admin_delete_promo(update, context)
    elif data.startswith("admin_delsponsor_"):
        await admin_delete_sponsor(update, context)
