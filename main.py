import nextcord
import datetime
from nextcord.utils import format_dt
from nextcord.ext import commands
from nextcord import SlashOption
import os
from dotenv import load_dotenv
from collections import deque
import yt_dlp
import asyncio

load_dotenv()
TOKEN = os.getenv("TOKEN")
intents = nextcord.Intents.default()
bot = commands.Bot(intents=intents)
session_list = {}

FFMPEG_PATH = "ffmpeg/ffmpeg.exe"
FFMPEG_OPTIONS = {"options": "-vn -sn"}
YTDL_OPTIONS = {"format": "bestaudio",
                "outtmpl": "downloaded_musics/%(extractor)s-%(id)s-%(title)s.%(ext)s",
                "restrictfilenames": True,
                # "no-playlist": True,
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
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class Music:
    """stores music info"""
    def __init__(self, audio_source: nextcord.AudioSource, audio_info):
        self.audio_source = audio_source
        self.audio_info = audio_info
        self.title = audio_info.get("title", "Error parsing title")
        self.video_url = audio_info.get("webpage_url", "Error parsing url")
        self.duration = audio_info.get("duration", 0)


class Session:
    """stores bot voice client sessions"""
    def __init__(self, server_id, voice_client: nextcord.VoiceClient):
        self.server_id = server_id
        self.voice_client = voice_client
        self.music_queue = deque()

    async def add_queue(self, ctx, url):
        """adds music to queues"""
        try:
            music_info = await asyncio.to_thread(lambda: ytdl.extract_info(url, download=True))
            if "entries" in music_info and music_info["entries"]:  # if it's playlist, take first one
                music_info = music_info["entries"][0]
            if not music_info:
                await ctx.send("An error occurred getting music info.")
                return
        except Exception as e:
            await ctx.followup.send(f"Failed to extract audio: {e}")
            return

        audio_file = ytdl.prepare_filename(music_info)
        audio_source = await nextcord.FFmpegOpusAudio.from_probe(audio_file, **FFMPEG_OPTIONS, executable=FFMPEG_PATH)
        music = Music(audio_source, music_info)
        self.music_queue.append(music)
        if self.voice_client.is_playing() or self.voice_client.is_paused():
            await ctx.followup.send(f"{music.title} was added to queue.")
        if not self.voice_client.is_playing() and not self.voice_client.is_paused():
            await self.play_next(ctx)

    async def play_next(self, ctx):
        to_play = self.music_queue.popleft()
        start = datetime.datetime.now()
        end = start + datetime.timedelta(seconds=to_play.duration)
        await ctx.followup.send(f"Now playing: [{to_play.title}](<{to_play.video_url}>)\n"
                               f"Duration: {format_dt(start, style="R")} - {format_dt(end, style="R")}")
        self.voice_client.play(to_play.audio_source, after=lambda e=None: self.after_playing(ctx, e))

    async def after_playing(self, ctx, error):
        if error:
            await ctx.send("An error occurred playing music")
        if self.music_queue:  # queue is not empty
            await self.play_next(ctx)
        else:
            await ctx.followup.send("The queue is empty now")


def clear_cache():
    """removes all the downloaded files"""
    if not os.path.exists("downloaded_musics"):
        os.makedirs("downloaded_musics") # Ensure directory exists
        return
    if not session_list:
        for file in os.listdir("downloaded_musics"):
            os.remove(os.path.join("downloaded_musics", file))
    print("cleared cache")


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
        if session_list[server_id].voice_client.is_paused():
            session_list[server_id].voice_client.resume()
            await ctx.send(f"<@{ctx.user.id}> Resumed a music.")


@bot.slash_command()
async def leave(ctx: nextcord.Interaction):
    """leave voice channel and delete the server from session list"""
    if ctx.user.voice is None:
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
        clear_cache()
        await ctx.send(f"<@{ctx.user.id}> Disconnected from a voice channel.")


@bot.slash_command()
async def skip(ctx: nextcord.Interaction):
    """skip current music"""
    server_id = ctx.guild.id
    if server_id not in session_list:
        await ctx.send("I'm not playing anything.")
        return
    session = session_list[server_id]
    if ctx.user.voice is None or ctx.user.voice.channel != session.voice_client.channel:
        await ctx.send("You must be in the same voice channel!")
        return
    if session.voice_client.is_playing() or session.voice_client.is_paused():
        session.voice_client.stop()
        await ctx.send(f"Skipped by <@{ctx.user.id}>.")
    else:
        await ctx.send("Nothing is playing.")


@bot.slash_command()
async def play(ctx: nextcord.Interaction, query: str = SlashOption(
    name="query",
    description="Put a link of the song you want to play",
    required=True)):
    """receive query from a user, and then download the music and play"""

    await ctx.response.defer()
    server_id = ctx.guild.id
    if ctx.user.voice is None:
        await ctx.send("You are not connected to a voice channel!", ephemeral=True)
        return

    if server_id not in session_list:  # 음성채널에 있지 않음
        try:
            session = await ctx.user.voice.channel.connect()
            session_list[server_id] = Session(ctx.guild.id, session)
            await ctx.followup.send(f"Connected to <#{ctx.user.voice.channel.id}>")
        except Exception as e:
            await ctx.followup.send(f"Could not connect to the voice channel: {e}", ephemeral=True)
            return

    session = session_list[server_id]
    if session.voice_client.channel != ctx.user.voice.channel:
        if any(m for m in session.voice_client.channel.members if not m.bot and m.id != bot.user.id):
            await ctx.followup.send(f"I'm currently in <#{ctx.user.voice.channel.id}> with other users.", ephemeral=True)
            return
        try:
            await session.voice_client.move_to(ctx.user.voice.channel)
            await ctx.followup.send(f"Moved to <#{ctx.user.voice.channel.id}>")
        except Exception as e:
            await ctx.followup.send(f"Could not connect to the voice channel: {e}", ephemeral=True)
            return
    await session.add_queue(ctx, query)


if __name__ == "__main__":
    clear_cache()
    bot.run(TOKEN)
