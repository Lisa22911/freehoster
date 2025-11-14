import os
import zipfile
import tempfile
import subprocess
import logging
from flask import Flask, request
import telegram
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
import threading
import time
import shutil

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
PORT = int(os.environ.get('PORT', 8443))
HEROKU_APP_NAME = os.environ.get('HEROKU_APP_NAME')  # Not used for Render, but keeping for compatibility

app = Flask(__name__)

# Store active bots
active_bots = {}

class BotHost:
    def __init__(self):
        self.updater = None
        self.bot_processes = {}
    
    def start_bot(self, update, context):
        """Start command handler"""
        chat_id = update.effective_message.id
        welcome_message = (
            "Welcome to the Bot Hosting Service!\n\n"
            "Send me a .py or .zip file containing your bot code.\n"
            "I'll host it for you and provide a link to access it.\n\n"
            "Commands:\n"
            "/start - Show this message\n"
            "/mybots - List your hosted bots\n"
            "/stopbot <bot_id> - Stop a hosted bot"
        )
        context.bot.send_message(chat_id=chat_id, text=welcome_message)
    
    def list_bots(self, update, context):
        """List all bots hosted by the user"""
        chat_id = update.effective_message.id
        user_bots = [bot_id for bot_id, bot_info in active_bots.items() if bot_info['owner'] == chat_id]
        
        if not user_bots:
            context.bot.send_message(chat_id=chat_id, text="You don't have any hosted bots.")
            return
        
        message = "Your hosted bots:\n"
        for bot_id in user_bots:
            bot_info = active_bots[bot_id]
            status = "Running" if bot_info['process'] and bot_info['process'].poll() is None else "Stopped"
            message += f"- {bot_id}: {status}\n"
        
        context.bot.send_message(chat_id=chat_id, text=message)
    
    def stop_bot(self, update, context):
        """Stop a hosted bot"""
        chat_id = update.effective_message.id
        try:
            bot_id = context.args[0]
        except IndexError:
            context.bot.send_message(chat_id=chat_id, text="Please provide a bot ID. Usage: /stopbot <bot_id>")
            return
        
        if bot_id not in active_bots:
            context.bot.send_message(chat_id=chat_id, text=f"Bot with ID {bot_id} not found.")
            return
        
        if active_bots[bot_id]['owner'] != chat_id:
            context.bot.send_message(chat_id=chat_id, text="You don't have permission to stop this bot.")
            return
        
        bot_info = active_bots[bot_id]
        if bot_info['process']:
            bot_info['process'].terminate()
            bot_info['process'].wait()
        
        context.bot.send_message(chat_id=chat_id, text=f"Bot {bot_id} has been stopped.")
        active_bots[bot_id]['process'] = None
    
    def handle_document(self, update, context):
        """Handle incoming documents (py/zip files)"""
        chat_id = update.effective_message.id
        document = update.message.document
        
        # Check file extension
        file_name = document.file_name
        if not (file_name.endswith('.py') or file_name.endswith('.zip')):
            context.bot.send_message(
                chat_id=chat_id, 
                text="Please send a .py or .zip file containing your bot code."
            )
            return
        
        # Download file
        file = context.bot.get_file(document.file_id)
        file_path = os.path.join(tempfile.gettempdir(), file_name)
        file.download(file_path)
        
        context.bot.send_message(
            chat_id=chat_id, 
            text=f"Received {file_name}. Processing..."
        )
        
        # Process the file
        try:
            bot_id = self.process_bot_file(chat_id, file_path, file_name)
            if bot_id:
                context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Your bot has been deployed successfully!\nBot ID: {bot_id}\nAccess it at: https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'your-app-name.onrender.com')}/bots/{bot_id}"
                )
            else:
                context.bot.send_message(
                    chat_id=chat_id,
                    text="Failed to deploy your bot. Please check the file and try again."
                )
        except Exception as e:
            logger.error(f"Error processing bot file: {str(e)}")
            context.bot.send_message(
                chat_id=chat_id,
                text=f"Error deploying your bot: {str(e)}"
            )
    
    def process_bot_file(self, owner_id, file_path, file_name):
        """Process the uploaded bot file and start hosting it"""
        bot_id = f"bot_{int(time.time())}"
        bot_dir = os.path.join("bots", bot_id)
        os.makedirs(bot_dir, exist_ok=True)
        
        try:
            if file_name.endswith('.py'):
                # Handle single Python file
                shutil.copy(file_path, os.path.join(bot_dir, "bot.py"))
            elif file_name.endswith('.zip'):
                # Handle ZIP file
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(bot_dir)
            
            # Look for main bot file
            bot_file = self.find_bot_file(bot_dir)
            if not bot_file:
                raise Exception("Could not find main bot file")
            
            # Install requirements if present
            requirements_file = os.path.join(bot_dir, "requirements.txt")
            if os.path.exists(requirements_file):
                subprocess.run(["pip", "install", "-r", requirements_file], check=True)
            
            # Start the bot in a separate process
            process = subprocess.Popen([
                "python", bot_file
            ], cwd=bot_dir)
            
            # Store bot information
            active_bots[bot_id] = {
                'owner': owner_id,
                'directory': bot_dir,
                'process': process,
                'file_name': file_name
            }
            
            return bot_id
        except Exception as e:
            logger.error(f"Error processing bot: {str(e)}")
            # Clean up on failure
            if os.path.exists(bot_dir):
                shutil.rmtree(bot_dir)
            if bot_id in active_bots:
                del active_bots[bot_id]
            raise e
    
    def find_bot_file(self, directory):
        """Find the main bot file in the directory"""
        # Common entry point names
        entry_points = ['bot.py', 'main.py', 'app.py', 'run.py']
        
        for entry_point in entry_points:
            full_path = os.path.join(directory, entry_point)
            if os.path.exists(full_path):
                return full_path
        
        # If no common entry point found, look for any .py file
        py_files = [f for f in os.listdir(directory) if f.endswith('.py')]
        if py_files:
            return os.path.join(directory, py_files[0])
        
        return None
    
    def setup_webhook(self):
        """Setup webhook for the Telegram bot"""
        if not TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN not set")
            return
        
        self.updater = Updater(TOKEN, use_context=True)
        
        # Register handlers
        dp = self.updater.dispatcher
        dp.add_handler(CommandHandler("start", self.start_bot))
        dp.add_handler(CommandHandler("mybots", self.list_bots))
        dp.add_handler(CommandHandler("stopbot", self.stop_bot))
        dp.add_handler(MessageHandler(Filters.document, self.handle_document))
        
        # Start the bot
        self.updater.start_polling()
        logger.info("Telegram bot started")
    
    def run_flask_app(self):
        """Run the Flask app for serving hosted bots"""
        @app.route('/')
        def index():
            return "Bot Hosting Service is running!"
        
        @app.route('/bots/<bot_id>')
        def serve_bot(bot_id):
            if bot_id in active_bots:
                bot_info = active_bots[bot_id]
                status = "Running" if bot_info['process'] and bot_info['process'].poll() is None else "Stopped"
                return f"Bot {bot_id} is {status}"
            else:
                return "Bot not found", 404
        
        app.run(host='0.0.0.0', port=PORT)

# Initialize bot host
bot_host = BotHost()

if __name__ == '__main__':
    # Create bots directory
    os.makedirs("bots", exist_ok=True)
    
    # Start the Telegram bot in a separate thread
    bot_thread = threading.Thread(target=bot_host.setup_webhook)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Run Flask app (this will block)
    bot_host.run_flask_app()