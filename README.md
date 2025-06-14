
# Discord Music bot

A discord music bot with basic features like play, pause, resume, and so on.

## How to Use

**Python 3.12 or higher is required**

- Download the source code and install libraries in requirements.txt
```
pip install -r requirements.txt
```

- Sign up for discord and go to [Discord Developer Portal](https://discord.com/developers/applications), make your own application.

- Go to "Bot" on the left and copy the token, and make an .env file with the content TOKEN="Your Token" inside the folder main.py is in.

- Toggle intents for your bot in the Bot settings ![intents](https://i.imgur.com/VRr6vMd.png)

- In the OAuth2 menu, select "bot" and "applications.commands" for scopes, scroll down and give bot permissions in the following image, and invite the bot to the server with the generated url. ![permission](https://i.imgur.com/UQBEXrb.png)

- Run main.py and use

### Used Tools
- ffmpeg
- nextcord
- yt_dlp
