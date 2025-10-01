from flask import Flask
import threading
import time
from bot import main as bot_main

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot Telegram è attivo!"

def run_bot():
    bot_main()

if __name__ == "__main__":
    # Avvia il bot in un thread separato
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Avvia Flask
    app.run(host='0.0.0.0', port=5000)
