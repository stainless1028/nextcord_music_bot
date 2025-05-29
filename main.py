import nextcord
from nextcord.ext import commands
from nextcord import SlashOption
import os
from dotenv import load_dotenv
from collections import deque
import yt_dlp

load_dotenv()
TOKEN = os.getenv("TOKEN")
intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(intents=intents)
session_list = {}

ffmpeg = "ffmpeg/ffmpeg.exe"
ffmpeg_options = {"options": "-vn -sn"}
ytdl_opts = {"format": "bestaudio",
             "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
             "restrictfilenames": True,
             "no-playlist": True,
             "nocheckcertificate": True,
             "ignoreerrors": False,
             "logtostderr": False,
             "geo-bypass": True,
             "quiet": True,
             "no_warnings": True,
             "default_search": "auto",
             "source_address": "0.0.0.0",
             "no_color": True,
             "overwrites": True,
             "age_limit": 100}
ytdl = yt_dlp.YoutubeDL(ytdl_opts)


class Session:
    def __init__(self, server, voice_client):
        self.server_id = server
        self.voice_client: nextcord.VoiceClient = voice_client
        self.music_queue = deque()


@bot.event
async def on_ready():
    """just to check if we connected to a bot"""
    print(f"We have logged in as {bot.user}")


@bot.slash_command()
async def pause(ctx: nextcord.Interaction):
    """pause current playing music"""
    server_id = ctx.guild_id
    if server_id not in session_list:
        await ctx.send("I am not connected to any voice channel.", ephemeral=True)
        return
    else:
        if session_list[server_id].voice_client.is_playing():
            session_list[server_id].voice_client.pause()
            await ctx.send(f"<@{ctx.user.id}> Paused a music.")


@bot.slash_command()
async def resume(ctx: nextcord.Interaction):
    """start playing paused music"""
    server_id = ctx.guild_id
    if server_id not in session_list:
        await ctx.send("I am not connected to any voice channel.", ephemeral=True)
        return
    else:
        if session_list[server_id].voice_client.is_playing():
            session_list[server_id].voice_client.resume()
            await ctx.send(f"<@{ctx.user.id}> Resumed a music.")


@bot.slash_command()
async def leave(ctx: nextcord.Interaction):
    """leave voice channel and delete the server from session list"""
    if ctx.user.voice.channel is None:
        await ctx.send("You are not connected to a voice channel!", ephemeral=True)
        return
    server_id = ctx.guild.id
    if server_id not in session_list:
        await ctx.send("I am not connected to any voice channel.", ephemeral=True)
        return
    else:
        session_list[server_id].voice_client.cleanup()
        await session_list[server_id].voice_client.disconnect()
        del session_list[server_id]
        await ctx.send(f"<@{ctx.user.id}> Disconnected from a voice channel.")


@bot.slash_command()
async def play(ctx: nextcord.Interaction, query: str = SlashOption(
    name="query",
    description="Put a link of the song you want to play",
    required=True)):
    """receive query from a user, and then download the music and play"""
    server_id = ctx.guild.id
    if server_id not in session_list:  # 음성채널에 있지 않음
        if ctx.user.voice is None:
            await ctx.send("You are not connected to a voice channel!")
            return
        else:
            session = await ctx.user.voice.channel.connect()
            session_list[server_id] = Session(ctx.guild.id, session)
            session = session_list[server_id]
    else:
        session = session_list[server_id]
        if session.voice_client.channel != ctx.user.voice.channel:
            await session.voice_client.move_to(ctx.user.voice.channel)
    await ctx.send("this is for a test response", ephemeral=True)
    """다운하고 실행하는 기능 만들기, Session 클래스 내에서"""


if __name__ == "__main__":
    bot.run(TOKEN)
