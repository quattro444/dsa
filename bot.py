import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext
from datetime import datetime, timedelta
import asyncio
from threading import Thread
import json
import re

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurazione
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Database semplice (in produzione usa un database vero)
try:
    with open('user_data.json', 'r') as f:
        user_data = json.load(f)
except:
    user_data = {}

try:
    with open('reminders.json', 'r') as f:
        reminders = json.load(f)
except:
    reminders = {}

def save_data():
    with open('user_data.json', 'w') as f:
        json.dump(user_data, f)
    with open('reminders.json', 'w') as f:
        json.dump(reminders, f)

def get_user_data(user_id):
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            'todos': [],
            'remembers': [],
            'waiting_for_date': None,
            'waiting_for_time': None,
            'last_item_text': None
        }
    return user_data[user_id_str]

def parse_datetime(date_str, time_str):
    try:
        # Prova diversi formati di data
        date_formats = ['%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%Y-%m-%d']
        time_formats = ['%H:%M', '%H.%M', '%H:%M:%S']
        
        date_obj = None
        time_obj = None
        
        for fmt in date_formats:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        
        for fmt in time_formats:
            try:
                time_obj = datetime.strptime(time_str, fmt)
                break
            except ValueError:
                continue
        
        if date_obj and time_obj:
            return datetime.combine(date_obj.date(), time_obj.time())
        else:
            return None
    except:
        return None

def categorize_message(text):
    text_lower = text.lower()
    
    todo_keywords = [
        'devo', 'dovrei', 'devi', 'fare', 'completare', 'finire',
        'task', 'compito', 'lavoro', 'progetto', 'preparare',
        'scrivere', 'leggere', 'studiare', 'comprare', 'prenotare',
        'chiamare', 'inviare', 'mandare', 'consegnare', 'svolgere'
    ]
    
    remember_keywords = [
        'ricordare', 'ricorda', 'memoria', 'importante',
        'non dimenticare', 'ricordati', 'promemoria',
        'appuntamento', 'data', 'compleanno', 'anniversario',
        'memorizza', 'ricordarmi', 'non scordare'
    ]
    
    todo_count = sum(1 for keyword in todo_keywords if keyword in text_lower)
    remember_count = sum(1 for keyword in remember_keywords if keyword in text_lower)
    
    if todo_count > remember_count:
        return "todo"
    elif remember_count > todo_count:
        return "remember"
    else:
        if any(word in text_lower for word in ['dovere', 'compito', 'lavoro', 'project']):
            return "todo"
        elif any(word in text_lower for word in ['compleanno', 'anniversario', 'appuntamento']):
            return "remember"
        else:
            return "remember"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Ciao {user.first_name}! Sono il tuo assistente personale! ✨\n\n"
        "📝 **Come funziono:**\n"
        "1. Scrivi un task o promemoria\n"
        "2. Ti chiederò data e ora\n"
        "3. Ti ricorderò quando è il momento!\n\n"
        "💡 **Comandi disponibili:**\n"
        "/view_todos - Vedi to-do list\n"
        "/view_remembers - Vedi remember\n"
        "/view_reminders - Vedi tutti i promemoria\n"
        "/clear - Pulisci tutto\n"
        "/help - Aiuto"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **Formato data/ora consigliato:**\n"
        "• Data: GG/MM/AAAA (es: 25/12/2024)\n"
        "• Ora: HH:MM (es: 14:30)\n\n"
        "⏰ **Sistema di notifiche:**\n"
        "• 1° notifica: 10 minuti prima\n"
        "• 2° notifica: 5 minuti prima (se non rispondi OK)\n"
        "• 3° notifica: All'orario esatto\n\n"
        "Rispondi 'ok' per confermare e fermare le notifiche!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    user_data = get_user_data(user_id)
    
    # Se sta aspettando una data
    if user_data['waiting_for_date']:
        user_data['waiting_for_date'] = text
        await update.message.reply_text("📅 Ok! Ora mandami l'ora (formato HH:MM):")
        save_data()
        return
    
    # Se sta aspettando un'ora
    elif user_data['waiting_for_time']:
        time_str = text
        date_str = user_data['waiting_for_time']
        
        reminder_time = parse_datetime(date_str, time_str)
        
        if reminder_time:
            # Crea il promemoria
            reminder_id = f"{user_id}_{datetime.now().timestamp()}"
            reminders[reminder_id] = {
                'user_id': user_id,
                'text': user_data['last_item_text'],
                'datetime': reminder_time.isoformat(),
                'category': user_data.get('last_category', 'remember'),
                'notifications_sent': 0,
                'user_responded': False
            }
            
            # Aggiungi alla lista appropriata
            category = user_data.get('last_category', 'remember')
            if category == "todo":
                user_data['todos'].append({
                    'text': user_data['last_item_text'],
                    'datetime': reminder_time.isoformat(),
                    'reminder_id': reminder_id
                })
            else:
                user_data['remembers'].append({
                    'text': user_data['last_item_text'],
                    'datetime': reminder_time.isoformat(),
                    'reminder_id': reminder_id
                })
            
            # Reset stato
            user_data['waiting_for_date'] = None
            user_data['waiting_for_time'] = None
            user_data['last_item_text'] = None
            
            await update.message.reply_text(
                f"✅ Perfect! Ti ricorderò:\n"
                f"\"{reminders[reminder_id]['text']}\"\n"
                f"📅 Il {reminder_time.strftime('%d/%m/%Y alle %H:%M')}\n\n"
                f"Riceverai:\n"
                f"• 1 notifica 10 minuti prima\n"
                f"• 1 notifica 5 minuti prima\n"
                f"• 1 notifica all'orario esatto\n\n"
                f"Rispondi 'ok' per confermare!"
            )
            save_data()
        else:
            await update.message.reply_text("❌ Formato data/ora non valido. Riprova:\nData (GG/MM/AAAA):")
        return
    
    # Se l'utente risponde "ok" a un promemoria
    if text.lower() in ['ok', 'ok!', 'ok.', 'va bene', 'perfetto']:
        # Cerca promemoria attivi per questo utente
        user_reminders = {k: v for k, v in reminders.items() if v['user_id'] == user_id and not v['user_responded']}
        
        if user_reminders:
            for reminder_id in user_reminders:
                reminders[reminder_id]['user_responded'] = True
            await update.message.reply_text("✅ Grazie! Ho registrato la tua conferma.")
            save_data()
        return
    
    # Messaggio normale - categorizza e chiedi data/ora
    category = categorize_message(text)
    user_data['last_item_text'] = text
    user_data['last_category'] = category
    user_data['waiting_for_date'] = "waiting"  # Flag
    
    category_emoji = "✅" if category == "todo" else "📌"
    await update.message.reply_text(
        f"{category_emoji} Ho categorizzato come: {category.upper()}\n\n"
        f"📅 Ora dimmi la data (formato GG/MM/AAAA):"
    )
    save_data()

async def view_todos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data['todos']:
        await update.message.reply_text("📝 La tua to-do list è vuota!")
    else:
        todos_text = ""
        for i, todo in enumerate(user_data['todos'], 1):
            todo_time = datetime.fromisoformat(todo['datetime']).strftime('%d/%m/%Y alle %H:%M')
            todos_text += f"{i}. {todo['text']}\n   ⏰ {todo_time}\n\n"
        
        await update.message.reply_text(f"✅ LA TUA TO-DO LIST:\n\n{todos_text}")

async def view_remembers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data['remembers']:
        await update.message.reply_text("🧠 Non hai nulla da ricordare!")
    else:
        remembers_text = ""
        for i, remember in enumerate(user_data['remembers'], 1):
            remember_time = datetime.fromisoformat(remember['datetime']).strftime('%d/%m/%Y alle %H:%M')
            remembers_text += f"{i}. {remember['text']}\n   ⏰ {remember_time}\n\n"
        
        await update.message.reply_text(f"📌 COSE DA RICORDARE:\n\n{remembers_text}")

async def view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_reminders = [r for r in reminders.values() if r['user_id'] == user_id]
    
    if not user_reminders:
        await update.message.reply_text("⏰ Non hai promemoria attivi!")
    else:
        reminders_text = ""
        for i, reminder in enumerate(user_reminders, 1):
            reminder_time = datetime.fromisoformat(reminder['datetime']).strftime('%d/%m/%Y alle %H:%M')
            status = "✅ Confermato" if reminder['user_responded'] else "⏳ In attesa"
            reminders_text += f"{i}. {reminder['text']}\n   📅 {reminder_time}\n   {status}\n\n"
        
        await update.message.reply_text(f"⏰ I TUOI PROMEMORIA:\n\n{reminders_text}")

async def clear_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    if user_id_str in user_data:
        user_data[user_id_str] = {'todos': [], 'remembers': [], 'waiting_for_date': None, 'waiting_for_time': None, 'last_item_text': None}
    
    # Rimuovi i promemoria di questo utente
    reminders_to_remove = [k for k, v in reminders.items() if v['user_id'] == user_id]
    for reminder_id in reminders_to_remove:
        del reminders[reminder_id]
    
    save_data()
    await update.message.reply_text("🗑️ Tutto pulito! Liste e promemoria cancellati.")

async def check_reminders(context: CallbackContext):
    now = datetime.now()
    
    for reminder_id, reminder in list(reminders.items()):
        if reminder['user_responded']:
            continue
            
        reminder_time = datetime.fromisoformat(reminder['datetime'])
        time_diff = reminder_time - now
        
        # Notifica 1: 10 minuti prima
        if timedelta(minutes=0) < time_diff <= timedelta(minutes=10) and reminder['notifications_sent'] == 0:
            await context.bot.send_message(
                chat_id=reminder['user_id'],
                text=f"🔔 **PRIMO AVVISO**\n\n"
                     f"Tra 10 minuti: {reminder['text']}\n"
                     f"⏰ Orario: {reminder_time.strftime('%H:%M')}\n\n"
                     f"Rispondi 'OK' per confermare!"
            )
            reminder['notifications_sent'] = 1
            save_data()
        
        # Notifica 2: 5 minuti prima
        elif timedelta(minutes=0) < time_diff <= timedelta(minutes=5) and reminder['notifications_sent'] == 1:
            await context.bot.send_message(
                chat_id=reminder['user_id'],
                text=f"🔔 **SECONDO AVVISO**\n\n"
                     f"Tra 5 minuti: {reminder['text']}\n"
                     f"⏰ Orario: {reminder_time.strftime('%H:%M')}\n\n"
                     f"Rispondi 'OK' per confermare!"
            )
            reminder['notifications_sent'] = 2
            save_data()
        
        # Notifica 3: Orario esatto o fino a 5 minuti dopo
        elif timedelta(minutes=-5) <= time_diff <= timedelta(minutes=0) and reminder['notifications_sent'] == 2:
            await context.bot.send_message(
                chat_id=reminder['user_id'],
                text=f"🔔 **AVVISO IMMEDIATO**\n\n"
                     f"È il momento: {reminder['text']}\n"
                     f"⏰ Ora: {reminder_time.strftime('%H:%M')}\n\n"
                     f"Rispondi 'OK' per confermare!"
            )
            reminder['notifications_sent'] = 3
            save_data()

def main():
    # Crea l'applicazione
    application = Application.builder().token(TOKEN).build()
    
    # Aggiungi handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("view_todos", view_todos))
    application.add_handler(CommandHandler("view_remembers", view_remembers))
    application.add_handler(CommandHandler("view_reminders", view_reminders))
    application.add_handler(CommandHandler("clear", clear_all))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Aggiungi job per controllare i promemoria ogni 30 secondi
    job_queue = application.job_queue
    job_queue.run_repeating(check_reminders, interval=30, first=10)
    
    # Avvia il bot
    application.run_polling()

if __name__ == "__main__":
    main()
