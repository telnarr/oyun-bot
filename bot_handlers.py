#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Callback Handler Modülü - Tüm buton işlemleri
Güncellenmiş Versiyon - Yeni Oyun Sistemi ve Sponsor Kontrolü
"""

import asyncio
import logging
import random
import time
from collections import Counter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

# Import from bot_main
from bot_main import (
    db, Config,
    check_channel_membership,
    check_sponsor_membership,
    check_bot_admin_in_sponsor,
    can_play_game,
    get_main_menu_keyboard,
    get_earn_menu_keyboard,
    get_games_keyboard,
    show_main_menu
)

# Import from bot_admin
from bot_admin import (
    show_admin_panel,
    handle_admin_callbacks
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

    # HER İŞLEMDE AKTİVİTE GÜNCELLE - YENİ
    db.update_last_activity(user_id)

    # Ana menü
    if data == "back_main":
        await show_main_menu(update, context)

    # Kanal takibi kontrolü
    elif data.startswith("check_membership_"):
        await handle_membership_check(update, context)

    # Profil
    elif data == "menu_profile":
        await show_profile(update, context)

    # Diamond kazan menüsü
    elif data == "menu_earn":
        await show_earn_menu(update, context)

    # Oyunlar
    elif data == "earn_games":
        await show_games_menu(update, context)

    # Para çekme
    elif data == "menu_withdraw":
        await show_withdraw_menu(update, context)

    # Para çekme miktarı seçimi
    elif data.startswith("withdraw_request_"):
        await handle_withdraw_request(update, context)

    # SSS
    elif data == "menu_faq":
        await show_faq(update, context)

    # Günlük bonus
    elif data == "earn_daily_bonus":
        await claim_daily_bonus(update, context)

    # Günlük görevler (Sponsor sistemi)
    elif data == "earn_tasks":
        await show_daily_tasks(update, context)

    # Sponsor takip
    elif data.startswith("sponsor_check_"):
        await handle_sponsor_check(update, context)

    # Promo kod
    elif data == "earn_promo":
        await show_promo_input(update, context)

    elif data == "earn_promo_cancel":
        context.user_data['waiting_for_promo'] = False
        await show_earn_menu(update, context)

    # Oyunlar - Bilgi ekranı
    elif data.startswith("game_") and not data.startswith("game_play_"):
        await handle_game_info(update, context)

    # Oyun başlatma
    elif data.startswith("game_play_"):
        await handle_game_start(update, context)

    # Elma kutusu seçimi
    elif data.startswith("apple_choice_"):
        await handle_apple_choice(update, context)

    # Kazı kazan açma
    elif data.startswith("scratch_reveal_"):
        await handle_scratch_reveal(update, context)

    # Admin paneli
    elif data == "admin_panel":
        if user_id in Config.ADMIN_IDS:
            await show_admin_panel(update, context)
        else:
            await query.answer("❌ Siziň admin wezipaňiz ýok!", show_alert=True)

    # Admin işlemleri
    elif data.startswith("admin_"):
        await handle_admin_callbacks(update, context)

# ============================================================================
# KANAL TAKİBİ KONTROLÜ - GELİŞTİRİLMİŞ
# ============================================================================

async def handle_membership_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanal takibi kontrolü - Geliştirilmiş versiyon"""
    query = update.callback_query
    user = query.from_user

    # Aktivite güncelle - YENİ
    db.update_last_activity(user.id)

    referred_by = None
    if "_" in query.data:
        ref_id = query.data.split("_")[2]
        if ref_id != "0":
            try:
                referred_by = int(ref_id)
            except:
                pass

    # Tüm zorunlu kanalları kontrol et
    is_member, not_joined = await check_channel_membership(user.id, context)

    if not is_member:
        # Hangi kanalları takip etmediğini göster
        warning_text = (
            "❌ <b>Heniz ähli kanallara agza bolmadyňyz!</b>\n\n"
            "Agza bolmadyk kanallar:\n"
        )
        for channel in not_joined:
            warning_text += f"📢 {channel}\n"

        warning_text += "\n⚠️ Ähli kanallara agza boluň we täzeden synanyşyň!"

        await query.answer(
            "❌ Ähli kanallara agza boluň!",
            show_alert=True
        )

        # Mesajı güncelle
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

        await query.edit_message_text(
            warning_text,
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

        await query.edit_message_text(welcome_msg, parse_mode="HTML")
        await asyncio.sleep(2)

    await show_main_menu(update, context)

# ============================================================================
# MENÜ FONKSİYONLARI
# ============================================================================

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Profil göster"""
    query = update.callback_query
    user_id = query.from_user.id

    user_data = db.get_user(user_id)

    if not user_data:
        await query.answer("❌ Hata! /start ile başlayın", show_alert=True)
        return

    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"

    text = (
        f"👤 <b>Siziň profilyňyz</b>\n\n"
        f"🆔 ID: <code>{user_data['user_id']}</code>\n"
        f"👤 Ulanyjy: @{user_data['username']}\n"
        f"💎 Diamond: <b>{user_data['diamond']:.1f}</b>\n"
        f"👥 Referal: <b>{user_data['referral_count']}</b> adam\n"
        f"💸 Çekilen: <b>{user_data['total_withdrawn']:.1f}</b> diamond\n\n"
        f"🔗 <b>Referal adres:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"💡 Dostlaryňyzy çagyryň we bonus gazanyň!\n"
        f"🎁 Her bir referal üçin: <b>{Config.REFERAL_REWARD} diamond</b>"
    )

    keyboard = [[InlineKeyboardButton("🔙 Yza gaýt", callback_data="back_main")]]

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
        f"🎮 Oýunlary oýnaň\n"
        f"🎁 Gündelik bonus alyň\n"
        f"📋 Zadanýalary ýerine ýetiriň\n"
        f"🎟 Promo kod ulanyň\n"
        f"👥 Referal çagyryň\n\n"
        f"🚀 Haýsy usuly saýlaýaňyz?"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=get_earn_menu_keyboard()
    )

async def show_games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oyunlar menüsü - Güncellenmiş"""
    query = update.callback_query
    user_id = query.from_user.id

    user_data = db.get_user(user_id)
    balance = user_data['diamond'] if user_data else 0

    text = (
        f"🎮 <b>Oýunlar</b>\n\n"
        f"💰 Siziň balansynyz: <b>{balance:.1f} 💎</b>\n\n"
        f"🎯 <b>Almany Tap</b>\n"
        f"   • Oýnamak: 0 💎!\n"
        f"   • Gazansaň: +{Config.APPLE_BOX_WIN_REWARD} 💎\n"
        f"   • Ýitirseň: {Config.APPLE_BOX_LOSE_PENALTY} 💎\n"
        f"   • Şans: %{Config.APPLE_BOX_WIN_CHANCE}\n\n"
        f"🎰 <b>Lotereýa (Ýeňil)</b>\n"
        f"   • Oýnamak: 0 💎!\n"
        f"   • Gazansaň: +{Config.SCRATCH_EASY_WIN_REWARD} 💎\n"
        f"   • Ýitirseň: {Config.SCRATCH_EASY_LOSE_PENALTY} 💎\n"
        f"   • Şans: %{Config.SCRATCH_EASY_WIN_CHANCE}\n\n"
        f"🎰 <b>Lotereýa (Kyn)</b>\n"
        f"   • Oýnamak: 0 💎!\n"
        f"   • Gazansaň: +{Config.SCRATCH_HARD_WIN_REWARD} 💎\n"
        f"   • Ýitirseň: {Config.SCRATCH_HARD_LOSE_PENALTY} 💎\n"
        f"   • Şans: %{Config.SCRATCH_HARD_WIN_CHANCE}\n\n"
        f"🎡 <b>Şansly Aýlaw</b>\n"
        f"   • Oýnamak: 0 💎!\n"
        f"   • Täsirli baýraklar (0 → +50 💎)\n\n"
        f"⚠️ <b>Ähli oýunlarda Diamond utup bolyar!</b>\n"
        f"✅ Gazansaň diamond alýarsyň\n"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=get_games_keyboard()
    )

# ============================================================================
# OYUN SİSTEMİ - YENİ: BEDAVA AMA KAYIPLARDA CEZA
# ============================================================================

async def handle_game_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oyun bilgilerini göster - Güncellenmiş"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    user_data = db.get_user(user_id)

    if not user_data:
        await query.answer("❌ Hata! /start ile başlayın", show_alert=True)
        return

    balance = user_data['diamond']

    # Oyun tipine göre bilgi
    if data == "game_apple":
        text = (
            f"🎯 <b>Almany Tap</b>\n\n"
            f"🎮 <b>Näme oýnamaly?</b>\n"
            f"3 sany guty görkeziler. Bularyň birinde alma bar!\n"
            f"Dogry gutuny saýlasaňyz utýaňyz! 🎉\n\n"
            f"💰 <b>Giriş tölegi:</b> 0 💎!\n"
            f"💎 <b>Gazanç:</b> +{Config.APPLE_BOX_WIN_REWARD} diamond\n"
            f"⚠️ <b>Ýitirseň:</b> {Config.APPLE_BOX_LOSE_PENALTY} diamond\n"
            f"📊 <b>Şans:</b> %{Config.APPLE_BOX_WIN_CHANCE}\n\n"
            f"💰 Siziň balansynyz: <b>{balance:.1f} 💎</b>"
        )

    elif data == "game_scratch_easy":
        text = (
            f"🎰 <b>Lotereýa (Ýeňil)</b>\n\n"
            f"🎯 <b>Näme oýnamaly?</b>\n"
            f"9 sany kart bar. 4 karty açyp bilýäňiz!\n"
            f"3 sany şol bir stikeri tapsaňyz utýaňyz! 🎊🍊🍇\n\n"
            f"💰 <b>Giriş tölegi:</b> 0 💎!\n"
            f"💎 <b>Gazanç:</b> +{Config.SCRATCH_EASY_WIN_REWARD} diamond\n"
            f"⚠️ <b>Ýitirseň:</b> {Config.SCRATCH_EASY_LOSE_PENALTY} diamond\n"
            f"📊 <b>Şans:</b> %{Config.SCRATCH_EASY_WIN_CHANCE} (Ýeňil)\n\n"
            f"💰 Siziň balansynyz: <b>{balance:.1f} 💎</b>"
        )

    elif data == "game_scratch_hard":
        text = (
            f"🎰 <b>Lotereýa (Kyn)</b>\n\n"
            f"🎯 <b>Näme oýnamaly?</b>\n"
            f"9 sany kart bar. 4 karty açyp bilýäňiz!\n"
            f"3 sany şol bir stikeri tapsaňyz utýaňyz! 🎊🍊🍇🍋🍓🍉\n"
            f"⚠️ Has köp dürli miweler bar - has kyn!\n\n"
            f"💰 <b>Giriş tölegi:</b> 0 💎!\n"
            f"💎 <b>Gazanç:</b> +{Config.SCRATCH_HARD_WIN_REWARD} diamond\n"
            f"⚠️ <b>Ýitirseň:</b> {Config.SCRATCH_HARD_LOSE_PENALTY} diamond\n"
            f"📊 <b>Şans:</b> %{Config.SCRATCH_HARD_WIN_CHANCE} (Kyn)\n\n"
            f"💰 Siziň balansynyz: <b>{balance:.1f} 💎</b>"
        )

    elif data == "game_wheel":
        # Çarkıfelek için olası sonuçları göster
        rewards_display = {}
        for reward in set(Config.WHEEL_REWARDS):
            count = Config.WHEEL_REWARDS.count(reward)
            total = sum(Config.WHEEL_WEIGHTS)
            probability = (Config.WHEEL_WEIGHTS[Config.WHEEL_REWARDS.index(reward)] / total) * 100
            rewards_display[reward] = probability

        rewards_text = ""
        for reward in sorted(rewards_display.keys(), reverse=True):
            prob = rewards_display[reward]
            if reward > 0:
                rewards_text += f"   • +{reward} 💎 (şans: ~{prob:.0f}%)\n"
            elif reward == 0:
                rewards_text += f"   • 0 💎 - boş (şans: ~{prob:.0f}%)\n"
            else:
                rewards_text += f"   • {reward} 💎 - jeza (şans: ~{prob:.0f}%)\n"

        text = (
            f"🎡 <b>Şansly Aýlaw</b>\n\n"
            f"🎯 <b>Näme oýnamaly?</b>\n"
            f"Şanşly Aýlaw aýlanar we random utuş alarsyňyz!\n"
            f"Şansly bolsaňyz uly utuşlar alyp bilersiňiz! 💰\n\n"
            f"💰 <b>Giriş tölegi:</b> 0 💎!\n"
            f"🎁 <b>Mümkin bolan netijeler:</b>\n"
            f"{rewards_text}\n"
            f"💰 Siziň balansynyz: <b>{balance:.1f} 💎</b>"
        )
    else:
        text = "❌ Oýun tapylmady!"

    # Bakiye kontrolü - Oyun bedava ama bakiye 0'dan az olamaz
    can_play = can_play_game(balance)

    if not can_play:
        keyboard = [[InlineKeyboardButton("🔙 Yza gaýt", callback_data="earn_games")]]
        text += f"\n\n❌ <b>Bakiýeňiz ýeterlik däl!</b>\n💡 Ilki bilen diamond gazanyň!"
    else:
        keyboard = [
            [InlineKeyboardButton("🎮 BAŞLA!", callback_data=f"game_play_{data}")],
            [InlineKeyboardButton("🔙 Yza gaýt", callback_data="earn_games")]
        ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oyunu gerçekten başlat - Güncellenmiş"""
    query = update.callback_query
    user_id = query.from_user.id

    # game_play_game_apple -> game_apple
    game_data = query.data.replace("game_play_", "")

    user_data = db.get_user(user_id)

    if not user_data:
        await query.answer("❌ Hata! /start ile başlayın", show_alert=True)
        return

    balance = user_data['diamond']

    # Bakiye kontrolü - Oyunlar bedava ama kullanıcı 0'ın altına inemez
    if not can_play_game(balance):
        await query.answer(
            f"❌ Bakiýeňiz ýeterlik däl! Ilki bilen diamond gazanyň.",
            show_alert=True
        )
        return

    # Oyunu başlat (artık diamond düşürme yok, oyun bedava)
    if game_data == "game_apple":
        await play_apple_box_game(update, context)
    elif game_data == "game_scratch_easy":
        await play_scratch_game(update, context, "easy")
    elif game_data == "game_scratch_hard":
        await play_scratch_game(update, context, "hard")
    elif game_data == "game_wheel":
        await play_wheel_game(update, context)

# ============================================================================
# ELMA KUTUSU OYUNU - GÜNCELLENMİŞ
# ============================================================================

async def play_apple_box_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kutudaki Elmayı Bul oyunu - Bedava ama kayıplarda ceza"""
    query = update.callback_query
    user_id = query.from_user.id

    # Animasyon
    await query.edit_message_text("🎁 Oýun başlaýar...")
    await asyncio.sleep(1)

    await query.edit_message_text("📦 Gutular taýýarlanýar...")
    await asyncio.sleep(1)

    await query.edit_message_text("🔄 Gutular garyşdyrylýar...")
    await asyncio.sleep(1.5)

    # Elma konumu rastgele
    apple_pos = random.randint(0, 2)

    keyboard = [[
        InlineKeyboardButton("📦 1", callback_data=f"apple_choice_0_{apple_pos}"),
        InlineKeyboardButton("📦 2", callback_data=f"apple_choice_1_{apple_pos}"),
        InlineKeyboardButton("📦 3", callback_data=f"apple_choice_2_{apple_pos}")
    ]]

    await query.edit_message_text(
        "🎮 <b>Almany Tap</b>\n\n"
        "🎯 Alma haýsy gutuda? Saýlaň!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_apple_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kutu seçimi - Güncellenmış ödül sistemi"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data.split("_")
    choice = int(data[2])
    apple_pos = int(data[3])

    # Animasyon
    await query.edit_message_text("📦 Gutu açylýar...")
    await asyncio.sleep(1.5)

    if choice == apple_pos:
        # Kazandı - Diamond ekle
        reward = Config.APPLE_BOX_WIN_REWARD
        db.update_diamond(user_id, reward)

        await query.edit_message_text(
            f"🎉 <b>GUTLAÝARYS!</b>\n\n"
            f"🎯 Almany tapdyňyz!\n"
            f"💎 Gazanç: <b>+{reward} diamond</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎮 Täzeden oýnamak", callback_data="game_play_game_apple"),  # ← DÜZELTME BURASI
                InlineKeyboardButton("🔙 Oýunlar", callback_data="earn_games")
            ]])
        )
    else:
        # Kaybetti - Diamond düş
        penalty = Config.APPLE_BOX_LOSE_PENALTY
        db.update_diamond(user_id, penalty)

        result_list = ["❌", "❌", "❌"]
        result_list[apple_pos] = "🎯"
        result_text = " ".join(result_list)

        await query.edit_message_text(
            f"😢 <b>Gynandyryjy...</b>\n\n"
            f"{result_text}\n\n"
            f"🎯 Alma bu gutuda däldi!\n"
            f"💎 Ýitirilen: <b>{penalty} diamond</b>\n"
            f"💪 Täzeden synanyşyň!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎮 Täzeden oýnamak", callback_data="game_play_game_apple"),  # ← DÜZELTME BURASI
                InlineKeyboardButton("🔙 Oýunlar", callback_data="earn_games")
            ]])
        )

# ============================================================================
# KAZI KAZAN OYUNU - GÜNCELLENMİŞ
# ============================================================================

async def play_scratch_game(update: Update, context: ContextTypes.DEFAULT_TYPE, difficulty: str):
    """Kazı Kazan oyunu - Bedava ama kayıplarda ceza"""
    query = update.callback_query

    await query.edit_message_text("🎰 Lotereýa taýýarlanýar...")
    await asyncio.sleep(1)

    # Zorluk ayarları
    if difficulty == "easy":
        fruits = ["🍎", "🍊", "🍇"]
        distribution = [4, 3, 2]
    else:  # hard
        fruits = ["🍎", "🍊", "🍇", "🍋", "🍓", "🍉"]
        distribution = [3, 1, 1, 1, 1, 2]

    # Kartları oluştur
    cards = []
    for fruit, count in zip(fruits, distribution):
        cards.extend([fruit] * count)
    random.shuffle(cards)

    # Oyun durumunu sakla
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
        f"🎰 <b>Lotereýa</b>\n\n"
        f"🎯 3 sany şol bir miweden tapyň!\n"
        f"🎫 Galan synanyşyk: <b>{attempts}</b>"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_scratch_reveal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kazı Kazan kartını aç - Güncellenmiş ödül sistemi"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    idx = int(query.data.split("_")[2])

    revealed = context.user_data.get('scratch_revealed', [])

    if revealed[idx]:
        return

    revealed[idx] = True
    context.user_data['scratch_revealed'] = revealed
    context.user_data['scratch_attempts'] -= 1

    attempts = context.user_data['scratch_attempts']
    cards = context.user_data['scratch_cards']

    # Önce tahtayı güncelle
    await show_scratch_board(update, context)

    # Kazanma kontrolü
    revealed_cards = [cards[i] for i, r in enumerate(revealed) if r]

    counts = Counter(revealed_cards)

    won = False
    winning_fruit = None
    for fruit, count in counts.items():
        if count >= 3:
            won = True
            winning_fruit = fruit
            break

    # Eğer oyun bittiyse (kazandı veya denemeler bitti)
    if won or attempts == 0:
        # Kısa bir bekleme
        await asyncio.sleep(1)

        difficulty = context.user_data['scratch_difficulty']

        if won:
            # Kazandı - Diamond ekle
            reward = Config.SCRATCH_EASY_WIN_REWARD if difficulty == "easy" else Config.SCRATCH_HARD_WIN_REWARD
            db.update_diamond(user_id, reward)

            # Tüm kartları göster
            context.user_data['scratch_revealed'] = [True] * 9
            await show_scratch_board(update, context)

            await asyncio.sleep(0.5)

            await query.message.reply_text(
                f"🎉 <b>GUTLAÝARYS!</b>\n\n"
                f"🎰 3 sany {winning_fruit} tapdyňyz!\n"
                f"💎 Gazanç: <b>+{reward} diamond</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Oýunlar", callback_data="earn_games")
                ]])
            )
        else:
            # Kaybetti - Diamond düş
            penalty = Config.SCRATCH_EASY_LOSE_PENALTY if difficulty == "easy" else Config.SCRATCH_HARD_LOSE_PENALTY
            db.update_diamond(user_id, penalty)

            # Tüm kartları göster
            context.user_data['scratch_revealed'] = [True] * 9
            await show_scratch_board(update, context)

            await asyncio.sleep(0.5)

            await query.message.reply_text(
                f"😢 <b>Gynandyryjy...</b>\n\n"
                f"🎫 Tapyp bilmediňiz!\n"
                f"💎 Ýitirilen: <b>{penalty} diamond</b>\n"
                f"💪 Täzeden synanyşyň!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Oýunlar", callback_data="earn_games")
                ]])
            )

# ============================================================================
# ÇARK OYUNU - GÜNCELLENMİŞ OLASILIKLAR
# ============================================================================

async def play_wheel_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Çarkı Felek oyunu - Animasyonlu ve Olasılıklı"""
    query = update.callback_query
    user_id = query.from_user.id

    rewards = Config.WHEEL_REWARDS
    weights = Config.WHEEL_WEIGHTS

    # Animasyon - ödülleri göster
    await query.edit_message_text("🎡 <b>Şansly Aýlaw taýýarlanýar...</b>", parse_mode="HTML")
    await asyncio.sleep(1)

    # Çarkta ne var göster
    rewards_text = "🎡 <b>Aýlawdaky baýraklar:</b>\n\n"
    for reward in sorted(set(rewards), reverse=True):
        if reward > 0:
            rewards_text += f"💎 +{reward} diamond\n"
        elif reward == 0:
            rewards_text += f"❌ 0 diamond (boş)\n"
        else:
            rewards_text += f"⚠️ {reward} diamond (jeza)\n"

    await query.edit_message_text(rewards_text, parse_mode="HTML")
    await asyncio.sleep(2)

    # Çark dönüyor
    spin_frames = [
        "🎡 aýlanýar...\n\n🔄",
        "🎡 aýlanýar...\n\n🔄 💎",
        "🎡 aýlanýar...\n\n🔄 +3 💎",
        "🎡 aýlanýar...\n\n🔄 💎 +5",
        "🎡 aýlanýar...\n\n🔄 0 💎",
        "🎡 aýlanýar...\n\n🔄 💎 -1",
        "🎡 aýlanýar...\n\n🔄 -2 💎",
        "🎡 aýlanýar...\n\n🔄 💎 +8",
        "🎡 aýlanýar...\n\n🔄 +2 💎",
    ]

    for frame in spin_frames:
        await query.edit_message_text(frame, parse_mode="HTML")
        await asyncio.sleep(0.4)

    await query.edit_message_text("🎡 <b>Aýlaw haýallaýar...</b>", parse_mode="HTML")
    await asyncio.sleep(1)

    await query.edit_message_text("🎡 <b>Aýlaw durdy...</b>", parse_mode="HTML")
    await asyncio.sleep(1)

    # Sonuç seç - AĞIRLIKLI RASTGELE
    result = random.choices(rewards, weights=weights)[0]

    # Sonucu uygula
    db.update_diamond(user_id, result)

    if result > 0:
        emoji = "🎉"
        message = f"GUTLAÝARYS! +{result} diamond gazandyňyz!"
    elif result == 0:
        emoji = "😐"
        message = "Bu gezek hiç zat çykmady!"
    else:  # ceza
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
# SLOT OYUNU - DÜZELTİLMİŞ VERSİYON
# ============================================================================

async def play_slot_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Slot oyunu - Sadece belirli grupta çalışır"""
    message = update.message
    user_id = message.from_user.id
    chat_id = message.chat_id

    # Sadece belirli grupta oynansın
    if str(chat_id) != str(Config.SLOT_CHAT_ID):
        return

    # ✅ AKTİVİTE GÜNCELLE - EKLENDİ
    db.update_last_activity(user_id)

    # Kullanıcı bilgilerini al
    user_data = db.get_user(user_id)

    if not user_data:
        await message.reply_text(
            "⚠️ İlki boty ulanmaly bolýaňyz: @gazandyryan_bot",
            reply_to_message_id=message.message_id
        )
        return

    balance = user_data['diamond']

    # Bakiye kontrolü (0'ın altına inemez)
    if balance < 0:
        await message.reply_text(
            f"❌ <b>Hasabyňyz ýeterlik däl!</b>\n"
            f"💎 Häzirki balans: <b>{balance:.1f} diamond</b>\n\n"
            f"💡 Diamond gazanmak üçin bota giriň!",
            parse_mode="HTML",
            reply_to_message_id=message.message_id
        )
        return

    # Animasyon başlat
    animation_msg = await message.reply_text(
        "🎰 <b>SLOT çark aýlanýar...</b>",
        parse_mode="HTML",
        reply_to_message_id=message.message_id
    )

    # Slot emojileri (sadece 7 ve meyveler)
    slot_symbols = ["🍎", "🍋", "🍊", "🍉", "🍇", "7️⃣"]

    # Animasyon frameleri (hızlı değişim)
    for _ in range(8):
        frame = " ".join([random.choice(slot_symbols) for _ in range(3)])
        try:
            await animation_msg.edit_text(
                f"🎰 <b>SLOT</b>\n\n"
                f"[ {frame} ]\n\n"
                f"💫 Aýlanýar...",
                parse_mode="HTML"
            )
        except:
            pass  # Rate limit hatalarını yoksay
        await asyncio.sleep(0.3)

    # Sonucu belirle - Şans kontrolü
    is_winner = random.randint(1, 100) <= Config.SLOT_WIN_CHANCE

    if is_winner:
        # Kazandı - 7️⃣ 7️⃣ 7️⃣
        result = ["7️⃣", "7️⃣", "7️⃣"]
        reward = Config.SLOT_WIN_REWARD
        db.update_diamond(user_id, reward)

        result_text = (
            f"🎰 <b>SLOT</b>\n\n"
            f"[ 7️⃣ 7️⃣ 7️⃣ ]\n\n"
            f"🎉 <b>GUTLAÝARYS!</b>\n"
            f"💎 Gazanç: <b>+{reward:.1f} diamond</b>\n"
            f"💰 Täze balans: <b>{balance + reward:.1f} diamond</b>"
        )

        # Kazananı duyur (opsiyonel)
        try:
            await context.bot.send_message(
                chat_id=Config.SLOT_CHAT_ID,
                text=(
                    f"🏆 <b>ÝEŇIJI!</b>\n\n"
                    f"👤 @{message.from_user.username or message.from_user.first_name}\n"
                    f"🎰 777 tapdy!\n"
                    f"💎 Gazanç: <b>+{reward:.1f} diamond</b>"
                ),
                parse_mode="HTML"
            )
        except:
            pass
    else:
        # Kaybetti - Rastgele ama 777 değil
        result = []
        for _ in range(3):
            symbol = random.choice(slot_symbols)
            result.append(symbol)

        # Eğer 3'ü de aynıysa, birini değiştir
        if result[0] == result[1] == result[2]:
            result[2] = random.choice([s for s in slot_symbols if s != result[0]])

        reward = Config.SLOT_LOSE_PENALTY
        db.update_diamond(user_id, reward)

        result_text = (
            f"🎰 <b>SLOT</b>\n\n"
            f"[ {' '.join(result)} ]\n\n"
            f"😢 <b>Gynandyryjy...</b>\n"
            f"💎 Ýitirilen: <b>{reward} diamond</b>\n"
            f"💰 Täze balans: <b>{balance + reward:.1f} diamond</b>\n"
            f"💪 Täzeden synanyşyň!"
        )

    try:
        await animation_msg.edit_text(result_text, parse_mode="HTML")
    except:
        # Eğer edit başarısız olursa yeni mesaj gönder
        await message.reply_text(result_text, parse_mode="HTML")

    # İstatistik kaydet (opsiyonel)
    # db.log_slot_play(user_id, "".join(result), reward)
# ============================================================================
# PARA ÇEKME SİSTEMİ
# ============================================================================

async def show_withdraw_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Para çekme menüsü"""
    query = update.callback_query
    user_id = query.from_user.id

    user_data = db.get_user(user_id)

    if not user_data:
        await query.answer("❌ Hata! /start ile başlayın", show_alert=True)
        return

    can_withdraw = (
        user_data['diamond'] >= Config.MIN_WITHDRAW_DIAMOND and
        user_data['referral_count'] >= Config.MIN_REFERRAL_COUNT
    )

    text = (
        f"💰 <b>Pul Çekmek</b>\n\n"
        f"💎 Siziň balansynyz: <b>{user_data['diamond']:.1f} diamond</b>\n"
        f"💵 Manat görnüşinde: <b>{user_data['diamond'] / Config.DIAMOND_TO_MANAT:.2f} TMT</b>\n\n"
        f"📋 <b>Şertler:</b>\n"
        f"   • Minimum: {Config.MIN_WITHDRAW_DIAMOND} 💎\n"
        f"   • Azyndan {Config.MIN_REFERRAL_COUNT} referal çagyrm aly\n"
        f"   • {Config.DIAMOND_TO_MANAT} diamond = 1 manat\n\n"
    )

    keyboard = []

    if can_withdraw:
        text += f"✅ Siz pul çekip bilersiňiz!\n\n"
        text += f"💎 <b>Çekmek isleýän mukdaryňyzy saýlaň:</b>"

        # Para çekme seçenekleri
        withdraw_buttons = []
        for amount in Config.WITHDRAW_OPTIONS:
            if user_data['diamond'] >= amount:
                manat = amount / Config.DIAMOND_TO_MANAT
                withdraw_buttons.append(
                    InlineKeyboardButton(
                        f"💎 {amount:.0f} ({manat:.1f} TMT)",
                        callback_data=f"withdraw_request_{amount}"
                    )
                )

        # Her satırda 2 buton
        for i in range(0, len(withdraw_buttons), 2):
            keyboard.append(withdraw_buttons[i:i+2])
    else:
        reasons = []
        if user_data['diamond'] < Config.MIN_WITHDRAW_DIAMOND:
            reasons.append(f"❌ Ýeterlik diamond ýok ({Config.MIN_WITHDRAW_DIAMOND} gerek)")
        if user_data['referral_count'] < Config.MIN_REFERRAL_COUNT:
            reasons.append(f"❌ Azyndan {Config.MIN_REFERRAL_COUNT} referal çagyrmalysynyz")

        text += "\n".join(reasons)

    keyboard.append([InlineKeyboardButton("🔙 Yza gaýt", callback_data="back_main")])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_withdraw_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Para çekme talebini işle"""
    query = update.callback_query
    user_id = query.from_user.id

    amount_str = query.data.split("_")[2]
    amount = float(amount_str)

    user_data = db.get_user(user_id)

    if not user_data:
        await query.answer("❌ Hata! /start ile başlayın", show_alert=True)
        return

    # Son kontroller
    if user_data['diamond'] < amount:
        await query.answer("❌ Ýeterlik diamond ýok!", show_alert=True)
        return

    if user_data['referral_count'] < Config.MIN_REFERRAL_COUNT:
        await query.answer(f"❌ Azyndan {Config.MIN_REFERRAL_COUNT} referal çagyrmalysynyz!", show_alert=True)
        return

    # Para çekme talebini oluştur
    manat_amount = amount / Config.DIAMOND_TO_MANAT
    request_id = db.create_withdrawal_request(
        user_id,
        user_data['username'],
        amount,
        manat_amount
    )

    # Kullanıcıya bildirim
    await query.edit_message_text(
        f"✅ <b>Talap döredildi!</b>\n\n"
        f"📋 Talap №: <code>{request_id}</code>\n"
        f"💎 Mukdar: <b>{amount:.1f} diamond</b>\n"
        f"💵 Manat: <b>{manat_amount:.2f} TMT</b>\n\n"
        f"⏳ Admin siziň talabyňyzy gözden geçirer we siz bilen habarlaşar.\n\n"
        f"⚠️ Talap kabul edilende diamond hasabyňyzdan düşüriler.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="back_main")
        ]])
    )

    # Admin'e bildirim
    for admin_id in Config.ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"💰 <b>TÄZE PUL ÇEKMEK TALABY!</b>\n\n"
                    f"📋 Talap №: <code>{request_id}</code>\n"
                    f"👤 Ulanyjy: @{user_data['username']} (ID: {user_id})\n"
                    f"💎 Mukdar: <b>{amount:.1f} diamond</b>\n"
                    f"💵 Manat: <b>{manat_amount:.2f} TMT</b>\n\n"
                    f"Talapy işlemek üçin:\n"
                    f"/approve {request_id} - Tassyklamak\n"
                    f"/reject {request_id} - Ret etmek"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Admin bildirimi gönderilemedi: {e}")

# ============================================================================
# GÜNLÜK GÖREVLER - SPONSOR SİSTEMİ GELİŞTİRİLMİŞ
# ============================================================================

async def show_daily_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Günlük görevler menüsü - Geliştirilmiş"""
    query = update.callback_query
    user_id = query.from_user.id

    # Günlük reset kontrolü
    if db.check_daily_task_reset(user_id):
        db.reset_user_daily_tasks(user_id)

    # Bir sonraki sponsoru getir
    sponsor = db.get_user_next_sponsor(user_id)

    if not sponsor:
        await query.edit_message_text(
            "📋 <b>Gündelik Zadanýalar</b>\n\n"
            "✅ <b>Gutlaýarys!</b> Ähli zadanýalary tamamladyňyz!\n\n"
            "🎁 Täze zadanýalar gelýänçä garaşyň.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="menu_earn")
            ]])
        )
        return

    # Botun bu kanalda admin olup olmadığını kontrol et
    is_bot_admin = await check_bot_admin_in_sponsor(sponsor['sponsor_id'], context)

    text = (
        f"📋 <b>Gündelik Zadanýalar</b>\n\n"
        f"📢 <b>{sponsor['channel_name']}</b>\n"
        f"💎 Baýrak: <b>+{sponsor['diamond_reward']:.1f} diamond</b>\n\n"
    )

    if not is_bot_admin:
        text += (
            f"⚠️ <b>DİKKAT!</b>\n"
            f"Bot bu kanalda admin däl. Üýtgeme bolmasa admina habar berildi.\n\n"
        )

    text += f"👇 Kanala agza boluň we 'Agza Boldum' düwmesine basyň!"

    keyboard = [
        [InlineKeyboardButton(
            f"📢 {sponsor['channel_name']} - Açmak",
            url=f"https://t.me/{sponsor['channel_id'].replace('@', '')}"
        )],
        [InlineKeyboardButton(
            "✅ Agza Boldum",
            callback_data=f"sponsor_check_{sponsor['sponsor_id']}"
        )],
        [InlineKeyboardButton("🔙 Yza gaýt", callback_data="menu_earn")]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_sponsor_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sponsor takip kontrolü - Geliştirilmiş"""
    query = update.callback_query
    user_id = query.from_user.id

    sponsor_id = int(query.data.split("_")[2])

    # Sponsor bilgilerini getir
    sponsor = db.get_sponsor_by_id(sponsor_id)

    if not sponsor:
        await query.answer("❌ Sponsor tapylmady!", show_alert=True)
        return

    # Üyelik kontrolü
    is_member = await check_sponsor_membership(user_id, sponsor['channel_id'], context)

    if not is_member:
        await query.answer(
            f"❌ Ilki bilen {sponsor['channel_name']} takip ediň!",
            show_alert=True
        )
        return

    # Ödülü ver
    if db.complete_sponsor(user_id, sponsor_id):
        db.update_diamond(user_id, sponsor['diamond_reward'])

        await query.answer(
            f"✅ +{sponsor['diamond_reward']:.1f} 💎 aldyňyz!",
            show_alert=True
        )

        # Otomatik bir sonraki sponsoru göster
        await show_daily_tasks(update, context)
    else:
        await query.answer("❌ Bu zadanýany tamamladyňyz!", show_alert=True)

# ============================================================================
# PROMO KOD SİSTEMİ
# ============================================================================

async def show_promo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo kod girişi"""
    query = update.callback_query

    context.user_data['waiting_for_promo'] = True

    await query.edit_message_text(
        "🎟 <b>Promo Kod</b>\n\n"
        "💎 Promo kodyňyzy ýazyň:\n\n"
        "Mysal: <code>BONUS2026</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="earn_promo_cancel")
        ]])
    )

async def handle_promo_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promo kod mesajını işle"""
    # Güvenli kontrol - context.user_data None olabilir
    if not context.user_data:
        return

    if not context.user_data.get('waiting_for_promo'):
        return

    user_id = update.effective_user.id

    # Aktivite güncelle - YENİ
    db.update_last_activity(user_id)

    promo_code = update.message.text.strip().upper()

    result = db.use_promo_code(promo_code, user_id)

    if result is None:
        await update.message.reply_text(
            "❌ <b>Çalışmaýan kod!</b>\n\n"
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
            f"💎 Siz <b>{result:.1f} diamond</b> aldyňyz!\n"
            f"🎟 Kod: <code>{promo_code}</code>",
            parse_mode="HTML"
        )

    context.user_data['waiting_for_promo'] = False


# ============================================================================
# DİĞER FONKSİYONLAR
# ============================================================================

async def show_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SSS göster"""
    query = update.callback_query

    text = (
        f"❓ <b>Ýygy-ýygydan soralýan soraglar</b>\n\n"
        f"<b>🎮 Näme oýnamaly?</b>\n"
        f"Oýunlary saýlap oýnaň! Gazansaňyz diamond alýarsyňyz, ýitirseňiz azalýar.\n\n"
        f"<b>💎 Diamond näme gazanmaly?</b>\n"
        f"• Oýunlar oýnaň\n"
        f"• Gündelik bonus alyň\n"
        f"• Zadanýalary ýerine ýetiriň\n"
        f"• Referalyňyz bilen adam çagryň ({Config.REFERAL_REWARD} 💎 bonus)\n"
        f"• Promo kodlary ulanyň\n\n"
        f"<b>💰 Pul näme çekmeli?</b>\n"
        f"• Azyndan {Config.MIN_WITHDRAW_DIAMOND} diamond jemlemeli\n"
        f"• {Config.MIN_REFERRAL_COUNT} adam çagyrm aly\n"
        f"• 'Pul çekmek' bölüminden talap döretmeli\n"
        f"• Admin siz bilen habarlaşýar\n\n"
        f"<b>🔒 Howpsuzlyk</b>\n"
        f"Siziň maglumatlarňyz goragly saklanýar. Hiç bir üçünji tarapa berilmeýär.\n\n"
        f"<b>📞 Goldaw</b>\n"
        f"Soraglaryňyz bar bolsa: @alpen_silver"
    )

    keyboard = [[InlineKeyboardButton("🔙 Yza gaýt", callback_data="back_main")]]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def claim_daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Günlük bonus al"""
    query = update.callback_query
    user_id = query.from_user.id

    user_data = db.get_user(user_id)

    if not user_data:
        await query.answer("❌ Hata! /start ile başlayın", show_alert=True)
        return

    current_time = int(time.time())
    time_since_last = current_time - user_data['last_bonus_time']

    if time_since_last < Config.DAILY_BONUS_COOLDOWN:
        remaining = Config.DAILY_BONUS_COOLDOWN - time_since_last
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60

        await query.answer(
            f"⏰ Indiki bonusa {hours} sagat {minutes} minut galdy!",
            show_alert=True
        )

        await query.edit_message_text(
            f"⏰ <b>Garaşyň!</b>\n\n"
            f"🎁 Gündelik bonusynyzy eýýäm aldyňyz!\n\n"
            f"⏳ Indiki bonus: <b>{hours} sagat {minutes} minut</b> soň\n"
            f"💎 Bonus mukdary: <b>{Config.DAILY_BONUS_AMOUNT:.1f} diamond</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Yza gaýt", callback_data="menu_earn")
            ]])
        )
        return

    # Bonus ver
    db.update_diamond(user_id, Config.DAILY_BONUS_AMOUNT)
    db.set_last_bonus_time(user_id)

    await query.edit_message_text(
        f"🎁 <b>Gutlaýarys!</b>\n\n"
        f"💎 Siz <b>{Config.DAILY_BONUS_AMOUNT:.1f} diamond</b> aldyňyz!\n\n"
        f"⏰ Indiki bonus üçin 24 sagatdan soň geliň.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Yza gaýt", callback_data="menu_earn")
        ]])
    )
