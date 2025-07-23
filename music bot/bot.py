import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

queue = []
current_voice_client = None
ffmpeg_opts = {
    'before_options':
    '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}


# Helper: Extract direct audio URL and title from YouTube URL
def get_audio_info(youtube_url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'skip_download': True,
        'extract_flat': False,
        'nocheckcertificate': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        # Return direct audio stream URL, title and webpage_url
        return info['url'], info['title'], info['webpage_url']


async def play_next(ctx):
    global current_voice_client
    if queue:
        song = queue.pop(0)
        audio_url, title, webpage_url = None, song['title'], song[
            'webpage_url']

        try:
            audio_url, _, _ = get_audio_info(webpage_url)
        except Exception as e:
            await ctx.send(f"❌ Error extracting audio URL for **{title}**: {e}"
                           )
            await play_next(ctx)
            return

        try:
            source = await discord.FFmpegOpusAudio.from_probe(
                audio_url, **ffmpeg_opts)
        except Exception as e:
            await ctx.send(f"❌ Error playing **{title}**: {e}")
            await play_next(ctx)
            return

        def after_playing(error):
            if error:
                print(f"Player error: {error}")
            fut = asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
            try:
                fut.result()
            except Exception as e:
                print(f"Error in after_playing: {e}")

        if not current_voice_client:
            current_voice_client = ctx.voice_client

        current_voice_client.play(source, after=after_playing)
        await ctx.send(f"🎶 Now playing: **{title}**")
    else:
        if current_voice_client and current_voice_client.is_connected():
            await current_voice_client.disconnect()
        current_voice_client = None
        await ctx.send("🛑 Queue ended. Disconnected.")


@bot.command()
async def join(ctx):
    if ctx.author.voice is None:
        await ctx.send("❌ You are not connected to a voice channel.")
        return
    channel = ctx.author.voice.channel
    vc = ctx.voice_client
    if vc is not None:
        await vc.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"✅ Connected to {channel.name}")


@bot.command()
async def play(ctx, *, url_or_search: str):
    if ctx.author.voice is None:
        await ctx.send("❌ You are not connected to a voice channel.")
        return
    channel = ctx.author.voice.channel
    vc = ctx.voice_client
    if vc is None:
        vc = await channel.connect()

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'skip_download': True,
        'default_search': 'ytsearch',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_or_search, download=False)

        if 'entries' in info:
            info = info['entries'][0]

        title = info.get('title', 'Unknown title')
        webpage_url = info.get('webpage_url', url_or_search)
    except Exception as e:
        await ctx.send(f"❌ Error extracting info: {e}")
        return

    queue.append({'title': title, 'webpage_url': webpage_url})
    await ctx.send(f"✅ Added to queue: **{title}**")

    if not vc.is_playing():
        await play_next(ctx)


@bot.command()
async def add(ctx, *, url_or_search: str):
    # Same as play but DOES NOT start playing automatically if not playing
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'skip_download': True,
        'default_search': 'ytsearch',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_or_search, download=False)

        if 'entries' in info:
            info = info['entries'][0]

        title = info.get('title', 'Unknown title')
        webpage_url = info.get('webpage_url', url_or_search)
    except Exception as e:
        await ctx.send(f"❌ Error extracting info: {e}")
        return

    queue.append({'title': title, 'webpage_url': webpage_url})
    await ctx.send(f"✅ Added to queue: **{title}**")


@bot.command()
async def pause(ctx):
    vc = ctx.voice_client
    if vc is None or not vc.is_connected():
        await ctx.send("❌ I'm not connected to a voice channel.")
        return
    if vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ Paused the music.")
    else:
        await ctx.send("❌ No music is playing right now.")


@bot.command()
async def resume(ctx):
    vc = ctx.voice_client
    if vc is None or not vc.is_connected():
        await ctx.send("❌ I'm not connected to a voice channel.")
        return
    if vc.is_paused():
        vc.resume()
        await ctx.send("▶️ Resumed the music.")
    else:
        await ctx.send("❌ Music is not paused.")


@bot.command()
async def next(ctx):
    vc = ctx.voice_client
    if vc is None or not vc.is_connected():
        await ctx.send("❌ Not connected to a voice channel.")
        return
    if vc.is_playing():
        vc.stop()
        await ctx.send("⏭️ Skipped current song.")
    else:
        await ctx.send("❌ No song is playing right now.")


@bot.command()
async def list(ctx):
    if not queue:
        await ctx.send("📭 The queue is empty.")
        return
    msg = "**Current Queue:**\n"
    for i, song in enumerate(queue, start=1):
        msg += f"{i}. {song['title']}\n"
    await ctx.send(msg)


@bot.command()
async def remove(ctx, *, title: str):
    to_remove = None
    for song in queue:
        if title.lower() in song['title'].lower():
            to_remove = song
            break
    if to_remove:
        queue.remove(to_remove)
        await ctx.send(f"🗑️ Removed **{to_remove['title']}** from queue.")
    else:
        await ctx.send(
            f"❌ Could not find a song with name containing '{title}'.")


@bot.command()
async def exit(ctx):
    global queue, current_voice_client
    vc = ctx.voice_client
    if vc and vc.is_connected():
        queue.clear()
        await vc.disconnect()
        current_voice_client = None
        await ctx.send("👋 Disconnected and cleared the queue.")
    else:
        await ctx.send("❌ I'm not connected to a voice channel.")


@bot.command()
async def search(ctx, *, query: str):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'bestaudio/best'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            search_results = ydl.extract_info(f"ytsearch5:{query}",
                                              download=False)['entries']
        except Exception as e:
            await ctx.send(f"❌ Search error: {e}")
            return

    if not search_results:
        await ctx.send("❌ No results found.")
        return

    embed = discord.Embed(
        title=f"Search results for '{query}':",
        description="Use ⬆️⬇️ to select a song and ✅ to play.",
        color=discord.Color.blue())
    for i, entry in enumerate(search_results, start=1):
        embed.add_field(name=f"{i}. {entry['title']}",
                        value=entry['webpage_url'],
                        inline=False)

    msg = await ctx.send(embed=embed)

    reactions = ['⬆️', '⬇️', '✅']
    for r in reactions:
        await msg.add_reaction(r)

    selected = 0

    def check(reaction, user):
        return user == ctx.author and str(
            reaction.emoji) in reactions and reaction.message.id == msg.id

    while True:
        try:
            reaction, user = await bot.wait_for('reaction_add',
                                                timeout=60.0,
                                                check=check)
        except asyncio.TimeoutError:
            await msg.edit(content="⌛ Selection timed out.", embed=None)
            await msg.clear_reactions()
            return

        if str(reaction.emoji) == '⬆️':
            selected = (selected - 1) % len(search_results)
        elif str(reaction.emoji) == '⬇️':
            selected = (selected + 1) % len(search_results)
        elif str(reaction.emoji) == '✅':
            song = search_results[selected]
            queue.append({
                'title': song['title'],
                'webpage_url': song['webpage_url']
            })
            await ctx.send(f"✅ Added to queue: **{song['title']}**")

            vc = ctx.voice_client
            if vc is None:
                if ctx.author.voice is None:
                    await ctx.send(
                        "❌ You are not connected to a voice channel.")
                    return
                vc = await ctx.author.voice.channel.connect()

            if not vc.is_playing():
                await play_next(ctx)

            await msg.clear_reactions()
            await msg.edit(content=f"✅ Selected **{song['title']}**",
                           embed=None)
            return

        embed = discord.Embed(
            title=f"Search results for '{query}':",
            description="Use ⬆️⬇️ to select a song and ✅ to play.",
            color=discord.Color.blue())
        for i, entry in enumerate(search_results, start=1):
            prefix = "▶️ " if (i - 1) == selected else ""
            embed.add_field(name=f"{prefix}{i}. {entry['title']}",
                            value=entry['webpage_url'],
                            inline=False)
        await msg.edit(embed=embed)

        try:
            await msg.remove_reaction(reaction, user)
        except:
            pass


@bot.command(name="commands")
async def commands_cmd(ctx):
    help_text = """
    **Available Commands:**
    !join - Join your voice channel
    !play <url or search term> - Play a song or add to queue and start playing
    !add <url or search term> - Add a song to the queue without playing immediately
    !pause - Pause the current song
    !resume - Resume the paused song
    !next - Skip the current song
    !list - Show the current queue
    !remove <song title> - Remove a song from the queue
    !search <query> - Search for a song and select to add
    !exit - Clear queue and disconnect the bot
    !commands - Show this help message
    """
    await ctx.send(help_text)


bot.run(TOKEN)

