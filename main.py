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
from math import ceil

load_dotenv()
TOKEN = os.getenv("TOKEN")
intents = nextcord.Intents.default()
bot = commands.Bot(intents=intents)
session_list = {}

FFMPEG_PATH = "ffmpeg/ffmpeg.exe"
FFMPEG_OPTIONS = {"options": "-vn -sn"}
YTDL_OPTIONS = {
    "format": "bestaudio[ext=opus]/bestaudio[ext=m4a]/bestaudio/best",
    "outtmpl": "downloaded_musics/%(extractor)s-%(id)s-%(title)s-%(epoch)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
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
    "age_limit": 100,
    "paths": {
        "temp": "temp_files",
    },
    "concurrent_fragment_downloads": 8,
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class Music:
    """stores music info"""
    def __init__(self, audio_info, filepath, requested):
        self.audio_info = audio_info
        self.title = audio_info.get("title", "Error parsing title")
        self.video_url = audio_info.get("webpage_url", "Error parsing url")
        self.duration = audio_info.get("duration", 0)
        self.thumbnail = audio_info.get("thumbnail", 0)
        self.filepath = filepath
        self.audio_source = None
        self.requested = requested


class QueueView(nextcord.ui.View):
    def __init__(self, music_queue: deque):
        super().__init__(timeout=60)
        self.queue_list = list(music_queue)
        self.songs_per_page = 10
        self.current_page = 1
        self.total_pages = ceil(len(self.queue_list) / self.songs_per_page)
        self.message = None
        self.update_button()

    def create_embed(self) -> nextcord.Embed:
        """Creates an embed for queue command"""
        start_index = (self.current_page - 1) * self.songs_per_page
        end_index = start_index + self.songs_per_page

        description = []
        for i, music in enumerate(self.queue_list[start_index:end_index], start=start_index + 1):
            description.append(f"{i}: [{music.title}](<{music.video_url}>) - Requested by <@{music.requested}>")

        embed = nextcord.Embed(
            title="Queue",
            description="\n".join(description),
            color = nextcord.Color.from_rgb(25, 246, 157)
        )
        footer_page_num = self.current_page
        footer_total_pages = self.total_pages
        embed.set_footer(text=f"Page {footer_page_num}/{footer_total_pages}")
        return embed

    def update_button(self):
        """Disables buttons based on current page"""
        self.children[0].disabled = self.current_page == 1
        self.children[1].disabled = self.current_page == self.total_pages

    @nextcord.ui.button(label="⬅️", style=nextcord.ButtonStyle.blurple)
    async def previous_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if self.current_page > 1:
            self.current_page -= 1
        self.update_button()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @nextcord.ui.button(label="➡️", style=nextcord.ButtonStyle.blurple)
    async def next_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if self.current_page < self.total_pages:
            self.current_page += 1
        self.update_button()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except (nextcord.NotFound, nextcord.Forbidden):
                pass
            finally:
                self.message = None

class Session:
    """stores bot voice client sessions"""
    def __init__(self, server_id, voice_client: nextcord.VoiceClient, text_channel):
        self.server_id = server_id
        self.voice_client = voice_client
        self.music_queue = deque()
        self.disconnect_timer = None
        self.text_channel = text_channel
        self.now_playing_msg = None
        self.downloading = False

    def cancel_disconnect_timer(self):
        if self.disconnect_timer and not self.disconnect_timer.done():
            self.disconnect_timer.cancel()

    async def _start_disconnect_timer(self):
        self.cancel_disconnect_timer()
        self.disconnect_timer = bot.loop.create_task(self._auto_leave())

    async def _auto_leave(self):
        """leave after 5 mins of not playing"""
        await asyncio.sleep(300)
        if self.voice_client.is_connected() and not (self.voice_client.is_playing() or self.voice_client.is_paused()):
            await self.voice_client.disconnect()
            await self.text_channel.send("Left after 5 mins of idling.", delete_after=30)


    async def add_queue(self, url, user, ctx):
        """adds music to queues"""
        while self.downloading: # to prevent problems when play command is called too fast
            await asyncio.sleep(0.5)

        try:
            self.downloading = True
            self.cancel_disconnect_timer()
            music_info = await asyncio.to_thread(lambda: ytdl.extract_info(url, download=True))
            if not music_info:
                await ctx.followup.send("An error occurred getting music info.", delete_after=10)
                return
        except Exception as e:
            await ctx.followup.send(f"Failed to extract audio: {e}", delete_after=10)
            return
        finally:
            self.downloading = False

        audio_file = ytdl.prepare_filename(music_info)
        music = Music(music_info, audio_file, user)
        self.music_queue.append(music)

        if self.voice_client.is_playing() or self.voice_client.is_paused():
            await ctx.followup.send(f"{music.title} was added to queue.", delete_after=15)

        if not self.voice_client.is_playing() and not self.voice_client.is_paused():
            await self.play_next(ctx)

    async def play_next(self, ctx=None):
        to_play = self.music_queue.popleft()
        try:
            to_play.audio_source = await nextcord.FFmpegOpusAudio.from_probe(to_play.filepath, **FFMPEG_OPTIONS, executable=FFMPEG_PATH)
        except Exception as e:
            await self.after_playing(to_play.filepath, e)
            return
        start = datetime.datetime.now()
        end = start + datetime.timedelta(seconds=to_play.duration)
        now_playing_embed = nextcord.Embed(
            title="Now playing:",
            description=f"[{to_play.title}](<{to_play.video_url}>)\n"
                        f"-# Requested by <@{to_play.requested}>",
            color=nextcord.Color.from_rgb(25, 246, 157))
        now_playing_embed.add_field(
            name=f"**{format_dt(start, style="R")} ---------- {format_dt(end, style="R")}**",
            value=f"**(0:00) ---------- ({str(datetime.timedelta(0, to_play.duration))})**")
        now_playing_embed.set_image(url=to_play.thumbnail)

        if ctx:
            self.now_playing_msg = await ctx.followup.send(embed=now_playing_embed)
        else:
            self.now_playing_msg = await self.text_channel.send(embed=now_playing_embed)

        self.voice_client.play(to_play.audio_source, after=lambda e=None: bot.loop.create_task(self.after_playing(to_play, e)))

    async def after_playing(self, played, error=None):
        if self.now_playing_msg:
            try:
                await self.now_playing_msg.delete()
            except (nextcord.NotFound, nextcord.Forbidden):
                pass # ignore when can't delete message
            finally:
                self.now_playing_msg = None

        if error:
            await self.text_channel.send("An error occurred playing music", delete_after=10)

        await asyncio.sleep(0.5)

        if os.path.exists(played.filepath):
            try:
                os.remove(played.filepath)
            except OSError as e:
                print(f"Error removing played file: {e}")
        if not self.voice_client.is_connected():
            return
        if self.music_queue:  # queue is not empty
            await self.play_next()
        else:
            await self.text_channel.send("The queue is empty now", delete_after=10)
            await self._start_disconnect_timer()


def clear_cache():
    """removes all the downloaded files on execute"""
    for file in os.listdir("downloaded_musics"):
        os.remove(os.path.join("downloaded_musics", file))
    for file in os.listdir("temp_files\\downloaded_musics"):
        os.remove(os.path.join("temp_files\\downloaded_musics", file))
    print("cleared cache")


@bot.event
async def on_ready():
    """just to check if we connected to a bot"""
    print(f"We have logged in as {bot.user}")


@bot.event
async def on_voice_state_update(member, before, after):
    """to remove downloaded files on leave"""
    if member.id == bot.user.id and before.channel is not None and after.channel is None:
        server_id = member.guild.id
        session = session_list[server_id]
        session.cancel_disconnect_timer()
        session.voice_client.cleanup()
        for music in session.music_queue:
            filepath = music.filepath
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError as e:
                    print(f"Error removing remaining file: {e}")
        del session_list[server_id]


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
            await ctx.send(f"<@{ctx.user.id}> Paused a music.", delete_after=10)


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
            await ctx.send(f"<@{ctx.user.id}> Resumed a music.", delete_after=10)


@bot.slash_command()
async def leave(ctx: nextcord.Interaction):
    """leave voice channel"""
    if ctx.user.voice is None:
        await ctx.send("You are not connected to a voice channel!", ephemeral=True)
        return
    server_id = ctx.guild.id
    if server_id not in session_list:
        await ctx.send("I am not connected to any voice channel.", ephemeral=True)
        return
    else:
        await session_list[server_id].voice_client.disconnect()
        await ctx.send(f"<@{ctx.user.id}> Disconnected from a voice channel.", delete_after=10)


@bot.slash_command()
async def skip(ctx: nextcord.Interaction):
    """skip current music"""
    server_id = ctx.guild.id
    if server_id not in session_list:
        await ctx.send("I am not connected to any voice channel.", ephemeral=True)
        return
    session = session_list[server_id]
    if ctx.user.voice is None or ctx.user.voice.channel != session.voice_client.channel:
        await ctx.send("You must be in the same voice channel!", ephemeral=True)
        return
    if session.voice_client.is_playing() or session.voice_client.is_paused():
        session.voice_client.stop()
        await ctx.send(f"Skipped by <@{ctx.user.id}>.", delete_after=10)
    else:
        await ctx.send("Nothing is playing.", ephemeral=True)


@bot.slash_command()
async def queue(ctx: nextcord.Interaction):
    """shows what musics are in queue"""
    server_id = ctx.guild.id
    if server_id not in session_list:
        await ctx.send("I am not connected to any voice channel.", ephemeral=True)
        return

    session = session_list[server_id]
    if ctx.user.voice is None or ctx.user.voice.channel != session.voice_client.channel:
        await ctx.send("You must be in the same voice channel!", ephemeral=True)
        return

    if session.music_queue:
        view = QueueView(session.music_queue)
        initial_embed = view.create_embed()
        message = await ctx.send(embed=initial_embed, view=view)
        view.message = message
    else:
        await ctx.send("The queue is empty", ephemeral=True)


@bot.slash_command()
async def play(ctx: nextcord.Interaction, url: str = SlashOption(
    name="url",
    description="Put a link of the song you want to play",
    required=True)):
    """receive url from a user and play"""

    if ctx.user.voice is None:
        await ctx.send("You are not connected to a voice channel!", ephemeral=True)
        return

    await ctx.response.defer()
    server_id = ctx.guild.id

    if server_id not in session_list:
        try:
            session = await ctx.user.voice.channel.connect()
            session_list[server_id] = Session(ctx.guild.id, session, ctx.channel)
            await ctx.followup.send(f"Connected to <#{ctx.user.voice.channel.id}>")
        except Exception as e:
            await ctx.followup.send(f"Could not connect to the voice channel: {e}", delete_after=10)
            return

    session = session_list[server_id]
    if session.voice_client.channel != ctx.user.voice.channel:
        if any(m for m in session.voice_client.channel.members if not m.bot and m.id != bot.user.id):
            await ctx.followup.send(f"I'm currently in <#{ctx.user.voice.channel.id}> with other users.", delete_after=10)
            return
        try:
            await session.voice_client.move_to(ctx.user.voice.channel)
            await ctx.followup.send(f"Moved to <#{ctx.user.voice.channel.id}>", delete_after=10)
        except Exception as e:
            await ctx.followup.send(f"Could not connect to the voice channel: {e}", delete_after=10)
            return
    await session.add_queue(url, ctx.user.id, ctx)


if __name__ == "__main__":
    if not os.path.exists("downloaded_musics"):
        os.makedirs("downloaded_musics")
    if not os.path.exists("temp_files\\downloaded_musics"):
        os.makedirs("temp_files\\downloaded_musics")
    clear_cache()
    bot.run(TOKEN)
