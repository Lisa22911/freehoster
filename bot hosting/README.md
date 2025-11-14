# Telegram Bot Hosting Service

This service allows you to host your Telegram bots by simply sending your bot's Python code (.py) or a zip file containing your bot project.

## How to Use

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather) and get your bot token
2. Deploy this service to Render.com (instructions below)
3. Set your bot token as an environment variable on Render
4. Send your bot's .py file or .zip archive to the hosting bot
5. Get a link to access your hosted bot

## Features

- Upload .py files for simple bots
- Upload .zip files for complex bot projects
- Automatic requirements installation
- List and manage your hosted bots
- Stop bots when needed

## Deployment to Render.com

1. Fork this repository
2. Go to [Render Dashboard](https://dashboard.render.com/)
3. Click "New+" and select "Web Service"
4. Connect your GitHub/GitLab account
5. Select your forked repository
6. Set the following:
   - Name: Choose a name for your service
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot_host.py`
7. Add environment variables:
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from @BotFather
8. Click "Create Web Service"

## Commands

- `/start` - Show welcome message and instructions
- `/mybots` - List your hosted bots
- `/stopbot <bot_id>` - Stop a hosted bot

## How It Works

1. When you send a .py or .zip file to the bot, it:
   - Downloads the file
   - Extracts it to a dedicated directory
   - Installs any requirements if a requirements.txt is present
   - Runs the bot in a separate process
   - Provides you with a URL to access your bot

2. Your bot runs in isolation with its own directory and process

## Limitations

- Each hosted bot runs in the same container as the host service
- Resource usage is shared among all bots
- For production bots, consider dedicated hosting

## Security Notes

- Uploaded bots run in isolated directories
- Validate and sanitize any user inputs in your bots
- Be cautious with the permissions you grant to uploaded bots