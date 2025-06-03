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
intents.message_content = True
intents.members = True
bot = commands.Bot(intents=intents)
session_list = {}

FFMPEG_PATH = "ffmpeg/ffmpeg.exe"
FFMPEG_OPTIONS = {"options": "-vn -sn"}
YTDL_OPTIONS = {"format": "bestaudio",
             "outtmpl": "downloaded_musics/%(extractor)s-%(id)s-%(title)s.%(ext)s",
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
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class Music:
    """stores music info"""
    def __init__(self, audio_source: nextcord.AudioSource, audio_info):
        self.audio_source = audio_source
        self.audio_info = audio_info
        self.title = audio_info.get("title", "Error parsing title")
        # self.stream_url = audio_info.get("url", "Error parsing url")
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
        song_info = await asyncio.to_thread(lambda: ytdl.extract_info(url, download=True))
        if not song_info:
            await ctx.send("An error occurred getting music info.")
            return

        audio_file = ytdl.prepare_filename(song_info)
        music = Music(await nextcord.FFmpegOpusAudio.from_probe(audio_file, **FFMPEG_OPTIONS, executable=FFMPEG_PATH), song_info)
        self.music_queue.append(music)
        if self.voice_client.is_playing():
            await ctx.send(f"{music.title} was added to queue.")
        await self.fortest(ctx)

    async def fortest(self, ctx):
        to_play = self.music_queue.popleft()
        self.voice_client.play(to_play.audio_source)
        start = datetime.datetime.now()
        end = start + datetime.timedelta(seconds=to_play.duration)
        await ctx.send(f"Now playing: [{to_play.title}](<{to_play.video_url}>)\n"
                       f"Duration: {format_dt(start, style="R")} - {format_dt(end, style="R")}")


def clear_cache():
    """removes all the downloaded files"""
    if not session_list:
        for file in os.listdir("downloaded_musics"):
            os.remove(os.path.join("downloaded_musics", file))


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
            await ctx.send(f"Connected to <#{ctx.user.voice.channel.id}>")
            session_list[server_id] = Session(ctx.guild.id, session)
            session = session_list[server_id]
    else:
        session = session_list[server_id]
        if session.voice_client.channel != ctx.user.voice.channel:
            await session.voice_client.move_to(ctx.user.voice.channel)
    await session.add_queue(ctx, query)


if __name__ == "__main__":
    clear_cache()
    bot.run(TOKEN)
